"""OmniPad Next fixed lighting zones, volatile previews and input feedback.

No VIA keymap writes, no K0/encoder system menu writes, no app profile writes.
EEPROM changes occur only on explicit user initiated "LEDs auf Pad speichern".
All writes are staged; only one final commit publishes them. The device is
read back and byte-compared afterwards. Firmware MZ01 is never written to.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from hid_backend import load_hidapi
from pad_profile import PROFILE_SIZE, profile_with_assignments
from model import (BASE_GROUPS, COLOR_MODES, EFFECTS, MATRIX_TRIGGER_ZONES,
                   REACTION_PALETTES, SUBZONES, TRIGGERS, ZONE_LEDS, group_reaction)

VIDS = {(0x4F4D, 0x7789), (0xFEED, 0x7789)}
MATRIX_LAYERS = 8
PALETTE_OFFSET = 96
BRIGHTNESS_BYTES = MATRIX_LAYERS * 4
COLOR_BYTES = PALETTE_OFFSET + MATRIX_LAYERS * 2
LIGHTING_VERSION = 4
LIVE_LED_COUNT = 73
LIVE_CHUNK_BYTES = 27
TRIGGER_FLAGS = {name: 1 << i for i, name in enumerate(TRIGGERS)}
EFFECT_IDS = {value: index for index, value in enumerate(EFFECTS)}
ZONE_MAP = [next(i for i, name in enumerate(SUBZONES) if led in ZONE_LEDS[name])
            for led in range(30)]
SERPENTINE_MAP = [ZONE_MAP[row * 5 + (4 - col if row % 2 else col)]
                  for row in range(6) for col in range(5)]


class ProtocolError(RuntimeError):
    pass


class UnsupportedFirmware(ProtocolError):
    pass


def rgb565(hex_color):
    rgb = [int(hex_color[i:i+2], 16) for i in (1, 3, 5)]
    return (rgb[0] >> 3) << 11 | (rgb[1] >> 2) << 5 | (rgb[2] >> 3)


def zone_record(light, reaction, *, zone):
    """Pack the selected triggers and both animation color modes."""
    enabled = bool(light["enabled"]) and light["animation"] != "Aus"
    flags = int(enabled) | (int(light["reverse"]) << 1) | (int(reaction["enabled"]) << 2)
    triggers = sum(TRIGGER_FLAGS[t] for t in TRIGGERS if t in reaction["triggers"]
                   and (zone == "frame" or MATRIX_TRIGGER_ZONES[t] == zone))
    color_a = COLOR_MODES.index(light.get("color_a_mode", COLOR_MODES[0]))
    color_b = COLOR_MODES.index(light.get("color_b_mode", COLOR_MODES[0]))
    animation = EFFECT_IDS[light["animation"]] | ((color_a + 3 * color_b) << 4)
    return struct.pack("<BBBBHHBB", animation,
                       round(light["brightness"] * 64 / 100),
                       round(light["speed"] * 255 / 100), flags,
                       rgb565(light["color_a"]), rgb565(light["color_b"]),
                       triggers, max(1, round(reaction["duration"] / 10)))


@dataclass
class LightingPayload:
    zones: dict[tuple[int, int], bytes]
    tints: bytes
    mapping: bytes


@dataclass(frozen=True)
class LiveInputs:
    held: int
    pressed: int
    layer: int
    triggers: int
    preview_allowed: bool


def prepare_lighting(project):
    if len(project["layers"]) != MATRIX_LAYERS:
        raise ProtocolError("Die Firmware hat acht Layer.")
    records = {}
    colors = bytearray(COLOR_BYTES)
    for layer_id, layer in enumerate(project["layers"]):
        matrix, frame = (layer["groups"][group] for group in BASE_GROUPS)
        matrix_reaction, frame_reaction = (group_reaction(layer, group) for group in BASE_GROUPS)
        for i, group in enumerate(SUBZONES):
            records[(layer_id, i)] = zone_record(matrix, matrix_reaction, zone=group)
        # Firmware spare storage: rows 8 and 9, slots 0..7.
        records[(8 + layer_id // 5, layer_id % 5)] = zone_record(frame, frame_reaction, zone="frame")
        offset = layer_id * 4
        colors[offset:offset + 4] = bytes(
            light.get(f"color_{channel}_brightness", 100)
            for light in (matrix, frame) for channel in ("a", "b"))
        colors[PALETTE_OFFSET + layer_id] = REACTION_PALETTES.index(matrix_reaction["palette"])
        colors[PALETTE_OFFSET + MATRIX_LAYERS + layer_id] = REACTION_PALETTES.index(frame_reaction["palette"])
    return LightingPayload(records, bytes(colors), bytes(ZONE_MAP))


class Usb:
    def __init__(self, handle):
        self.handle = handle
        self.preview_sequence = 0

    @classmethod
    def connect(cls):
        hid = load_hidapi()
        matches = [e for e in hid.enumerate()
                   if (e.get("vendor_id"), e.get("product_id")) in VIDS
                   and e.get("usage_page") == 0xFF60 and e.get("usage") == 0x61]
        if len(matches) != 1:
            raise ProtocolError("Bitte genau ein OmniPad über VIA/HID verbinden.")
        handle = hid.device()
        handle.open_path(matches[0]["path"])
        return cls(handle)

    def close(self):
        self.handle.close()

    def exchange(self, data, *, timeout=4500):
        packet = bytes(data)
        if len(packet) > 32:
            raise ValueError("HID-Befehl zu lang")
        sent = self.handle.write(b"\x00" + packet.ljust(32, b"\x00"))
        if sent != 33:
            raise ProtocolError("HID-Schreibfehler")
        response = bytes(self.handle.read(32, timeout))
        if len(response) != 32:
            raise ProtocolError("HID-Antwort fehlt oder ist unvollständig")
        if response[0] == 0xFF:
            raise UnsupportedFirmware("Nicht unterstützter Firmwarebefehl")
        if response[:3] != packet[:3]:
            raise ProtocolError(f"Falsche HID-Antwort: {response[:3].hex()}")
        return response

    def capabilities(self):
        info = self.exchange((0x08, 0, 0x71))
        if info[3:7] != b"OMP2":
            raise UnsupportedFirmware("OmniPad-Profil nicht erkannt")
        zones = self.exchange((0x08, 0, 0x7B))
        if zones[3:7] != b"MZ01" or zones[7:10] != bytes((5, 30, 43)):
            raise UnsupportedFirmware("LED-Zonen fehlen")
        try:
            advanced = self.exchange((0x08, 0, 0x7D, 255, 0))
        except UnsupportedFirmware as exc:
            raise UnsupportedFirmware(
                "Die angeschlossene Firmware ist noch MZ01. "
                "Bitte zuerst die neue UF2 flashen; nichts wurde geschrieben."
            ) from exc
        if (advanced[3:7] != b"LX02" or advanced[7:10] != bytes((8, 6, PALETTE_OFFSET))
                or advanced[10] != LIGHTING_VERSION):
            raise UnsupportedFirmware(
                "Zum Speichern der neuen Farb- und Animationsmodi bitte die aktuelle UF2 flashen.")
        return advanced[11]

    def read_zone(self, row, col):
        return self.exchange((0x08, 0, 0x7A, row, col))[5:15]

    def read_map(self):
        return b"".join(self.exchange((0x08, 0, 0x7A, 255, i))[5:20]
                        for i in range(2))

    def read_live_inputs(self):
        status = self.exchange((0x08, 0, 0x7F), timeout=240)
        if status[3:7] != b"NL01":
            raise UnsupportedFirmware("Firmware ohne Live-Feedback")
        return LiveInputs(*struct.unpack_from("<HHBBB", status, 7))

    def send_preview(self, colors, *, serpentine):
        if len(colors) != LIVE_LED_COUNT:
            raise ValueError("Ein Vorschauframe muss 73 LEDs enthalten.")
        ordered = list(colors)
        if serpentine:
            for offset in (5, 15, 25):
                ordered[offset:offset + 5] = reversed(ordered[offset:offset + 5])
        frame = bytes(component for rgb in ordered for component in rgb)
        self.preview_sequence = (self.preview_sequence + 1) % 256
        for chunk, offset in enumerate(range(0, len(frame), LIVE_CHUNK_BYTES)):
            reply = self.exchange(
                (0x07, 0, 0x7E, chunk, self.preview_sequence,
                 *frame[offset:offset + LIVE_CHUNK_BYTES]), timeout=240)
            if reply[3] == 255:
                return False
            if reply[3:5] != bytes((chunk, self.preview_sequence)):
                raise ProtocolError("Vorschauframe wurde nicht bestätigt.")
        return True

    def stop_preview(self):
        self.exchange((0x07, 0, 0x7E, 255), timeout=240)

    def read_key_profile(self):
        data = bytearray()
        for offset in range(0, PROFILE_SIZE, 25):
            size = min(25, PROFILE_SIZE - offset)
            reply = self.exchange(struct.pack("<3BHB", 0x08, 0, 0x72, offset, size))
            data.extend(reply[6:6 + size])
        return bytes(data)

    def upload_assignments(self, project):
        info = self.exchange((0x08, 0, 0x71))
        if info[3:7] != b"OMP2" or struct.unpack_from("<H", info, 9)[0] != PROFILE_SIZE:
            raise UnsupportedFirmware("Die Firmware unterstützt dieses Tastenprofil nicht.")
        generation = struct.unpack_from("<I", info, 11)[0]
        current = self.read_key_profile() if info[7] else None
        payload = profile_with_assignments(project, current, encoder_push=bool(info[16] & 32))
        if payload == current:
            return "Belegung auf dem Pad ist bereits aktuell."
        checksum = 2166136261
        for value in payload:
            checksum = ((checksum ^ value) * 16777619) & 0xFFFFFFFF
        self.exchange(struct.pack("<3BII", 0x07, 0, 0x73, checksum, generation))
        for offset in range(0, len(payload), 25):
            chunk = payload[offset:offset + 25]
            self.exchange(struct.pack("<3BHB", 0x07, 0, 0x74, offset, len(chunk)) + chunk)
        self.exchange((0x07, 0, 0x75), timeout=12000)
        if self.read_key_profile() != payload:
            raise ProtocolError("Die zurückgelesene Belegung stimmt nicht mit dem Projekt überein.")
        return "Belegung auf dem Pad gespeichert. Bedienmodus am Pad prüfen."

    def read_tints(self):
        output = bytearray()
        for offset in range(0, COLOR_BYTES, 25):
            size = min(25, COLOR_BYTES - offset)
            output.extend(self.exchange((0x08, 0, 0x7D, offset, size))[5:5 + size])
        return bytes(output)

    def read_state(self):
        result = {}
        for layer in range(8):
            for zone in range(5):
                result[(layer, zone)] = self.read_zone(layer, zone)
        for layer in range(8):
            result[(8 + layer // 5, layer % 5)] = self.read_zone(
                8 + layer // 5, layer % 5)
        return LightingPayload(result, self.read_tints(), self.read_map())

    def upload(self, project, on_progress=None):
        payload = prepare_lighting(project)
        stored_version = self.capabilities()
        current = self.read_state()
        # Never rewrite the physical winding (straight vs serpentine).
        # Matrix/Frame editing only changes animations and trigger overlays.
        if current.mapping not in (bytes(ZONE_MAP), bytes(SERPENTINE_MAP)):
            raise ProtocolError("Physische LED-Zonen weichen von der erkannten Verdrahtung ab. "
                                "Keine Änderung, um die Zonenzuordnung zu schützen.")
        payload.mapping = current.mapping
        payload.tints = (payload.tints[:BRIGHTNESS_BYTES]
                         + current.tints[BRIGHTNESS_BYTES:PALETTE_OFFSET]
                         + payload.tints[PALETTE_OFFSET:])
        if stored_version == LIGHTING_VERSION and current == payload:
            return "Die LED-Konfiguration ist bereits identisch."
        try:
            actions = list(sorted(payload.zones.items()))
            for index, ((layer, zone), data) in enumerate(actions):
                self.exchange((0x07, 0, 0x7A, layer, zone, *data))
                if on_progress:
                    on_progress(index + 1, len(actions))
            for index in range(2):
                offset = index * 15
                self.exchange((0x07, 0, 0x7A, 255, index,
                               *payload.mapping[offset:offset + 15]))
            for offset in range(0, len(payload.tints), 25):
                chunk = payload.tints[offset:offset + 25]
                self.exchange((0x07, 0, 0x7D, offset, len(chunk), *chunk))
            # Stage is valid. Publish only once, after every preceding HID ACK.
            self.exchange((0x07, 0, 0x7B, LIGHTING_VERSION))
        except Exception:
            try:
                self.exchange((0x07, 0, 0x7B, 0))
            except Exception:
                pass
            raise
        applied = self.read_state()
        if applied != payload:
            raise ProtocolError("Gerät antwortet, aber zurückgelesene LEDs weichen ab.")
        return "LEDs auf dem Pad gespeichert und vollständig zurückgelesen."
