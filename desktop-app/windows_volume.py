"""Windows Core Audio master volume (no third-party Python dependencies).

The OmniPad firmware can emit relative media-volume keys but cannot query the
host's current volume. Use this only from the desktop editor when the user
selects absolute Windows volume mode; no background process is installed.
"""
import ctypes
import sys
import uuid

_CLSID_ENUMERATOR = "BCDE0395-E52F-467C-8E3D-C4579291692E"
_IID_ENUMERATOR = "A95664D2-9614-4F35-A746-DE8DB63617E6"
_IID_ENDPOINT = "5CDF2C82-841E-4546-9722-0CF74078229A"
_CLSCTX_ALL = 23
_RPC_E_CHANGED_MODE = -2147417850


class WindowsVolumeError(RuntimeError):
    pass


def _guid(value):
    class GUID(ctypes.Structure):
        _fields_ = [("data1", ctypes.c_uint32),
                    ("data2", ctypes.c_uint16),
                    ("data3", ctypes.c_uint16),
                    ("data4", ctypes.c_ubyte * 8)]
    return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)


def _checked(hr, label):
    if hr < 0:
        raise WindowsVolumeError(f"{label}: HRESULT 0x{hr & 0xffffffff:08X}")


def _method(pointer, index, result, *argument_types):
    method_address = ctypes.cast(
        pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ).contents[index]
    return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *argument_types)(method_address)


def _release(pointer):
    if pointer and pointer.value:
        _method(pointer, 2, ctypes.c_ulong)(pointer)


def get_master_volume_percent():
    return round(_volume_call(None) * 100)


def set_master_volume_percent(percent):
    if not isinstance(percent, (int, float)) or not 0 <= percent <= 100:
        raise ValueError("Lautstärke muss zwischen 0 und 100 % liegen.")
    _volume_call(float(percent) / 100)


def _volume_call(value):
    if sys.platform != "win32":
        raise WindowsVolumeError("Windows-Lautstärke ist nur unter Windows verfügbar.")
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.c_long

    init_result = ole32.CoInitializeEx(None, 2)
    if init_result < 0 and init_result != _RPC_E_CHANGED_MODE:
        _checked(init_result, "CoInitializeEx")
    should_uninit = init_result in (0, 1)
    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    endpoint = ctypes.c_void_p()
    try:
        clsid = _guid(_CLSID_ENUMERATOR)
        iid_enum = _guid(_IID_ENUMERATOR)
        _checked(ole32.CoCreateInstance(
            ctypes.byref(clsid), None, _CLSCTX_ALL,
            ctypes.byref(iid_enum), ctypes.byref(enumerator)
        ), "MMDeviceEnumerator")
        # eRender=0, eMultimedia=1
        _checked(_method(enumerator, 4, ctypes.c_long, ctypes.c_int, ctypes.c_int,
                         ctypes.POINTER(ctypes.c_void_p))(
            enumerator, 0, 1, ctypes.byref(device)), "GetDefaultAudioEndpoint")
        iid_volume = _guid(_IID_ENDPOINT)
        _checked(_method(device, 3, ctypes.c_long, ctypes.c_void_p,
                         ctypes.c_ulong, ctypes.c_void_p,
                         ctypes.POINTER(ctypes.c_void_p))(
            device, ctypes.byref(iid_volume), _CLSCTX_ALL, None,
            ctypes.byref(endpoint)), "Activate(IAudioEndpointVolume)")
        if value is None:
            result = ctypes.c_float()
            _checked(_method(endpoint, 9, ctypes.c_long,
                             ctypes.POINTER(ctypes.c_float))(
                endpoint, ctypes.byref(result)), "GetMasterVolumeLevelScalar")
            return result.value
        _checked(_method(endpoint, 7, ctypes.c_long, ctypes.c_float,
                         ctypes.c_void_p)(
            endpoint, ctypes.c_float(value), None),
            "SetMasterVolumeLevelScalar")
    finally:
        _release(endpoint)
        _release(device)
        _release(enumerator)
        if should_uninit:
            ole32.CoUninitialize()
