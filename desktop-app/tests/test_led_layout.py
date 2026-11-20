"""Run with: python -m unittest discover -s desktop-app/tests -p 'test_led_layout.py'"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from led_layout import (default_positions, validate_positions, read_positions,
                        write_positions, to_canvas, from_canvas, square_bounds, LED_COUNT, MAIN_COUNT)


class LayoutTests(unittest.TestCase):
    def test_default_has_unique_positions_and_stable_zone_bounds(self):
        positions = default_positions()
        self.assertEqual(len(positions), LED_COUNT)
        self.assertEqual(MAIN_COUNT, 14)
        self.assertEqual(len({tuple(p) for p in positions}), LED_COUNT)
        self.assertEqual(positions[14][1], 0.11)
        self.assertTrue(all(0 <= a <= 1 and 0 <= b <= 1 for a, b in positions))

    def test_round_trip_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "led-layout.json"
            points = default_positions()
            points[0] = [0.33333, 0.67891]
            write_positions(points, target)
            self.assertEqual(read_positions(target), points)
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["led_count"], 57)

    def test_read_missing_uses_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(read_positions(Path(directory) / "not-there.json"), default_positions())

    def test_invalid_layout_cannot_remap_indices(self):
        points = default_positions()
        points.pop()
        with self.assertRaises(ValueError):
            validate_positions({"schema": "omnipad-led-layout", "version": 1,
                                "led_count": 57, "positions": points})
        points.append([float("nan"), 0.3])
        with self.assertRaises(ValueError):
            validate_positions({"schema": "omnipad-led-layout", "version": 1,
                                "led_count": 57, "positions": points})

    def test_square_preview_bounds_landscape_and_portrait(self):
        for width, height in ((650, 440), (440, 650), (500, 500)):
            left, top, right, bottom = square_bounds(width, height)
            self.assertEqual(right - left, bottom - top)
            self.assertAlmostEqual((left + right) / 2, width / 2)
            self.assertAlmostEqual((top + bottom) / 2, height / 2)
            x, y = to_canvas([0.5, 0.5], width, height)
            self.assertAlmostEqual(x, width / 2)
            self.assertAlmostEqual(y, height / 2)

    def test_canvas_coordinates_and_clamp(self):
        for width, height in ((650, 440), (440, 650), (500, 500)):
            for point in ([0.0, 0.0], [1.0, 1.0], [0.34567, 0.78912]):
                x, y = to_canvas(point, width, height)
                self.assertEqual(from_canvas(x, y, width, height), point)
        self.assertEqual(from_canvas(-100, 9999, 650, 440), [0, 1])


if __name__ == "__main__":
    unittest.main()
