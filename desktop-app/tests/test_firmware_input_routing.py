"""Regression checks for K9 wiring and OmniPad gesture routing.

These tests intentionally read the shipped source files, not a duplicate map.
They catch the exact two regressions that disabled the physical keys.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYMAP = ROOT / "keyboards" / "icst7789v" / "keymaps" / "default"


class HardwareInputRoutingTests(unittest.TestCase):
    def test_k9_physical_matrix_is_2_1_in_every_source(self):
        design = json.loads((ROOT / "design" / "layer_system.json").read_text(encoding="utf-8"))
        physical = {key["id"]: (key["row"], key["col"]) for key in design["physical_keys"]}
        self.assertEqual(physical["K9"], (2, 1))
        keyboard = json.loads((ROOT / "keyboards" / "icst7789v" / "keyboard.json").read_text(encoding="utf-8"))
        self.assertEqual(keyboard["layouts"]["LAYOUT"]["layout"][8]["matrix"], [2, 1])
        generated = (KEYMAP / "generated_layers.h").read_text(encoding="utf-8")
        rows = re.search(r"cc_matrix_row\[CC_KEY_COUNT\] = \{([^}]+)\}", generated).group(1)
        cols = re.search(r"cc_matrix_col\[CC_KEY_COUNT\] = \{([^}]+)\}", generated).group(1)
        coords = list(zip([int(x.strip()) for x in rows.split(",")],
                          [int(x.strip()) for x in cols.split(",")]))
        self.assertEqual(coords[8], (2, 1))
        self.assertEqual(len(set(coords)), 10)

    def test_app_tap_dance_has_priority_over_fallback(self):
        source = (KEYMAP / "cc_controls.h").read_text(encoding="utf-8")
        handler = source.split("bool pre_process_record_user(", 1)[1].split(
            "if (!IS_ENCODEREVENT(", 1)[0]
        fixed = handler.index("cc_handle_fixed_modifier(row, col, record->event.pressed)")
        profile = handler.index("if (omp_enabled)")
        fallback = handler.index("cc_td_event(i, record->event.pressed)")
        self.assertLess(fixed, profile)
        self.assertLess(profile, fallback)
        self.assertIn("omp_key_event(i, record->event.pressed)", handler)

    def test_home_screen_does_not_redraw_on_every_press(self):
        controls = (KEYMAP / "cc_controls.h").read_text(encoding="utf-8")
        actions = (KEYMAP / "cc_editor_actions.h").read_text(encoding="utf-8")
        self.assertIn("if (!cc_home_view) cc_dirty = true;", controls)
        self.assertGreaterEqual(actions.count("if (!cc_home_view) cc_dirty = true;"), 2)

    def test_saved_profile_has_priority_over_standalone_layer_specials(self):
        source = (KEYMAP / "cc_omni_keymap.h").read_text(encoding="utf-8")
        for function, following in (
            ("static bool cc_special_key(", "if (cc_active == CC_RGB_LAYER)"),
            ("static bool cc_user_encoder_turn(", "if (cc_active == CC_RGB_LAYER)"),
            ("static bool cc_user_encoder_push(", "if (cc_active == CC_NAV_LAYER"),
        ):
            fragment = source.split(function, 1)[1].split(following, 1)[0]
            self.assertIn("if (omp_enabled) return false;", fragment)
        layer_change = source.split("static void cc_user_layer_change(", 1)[1].split(
            "for (uint8_t i = 0;", 1)[0]
        self.assertIn("if (!omp_enabled)", layer_change)
        self.assertIn("cc_rgb_preview_begin()", layer_change)

    def test_fallback_k9_ctrl_is_still_2_1(self):
        controls = (KEYMAP / "cc_controls.h").read_text(encoding="utf-8")
        self.assertIn("if (row != 2 || col != 1) return false;", controls)
        self.assertEqual(controls.count("!(row == 2 && col == 1)"), 2)
        self.assertIn("cc_activate_layer(0)", controls)


if __name__ == "__main__":
    unittest.main()
