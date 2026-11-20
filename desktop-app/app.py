"""OmniPad configuration, lighting, macro library and screen editor."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

from profile import (
    ROOT, USER_DATA, BASIC_CODES, MAX_LAYERS, MAX_SNIPPETS, MACRO_POOL_SIZE, MATRIX,
    MODES, EFFECTS, SLIDER_MODES, atomic_json, compile_snippet, decode_profile,
    default_profile, encode_profile, key_config, label_for_code, layer_config,
)
from screen_editor import ScreenEditor
from led_layout import (LED_COUNT, MAIN_COUNT, LED_LAYOUT_PATH, default_positions,
                        read_positions, write_positions, to_canvas, from_canvas, square_bounds)
from tester import Tester
from ui_helpers import BG, PANEL, KEY, TEXT, MUTED, ACCENT, Form, ScrollPanel, button, label, style
from via import OmniPad, ViaError, UnsupportedCommand


class Editor:
    def __init__(self, window):
        self.window = window
        window.title("OmniPad Editor")
        window.geometry("1240x820")
        window.minsize(1080, 720)
        style(window)
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.tasks = {}
        self.polling = False
        self.device = None
        self.capabilities = None
        self.generation = None
        self.detection = None
        self.has_detection = False
        self.closing = False
        self.progress = queue.SimpleQueue()
        self.history, self.future = [], []
        self.layer, self.target, self.action_slot = 0, ("key", 0), 0
        self.clipboard = None
        self.snippet_selection = 0
        self.autosave_id = None
        self.on_device = None
        self.active_profile = None
        self.preview_phase = 0
        self.led_selected = None
        self.led_drag_start = None
        self.led_drag_changed = False
        self.led_undo = []
        try:
            self.led_positions = read_positions()
            self.led_layout_warning = None
        except (OSError, ValueError) as error:
            self.led_positions = default_positions()
            self.led_layout_warning = str(error)
        self.profile = default_profile()
        self.disk_draft = False
        draft = USER_DATA / "draft.omnipad.json"
        if draft.exists():
            try:
                loaded = json.loads(draft.read_text(encoding="utf-8"))
                encode_profile(loaded)
                self.profile, self.disk_draft = loaded, True
            except (OSError, KeyError, TypeError, ValueError):
                pass
        self.keys = json.loads((ROOT / "keyboards/icst7789v/keyboard.json").read_text())[
            "layouts"]["LAYOUT"]["layout"]

        toolbar = tk.Frame(window, bg=BG)
        toolbar.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(toolbar, text="OmniPad", bg=BG, fg=TEXT, font=("Segoe UI", 24, "bold")).pack(side="left", padx=(0, 16))
        self.undo_button = button(toolbar, "↶", self.undo)
        self.undo_button.pack(side="left", padx=3)
        self.redo_button = button(toolbar, "↷", self.redo)
        self.redo_button.pack(side="left", padx=3)
        button(toolbar, "Import", self.import_profile).pack(side="left", padx=(12, 3))
        button(toolbar, "Export", self.export_profile).pack(side="left", padx=3)
        self.write_button = button(toolbar, "Auf Pad speichern", self.write_profile)
        self.write_button.pack(side="right", padx=(6, 0))
        self.connect_button = button(toolbar, "Verbinden", self.connect)
        self.connect_button.pack(side="right", padx=3)
        button(toolbar, "Vom Pad laden", lambda: self.connect(replace=True)).pack(side="right", padx=3)
        button(toolbar, "VIA-Sicherung", self.backup).pack(side="right", padx=3)
        self.status = tk.StringVar(value="Profil wird vorbereitet …")
        tk.Label(window, textvariable=self.status, bg=BG, fg=MUTED, anchor="w").pack(fill="x", padx=22)
        self.layer_bar = tk.Frame(window, bg=BG)
        self.layer_bar.pack(fill="x", padx=20, pady=(14, 8))
        self.layer_tabs = tk.Frame(self.layer_bar, bg=BG)
        self.layer_tabs.pack(side="left", fill="x", expand=True)
        button(self.layer_bar, "+ Layer", self.add_layer).pack(side="right")
        self.notebook = ttk.Notebook(window)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 18))
        self.key_page = tk.Frame(self.notebook, bg=BG)
        self.light_page = tk.Frame(self.notebook, bg=BG)
        self.snippet_page = tk.Frame(self.notebook, bg=BG)
        self.detect_page = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.key_page, text="Tasten & Regler")
        self.notebook.add(self.light_page, text="Beleuchtung")
        self.notebook.add(self.snippet_page, text="Snippet-Bibliothek")
        self.screen_page = ScreenEditor(self.notebook, self)
        self.notebook.add(self.screen_page, text="Display-Studio")
        self.notebook.add(self.detect_page, text="Erkennung")
        self.tester_page = Tester(self.notebook, self)
        self.notebook.add(self.tester_page, text="Tester")
        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self.refresh_selected_page())
        self.create_keys()
        self.create_lighting()
        self.create_snippets()
        self.create_detection()
        self.refresh()
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(100, self.tick)
        window.after(180, self.connect)

    @property
    def current_layer(self):
        return self.profile["layers"][self.layer]

    def busy(self):
        return any(not polling for _, polling in self.tasks.values())

    def submit(self, task, callback, *, polling=False):
        if self.closing:
            return
        future = self.worker.submit(task)
        self.tasks[future] = callback, polling
        if polling:
            self.polling = True
        self.refresh_buttons()

    def tick(self):
        while not self.progress.empty():
            done, size = self.progress.get()
            self.status.set(f"Profil wird übertragen · {round(done * 100 / size)} %")
        for future in list(self.tasks):
            if not future.done():
                continue
            callback, polling = self.tasks.pop(future)
            if polling:
                self.polling = False
            try:
                result = future.result()
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                self.status.set(str(error))
                if isinstance(error, OSError) or (polling and not isinstance(error, UnsupportedCommand)):
                    if self.device:
                        self.device.close()
                    self.device = None
                    self.has_detection = False
                    self.detection = None
                if isinstance(error, UnsupportedCommand) and polling:
                    self.has_detection = False
                if not polling and hasattr(self, "tester_page"):
                    self.tester_page.pending = False
                if not polling and not (isinstance(error, ViaError) and self.device is None):
                    messagebox.showerror("OmniPad", str(error), parent=self.window)
            else:
                try:
                    callback(result)
                except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                    self.status.set(str(error))
                    messagebox.showerror("OmniPad", str(error), parent=self.window)
            self.refresh_buttons()
        if not self.closing and self.device and self.has_detection and not self.polling and not self.busy():
            pad = self.device
            testing = self.tester_page.active

            def read_signals():
                detection = pad.detection()
                return detection, pad.tester_report() if testing else None

            self.submit(read_signals, self.receive_signals, polling=True)
        if not self.closing or self.tasks:
            self.window.after(100, self.tick)

    def receive_signals(self, result):
        detection, report = result
        self.detected(detection)
        if report is not None:
            self.tester_page.report(detection, report)

    def connect(self, replace=False):
        if self.busy():
            return
        if replace and self.dirty() and not messagebox.askyesno(
                "Profil vom Pad laden", "Den aktuellen Entwurf durch die Einstellungen des Pads ersetzen?",
                parent=self.window):
            return
        previous = self.device
        was_testing = self.tester_page.active
        self.tester_page.active = False
        self.device = None
        self.has_detection = False
        self.status.set("USB-Verbindung wird geprüft …")
        metadata = deepcopy(self.profile)
        def read():
            if previous:
                try:
                    if was_testing:
                        previous.diagnose(False)
                except (OSError, RuntimeError):
                    pass
                finally:
                    previous.close()
            pad = OmniPad.connect()
            try:
                caps = pad.capabilities()
                raw = pad.read_profile() if caps and caps["enabled"] else None
                snapshot = pad.snapshot()
                try:
                    detection = pad.detection()
                except UnsupportedCommand:
                    detection = None
                return pad, caps, raw, snapshot, detection
            except Exception:
                pad.close()
                raise
        def ready(result):
            self.device, self.capabilities, raw, snapshot, detection = result
            self.generation = self.capabilities["generation"] if self.capabilities else None
            self.on_device = raw
            self.active_profile = decode_profile(raw, metadata) if raw else None
            self.detection = detection
            self.has_detection = detection is not None
            atomic_json(USER_DATA / "backups" / f"via-{datetime.now():%Y%m%d-%H%M%S}.json", snapshot)
            if replace or not self.disk_draft:
                self.profile = deepcopy(self.active_profile) if raw else default_profile(snapshot)
                self.disk_draft = True
                self.history.clear()
                self.future.clear()
                self.save_draft()
            self.layer = min(self.layer, len(self.profile["layers"]) - 1)
            version = f"Firmware {self.device.firmware}"
            message = f"USB verbunden · {version} · {len(self.profile['layers'])} eingerichtete Layer"
            if not self.capabilities:
                message += " · Erweiterte Funktionen benötigen die neue Firmware"
            self.status.set(message)
            self.refresh()
        self.submit(read, ready)

    def change(self, mutator):
        candidate = deepcopy(self.profile)
        try:
            mutator(candidate)
            encode_profile(candidate)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            messagebox.showerror("Einstellung prüfen", str(error), parent=self.window)
            return False
        if candidate == self.profile:
            return True
        self.history.append(deepcopy(self.profile))
        self.history = self.history[-100:]
        self.future.clear()
        self.profile = candidate
        self.layer = min(self.layer, len(candidate["layers"]) - 1)
        self.save_draft()
        self.refresh()
        self.status.set("Entwurf gespeichert · Mit „Auf Pad speichern“ übertragen")
        return True

    def save_draft(self):
        if self.autosave_id:
            self.window.after_cancel(self.autosave_id)
        self.autosave_id = self.window.after(500, self._save_draft)

    def _save_draft(self):
        self.autosave_id = None
        try:
            atomic_json(USER_DATA / "draft.omnipad.json", self.profile)
        except OSError as error:
            self.status.set(f"Entwurf konnte nicht gespeichert werden · {error}")

    def dirty(self):
        try:
            return encode_profile(self.profile) != self.on_device
        except (ValueError, KeyError, TypeError):
            return True

    def undo(self):
        if self.history:
            self.future.append(deepcopy(self.profile))
            self.profile = self.history.pop()
            self.layer = min(self.layer, len(self.profile["layers"]) - 1)
            self.save_draft()
            self.refresh()

    def redo(self):
        if self.future:
            self.history.append(deepcopy(self.profile))
            self.profile = self.future.pop()
            self.save_draft()
            self.refresh()

    def refresh_buttons(self):
        if not hasattr(self, "write_button"):
            return
        self.undo_button.configure(state="normal" if self.history else "disabled")
        self.redo_button.configure(state="normal" if self.future else "disabled")
        self.connect_button.configure(state="disabled" if self.busy() else "normal",
                                      text="Neu verbinden" if self.device else "Verbinden")
        testing = hasattr(self, "tester_page") and self.tester_page.active
        self.write_button.configure(state="normal" if self.device and not self.busy() and not testing else "disabled")
        if hasattr(self, "tester_page"):
            self.tester_page.refresh()

    def refresh(self):
        if not hasattr(self, "key_canvas"):
            return
        self.refresh_layers()
        self.refresh_key_form()
        self.refresh_actions()
        self.draw_keys()
        self.refresh_light_form()
        self.refresh_snippets()
        self.screen_page.refresh()
        self.draw_light_preview()
        self.refresh_buttons()

    def refresh_selected_page(self):
        if hasattr(self, "key_canvas"):
            self.draw_keys()
            self.screen_page.draw()
            self.draw_light_preview()

    def refresh_layers(self):
        for widget in self.layer_tabs.winfo_children():
            widget.destroy()
        active = self.detection.active_layer if self.detection else None
        for index, layer in enumerate(self.profile["layers"]):
            text = layer["name"]
            if index == active:
                text = "● " + text
            tab = tk.Button(self.layer_tabs, text=text, relief="flat", padx=8, pady=6,
                            bg=layer["color"] if index == self.layer else KEY,
                            fg=BG if index == self.layer else layer["color"],
                            activebackground=layer["color"], command=lambda i=index: self.select_layer(i))
            tab.pack(side="left", padx=(0, 4))
            tab.bind("<Button-3>", lambda event, i=index: self.layer_menu(event, i))

    def select_layer(self, index):
        self.layer = index
        self.refresh_layers()
        self.refresh_key_form()
        self.draw_keys()
        self.refresh_light_form()
        self.refresh_actions()
        self.screen_page.refresh()
        self.draw_light_preview()

    def layer_menu(self, event, index):
        self.layer = index
        self.select_layer(index)
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label="Umbenennen", command=self.rename_layer)
        menu.add_command(label="Farbmarkierung wählen", command=self.color_layer)
        menu.add_command(label="Duplizieren", command=lambda: self.add_layer(copy=True))
        menu.add_command(label="Als Startlayer festlegen",
                         command=lambda: self.change(lambda p: p.__setitem__("default_layer", index)))
        menu.tk_popup(event.x_root, event.y_root)

    def rename_layer(self):
        text = simpledialog.askstring("Layername", "Name", initialvalue=self.current_layer["name"], parent=self.window)
        if text:
            self.change(lambda p: p["layers"][self.layer].__setitem__("name", text))

    def color_layer(self):
        color = colorchooser.askcolor(self.current_layer["color"], parent=self.window)[1]
        if color:
            self.change(lambda p: p["layers"][self.layer].__setitem__("color", color))

    def add_layer(self, copy=False):
        if len(self.profile["layers"]) >= MAX_LAYERS:
            messagebox.showinfo("Layer", f"Diese Firmware unterstützt {MAX_LAYERS} Layer.", parent=self.window)
            return
        value = deepcopy(self.current_layer) if copy else layer_config(len(self.profile["layers"]))
        value["name"] = f"{value['name']} Kopie" if copy else value["name"]
        self.layer = len(self.profile["layers"])
        if not self.change(lambda p: p["layers"].append(value)):
            self.layer -= 1

    def create_keys(self):
        workspace = tk.Frame(self.key_page, bg=BG)
        workspace.pack(fill="both", expand=True, pady=(8, 0))
        left = tk.Frame(workspace, bg=PANEL)
        left.pack(side="left", fill="both", expand=True)
        self.key_canvas = tk.Canvas(left, bg=PANEL, height=380, highlightthickness=0)
        self.key_canvas.pack(fill="both", expand=True)
        self.key_canvas.bind("<Configure>", lambda _: self.draw_keys())
        self.key_canvas.bind("<Button-1>", self.select_at)
        self.key_canvas.bind("<Button-3>", self.context_key)
        self.key_rectangles = {}
        self.key_live = tk.StringVar(value="Regler GP28 · Live-Wert erscheint nach Verbindung mit der neuen Firmware")
        label(left, textvariable=self.key_live, color=MUTED, wraplength=660).pack(
            fill="x", padx=18, pady=(0, 14))
        side = ttk.Notebook(workspace, width=320)
        side.pack(side="right", fill="y", padx=(12, 0))
        palette = tk.Frame(side, bg=PANEL)
        self.key_settings = ScrollPanel(side, 320)
        side.add(palette, text="Aktionen")
        side.add(self.key_settings, text="Taste / Regler")
        self.key_side = side
        label(palette, "Suchen und auf eine Taste ziehen", 10, color=MUTED).pack(anchor="w", padx=10, pady=10)
        self.search = tk.StringVar()
        search = ttk.Entry(palette, textvariable=self.search)
        search.pack(fill="x", padx=10, pady=(0, 4))
        search.insert(0, "")
        self.search.trace_add("write", lambda *_: self.refresh_actions())
        self.actions = tk.Listbox(palette, height=7, bg=KEY, fg=TEXT, selectbackground="#73503d",
                                   exportselection=False, relief="flat", highlightthickness=0)
        self.actions.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.actions.bind("<Double-Button-1>", lambda _: self.choose_action())
        self.actions.bind("<ButtonRelease-1>", self.drop_action)

    def refresh_key_form(self):
        self.key_settings.clear()
        form = self.key_form = Form(self.key_settings.content)
        kind, index = self.target
        if kind == "key":
            key = self.current_layer["keys"][index]
            form.title(self.key_name(index))
            form.entry("label", "Displaytext", key["label"])
            form.choice("mode", "Verhalten", key["mode"], MODES)
            form.entry("term", "Tap-Dance-Zeitfenster in ms", key["term"], kind=int)
            names = ["Einzeltipp", "Doppeltipp", "Dreifachtipp", "Vierfachtipp", "Halten"]
            if key["mode"] == 2:
                names = ["Schritt 1", "Schritt 2", "Schritt 3", "Schritt 4", "Halten (bei Tap Dance)"]
            self.action_destination = form.choice("destination", "Ziel für die Aktionsauswahl", self.action_slot, names)
            self.action_destination.trace_add("write", lambda *_: self.set_action_slot(names))
            for number, name in enumerate(names):
                form.entry(f"code{number}", f"{name} · {label_for_code(key['codes'][number])}",
                           f"0x{key['codes'][number]:04X}", kind="code")
            form.note("Direkt reagiert beim Drücken. Tap Dance wartet auf weitere Tipps. "
                      "Durchschalten wählt bei jedem Druck die nächste der vier Aktionen.")
            if index == 11:
                form.note("Ohne Aktion steuert K0 das Modul wie bisher. Zwei Sekunden halten öffnet immer das Modulmenü.")
        elif kind == "encoder":
            form.title("Encoder links" if index == 0 else "Encoder rechts")
            form.entry("code", "Aktion", f"0x{self.current_layer['encoders'][index]:04X}", kind="code")
            form.note("Die Belegung wirkt im Encoder-Modus. Im Display-Modus wählt die Drehung den Layer.")
        else:
            slider = self.current_layer["slider"]
            form.title("Schieberegler · GPIO28")
            form.choice("mode", "Aktion", slider["mode"], SLIDER_MODES)
            form.check("reverse", "Richtung umkehren", slider["reverse"])
            form.entry("min", "Kalibrierung Minimum (ADC)", slider["min"], kind=int)
            form.entry("max", "Kalibrierung Maximum (ADC)", slider["max"], kind=int)
            form.entry("deadband", "Totzone gegen Zittern (0–64)", slider["deadband"], kind=int)
            form.entry("step", "Abstand pro Tastenschritt (1–255)", slider["step"], kind=int)
            form.entry("low", "Aktion abwärts", f"0x{slider['low']:04X}", kind="code")
            form.entry("high", "Aktion aufwärts", f"0x{slider['high']:04X}", kind="code")
            for caption, mode, low, high in (("Zoom", 1, 0x0156, 0x0157),
                                            ("Lautstärke", 1, 0xAA, 0xA9),
                                            ("Mausrad", 1, 0xDB, 0xDA)):
                button(form.parent, caption, lambda m=mode, lo=low, hi=high:
                       self.change(lambda p: p["layers"][self.layer]["slider"].update(mode=m, low=lo, high=hi))).pack(
                           fill="x", padx=14, pady=3)
            button(form.parent, "Live-Wert als Minimum", lambda: self.calibrate("min")).pack(fill="x", padx=14, pady=3)
            button(form.parent, "Live-Wert als Maximum", lambda: self.calibrate("max")).pack(fill="x", padx=14, pady=3)
        form.apply(self.apply_key_form)

    def set_action_slot(self, choices):
        self.action_slot = choices.index(self.action_destination.get())

    def apply_key_form(self):
        try:
            values = self.key_form.values()
            kind, index = self.target
            if kind == "key":
                key = {"label": values["label"], "mode": values["mode"], "term": values["term"],
                       "codes": [values[f"code{n}"] for n in range(5)]}
                self.change(lambda p: p["layers"][self.layer]["keys"].__setitem__(index, key))
            elif kind == "encoder":
                self.change(lambda p: p["layers"][self.layer]["encoders"].__setitem__(index, values["code"]))
            else:
                self.change(lambda p: p["layers"][self.layer]["slider"].update(values))
        except ValueError as error:
            messagebox.showerror("Einstellung prüfen", str(error), parent=self.window)

    def calibrate(self, endpoint):
        if not self.detection or self.detection.slider_raw is None:
            messagebox.showinfo("Kalibrierung", "Für die Kalibrierung wird ein Live-Wert des Pads benötigt.", parent=self.window)
            return
        self.change(lambda p: p["layers"][self.layer]["slider"].__setitem__(endpoint, self.detection.slider_raw))

    @staticmethod
    def key_name(index):
        return f"K{index + 1}" if index < 10 else ("Encoder-Druck" if index == 10 else "K0")

    def draw_keys(self):
        if not hasattr(self, "key_canvas"):
            return
        canvas = self.key_canvas
        canvas.delete("all")
        self.key_rectangles.clear()
        width = max(560, canvas.winfo_width())
        step = min(122, (width - 155) / 4)
        for index, key in enumerate(self.keys):
            x, y = 20 + key["x"] * step, 24 + key["y"] * 79
            self.draw_key(("key", index), x, y, key.get("w", 1) * step - 8,
                          key.get("h", 1) * 79 - 8, self.key_name(index),
                          self.current_layer["keys"][index]["label"], index)
        x = 20 + 4 * step + 12
        for index, title in ((11, "K0"), (10, "Druck")):
            y = 24 if index == 11 else 83
            self.draw_key(("key", index), x, y, 98, 51, title,
                          self.current_layer["keys"][index]["label"], index)
        for direction, title in enumerate(("↶ Links", "↷ Rechts")):
            self.draw_key(("encoder", direction), x, 142 + direction * 59, 98, 51,
                          title, label_for_code(self.current_layer["encoders"][direction]))
        slider_y = 24 + 3 * 79 + 16
        self.draw_key(("slider", 0), 20, slider_y, width - 48, 54, "Schieberegler · GP28",
                      SLIDER_MODES[self.current_layer["slider"]["mode"]])
        if self.detection and self.detection.slider_percent is not None:
            value = self.detection.slider_percent
            canvas.create_rectangle(30, slider_y + 45, 30 + (width - 68) * value / 100,
                                     slider_y + 49, fill=ACCENT, outline="")

    def draw_key(self, target, x, y, width, height, title, detail, physical=None):
        down = physical is not None and self.detection and self.detection.mask & (1 << physical)
        self.key_rectangles[target] = (x, y, x + width, y + height)
        canvas = self.key_canvas
        canvas.create_rectangle(x, y, x + width, y + height,
                                 fill="#2e6656" if down else KEY, width=2,
                                 outline=ACCENT if target == self.target else "#424e5c")
        canvas.create_text(x + 8, y + 7, text=title, fill=MUTED, anchor="nw", font=("Segoe UI", 9))
        max_chars = max(5, int(width / 7))
        canvas.create_text(x + 8, y + height - 8, text=detail[:max_chars], fill=TEXT,
                            anchor="sw", font=("Segoe UI", 10, "bold"))

    def target_at(self, x, y):
        return next((target for target, (left, top, right, bottom) in self.key_rectangles.items()
                     if left <= x <= right and top <= y <= bottom), None)

    def select_target(self, target):
        self.target = target
        self.action_slot = 0
        self.refresh_key_form()
        if target[0] == "slider":
            self.key_side.select(self.key_settings)
        self.draw_keys()

    def select_at(self, event):
        target = self.target_at(event.x, event.y)
        if target:
            self.select_target(target)

    def context_key(self, event):
        target = self.target_at(event.x, event.y)
        if not target:
            return
        self.select_target(target)
        menu = tk.Menu(self.window, tearoff=False)
        if target[0] == "key":
            menu.add_command(label="Displaytext bearbeiten", command=self.focus_label)
            menu.add_command(label="Im Display-Studio anzeigen", command=self.display_key)
            menu.add_command(label="Belegung kopieren", command=lambda: self.copy_key())
            if self.clipboard:
                menu.add_command(label="Belegung einfügen", command=self.paste_key)
            menu.add_command(label="Auf anderen Layer kopieren", command=self.copy_key_layer)
        menu.add_command(label="Erkennung öffnen", command=lambda: self.notebook.select(self.detect_page))
        menu.tk_popup(event.x_root, event.y_root)

    def focus_label(self):
        self.key_side.select(self.key_settings)
        widget = self.key_form.widgets["label"]
        widget.focus_set()
        widget.selection_range(0, "end")

    def copy_key(self):
        self.clipboard = deepcopy(self.current_layer["keys"][self.target[1]])

    def paste_key(self):
        if self.clipboard and self.target[0] == "key":
            self.change(lambda p: p["layers"][self.layer]["keys"].__setitem__(self.target[1], deepcopy(self.clipboard)))

    def copy_key_layer(self):
        target = simpledialog.askinteger("Belegung kopieren", "Ziel-Layernummer (1–12)",
                                         minvalue=1, maxvalue=len(self.profile["layers"]), parent=self.window)
        if target:
            value = deepcopy(self.current_layer["keys"][self.target[1]])
            self.change(lambda p: p["layers"][target - 1]["keys"].__setitem__(self.target[1], value))

    def display_key(self):
        self.notebook.select(self.screen_page)
        self.screen_page.add(1, binding=2, key=self.target[1])

    def refresh_actions(self):
        if not hasattr(self, "actions"):
            return
        query = self.search.get().casefold()
        entries = list(BASIC_CODES.items())
        for index, layer in enumerate(self.profile["layers"]):
            entries.extend([(f"Layer {index + 1} · {layer['name']} wechseln", 0x5200 + index),
                            (f"Layer {index + 1} · {layer['name']} halten", 0x5220 + index),
                            (f"Layer {index + 1} · {layer['name']} umschalten", 0x5260 + index)])
        entries.extend((f"Snippet · {item['name']}", 0x7700 + index) for index, item in enumerate(self.profile["snippets"]))
        self.action_entries = [(name, code) for name, code in entries if query in name.casefold() or query in f"0x{code:04x}"]
        self.actions.delete(0, "end")
        for name, code in self.action_entries:
            self.actions.insert("end", f"{name}   ·   0x{code:04X}")

    def choose_action(self, target=None):
        selected = self.actions.curselection()
        if not selected:
            return
        code = self.action_entries[selected[0]][1]
        kind, index = target or self.target
        if kind == "key":
            slot = self.action_slot
            self.change(lambda p: p["layers"][self.layer]["keys"][index]["codes"].__setitem__(slot, code))
        elif kind == "encoder":
            self.change(lambda p: p["layers"][self.layer]["encoders"].__setitem__(index, code))
        else:
            self.status.set("Die Regleraktionen werden rechts im Regler-Menü eingestellt.")

    def drop_action(self, event):
        x, y = event.x_root - self.key_canvas.winfo_rootx(), event.y_root - self.key_canvas.winfo_rooty()
        target = self.target_at(x, y)
        if target:
            self.target = target
            self.choose_action(target)

    def create_lighting(self):
        left = tk.Frame(self.light_page, bg=PANEL)
        left.pack(side="left", fill="both", expand=True, pady=(8, 0))
        self.light_canvas = tk.Canvas(left, bg=PANEL, highlightthickness=0)
        self.light_canvas.pack(fill="both", expand=True)
        self.light_canvas.bind("<Configure>", lambda _: self.draw_light_preview())
        self.light_canvas.bind("<Button-1>", self.led_button_down)
        self.light_canvas.bind("<B1-Motion>", self.led_drag_move)
        self.light_canvas.bind("<ButtonRelease-1>", self.led_button_up)
        self.light_canvas.bind("<Left>", lambda _: self.nudge_led(-1, 0))
        self.light_canvas.bind("<Right>", lambda _: self.nudge_led(1, 0))
        self.light_canvas.bind("<Up>", lambda _: self.nudge_led(0, -1))
        self.light_canvas.bind("<Down>", lambda _: self.nudge_led(0, 1))
        self.light_canvas.bind("<Shift-Left>", lambda _: self.nudge_led(-5, 0))
        self.light_canvas.bind("<Shift-Right>", lambda _: self.nudge_led(5, 0))
        self.light_canvas.bind("<Shift-Up>", lambda _: self.nudge_led(0, -5))
        self.light_canvas.bind("<Shift-Down>", lambda _: self.nudge_led(0, 5))
        actions = tk.Frame(left, bg=PANEL)
        actions.pack(fill="x", padx=12, pady=(6, 2))
        self.led_show_numbers = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="LED-Nummern", variable=self.led_show_numbers,
                        command=self.draw_light_preview).pack(side="left")
        button(actions, "Anordnung laden", self.import_led_layout).pack(side="left", padx=(9, 0))
        button(actions, "Speichern unter", self.export_led_layout).pack(side="left", padx=(5, 0))
        button(actions, "Rückgängig", self.undo_led_layout).pack(side="left", padx=(5, 0))
        button(actions, "Zurücksetzen", self.reset_led_layout).pack(side="left", padx=(5, 0))
        self.led_status = tk.StringVar(value="LED anklicken und ziehen · Pfeiltasten: 1 px · Shift: 5 px")
        label(left, "", color=MUTED, textvariable=self.led_status).pack(anchor="w", padx=18, pady=(3, 0))
        label(left, "1:1 Vorschau · Main 0–13 · Frame 14–56 · Reihenfolge unverändert",
              color=MUTED).pack(anchor="w", padx=18, pady=(0, 8))
        if self.led_layout_warning:
            self.led_status.set("LED-Layout ungültig – Standardpositionen geladen")
        self.light_settings = ScrollPanel(self.light_page, 320)
        self.light_settings.pack(side="right", fill="y", padx=(12, 0), pady=(8, 0))
        self.zone = 0
        self.window.after(80, self.animate_lights)

    def refresh_light_form(self):
        self.light_settings.clear()
        form = self.light_form = Form(self.light_settings.content)
        form.title("Beleuchtung pro Layer")
        chosen = form.choice("zone", "LED-Gruppe", self.zone, ["Main · 14 LEDs", "Frame · 43 LEDs"])
        chosen.trace_add("write", lambda *_: self.select_zone(chosen))
        zone = self.current_layer["lighting"][self.zone]
        form.check("enabled", "LED-Gruppe einschalten", zone["enabled"])
        form.choice("effect", "Animation", zone["effect"], EFFECTS)
        form.color("color_a", "Farbe A", zone["color_a"])
        form.color("color_b", "Farbe B", zone["color_b"])
        form.entry("brightness", "Helligkeit (0–64)", zone["brightness"], kind=int)
        form.entry("speed", "Geschwindigkeit (0–255)", zone["speed"], kind=int)
        form.check("reverse", "Animationsrichtung umkehren", zone["reverse"])
        form.title("Animationstrigger")
        for bit, caption in ((1, "Tastendruck"), (2, "Encoder · Lauflicht in Drehrichtung"),
                             (4, "Layer-Wechsel"), (8, "Reglerbewegung")):
            form.check(f"trigger{bit}", caption, bool(zone["triggers"] & bit))
        form.entry("duration", "Triggerdauer in 10 ms (1–255)", zone["duration"], kind=int)
        form.apply(self.apply_lighting)
        button(form.parent, "Layerfarbe als Farbe A",
               lambda: self.change(lambda p: p["layers"][self.layer]["lighting"][self.zone].__setitem__(
                   "color_a", p["layers"][self.layer]["color"]))).pack(fill="x", padx=14, pady=4)

    def select_zone(self, variable):
        self.zone = 0 if variable.get().startswith("Main") else 1
        self.refresh_light_form()

    def apply_lighting(self):
        try:
            values = self.light_form.values()
            values.pop("zone")
            values["triggers"] = sum(bit for bit in (1, 2, 4, 8) if values.pop(f"trigger{bit}"))
            self.change(lambda p: p["layers"][self.layer]["lighting"][self.zone].update(values))
        except ValueError as error:
            messagebox.showerror("Beleuchtung", str(error), parent=self.window)

    def animate_lights(self):
        if self.closing:
            return
        self.preview_phase += 1
        if self.notebook.select() == str(self.light_page):
            self.draw_light_preview()
        self.window.after(60, self.animate_lights)

    def update_led_status(self):
        if self.led_selected is None:
            self.led_status.set("LED anklicken und ziehen · Pfeiltasten: 1 px · Shift: 5 px")
            return
        x, y = self.led_positions[self.led_selected]
        group = "Main" if self.led_selected < MAIN_COUNT else "Frame"
        self.led_status.set(
            f"LED {self.led_selected:02d} · {group} · X {x*100:.1f} % / Y {y*100:.1f} %")

    def led_button_down(self, event):
        self.light_canvas.focus_set()
        width = self.light_canvas.winfo_width()
        height = self.light_canvas.winfo_height()
        hits = []
        for index, point in enumerate(self.led_positions):
            x, y = to_canvas(point, width, height)
            distance2 = (event.x-x)**2 + (event.y-y)**2
            limit = 17 if index < MAIN_COUNT else 13
            if distance2 <= limit**2:
                hits.append((distance2, index))
        self.led_selected = min(hits)[1] if hits else None
        self.led_drag_start = deepcopy(self.led_positions) if hits else None
        self.led_drag_changed = False
        self.update_led_status()
        self.draw_light_preview()

    def led_drag_move(self, event):
        if self.led_selected is None or self.led_drag_start is None:
            return
        point = from_canvas(event.x, event.y,
                            self.light_canvas.winfo_width(),
                            self.light_canvas.winfo_height())
        if point != self.led_positions[self.led_selected]:
            self.led_positions[self.led_selected] = point
            self.led_drag_changed = True
            self.update_led_status()
            self.draw_light_preview()

    def commit_led_positions(self, previous):
        if previous == self.led_positions:
            return
        try:
            write_positions(self.led_positions)
        except (OSError, ValueError) as error:
            self.led_positions = previous
            messagebox.showerror("LED-Anordnung", str(error), parent=self.window)
            self.draw_light_preview()
            self.update_led_status()
            return
        self.led_undo.append(previous)
        self.led_undo = self.led_undo[-50:]
        self.update_led_status()
        self.draw_light_preview()

    def led_button_up(self, _):
        previous = self.led_drag_start
        self.led_drag_start = None
        if previous is not None and self.led_drag_changed:
            self.commit_led_positions(previous)
        self.led_drag_changed = False

    def nudge_led(self, dx, dy):
        if self.led_selected is None:
            return
        previous = deepcopy(self.led_positions)
        x, y = to_canvas(self.led_positions[self.led_selected],
                         self.light_canvas.winfo_width(), self.light_canvas.winfo_height())
        self.led_positions[self.led_selected] = from_canvas(
            x + dx, y + dy, self.light_canvas.winfo_width(), self.light_canvas.winfo_height())
        self.commit_led_positions(previous)

    def undo_led_layout(self):
        if not self.led_undo:
            return
        previous = self.led_undo.pop()
        try:
            write_positions(previous)
        except (OSError, ValueError) as error:
            self.led_undo.append(previous)
            messagebox.showerror("LED-Anordnung", str(error), parent=self.window)
            return
        self.led_positions = previous
        self.update_led_status()
        self.draw_light_preview()

    def reset_led_layout(self):
        if not messagebox.askyesno(
                "LED-Anordnung zurücksetzen",
                "Alle 57 LED-Positionen auf die Ausgangsansicht zurücksetzen?",
                parent=self.window):
            return
        previous = deepcopy(self.led_positions)
        self.led_positions = default_positions()
        self.commit_led_positions(previous)

    def import_led_layout(self):
        path = filedialog.askopenfilename(
            title="LED-Anordnung laden",
            filetypes=[("OmniPad LED-Layout", "*.json")], parent=self.window)
        if not path:
            return
        try:
            positions = read_positions(Path(path))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("LED-Anordnung", str(error), parent=self.window)
            return
        previous = deepcopy(self.led_positions)
        self.led_positions = positions
        self.commit_led_positions(previous)

    def export_led_layout(self):
        path = filedialog.asksaveasfilename(
            title="LED-Anordnung speichern",
            initialfile="omnipad.led-layout.json", defaultextension=".json",
            filetypes=[("OmniPad LED-Layout", "*.json")], parent=self.window)
        if path:
            try:
                write_positions(self.led_positions, Path(path))
            except (OSError, ValueError) as error:
                messagebox.showerror("LED-Anordnung", str(error), parent=self.window)

    def draw_light_preview(self):
        if not hasattr(self, "light_canvas"):
            return
        canvas = self.light_canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        left, top, right, bottom = square_bounds(width, height)
        canvas.create_rectangle(left, top, right, bottom,
                                fill="#192028", outline="#3c4855", width=2)
        for zone_index, count in ((0, 14), (1, 43)):
            zone = self.current_layer["lighting"][zone_index]
            for index in range(count):
                phase = self.preview_phase * (zone["speed"] + 16) / 200
                position = count - 1 - index if zone["reverse"] else index
                blend, level = 0, zone["brightness"] / 64
                effect = zone["effect"]
                if effect == 1:
                    blend = index % 2
                elif effect == 2:
                    blend = int(index >= count // 2)
                elif effect == 3:
                    blend = position / (count - 1)
                elif effect == 4:
                    blend = int((position + int(phase)) % count >= 4)
                elif effect == 5:
                    wave = phase % 256
                    level *= (32 + (wave * 2 if wave < 128 else (255 - wave) * 2) * 7 / 8) / 255
                elif effect == 6:
                    distance = (position + count - int(phase) % count) % count
                    level *= (8 - distance) / 8 if distance < 8 else 1 / 16
                elif effect == 7:
                    blend = int((position * 37 + int(phase) * 13) % 97 < 8)
                a, b = zone["color_a"], zone["color_b"]
                rgb = [round((int(a[i:i + 2], 16) * (1 - blend) + int(b[i:i + 2], 16) * blend) * level)
                       for i in (1, 3, 5)]
                if effect == 8:
                    import colorsys
                    rgb = [round(channel * level * 255) for channel in colorsys.hsv_to_rgb(
                        (position / count + phase / 255) % 1, 1, 1)]
                color = "#" + "".join(f"{max(0, min(255, channel)):02x}" for channel in rgb) if zone["enabled"] else "#293039"
                led_number = index if zone_index == 0 else MAIN_COUNT + index
                x, y = to_canvas(self.led_positions[led_number], width, height)
                radius = 13 if zone_index == 0 else 9
                selected = led_number == self.led_selected
                canvas.create_oval(
                    x-radius, y-radius, x+radius, y+radius, fill=color,
                    outline=ACCENT if selected else "#50606e",
                    width=3 if selected else 1, tags=(f"led-{led_number}",))
                if self.led_show_numbers.get():
                    brightness = sum(rgb) if zone["enabled"] else 0
                    ink = "#11171e" if brightness > 380 else "#f0eee9"
                    canvas.create_text(
                        x, y, text=str(led_number), fill=ink,
                        font=("Segoe UI", 8 if zone_index == 0 else 7, "bold"),
                        tags=(f"led-{led_number}",))
        canvas.create_text(width / 2, top + 13, text=self.current_layer["name"], fill=TEXT,
                           font=("Segoe UI", 14, "bold"))

    def create_snippets(self):
        left = tk.Frame(self.snippet_page, bg=PANEL, width=240)
        left.pack(side="left", fill="y", pady=(8, 0))
        left.pack_propagate(False)
        label(left, "Snippets", 14).pack(anchor="w", padx=14, pady=14)
        self.snippet_list = tk.Listbox(left, bg=KEY, fg=TEXT, selectbackground="#73503d",
                                       exportselection=False, relief="flat")
        self.snippet_list.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.snippet_list.bind("<<ListboxSelect>>", self.select_snippet)
        button(left, "+ Snippet", self.add_snippet).pack(fill="x", padx=14, pady=(0, 6))
        button(left, "Duplizieren", self.duplicate_snippet).pack(fill="x", padx=14, pady=(0, 14))
        self.snippet_body = tk.Frame(self.snippet_page, bg=PANEL)
        self.snippet_body.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(8, 0))

    def refresh_snippets(self):
        if not hasattr(self, "snippet_list"):
            return
        self.snippet_list.delete(0, "end")
        snippets = self.profile["snippets"]
        for index, item in enumerate(snippets):
            self.snippet_list.insert("end", f"{index + 1}  {item['name']}")
        for child in self.snippet_body.winfo_children():
            child.destroy()
        if not snippets:
            label(self.snippet_body, "Lege dein erstes Snippet an.", 16).pack(anchor="w", padx=20, pady=20)
            label(self.snippet_body, "Die Einträge stehen anschließend in der Aktionsauswahl zur Verfügung.",
                  color=MUTED).pack(anchor="w", padx=20)
            return
        self.snippet_selection = min(self.snippet_selection, len(snippets) - 1)
        self.snippet_list.selection_set(self.snippet_selection)
        snippet = snippets[self.snippet_selection]
        self.snippet_form = form = Form(self.snippet_body)
        form.title("Snippet bearbeiten")
        self.snippet_name = form.entry("name", "Name", snippet["name"])
        form.note("Ein Schritt pro Zeile. Beispiele stehen unter dem Eingabefeld. "
                  "Text wird für ein deutsches Tastaturlayout übersetzt.")
        self.snippet_steps = tk.Text(self.snippet_body, height=12, bg=KEY, fg=TEXT,
                                     insertbackground=TEXT, relief="flat", undo=True, font=("Consolas", 11))
        self.snippet_steps.pack(fill="both", expand=True, padx=14, pady=(2, 6))
        lines = []
        for step in snippet["steps"]:
            value = str(step["value"]) if step["type"] in ("text", "delay") else label_for_code(step["value"])
            lines.append(f"{step['type']} {value}")
        self.snippet_steps.insert("1.0", "\n".join(lines))
        builder = tk.Frame(self.snippet_body, bg=PANEL)
        builder.pack(fill="x", padx=14, pady=5)
        kind = tk.StringVar(value="text")
        ttk.Combobox(builder, textvariable=kind, state="readonly",
                     values=["text", "tap", "down", "up", "delay"], width=7).pack(side="left")
        value = tk.StringVar()
        ttk.Combobox(builder, textvariable=value, values=list(BASIC_CODES), width=25).pack(
            side="left", fill="x", expand=True, padx=5)
        def append():
            text = value.get()
            if text:
                current = self.snippet_steps.get("1.0", "end-1c")
                self.snippet_steps.insert("end", ("\n" if current and not current.endswith("\n") else "") + kind.get() + " " + text)
                value.set("")
        button(builder, "+ Schritt", append).pack(side="right")
        label(self.snippet_body, "text Hallo Sina!\ntap Kopieren\ndown Strg\n"
              "delay 150   · Pause in ms\nup Strg", 9, color=MUTED).pack(
                  anchor="w", padx=14, pady=6)
        usage = sum(len(compile_snippet(item)) for item in snippets)
        label(self.snippet_body, f"Gerätespeicher für Snippets · {usage} / {MACRO_POOL_SIZE} Byte",
              color=MUTED).pack(anchor="w", padx=14, pady=6)
        form.apply(self.apply_snippet)

    def select_snippet(self, _):
        selected = self.snippet_list.curselection()
        if selected and selected[0] != self.snippet_selection:
            self.snippet_selection = selected[0]
            self.refresh_snippets()

    def add_snippet(self):
        if len(self.profile["snippets"]) >= MAX_SNIPPETS:
            messagebox.showinfo("Snippets", f"Bis zu {MAX_SNIPPETS} Snippets können gespeichert werden.", parent=self.window)
            return
        self.snippet_selection = len(self.profile["snippets"])
        self.change(lambda p: p["snippets"].append({"name": f"Snippet {self.snippet_selection + 1}", "steps": []}))

    def duplicate_snippet(self):
        if not self.profile["snippets"] or len(self.profile["snippets"]) >= MAX_SNIPPETS:
            return
        copied = deepcopy(self.profile["snippets"][self.snippet_selection])
        copied["name"] += " Kopie"
        self.snippet_selection = len(self.profile["snippets"])
        self.change(lambda p: p["snippets"].append(copied))

    def apply_snippet(self):
        try:
            steps = []
            for line in self.snippet_steps.get("1.0", "end-1c").splitlines():
                if not line.strip():
                    continue
                kind, separator, value = line.partition(" ")
                if not separator or kind not in ("text", "tap", "down", "up", "delay"):
                    raise ValueError(f"Ungültiger Schritt · {line}")
                if kind != "text":
                    value = value.strip()
                    value = BASIC_CODES[value] if kind != "delay" and value in BASIC_CODES else int(
                        value, 10 if kind == "delay" else 16)
                steps.append({"type": kind, "value": value})
            snippet = {"name": self.snippet_name.get(), "steps": steps}
            compile_snippet(snippet)
            self.change(lambda p: p["snippets"].__setitem__(self.snippet_selection, snippet))
        except ValueError as error:
            messagebox.showerror("Snippet prüfen", str(error), parent=self.window)

    def create_detection(self):
        actions = tk.Frame(self.detect_page, bg=BG)
        actions.pack(fill="x", pady=10)
        button(actions, "Hardware-Test starten", lambda: self.diagnose(True)).pack(side="left")
        button(actions, "Hardware-Test beenden", lambda: self.diagnose(False)).pack(side="left", padx=8)
        self.detect_text = tk.StringVar(value="OmniPad verbinden, um Eingaben zu erkennen.")
        label(self.detect_page, textvariable=self.detect_text, size=13, wraplength=920).pack(
            anchor="w", fill="x", padx=18, pady=18)
        self.detect_log = tk.Listbox(self.detect_page, bg=PANEL, fg=TEXT, relief="flat", font=("Consolas", 11))
        self.detect_log.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def diagnose(self, enabled):
        if not self.device or not self.capabilities or self.busy():
            self.status.set("Der Hardware-Test in der App benötigt die erweiterte OmniPad-Firmware.")
            return
        self.submit(lambda: self.device.diagnose(enabled),
                    lambda _: self.status.set("Hardware-Test aktiv · Tasten lösen hier keine PC-Aktionen aus"
                                              if enabled else "Hardware-Test beendet"))

    def detected(self, value):
        previous = self.detection
        self.detection = value
        if previous == value:
            return
        if previous is None or previous.active_layer != value.active_layer:
            self.refresh_layers()
        slider = "Regler GP28 · Live-Wert benötigt die erweiterte Firmware"
        if value.slider_raw is not None:
            slider = f"Regler GP28 · {value.slider_percent} % · ADC {value.slider_raw}"
        self.key_live.set(slider)
        text = f"Layer {value.active_layer + 1} · {'Hardware-Test aktiv' if value.enabled else 'Normalbetrieb'}\n{slider}"
        if value.last_key < 12:
            gestures = ["Drücken", "Einzeltipp", "Doppeltipp", "Dreifachtipp", "Vierfachtipp", "Halten"]
            gesture = gestures[min(value.gesture, 5)]
            text += f"\nZuletzt {self.key_name(value.last_key)} · {gesture}"
        sensor_states = ["ADXL deaktiviert", "ADXL wird gesucht", "ADXL erkannt", "ADXL fehlt",
                         "ADXL falsche Kennung", "ADXL I²C-Fehler"]
        text += f"\n{sensor_states[min(value.sensor_status, 5)]} · XYZ {value.sensor_xyz}"
        text += f"\nMatrix über {'PCF8575' if value.expander else 'GPIO'}"
        self.detect_text.set(text)
        events = []
        if previous:
            newly_pressed = value.mask & ~previous.mask
            for index in range(12):
                if newly_pressed & (1 << index):
                    events.append(f"{self.key_name(index)} gedrückt")
            if value.clockwise != previous.clockwise:
                events.append("Encoder rechts")
            if value.counterclockwise != previous.counterclockwise:
                events.append("Encoder links")
            if value.encoder_pushes != previous.encoder_pushes:
                events.append("Encoder-Druck")
            if value.gesture != previous.gesture and value.gesture:
                events.append(f"{self.key_name(value.last_key)} · Geste {value.gesture}")
        for event in events:
            self.detect_log.insert(0, f"{datetime.now():%H:%M:%S}  {event}")
        if self.detect_log.size() > 200:
            self.detect_log.delete(200, "end")
        self.draw_keys()
        if self.notebook.select() == str(self.screen_page):
            self.screen_page.draw()

    def write_profile(self):
        if not self.device or self.busy() or self.tester_page.active:
            return
        if not self.capabilities:
            messagebox.showinfo("Firmware aktualisieren",
                                "Das Pad benötigt die erweiterte Firmware für dieses Profil. "
                                "Dein Entwurf ist lokal gespeichert und kann als Profil exportiert werden.",
                                parent=self.window)
            return
        payload = encode_profile(self.profile)
        captured = deepcopy(self.profile)
        generation = self.generation
        def write():
            atomic_json(USER_DATA / "backups" / f"profile-before-{datetime.now():%Y%m%d-%H%M%S}.json",
                        decode_profile(self.device.read_profile()) if self.capabilities["enabled"] else captured)
            return self.device.write_profile(payload, generation, lambda done, size: self.progress.put((done, size)))
        def saved(capabilities):
            self.capabilities = capabilities
            self.generation = capabilities["generation"]
            self.on_device = payload
            self.active_profile = captured
            atomic_json(USER_DATA / "last-device.omnipad.json", captured)
            self.status.set("Profil auf dem Pad gespeichert und vollständig zurückgelesen")
        self.submit(write, saved)

    def import_profile(self):
        path = filedialog.askopenfilename(filetypes=[("OmniPad / VIA Profil", "*.json")], parent=self.window)
        if not path:
            return
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if value.get("schema") == "omnipad-via-backup":
                value = default_profile(value)
            encode_profile(value)
            self.change(lambda p: (p.clear(), p.update(value)))
        except (OSError, ValueError, KeyError, TypeError) as error:
            messagebox.showerror("Profil importieren", str(error), parent=self.window)

    def export_profile(self):
        path = filedialog.asksaveasfilename(defaultextension=".omnipad.json", initialfile="omnipad.omnipad.json",
                                           filetypes=[("OmniPad Profil", "*.omnipad.json")], parent=self.window)
        if path:
            try:
                atomic_json(path, self.profile)
                self.status.set(f"Profil exportiert · {path}")
            except OSError as error:
                messagebox.showerror("Export", str(error), parent=self.window)

    def backup(self):
        if not self.device or self.busy():
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="omnipad-via-backup.json",
                                           filetypes=[("VIA-Sicherung", "*.json")], parent=self.window)
        if path:
            self.submit(self.device.snapshot, lambda snapshot: self.backup_done(path, snapshot))

    def backup_done(self, path, snapshot):
        atomic_json(path, snapshot)
        self.status.set(f"VIA-Sicherung gespeichert · {path}")

    def close(self):
        self.closing = True
        if self.tasks:
            self.window.after(100, self.close)
            return
        if self.autosave_id:
            self.window.after_cancel(self.autosave_id)
            self._save_draft()
        if self.led_drag_start is not None and self.led_drag_changed:
            self.commit_led_positions(self.led_drag_start)
        if self.device:
            try:
                if self.capabilities and (self.tester_page.active or (self.detection and self.detection.enabled)):
                    self.device.diagnose(False)
            except (OSError, RuntimeError):
                pass
            self.device.close()
        self.worker.shutdown(wait=False)
        self.window.destroy()


def main():
    # Multiple windows would compete for the same USB response stream.
    if __import__("sys").platform == "win32":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.CreateMutexW.restype = ctypes.c_void_p
        instance = kernel.CreateMutexW(None, False, "Local\\OmniPadEditor")
        if kernel.GetLastError() == 183:
            existing = ctypes.windll.user32.FindWindowW(None, "OmniPad Editor")
            if existing:
                ctypes.windll.user32.ShowWindow(existing, 9)
                ctypes.windll.user32.SetForegroundWindow(existing)
            kernel.CloseHandle(ctypes.c_void_p(instance))
            return
    root = tk.Tk()
    Editor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
