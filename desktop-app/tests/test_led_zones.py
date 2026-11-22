import sys
from pathlib import Path
import unittest
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from led_zones import (default_zone_map, validate_zone_map, MATRIX_COUNT, FRAME_COUNT,
                       LED_COUNT, matrix_positions, ZONE_NAMES)
from profile import default_profile, encode_profile, decode_profile, encode_lighting, zone_config


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
