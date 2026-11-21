"""Unit tests: reordering/deleting layers must not redirect key actions."""
from copy import deepcopy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layer_operations import (move_layer, delete_layer, rename_layer, duplicate_layer,
                              layer_references, valid_layer_name)
from bindings import DISABLED
from profile import default_profile, encode_profile, MAX_LAYERS


class LayerOperationsTests(unittest.TestCase):
    def setUp(self):
        self.p = default_profile()
        self.p["layers"] = self.p["layers"][:4]
        for i, lay in enumerate(self.p["layers"]):
            lay["name"] = ("ROOT", "NAV", "TEXT", "MACROS")[i]
            lay["keys"][0]["codes"] = [0x5202, 0x5221, 0x5263, 0, 0]
            lay["encoders"] = [0x5202, 0x5221]
            lay["slider"].update(mode=1, low=0x5263, high=0x5202)
        self.p["default_layer"] = 2
        self.p["snippets"] = [{"name": "test", "steps": [
            {"type": "tap", "value": 0x5202},
            {"type": "down", "value": 0x5221},
            {"type": "up", "value": 0x5263},
            {"type": "delay", "value": 50},
        ]}]
        self.p["screen"]["fields"] = [
            {"layer": 2, "id": "text"}, {"layer": 1, "id": "nav"},
            {"layer": -1, "id": "global"}]

    def test_move_remaps_references_and_start_and_screen(self):
        initial = deepcopy(self.p)
        self.assertEqual(move_layer(self.p, 2, 0), 0)
        self.assertEqual([l["name"] for l in self.p["layers"]], ["TEXT", "ROOT", "NAV", "MACROS"])
        self.assertEqual(self.p["default_layer"], 0)
        for layer in self.p["layers"]:
            self.assertEqual(layer["keys"][0]["codes"][:3], [0x5200, 0x5222, 0x5263])
            self.assertEqual(layer["encoders"], [0x5200, 0x5222])
            self.assertEqual((layer["slider"]["low"], layer["slider"]["high"]), (0x5263, 0x5200))
        self.assertEqual([s["value"] for s in self.p["snippets"][0]["steps"]],
                         [0x5200, 0x5222, 0x5263, 50])
        self.assertEqual([f["layer"] for f in self.p["screen"]["fields"]], [0, 2, -1])
        self.assertEqual(move_layer(self.p, 0, 2), 2)
        self.assertEqual(self.p, initial)

    def test_delete_clears_deleted_targets_and_screen_fields(self):
        stats = delete_layer(self.p, 2)
        self.assertGreater(stats[0], 0)
        self.assertEqual(stats[1], 1)
        self.assertEqual(self.p["default_layer"], 2)
        self.assertEqual([l["name"] for l in self.p["layers"]], ["ROOT", "NAV", "MACROS"])
        for layer in self.p["layers"]:
            self.assertEqual(layer["keys"][0]["codes"][:3], [DISABLED, 0x5221, 0x5262])
            self.assertEqual(layer["encoders"], [DISABLED, 0x5221])
            self.assertEqual((layer["slider"]["low"], layer["slider"]["high"]), (0x5262, DISABLED))
        self.assertEqual([f["id"] for f in self.p["screen"]["fields"]], ["nav", "global"])
        self.assertEqual([s["value"] for s in self.p["snippets"][0]["steps"]],
                         [DISABLED, 0x5221, 0x5262, 50])

    def test_delete_before_start_remaps_start(self):
        delete_layer(self.p, 1)
        self.assertEqual(self.p["default_layer"], 1)
        self.assertEqual([l["name"] for l in self.p["layers"]], ["ROOT", "TEXT", "MACROS"])

    def test_delete_last_is_forbidden(self):
        self.p["layers"] = self.p["layers"][:1]
        with self.assertRaises(ValueError):
            delete_layer(self.p, 0)

    def test_duplicate_is_independent_and_unique(self):
        index = duplicate_layer(self.p, 2, MAX_LAYERS)
        self.assertEqual(index, 4)
        self.assertEqual(self.p["layers"][index]["keys"], self.p["layers"][2]["keys"])
        self.p["layers"][index]["keys"][0]["codes"][0] = 0x04
        self.assertEqual(self.p["layers"][2]["keys"][0]["codes"][0], 0x5202)
        self.assertNotEqual(self.p["layers"][index]["name"], "TEXT")
        with self.assertRaises(ValueError):
            rename_layer(self.p, index, "nav")

    def test_rename_wire_safety(self):
        rename_layer(self.p, 1, "Navigation")
        self.assertEqual(self.p["layers"][1]["name"], "Navigation")
        for bad in ("", "        ", "VERYLONG_LAYER_NAME", "text"):
            with self.assertRaises(ValueError):
                valid_layer_name(self.p, bad, exclude=1)

    def test_profile_roundtrip_after_structure_change(self):
        self.p["screen"]["fields"] = []
        self.p["snippets"] = []
        move_layer(self.p, 1, 3)
        delete_layer(self.p, 0)
        # New wire format remains fixed-size even if the count changes.
        self.assertEqual(len(encode_profile(self.p)), 6084)


if __name__ == "__main__":
    unittest.main()
