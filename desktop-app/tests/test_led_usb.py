"""USB protocol contract tests for the 30-LED zone sidecar."""
import sys
import unittest
from pathlib import Path
from struct import unpack_from
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from profile import (default_profile, zone_config, ZONE_STRUCT, encode_lighting,
                     MAX_LAYERS, colorhex)
from led_zones import default_zone_map, MATRIX_ZONES
from via import OmniPad


class FakeZonePad:
    def __init__(self):
        self.zones = [[zone_config() for _ in MATRIX_ZONES] for _ in range(MAX_LAYERS)]
        self.mapping = default_zone_map()
        self.commits = 0
        self.requests = []

    def _exchange(self, request, **_kwargs):
        request = bytes(request)
        self.requests.append(request)
        command, channel, action = request[:3]
        self_reply = bytearray(request.ljust(32, b"\0"))
        if action == 0x7B:
            if command == 0x08:
                self_reply[3:10] = b"MZ01" + bytes((5, 30, 43))
                return bytes(self_reply)
            assert command == 0x07 and request[3] == 1
            self.commits += 1
            return bytes(self_reply)
        assert action == 0x7A
        layer, zone = request[3:5]
        if layer == 255:
            if command == 0x08:
                self_reply[5:20] = bytes(self.mapping[zone * 15:(zone+1) * 15])
            else:
                self.mapping[zone*15:(zone+1)*15] = list(request[5:20])
            return bytes(self_reply)
        if command == 0x08:
            self_reply[5:15] = encode_lighting([self.zones[layer][zone]]*2)[:10]
        else:
            effect, brightness, speed, flags, a, b, triggers, duration = ZONE_STRUCT.unpack_from(request, 5)
            self.zones[layer][zone].update(
                effect=effect, brightness=brightness, speed=speed,
                enabled=bool(flags & 1), reverse=bool(flags & 2),
                color_a=colorhex(a), color_b=colorhex(b), triggers=triggers,
                duration=duration)
        return bytes(self_reply)


class UsbZoneTests(unittest.TestCase):
    def _editor_pad(self):
        pad = FakeZonePad()
        editor = object.__new__(OmniPad)
        editor._exchange = pad._exchange
        return editor, pad

    def test_read_matrix_zones_all_12_layers_and_30_pixels(self):
        editor, pad = self._editor_pad()
        zones, mapping = editor.read_matrix_zones()
        self.assertEqual(len(zones), 12)
        self.assertEqual(len(zones[0]), 5)
        self.assertEqual(mapping, default_zone_map())
        self.assertEqual(len(pad.requests), 1 + 60 + 2)

    def test_write_and_verify_is_independent_of_main_profile(self):
        editor, pad = self._editor_pad()
        profile = default_profile()
        profile["led_zone_map"][0] = 1
        profile["layers"][0]["matrix_zones"][0].update(
            brightness=8, effect=5, color_a="#ff0000")
        editor.write_matrix_zones(profile)
        self.assertEqual(pad.commits, 1)
        self.assertEqual(pad.mapping[0], 1)
        self.assertEqual(pad.zones[0][0]["brightness"], 8)
        self.assertEqual(pad.zones[0][0]["effect"], 5)
        self.assertEqual(pad.zones[0][0]["color_a"], "#ff0000")
        self.assertEqual(profile["layers"][0]["lighting"][1]["brightness"], 24)


if __name__ == "__main__":
    unittest.main()
