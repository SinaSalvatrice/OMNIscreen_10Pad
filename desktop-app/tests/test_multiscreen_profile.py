"""Multiscreen OmniPad profile compatibility and isolation."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from profile import (default_profile, encode_profile, decode_profile, PROFILE_SIZE,
                     LEGACY_PROFILE_SIZE, SCREEN_VIEWS, SCREEN_PRESETS, new_field,
                     validate_screen, default_screen_themes)


class ScreenProfilesTests(unittest.TestCase):
    def test_profile_with_six_screens_roundtrip(self):
        p = default_profile()
        p["screen"]["enabled"] = True
        for i, theme in enumerate(p["screen"]["themes"]):
            theme.update(preset=i % 3, background="#123456",
                         accent="#abcdef")
        payload = encode_profile(p)
        self.assertEqual(len(payload), 6124)
        self.assertEqual(PROFILE_SIZE-LEGACY_PROFILE_SIZE, 40)
        self.assertEqual(payload[LEGACY_PROFILE_SIZE:LEGACY_PROFILE_SIZE+4], b"SCR1")
        restored = decode_profile(payload)
        self.assertEqual(encode_profile(restored), payload)
        self.assertEqual([x["preset"] for x in restored["screen"]["themes"]],
                         [0, 1, 2, 0, 1, 2])

    def test_old_user_draft_auto_upgrades_without_losing_fields(self):
        p = default_profile()
        p["screen"].pop("themes")
        field = new_field(1)
        field["text"] = "LEGACY TEXT"
        p["screen"]["fields"] = [field]
        payload = encode_profile(p)
        restored = decode_profile(payload)
        self.assertEqual(restored["screen"]["fields"][0]["text"], "LEGACY TEXT")
        self.assertEqual(len(restored["screen"]["themes"]), len(SCREEN_VIEWS))

    def test_scoped_fields_keep_screen_and_layer(self):
        p = default_profile()
        p["screen"]["enabled"] = True
        field = new_field(1)
        field.update(view=4, layer=1, text="NAV")
        generic = new_field(1)
        generic.update(view=0, layer=-1, text="HOME")
        p["screen"]["fields"] = [field, generic]
        restored = decode_profile(encode_profile(p))
        self.assertEqual(restored["screen"]["fields"][0]["view"], 4)
        self.assertEqual(restored["screen"]["fields"][0]["layer"], 1)
        self.assertEqual(restored["screen"]["fields"][1]["view"], 0)
        self.assertEqual(restored["screen"]["fields"][1]["layer"], -1)

    def test_invalid_theme_refused(self):
        p = default_profile()
        p["screen"]["themes"][0]["preset"] = 3
        with self.assertRaises(ValueError):
            encode_profile(p)

    def test_six_views_three_templates(self):
        self.assertEqual(len(SCREEN_VIEWS), 6)
        self.assertEqual(list(SCREEN_PRESETS), ["Industrial", "Terminal", "Spectrum"])


if __name__ == "__main__":
    unittest.main()
