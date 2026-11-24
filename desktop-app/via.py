"""USB transport and the VIA commands supported by the OMNIscreen 10Pad."""

from dataclasses import dataclass
import os
from pathlib import Path
from datetime import datetime, timezone
from struct import iter_unpack, pack, unpack

from profile import PROFILE_SIZE, ZONE_STRUCT, encode_lighting, colorhex, MAX_LAYERS, zone_config
from led_zones import MATRIX_COUNT, MATRIX_ZONES, FRAME_COUNT, validate_zone_map, default_zone_map

import hid


PRODUCT = "OMNIscreen 10Pad"
USB_IDS = ((0x4F4D, 0x7789), (0xFEED, 0x7789))
ROWS, COLS = 3, 4
FIXED_KEYS = {(1, 0): "Shift", (2, 2): "Strg", (2, 3): "Alt"}
# The RP2040 can spend over a second redrawing the TFT after a diagnostic command.
DIAGNOSTIC_TIMEOUT_MS = 4500


class ViaError(RuntimeError):
    pass


class UnsupportedCommand(ViaError):
    pass


def _acquire_usb_lease():
    """Prevent parallel OmniPad clients from mixing HID replies."""
    if os.name != "nt":
        return None
    import msvcrt

    folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OmniPad"
    folder.mkdir(parents=True, exist_ok=True)
    handle = (folder / "via-usb.lock").open("a+b")
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as error:
        handle.close()
        raise ViaError(
            "Ein anderer OmniPad-Editor verwendet bereits die USB-Schnittstelle. "
            "Bitte das andere Editorfenster schließen; der Entwurf bleibt erhalten."
        ) from error
    return handle


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
    def __init__(self, device, usb_id, lease=None):
        self._device = device
        self._lease = lease
        self.usb_id = usb_id
        self._device.set_nonblocking(0)
        self.protocol = self._integer((0x01,), 1, 2)
        try:
            self.firmware = self._integer((0x02, 0x04), 2, 4)
        except UnsupportedCommand:
            self.firmware = 0
        self.layer_count = self._integer((0x11,), 1, 1)
        if self.protocol < 12 or not 1 <= self.layer_count <= 32:
            raise ViaError("Diese VIA-Firmware wird vom Editor nicht unterstützt.")

    @classmethod
    def connect(cls):
        lease = _acquire_usb_lease()
        device = None
        try:
            interfaces = [(entry, (vid, pid)) for vid, pid in USB_IDS for entry in hid.enumerate(vid, pid)]
            matches = {entry["path"]: usb_id for entry, usb_id in interfaces
                       if (entry.get("usage_page"), entry.get("usage")) == (0xFF60, 0x61)}
            if not matches:
                if interfaces:
                    raise ViaError("OmniPad über USB sichtbar · Die VIA-Schnittstelle fehlt.")
                raise ViaError("Kein OmniPad am USB-Anschluss gefunden.")
            if len(matches) > 1:
                raise ViaError("Mehrere OmniPads gefunden. Bitte nur ein Pad anschließen.")
            path, usb_id = next(iter(matches.items()))
            device = hid.device()
            device.open_path(path)
            return cls(device, usb_id, lease)
        except Exception:
            if device is not None:
                device.close()
            if lease is not None:
                lease.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        try:
            self._device.close()
        finally:
            if self._lease is not None:
                self._lease.close()
                self._lease = None

    def _exchange(self, request, echo=None, timeout=900):
        request = bytes(request)
        if len(request) > 32:
            raise ValueError("USB-Befehl ist zu lang.")
        packet = b"\x00" + request.ljust(32, b"\x00")
        if self._device.write(packet) != len(packet):
            raise ViaError("USB-Bericht konnte nicht vollständig gesendet werden.")
        reply = bytes(self._device.read(32, timeout))
        if not reply:
            raise ViaError("Die VIA-Schnittstelle antwortet nicht. VIA oder andere Pad-Editoren schließen und USB prüfen.")
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
        if reply[3:7] != b"OMP2":
            raise UnsupportedCommand("Diese Firmware unterstützt das OmniPad-Profilsystem nicht.")
        remote_size = int.from_bytes(reply[9:11], "little")
        if remote_size != PROFILE_SIZE:
            if remote_size == 6084:
                raise UnsupportedCommand(
                    "Auf dem Pad läuft noch die alte 6084-Byte-Firmware. "
                    "Das neue Display-Studio benötigt einmalig die Multi-Screen-UF2. "
                    "Bitte vorher den aktuellen Profilentwurf exportieren. "
                    "Die App überschreibt das Gerät mit dieser alten Firmware nicht.")
            raise UnsupportedCommand(
                f"Inkompatible Firmware: Geräteprofil {remote_size}, App erwartet {PROFILE_SIZE} Byte.")
        return {"enabled": bool(reply[7]), "max_layers": reply[8],
                "generation": int.from_bytes(reply[11:15], "little"), "expander": bool(reply[15]),
                "light_preview": bool(reply[16] & 1), "device_actions": bool(reply[16] & 2),
                "screen_themes": bool(reply[16] & 4), "matrix_zones": bool(reply[16] & 8),
                "simple_lighting": bool(reply[16] & 16)}

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
        self._exchange((0x07, 0, 0x76, (2 if tester else 1) if enabled else 0), timeout=DIAGNOSTIC_TIMEOUT_MS)

    def tester_report(self):
        reply = self._exchange((0x08, 0, 0x77), timeout=DIAGNOSTIC_TIMEOUT_MS)
        if reply[5] > 6:
            raise ViaError("Ungültiger Tester-Bericht vom OmniPad.")
        entries = tuple(iter_unpack("<BBH", reply[6:6 + 4 * reply[5]]))
        return bool(reply[3]), bool(reply[4]), entries

    def test_output(self, output):
        self._exchange((0x07, 0, 0x78, output), timeout=DIAGNOSTIC_TIMEOUT_MS)

    def preview_lighting(self, payload):
        mode = 0 if payload is None else 1 if len(payload) == 2 * ZONE_STRUCT.size else 2
        self._exchange(bytes((0x07, 0, 0x79, mode)) + (payload or b""))

    def matrix_zone_capabilities(self):
        reply = self._exchange((0x08, 0, 0x7B))
        if reply[3:7] != b"MZ01" or reply[7:10] != bytes((5, MATRIX_COUNT, FRAME_COUNT)):
            raise UnsupportedCommand("Firmware unterstützt die 30+43-LED-Zonen nicht.")
        return True

    def read_matrix_zones(self):
        self.matrix_zone_capabilities()
        result = []
        for layer in range(MAX_LAYERS):
            zones = []
            for index in range(len(MATRIX_ZONES)):
                reply = self._exchange((0x08, 0, 0x7A, layer, index))
                effect, brightness, speed, flags, a, b, triggers, duration = ZONE_STRUCT.unpack_from(reply, 5)
                zones.append({
                    "effect": effect, "brightness": brightness, "speed": speed,
                    "enabled": bool(flags & 1), "reverse": bool(flags & 2),
                    "color_a": colorhex(a), "color_b": colorhex(b),
                    "triggers": triggers, "duration": duration})
            result.append(zones)
        zone_map = []
        for page in range(2):
            reply = self._exchange((0x08, 0, 0x7A, 255, page))
            zone_map.extend(reply[5:20])
        validate_zone_map(zone_map)
        return result, zone_map

    def write_matrix_zones(self, profile, *, progress=None):
        self.matrix_zone_capabilities()
        zone_map = validate_zone_map(profile.get("led_zone_map", default_zone_map()))
        # Explicit separate config stored in the QMK USER datablock.
        # The original transactional profile and Frame settings are unchanged.
        for layer in range(MAX_LAYERS):
            stored = profile["layers"][layer] if layer < len(profile["layers"]) else {}
            zones = stored.get("matrix_zones", [zone_config() for _ in MATRIX_ZONES])
            if len(zones) != len(MATRIX_ZONES):
                raise ValueError("Die fünf Matrix-Zonen fehlen auf Layer {}.".format(layer + 1))
            for index, zone in enumerate(zones):
                packed = encode_lighting([zone, zone])[:ZONE_STRUCT.size]
                self._exchange(bytes((0x07, 0, 0x7A, layer, index)) + packed)
                if progress:
                    progress(layer * 5 + index + 1, MAX_LAYERS * 5 + 2)
        for page in range(2):
            self._exchange(bytes((0x07, 0, 0x7A, 255, page)) +
                           bytes(zone_map[page * 15:(page + 1) * 15]))
            if progress:
                progress(MAX_LAYERS * 5 + page + 1, MAX_LAYERS * 5 + 2)
        self._exchange((0x07, 0, 0x7B, 1), timeout=12000)
        received, actual_map = self.read_matrix_zones()
        if actual_map != zone_map:
            raise ViaError("LED-Zonenmatrix stimmt nach dem Speichern nicht überein.")
        for layer in range(len(profile["layers"])):
            for index, expected in enumerate(profile["layers"][layer].get("matrix_zones", [])):
                if encode_lighting([expected, expected])[:10] != encode_lighting(
                        [received[layer][index], received[layer][index]])[:10]:
                    raise ViaError(f"LED-Zone Layer {layer+1}, Zone {index+1}: Geräteabweichung.")
        return True

    def detection(self):
        reply = self._exchange((0x08, 0, 0x70), timeout=DIAGNOSTIC_TIMEOUT_MS)
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
