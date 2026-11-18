"""USB transport and the VIA commands supported by the OMNIscreen 10Pad."""

from dataclasses import dataclass
from datetime import datetime, timezone
from struct import iter_unpack, pack

from profile import PROFILE_SIZE

import hid


PRODUCT = "OMNIscreen 10Pad"
USB_IDS = ((0x4F4D, 0x7789), (0xFEED, 0x7789))
ROWS, COLS = 3, 4
FIXED_KEYS = {(1, 0): "Shift", (2, 2): "Strg", (2, 3): "Alt"}


class ViaError(RuntimeError):
    pass


class UnsupportedCommand(ViaError):
    pass


@dataclass(frozen=True)
class Detection:
    active_layer: int
    enabled: bool
    mask: int
    last_key: int
    presses: int
    clockwise: int
    counterclockwise: int
    encoder_pushes: int
    slider_raw: int | None = None
    slider_percent: int | None = None
    gesture: int = 0
    sensor_status: int = 0
    sensor_xyz: tuple = (0, 0, 0)
    display_mode: bool = True
    expander: bool = False


class OmniPad:
    def __init__(self, device, usb_id):
        self._device = device
        self.usb_id = usb_id
        self.protocol = self._integer((0x01,), 1, 2)
        self.firmware = self._integer((0x02, 0x04), 2, 4)
        self._device.set_nonblocking(0)
        self.layer_count = self._integer((0x11,), 1, 1)
        if self.protocol < 12 or not 1 <= self.layer_count <= 32:
            raise ViaError("Diese VIA-Firmware wird vom Editor nicht unterstützt.")

    @classmethod
    def connect(cls):
        matches = [
            (entry["path"], (vid, pid))
            for vid, pid in USB_IDS
            for entry in hid.enumerate(vid, pid)
            if (entry["usage_page"], entry["usage"]) == (0xFF60, 0x61)
            and entry["product_string"] == PRODUCT
        ]
        if not matches:
            raise ViaError("Kein OmniPad am USB-Anschluss gefunden.")
        if len(matches) > 1:
            raise ViaError("Mehrere OmniPads gefunden. Bitte nur ein Pad anschließen.")
        path, usb_id = matches[0]
        device = hid.device()
        try:
            device.open_path(path)
            return cls(device, usb_id)
        except Exception:
            device.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._device.close()

    def _exchange(self, request, echo=None, timeout=900):
        request = bytes(request)
        if len(request) > 32:
            raise ValueError("USB-Befehl ist zu lang.")
        packet = b"\x00" + request.ljust(32, b"\x00")
        if self._device.write(packet) != len(packet):
            raise ViaError("USB-Bericht konnte nicht vollständig gesendet werden.")
        reply = bytes(self._device.read(32, timeout))
        if reply[:1] == b"\xff":
            raise UnsupportedCommand("Die Firmware unterstützt diesen VIA-Befehl nicht.")
        prefix = request if echo is None else request[:echo]
        if len(reply) != 32 or not reply.startswith(prefix):
            raise ViaError("Ungültige Antwort vom OmniPad. Verbindung neu herstellen.")
        return reply

    def _integer(self, request, offset, size):
        return int.from_bytes(self._exchange(request)[offset:offset + size], "big")

    def _read_buffer(self, command, size):
        data = bytearray()
        for offset in range(0, size, 28):
            count = min(28, size - offset)
            reply = self._exchange((command, offset >> 8, offset & 0xFF, count))
            data.extend(reply[4:4 + count])
        return bytes(data)

    def keymap(self):
        raw = self._read_buffer(0x12, self.layer_count * ROWS * COLS * 2)
        rows = [list(row) for row in iter_unpack(f">{COLS}H", raw)]
        return [
            rows[start:start + ROWS] for start in range(0, len(rows), ROWS)
        ]

    def encoder_map(self):
        return [
            [self._integer((0x14, layer, 0, direction), 4, 2) for direction in range(2)]
            for layer in range(self.layer_count)
        ]

    def _binding(self, layer, target):
        if not 0 <= layer < self.layer_count:
            raise ValueError("Ungültiger Layer.")
        kind, *position = target
        if kind == "key" and len(position) == 2:
            row, col = position
            if 0 <= row < ROWS and 0 <= col < COLS and (row, col) not in FIXED_KEYS:
                return 0x04, 0x05, (layer, row, col)
        if kind == "encoder" and len(position) == 1 and position[0] in (0, 1):
            return 0x14, 0x15, (layer, 0, position[0])
        raise ValueError("Diese Belegung kann nicht geändert werden.")

    def set_binding(self, layer, target, previous, value):
        if not 0 <= value <= 0xFFFF:
            raise ValueError("Keycode muss zwischen 0x0000 und 0xFFFF liegen.")
        get, put, args = self._binding(layer, target)
        if self._integer((get, *args), 4, 2) != previous:
            raise ViaError("Die Belegung wurde inzwischen geändert. Bitte neu verbinden.")
        if value == previous:
            return
        self._exchange((put, *args, value >> 8, value & 0xFF))
        if self._integer((get, *args), 4, 2) != value:
            raise ViaError("Der gespeicherte Keycode stimmt nicht mit der Änderung überein.")

    def snapshot(self):
        macro_size = self._integer((0x0D,), 1, 2)
        lighting = {}
        for channel, lengths in ((0, (1, 2, 2, 1, 1, 1, 1, 2, 2, 1, 1)), (2, (1, 1, 1, 2))):
            for value, size in enumerate(lengths, start=1):
                try:
                    reply = self._exchange((0x08, channel, value))
                    lighting[f"{channel}:{value}"] = list(reply[3:3 + size])
                except UnsupportedCommand:
                    continue
        return {
            "schema": "omnipad-via-backup",
            "version": 1,
            "created": datetime.now(timezone.utc).isoformat(),
            "product": PRODUCT,
            "vendor_id": f"0x{self.usb_id[0]:04X}",
            "product_id": f"0x{self.usb_id[1]:04X}",
            "via_protocol": self.protocol,
            "firmware": self.firmware,
            "layout_options": self._integer((0x02, 0x02), 2, 4),
            "layers": self.keymap(),
            "encoder_ccw_cw": self.encoder_map(),
            "macro_slots": self._integer((0x0C,), 1, 1),
            "macro_buffer_hex": self._read_buffer(0x0E, macro_size).hex(),
            "lighting": lighting,
        }

    def capabilities(self):
        try:
            reply = self._exchange((0x08, 0, 0x71))
        except UnsupportedCommand:
            return None
        if reply[3:7] != b"OMP2" or int.from_bytes(reply[9:11], "little") != PROFILE_SIZE:
            raise UnsupportedCommand("Unbekannte OmniPad-Profilversion.")
        return {"enabled": bool(reply[7]), "max_layers": reply[8],
                "generation": int.from_bytes(reply[11:15], "little"), "expander": bool(reply[15])}

    def read_profile(self):
        data = bytearray()
        for offset in range(0, PROFILE_SIZE, 25):
            count = min(25, PROFILE_SIZE - offset)
            reply = self._exchange((0x08, 0, 0x72, offset & 255, offset >> 8, count))
            data.extend(reply[6:6 + count])
        return bytes(data)

    def write_profile(self, payload, generation, progress=None):
        if len(payload) != PROFILE_SIZE:
            raise ValueError("Ungültige Profilgröße.")
        checksum = 2166136261
        for byte in payload:
            checksum = ((checksum ^ byte) * 16777619) & 0xFFFFFFFF
        self._exchange(bytes((0x07, 0, 0x73)) + pack("<2I", checksum, generation))
        for offset in range(0, len(payload), 25):
            chunk = payload[offset:offset + 25]
            self._exchange(bytes((0x07, 0, 0x74, offset & 255, offset >> 8, len(chunk))) + chunk)
            if progress:
                progress(offset + len(chunk), len(payload))
        # Committing persistent storage can take longer than a regular HID read.
        self._exchange((0x07, 0, 0x75), timeout=12000)
        verified = self.read_profile()
        if verified != payload:
            raise ViaError("Das zurückgelesene Profil weicht von der Übertragung ab.")
        return self.capabilities()

    def diagnose(self, enabled, *, tester=False):
        self._exchange((0x07, 0, 0x76, (2 if tester else 1) if enabled else 0))

    def tester_report(self):
        reply = self._exchange((0x08, 0, 0x77))
        if reply[5] > 6:
            raise ViaError("Ungültiger Tester-Bericht vom OmniPad.")
        entries = tuple(iter_unpack("<BBH", reply[6:6 + 4 * reply[5]]))
        return bool(reply[3]), bool(reply[4]), entries

    def test_output(self, output):
        self._exchange((0x07, 0, 0x78, output))

    def detection(self):
        reply = self._exchange((0x08, 0, 0x70))
        if reply[3:7] != b"OMNI" or reply[7] not in (1, 2):
            raise UnsupportedCommand("Der Detect-Inspektor benötigt die passende Firmware.")
        return Detection(
            active_layer=reply[8],
            enabled=bool(reply[9]),
            mask=int.from_bytes(reply[10:12], "little"),
            last_key=reply[12],
            presses=int.from_bytes(reply[13:15], "little"),
            clockwise=reply[15],
            counterclockwise=reply[16],
            encoder_pushes=reply[17],
            slider_raw=int.from_bytes(reply[18:20], "little") if reply[7] >= 2 and reply[21] else None,
            slider_percent=reply[20] if reply[7] >= 2 and reply[21] else None,
            gesture=reply[22] if reply[7] >= 2 else 0,
            sensor_status=reply[23] if reply[7] >= 2 else 0,
            sensor_xyz=tuple(int.from_bytes(reply[index:index + 2], "little", signed=True)
                             for index in (24, 26, 28)) if reply[7] >= 2 else (0, 0, 0),
            display_mode=bool(reply[30]) if reply[7] >= 2 else True,
            expander=bool(reply[31]) if reply[7] >= 2 else False,
        )
