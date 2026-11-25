"""No-network regression tests for independent OmniPad Next editor."""
from __future__ import annotations
import copy
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import LAYER_IDS, ZONE_LEDS, new_project, validate, save_project, load_project
from renderer import Pulse, render


class ModelTests(unittest.TestCase):
    def test_exact_hardware(self):
        self.assertEqual(len(LAYER_IDS), 8)
        self.assertEqual(len(ZONE_LEDS["matrix"]), 30)
        self.assertEqual(len(ZONE_LEDS["frame"]), 43)
        self.assertEqual([len(ZONE_LEDS[z]) for z in
                          ("keys", "slider", "encoder", "k0", "display")],
                         [16, 3, 2, 2, 7])
        self.assertEqual(set(range(30)), set().union(*[
            set(ZONE_LEDS[z]) for z in ("keys", "slider", "encoder", "k0", "display")]))

    def test_fixed_reactive_zones_and_expiry(self):
        p = new_project()
        layer = p["layers"][1]
        for group in ("matrix", "frame"):
            layer["groups"][group]["reactive"].update(enabled=True, duration=400)
        layer["groups"]["matrix"].update(animation="Statisch")
        layer["groups"]["frame"].update(animation="Statisch")
        for trigger, zones in (("Tastendruck", ("keys",)), ("Encoder drehen", ("encoder",)),
                               ("Encoder drücken", ("encoder",)), ("Regler bewegen", ("slider",)),
                               ("Zusatzbutton", ("k0",)), ("Layerwechsel", ("display", "frame"))):
            e = [Pulse(trigger, 1.0, 1)]
            actual = {i for i, led in enumerate(render(p, 1, 1.1, e)) if any(led)}
            expected = {i for zone in zones for i in ZONE_LEDS[zone]}
            self.assertEqual(actual, expected)
            self.assertFalse(any(map(any, render(p, 1, 1.5, e))))
        self.assertFalse(any(map(any, render(p, 1, 1.1, []))))

    def test_reactive_chase_uses_selected_animation_and_palette(self):
        p = new_project()
        p["layers"][1]["groups"]["matrix"]["reactive"].update(enabled=True, palette="Zwei Farben")
        p["layers"][1]["groups"]["matrix"].update(
            animation="Lauflicht", color_a="#FF0000", color_b="#0000FF")
        e = [Pulse("Tastendruck", 1.0, 1)]
        first = render(p, 1, 1.05, e)
        second = render(p, 1, 1.23, e)
        self.assertNotEqual(first, second)
        self.assertTrue(any(led[0] and not led[2] for led in first))
        self.assertTrue(any(led[2] and not led[0] for led in first))

    def test_animated_colors_replace_fixed_color(self):
        p = new_project()
        matrix = p["layers"][1]["groups"]["matrix"]
        matrix.update(animation="Statisch", color_a_mode="Farbwechsel")
        first = render(p, 1, .15, [])[:30]
        self.assertEqual(len(set(first)), 1)
        self.assertNotEqual(first, render(p, 1, .35, [])[:30])
        matrix["color_a_mode"] = "Regenbogen"
        self.assertGreater(len(set(render(p, 1, .35, [])[:30])), 10)

    def test_legacy_offers_fixed_routes_and_retains_original_overrides(self):
        p = new_project()
        layer = p["layers"][1]
        light = layer["groups"]["matrix"]
        light.pop("color_a_mode")
        light["reactive"]["enabled"] = True
        layer["led_overrides"]["25"] = copy.deepcopy(light)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            save_project(p, path)
            updated = load_project(path)["layers"][1]
        self.assertTrue(updated["groups"]["matrix"]["reactive"]["enabled"])
        self.assertFalse(updated["groups"]["frame"]["reactive"]["enabled"])
        self.assertEqual(updated["groups"]["matrix"]["color_a_mode"], "Fest")
        self.assertEqual(updated["led_overrides"], layer["led_overrides"])

    def test_frame_and_matrix_use_independent_triggers(self):
        p = new_project()
        matrix = p["layers"][1]["groups"]["matrix"]
        frame = p["layers"][1]["groups"]["frame"]
        for light in (matrix, frame):
            light.update(animation="Statisch")
        matrix["reactive"].update(enabled=True, triggers=["Regler bewegen"])
        frame["reactive"].update(enabled=True, triggers=["Tastendruck"])
        keys = [Pulse("Tastendruck", 1.0, 1)]
        self.assertFalse(any(map(any, render(p, 1, 1.1, keys)[:30])))
        self.assertTrue(all(map(any, render(p, 1, 1.1, keys)[30:])))
        slider = [Pulse("Regler bewegen", 1.0, 1)]
        result = render(p, 1, 1.1, slider)
        self.assertEqual({i for i, rgb in enumerate(result) if any(rgb)}, set(ZONE_LEDS["slider"]))

    def test_color_brightness_scales_each_channel_to_black(self):
        p = new_project()
        light = p["layers"][1]["groups"]["matrix"]
        light.update(animation="Streifen", brightness=100,
                     color_a="#FF0000", color_b="#0000FF",
                     color_a_brightness=0, color_b_brightness=50)
        self.assertEqual(render(p, 1, 1.1, [])[:4], [(0, 0, 0), (0, 0, 128)] * 2)
        light["color_a_brightness"] = 75
        self.assertEqual(render(p, 1, 1.1, [])[:2], [(191, 0, 0), (0, 0, 128)])

    def test_migrates_shared_reaction_to_separate_groups(self):
        p = new_project()
        layer = p["layers"][1]
        layer["reaction"] = {**layer["groups"]["matrix"]["reactive"], "enabled": True, "palette": "Bunt"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shared.json"
            save_project(p, path)
            migrated = load_project(path)["layers"][1]
        self.assertEqual(migrated["groups"]["frame"]["reactive"]["triggers"], ["Layerwechsel"])
        self.assertTrue(migrated["groups"]["matrix"]["reactive"]["enabled"])
        self.assertNotIn("reaction", migrated)

    def test_round_trip_and_protected_system(self):
        p = new_project()
        p["layers"][1]["actions"]["K1"]["2×"] = "Kopieren"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            save_project(p, path)
            self.assertEqual(load_project(path), p)
        p["layers"][1]["actions"]["Encoder lang"] = {"1×": "Enter"}
        with self.assertRaisesRegex(ValueError, "Systemgesten"):
            validate(p)


class GuiTests(unittest.TestCase):
    def test_all_four_pages_controls_and_save(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.geometry("1240x820+4000+4000")
        from app import App, CARD, KEY_FLASH, TEXT
        from device import DeviceInfo
        from protocol import LiveInputs
        editor = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with patch("app.PROJECT_FILE", Path(tmp) / "empty.json"):
                    editor = App(root)
            root.update()
            self.assertEqual(len(editor.render_items), 73)
            self.assertEqual(set(editor.nav_buttons), {"Gerät", "LEDs", "Belegung", "Display"})
            editor.reaction_vars["enabled"].set(True)
            editor.reaction_vars["palette"].set("Zwei Farben")
            editor.light_vars["speed"].set(0)
            matrix = editor.project["layers"][1]["groups"]["matrix"]
            self.assertTrue(matrix["reactive"]["enabled"])
            editor.trigger_vars["Tastendruck"].set(False)
            self.assertNotIn("Tastendruck", matrix["reactive"]["triggers"])
            editor.simulate("Tastendruck")
            self.assertEqual(editor.events[-1].trigger, "Tastendruck")
            self.assertEqual(len(editor.zone_option["values"]), 2)
            editor.zone_option.current(1)
            editor.change_zone()
            editor.light_vars["brightness"].set(19)
            editor.light_vars["color_b_mode"].set("Regenbogen")
            frame = editor.project["layers"][1]["groups"]["frame"]
            self.assertEqual(frame["brightness"], 19)
            self.assertEqual(frame["color_b_mode"], "Regenbogen")
            self.assertFalse(editor.reaction_vars["enabled"].get())
            self.assertEqual(editor.reaction_vars["palette"].get(), "Eine Farbe")
            editor.trigger_vars["Tastendruck"].set(True)
            self.assertIn("Tastendruck", frame["reactive"]["triggers"])
            self.assertNotIn("Tastendruck", matrix["reactive"]["triggers"])
            editor.light_vars["color_a_brightness"].set(0)
            self.assertEqual(frame["color_a_brightness"], 0)
            self.assertEqual(matrix["color_a_brightness"], 100)
            from app import ScrollFrame
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            root.geometry("1000x680+4000+4000")
            root.update()
            animation, reaction = [w for w in descendants(editor.content) if isinstance(w, ScrollFrame)]
            notebook = animation.master
            animation_control = next(w for w in descendants(animation.body)
                                     if isinstance(w, tk.ttk.Combobox))
            before = animation.canvas.yview()[0]
            animation_control.event_generate("<MouseWheel>", delta=-120)
            root.update()
            self.assertGreater(animation.canvas.yview()[0], before)
            notebook.select(reaction)
            root.update()
            last_trigger = next(w for w in descendants(reaction.body)
                                if isinstance(w, tk.ttk.Checkbutton) and w.cget("text") == "Layerwechsel")
            self.assertTrue(last_trigger.winfo_viewable())
            self.assertLessEqual(last_trigger.winfo_rooty() + last_trigger.winfo_height(),
                                 reaction.canvas.winfo_rooty() + reaction.canvas.winfo_height())
            self.assertFalse(editor.project["layers"][1]["led_overrides"])

            editor.show("Belegung")
            editor.update_live_inputs(DeviceInfo("Verbunden", inputs=LiveInputs(4, 2, 1, 1, True)), 1)
            editor.update_key_highlights(1)
            self.assertEqual(editor.key_buttons["K2"].cget("bg"), KEY_FLASH)
            self.assertEqual(editor.key_buttons["K3"].cget("bg"), KEY_FLASH)
            editor.update_key_highlights(1.2)
            self.assertEqual(editor.key_buttons["K2"].cget("bg"), CARD)
            self.assertEqual(editor.key_buttons["K3"].cget("bg"), KEY_FLASH)
            editor.select_key("K1")
            editor.select_gesture("2×")
            editor.key_action.set("Kopieren")
            editor.write_action()
            self.assertEqual(editor.project["layers"][1]["actions"]["K1"]["2×"], "Kopieren")
            editor.select_key("K0")
            self.assertNotIn("K0", editor.project["layers"][1]["actions"])
            editor.show("Display")
            style = tk.ttk.Style(root)
            for state in (("readonly",), ("readonly", "focus")):
                self.assertEqual(style.lookup("TCombobox", "fieldbackground", state), CARD)
                self.assertEqual(style.lookup("TCombobox", "foreground", state), TEXT)
            popdown = root.tk.call("ttk::combobox::PopdownWindow", editor.svg_choice)
            self.assertEqual(root.tk.call(f"{popdown}.f.l", "cget", "-background"), CARD)
            self.assertGreater(len(editor.svg_paths), 0)
            editor.svg_choice.current(0)
            editor.assign_svg()
            self.assertTrue(editor.project["display_templates"][editor.screen].endswith(".svg"))
            editor.show("Gerät")
            with tempfile.TemporaryDirectory() as tmp:
                editor.path = Path(tmp) / "test.json"
                self.assertTrue(editor.save())
                self.assertEqual(load_project(editor.path), editor.project)
            root.update()
        finally:
            if editor:
                editor.dirty = False
                editor.close()
            else:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
