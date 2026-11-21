import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from profile_audit import action_differences


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.draft = {"default_layer": 0, "layers": [
            {"name": "DEFAULT", "keys": [
                {"mode": 1, "term": 240, "codes": [0, 0x5201, 0, 0, 0]}
            ], "encoders": [0, 0]}
        ]}

    def test_same(self):
        self.assertEqual(action_differences(self.draft, copy.deepcopy(self.draft)), [])

    def test_double_tap_slot(self):
        other = copy.deepcopy(self.draft)
        other["layers"][0]["keys"][0]["codes"][1] = 0
        result = action_differences(self.draft, other)
        self.assertEqual(len(result), 1)
        self.assertIn("2x", result[0])
        self.assertIn("5201", result[0])

    def test_start_layer_and_mode(self):
        other = copy.deepcopy(self.draft)
        other["default_layer"] = 1
        other["layers"][0]["keys"][0]["mode"] = 0
        result = action_differences(self.draft, other)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
