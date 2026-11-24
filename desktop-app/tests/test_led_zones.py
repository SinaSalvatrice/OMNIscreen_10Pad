import sys
from pathlib import Path
import unittest
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from led_zones import (default_zone_map, validate_zone_map, MATRIX_COUNT, FRAME_COUNT,
                       LED_COUNT, matrix_positions, matrix_order, ZONE_NAMES)
from profile import EFFECTS, default_profile, encode_profile, decode_profile, encode_lighting, zone_config
from lighting import animation_interval, led_colors, reactive_color, REACTIVE_DURATION_MS


class MatrixZoneTests(unittest.TestCase):
    def test_physical_chain_counts(self):
        self.assertEqual((MATRIX_COUNT, FRAME_COUNT, LED_COUNT), (30, 43, 73))
        groups = default_zone_map()
        self.assertEqual(len(groups), 30)
        self.assertEqual([groups.count(index) for index in range(5)], [16, 3, 2, 2, 7])
        self.assertEqual(ZONE_NAMES[-1], "Frame")

    def test_map_is_editable_but_frame_does_not_move(self):
        mapping = default_zone_map()
        mapping[2] = 1
        self.assertEqual(validate_zone_map(mapping)[2], 1)
        for invalid in ([0] * 29, [0] * 29 + [5], [0] * 29 + [-1]):
            with self.assertRaises(ValueError):
                validate_zone_map(invalid)

    def test_straight_and_serpentine_30_unique(self):
        for order in ("rows", "serpentine"):
            coords = matrix_positions(order)
            self.assertEqual(len(coords), 30)
            self.assertEqual(len({tuple(p) for p in coords}), 30)

    def test_zone_layout_preserves_standard_wiring_order(self):
        serpentine = default_zone_map("serpentine")
        self.assertEqual(matrix_order(serpentine), "serpentine")
        self.assertEqual(serpentine[5:10], list(reversed(default_zone_map()[5:10])))
        serpentine[0] = 1
        self.assertEqual(matrix_order(serpentine), "rows")

    def test_animated_layer_roundtrips_without_changing_profile_size(self):
        p = default_profile()
        matrix, frame = p["layers"][0]["lighting"]
        matrix.update(effect=12, speed=0, enabled=False, reactive=True)
        frame.update(effect=9, speed=10)
        raw = encode_profile(p)
        self.assertEqual(len(raw), 6124)
        matrix, frame = decode_profile(raw)["layers"][0]["lighting"]
        self.assertEqual((matrix["effect"], matrix["speed"], matrix["enabled"], matrix["reactive"]),
                         (12, 0, False, True))
        self.assertEqual((frame["effect"], frame["speed"]), (9, 10))

    def test_slow_frame_and_reactive_preview(self):
        self.assertEqual(animation_interval(0) * FRAME_COUNT, 22360)
        self.assertEqual(animation_interval(255), 20)
        zone = zone_config()
        for effect in range(len(EFFECTS)):
            zone.update(effect=effect, speed=0)
            self.assertEqual(len(led_colors(zone, FRAME_COUNT, 65000)), FRAME_COUNT)
        zone["enabled"] = False
        base = led_colors(zone, MATRIX_COUNT, 0)[0]
        self.assertEqual(base, (0, 0, 0))
        self.assertEqual(reactive_color(base, "#ff0000", 0), (127, 0, 0))
        self.assertEqual(reactive_color(base, "#ff0000", REACTIVE_DURATION_MS), base)

    def test_legacy_profile_still_wire_compatible(self):
        p = default_profile()
        old_size = len(encode_profile(p))
        self.assertEqual(old_size, 6124)
        self.assertEqual(len(p["layers"][0]["matrix_zones"]), 5)
        old = deepcopy(p)
        for layer in old["layers"]:
            layer.pop("matrix_zones")
        old.pop("led_zone_map")
        self.assertEqual(encode_profile(old), encode_profile(p))
        restored = decode_profile(encode_profile(old))
        self.assertEqual(len(restored["layers"][0]["matrix_zones"]), 5)

    def test_zone_settings_are_independent_of_frame(self):
        p = default_profile()
        p["layers"][0]["matrix_zones"][3]["color_a"] = "#123456"
        self.assertEqual(p["layers"][0]["lighting"][1]["color_a"], "#709fba")
        self.assertEqual(len(encode_lighting([p["layers"][0]["matrix_zones"][3]] * 2)), 20)

if __name__ == "__main__":
    unittest.main()
