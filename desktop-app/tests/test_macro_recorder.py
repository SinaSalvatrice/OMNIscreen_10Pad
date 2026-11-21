"""Run: python -m unittest discover -s desktop-app/tests -p test_macro_recorder.py -v"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_recorder import MacroCapture, parse_snippet_lines, format_snippet_lines, keysym_code
from profile import BASIC_CODES, compile_snippet


class RecorderTests(unittest.TestCase):
    def test_ctrl_v_keeps_modifier_through_v_key_release(self):
        model = MacroCapture()
        model.press("Control_L", 17, now=1.00)
        model.press("v", 86, now=1.05)
        model.release("v", 86, now=1.12)
        model.release("Control_L", 17, now=1.15)
        steps = model.finish()
        keysteps = [(s["type"], s["value"]) for s in steps if s["type"] != "delay"]
        self.assertEqual(keysteps, [
            ("down", BASIC_CODES["Strg"]), ("down", BASIC_CODES["V"]),
            ("up", BASIC_CODES["V"]), ("up", BASIC_CODES["Strg"])])
        self.assertTrue(any(s["type"] == "delay" for s in steps))
        snippet = {"name": "Paste", "steps": steps}
        self.assertEqual(len(compile_snippet(snippet)), len(steps) * 3)
        self.assertEqual(parse_snippet_lines(format_snippet_lines(steps)), steps)

    def test_shifted_release_does_not_drop_key(self):
        m = MacroCapture()
        m.press("Shift_L", 16, now=1.0)
        m.press("V", 86, now=1.01)
        m.release("Shift_L", 16, now=1.04)
        m.release("v", 86, now=1.06)
        seq = [(v["type"], v["value"]) for v in m.finish() if v["type"] != "delay"]
        self.assertEqual(seq, [("down", 225), ("down", BASIC_CODES["V"]),
                               ("up", 225), ("up", BASIC_CODES["V"])])

    def test_stop_releases_pending_modifiers(self):
        m = MacroCapture()
        m.press("Control_L", 17, now=2)
        m.press("Alt_L", 18, now=2.01)
        seq = m.finish()
        self.assertEqual(seq[-2:], [{"type": "up", "value": 226}, {"type": "up", "value": 224}])
        self.assertEqual(m.pressed, {})
        compile_snippet({"name": "closed", "steps": seq})

    def test_ignores_autorepeat_and_missing_release(self):
        m = MacroCapture()
        self.assertTrue(m.press("z", 90, now=0.0))
        self.assertFalse(m.press("z", 90, now=0.1))
        self.assertTrue(m.release("z", 90, now=0.2))
        self.assertFalse(m.release("z", 90, now=0.3))
        self.assertEqual(len([s for s in m.steps if s["type"] == "down"]), 1)

    def test_key_translation_german_and_function_keys(self):
        self.assertEqual(keysym_code("z"), BASIC_CODES["Z"])
        self.assertEqual(keysym_code("y"), BASIC_CODES["Y"])
        self.assertEqual(keysym_code("F12"), BASIC_CODES["F12"])
        self.assertEqual(keysym_code("BackSpace"), 42)
        self.assertEqual(keysym_code("Control_R"), 228)
        self.assertIsNone(keysym_code("Hyper_Unknown"))

    def test_format_parse_roundtrip_with_delay_and_hex(self):
        steps = [{"type": "down", "value": 228},
                 {"type": "delay", "value": 200},
                 {"type": "tap", "value": BASIC_CODES["C"]},
                 {"type": "up", "value": 228},
                 {"type": "text", "value": "Hallo Welt!"}]
        self.assertEqual(parse_snippet_lines(format_snippet_lines(steps)), steps)
        compile_snippet({"name": "test", "steps": steps})

    def test_no_extra_text_when_parsing(self):
        with self.assertRaises(ValueError):
            parse_snippet_lines("tap UNKNOWN_ALIEN")
        with self.assertRaises(ValueError):
            parse_snippet_lines("delay junk")


if __name__ == "__main__":
    unittest.main()
