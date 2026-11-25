"""OmniPad Next – small standalone Windows editor (Python standard library only)."""
from __future__ import annotations

import copy
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from xml.etree import ElementTree

from device import LiveUsb
from key_actions import (BUILTINS, DEFAULT_ACTION, FUNCTIONS, KEY_MODES, LEGACY_EMPTY,
                         LETTERS, LIBRARY_PREFIX, MEDIA, MOUSE, NAVIGATION, NO_ACTION,
                         NUMBERS, SHORTCUTS)
from library_editor import LibraryEditor
from pad_profile import KEY_NAMES, ROTATION_ACTIONS, SLIDER_ACTIONS, inferred_mode, locked_key
from protocol import prepare_lighting, ProtocolError
from model import (BASE_GROUPS, COLOR_MODES, EFFECTS, GESTURES,
                   LAYER_DATA, LAYER_IDS, NAMES, PROTECTED,
                   REACTION_PALETTES, ROOT, SCREENS, TRIGGERS, load_project,
                   new_project, save_project)
from renderer import Pulse, hexrgb, render

BG = "#111923"
PANEL = "#1A2734"
CARD = "#223344"
TEXT = "#F3F6F8"
MUTED = "#A3B5C4"
ACCENT = "#67B5A9"
KEY_FLASH = "#FFD782"
LIVE_KEYS = (*(f"K{i}" for i in range(1, 11)), "Encoder kurz", "K0")
PROJECT_FILE = ROOT / "omnipad-next" / "data" / "projekt.json"


class ScrollFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=PANEL, **kwargs)
        self.canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0, yscrollincrement=24)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=PANEL, padx=10, pady=12)
        self.window_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self.window_id, width=e.width))
        self.wheel_tag = f"OmniPadWheel{id(self)}"
        self.wheel_callbacks = {
            event: self.bind_class(self.wheel_tag, event, self._scroll)
            for event in ("<MouseWheel>", "<Button-4>", "<Button-5>")
        }

    def _scroll(self, e):
        if e.num in (4, 5):
            self.canvas.yview_scroll(-1 if e.num == 4 else 1, "units")
        elif e.delta:
            step = max(1, abs(e.delta) // 120)
            self.canvas.yview_scroll(-step if e.delta > 0 else step, "units")
        return "break"

    def bind_contents(self):
        widgets = [self]
        while widgets:
            widget = widgets.pop()
            widget.bindtags((self.wheel_tag, *widget.bindtags()))
            widgets.extend(widget.winfo_children())

    def destroy(self):
        for event, callback in self.wheel_callbacks.items():
            self.unbind_class(self.wheel_tag, event)
            self._root().deletecommand(callback)
        super().destroy()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("OmniPad Next · Neuanfang")
        root.geometry("1240x820")
        root.minsize(1000, 680)
        root.configure(bg=BG)
        self.style()
        self.path = PROJECT_FILE
        self.project = load_project(self.path) if self.path.exists() else new_project()
        self.dirty = False
        self.layer = self.project["active_layer"]
        self.view = "LEDs"
        self.zone = "matrix"
        self.led_tab = 0
        self.selected_key = "K1"
        self.selected_gesture = "1×"
        self.selected_entry = None
        self.events: list[Pulse] = []
        self.reaction_hue = 0
        self.started = time.monotonic()
        self.render_items = {}
        self._loading = False
        self.usb = LiveUsb()
        self.usb_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="OmniPad USB")
        self.usb_future = None
        self.usb_busy = False
        self.usb_refresh = False
        self.device_status = tk.StringVar(value="OmniPad wird gesucht …")
        self.live_status = tk.StringVar(value="Warte auf OmniPad …")
        self.pad_layer = None
        self.held_keys = 0
        self.key_flash_until = {}
        self.key_buttons = {}
        self.animation_tick = None
        self.nav_buttons = {}
        self.build_shell()
        self.build_page()
        self.animation_tick = self.root.after(40, self.animate)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=TEXT,
                    arrowcolor=TEXT, selectbackground=ACCENT, selectforeground=BG,
                    padding=6, bordercolor="#526A7A", lightcolor=CARD, darkcolor=CARD)
        s.map("TCombobox", fieldbackground=[("readonly", CARD)],
              foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", CARD)],
              selectforeground=[("readonly", TEXT)])
        for option, color in (("background", CARD), ("foreground", TEXT),
                              ("selectBackground", ACCENT), ("selectForeground", BG)):
            self.root.option_add(f"*TCombobox*Listbox.{option}", color)
        s.configure("TButton", padding=(10, 7), background=CARD, foreground=TEXT)
        s.map("TButton", background=[("active", "#344C5E")])
        s.configure("TCheckbutton", background=PANEL, foreground=TEXT, padding=3)
        s.configure("TRadiobutton", background=PANEL, foreground=TEXT)
        s.configure("TLabel", background=PANEL, foreground=TEXT)
        s.configure("Horizontal.TScale", background=PANEL)
        s.configure("TNotebook", background=PANEL, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD, foreground=TEXT, padding=(12, 7))
        s.map("TNotebook.Tab", background=[("selected", ACCENT)],
              foreground=[("selected", BG)])

    def text(self, parent, value, *, size=11, color=TEXT, bold=False, wrap=0):
        return tk.Label(parent, text=value, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        anchor="w", justify="left", wraplength=wrap)

    def build_shell(self):
        left = tk.Frame(self.root, bg=BG, width=175)
        left.pack(side="left", fill="y", padx=(14, 5), pady=16)
        left.pack_propagate(False)
        self.text(left, "OmniPad", size=19, bold=True).pack(anchor="w", pady=(12, 4))
        self.text(left, "NEXT  /  LOKAL", color=ACCENT, size=9).pack(anchor="w", pady=(0, 30))
        for title in ("Gerät", "LEDs", "Belegung", "Snippets & Makros", "Display"):
            btn = tk.Button(left, text=title, anchor="w", bd=0, relief="flat",
                            font=("Segoe UI", 12), padx=16, pady=13,
                            command=lambda v=title: self.show(v))
            btn.pack(fill="x", pady=3)
            self.nav_buttons[title] = btn
        self.text(left, "Firmware-Keymap\nbleibt unverändert", color=MUTED, size=9).pack(
            side="bottom", anchor="w", pady=12)
        main = tk.Frame(self.root, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=(5, 18), pady=13)
        top = tk.Frame(main, bg=BG)
        top.pack(fill="x", pady=(5, 12))
        self.title = self.text(top, "LEDs", size=19, bold=True)
        self.title.pack(side="left")
        ttk.Button(top, text="Projekt speichern", command=self.save).pack(side="right")
        self.save_status = tk.StringVar(value="Lokaler Entwurf")
        self.text(top, "Nur PC-Projekt · kein EEPROM-Schreiben", color=MUTED, size=9).pack(
            side="right", padx=12)
        self.layer_bar = tk.Frame(main, bg=PANEL, padx=14, pady=11)
        self.layer_bar.pack(fill="x", pady=(0, 12))
        self.text(self.layer_bar, "Layer", color=MUTED).pack(side="left", padx=(0, 10))
        self.layer_choice = ttk.Combobox(
            self.layer_bar, state="readonly", width=23,
            values=[f"{i} · {name}" for i, name in enumerate(LAYER_IDS)])
        self.layer_choice.current(self.layer)
        self.layer_choice.pack(side="left")
        self.layer_choice.bind("<<ComboboxSelected>>", self.select_layer)
        self.status = tk.StringVar(value="Neues Projekt · Änderungen werden lokal gespeichert")
        self.text(self.layer_bar, "", color=MUTED, size=9).pack(side="left", padx=6)
        self.status_label = tk.Label(self.layer_bar, textvariable=self.status, bg=PANEL,
                                     fg=MUTED, font=("Segoe UI", 9))
        self.status_label.pack(side="right")
        self.content = tk.Frame(main, bg=BG)
        self.content.pack(fill="both", expand=True)

    def mark_changed(self):
        self.dirty = True
        self.status.set("Nicht gespeichert")

    def save(self):
        try:
            save_project(self.project, self.path)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Projekt speichern", str(exc), parent=self.root)
            return False
        self.dirty = False
        self.status.set(f"Gespeichert: {self.path.name}")
        return True

    def close(self):
        if self.dirty:
            choice = messagebox.askyesnocancel(
                "Änderungen", "Änderungen vor dem Schließen lokal speichern?",
                parent=self.root)
            if choice is None:
                return
            if choice and not self.save():
                return
        self.root.after_cancel(self.animation_tick)
        self.usb_worker.submit(self.usb.close)
        self.usb_worker.shutdown(wait=False)
        self.root.destroy()

    def show(self, view):
        self.view = view
        self.build_page()

    def select_layer(self, _event=None):
        self.layer = self.layer_choice.current()
        self.project["active_layer"] = self.layer
        self.mark_changed()
        self.simulate("Layerwechsel")
        self.build_page()

    def build_page(self):
        for w in self.content.winfo_children():
            w.destroy()
        self.title.configure(text=self.view)
        for key, btn in self.nav_buttons.items():
            btn.configure(bg=ACCENT if key == self.view else PANEL,
                          fg=BG if key == self.view else TEXT,
                          activebackground="#85CCBD")
        if self.view == "LEDs":
            self.build_led_page()
        elif self.view == "Belegung":
            self.build_keys_page()
        elif self.view == "Snippets & Makros":
            self.build_library_page()
        elif self.view == "Display":
            self.build_display_page()
        else:
            self.build_device_page()

    def card(self, parent, **kwargs):
        return tk.Frame(parent, bg=PANEL, padx=14, pady=14, **kwargs)

    def build_device_page(self):
        box = self.card(self.content)
        box.pack(fill="both", expand=True)
        self.text(box, "Gerätestatus", size=17, bold=True).pack(anchor="w")
        self.text(box, "Die Firmware und ihre Systemgesten werden von dieser App nicht verändert.",
                  color=MUTED, wrap=620).pack(anchor="w", pady=(8, 15))
        self.text(box, "USB / HID", color=ACCENT, bold=True).pack(anchor="w")
        tk.Label(box, textvariable=self.device_status, bg=PANEL, fg=TEXT,
                 justify="left", anchor="w", wraplength=700).pack(fill="x", pady=8)
        ttk.Button(box, text="Verbindung prüfen (nur lesen)", command=self.check_device).pack(
            anchor="w", pady=(0, 24))
        for line in ("Matrix 30 LEDs  ·  Frame 43 LEDs",
                     "Regler  ·  Encoder mit Drucktaster  ·  Zusatzbutton",
                     "Firmware/App-Profil umschalten: nur im Display-Settings-Menü am Pad"):
            self.text(box, line, color=MUTED).pack(anchor="w", pady=4)
        self.text(box, "Projektverwaltung", size=15, bold=True).pack(anchor="w", pady=(28, 8))
        row = tk.Frame(box, bg=PANEL)
        row.pack(anchor="w")
        ttk.Button(row, text="Projekt öffnen", command=self.open_project).pack(side="left", padx=(0, 7))
        ttk.Button(row, text="Speichern unter …", command=self.save_as).pack(side="left")
    def check_device(self):
        self.usb_refresh = True

    def open_project(self):
        file = filedialog.askopenfilename(parent=self.root, filetypes=[("OmniPad-Projekt", "*.json")])
        if not file:
            return
        if self.dirty and not messagebox.askyesno("Entwurf", "Ungespeicherte Änderungen verwerfen?"):
            return
        try:
            project = load_project(Path(file))
        except (ValueError, OSError) as exc:
            messagebox.showerror("Projekt", str(exc))
            return
        self.project, self.path = project, Path(file)
        self.layer = project["active_layer"]
        self.layer_choice.current(self.layer)
        self.dirty = False
        self.build_page()
        self.status.set("Projekt geladen")

    def save_as(self):
        file = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json",
                filetypes=[("OmniPad-Projekt", "*.json")], initialfile="omnipad-projekt.json")
        if file:
            self.path = Path(file)
            self.save()

    def frame_header(self, parent, title, subtitle=""):
        self.text(parent, title, size=14, bold=True).pack(anchor="w", pady=(0, 3))
        if subtitle:
            self.text(parent, subtitle, size=9, color=MUTED, wrap=460).pack(
                anchor="w", pady=(0, 10))

    def build_led_page(self):
        area = tk.Frame(self.content, bg=BG)
        area.pack(fill="both", expand=True)
        area.grid_columnconfigure(0, weight=3, minsize=400)
        area.grid_columnconfigure(1, weight=2, minsize=320)
        area.grid_rowconfigure(0, weight=1)
        preview = self.card(area)
        preview.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.frame_header(preview, "73 LEDs · Live-Vorschau",
                          "30 Matrix-LEDs · 43 Rahmen-LEDs")
        tk.Label(preview, textvariable=self.live_status, bg=PANEL, fg=ACCENT,
                 anchor="w").pack(fill="x", pady=(0, 6))
        self.preview_canvas = tk.Canvas(preview, bg=BG, highlightthickness=0,
                                        height=380)
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_canvas.bind("<Configure>", lambda _: self.draw_led_shapes())
        row = tk.Frame(preview, bg=PANEL)
        row.pack(side="bottom", fill="x", pady=(8, 0), before=self.preview_canvas)
        self.text(row, "Reaktion simulieren:", size=9, color=MUTED).pack(anchor="w")
        buttons = tk.Frame(row, bg=PANEL)
        buttons.pack(fill="x", pady=(5, 0))
        for i, trigger in enumerate(TRIGGERS):
            btn = ttk.Button(buttons, text=trigger,
                             command=lambda v=trigger: self.simulate(v))
            btn.grid(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
            buttons.grid_columnconfigure(i % 3, weight=1)
        right = self.card(area)
        right.grid(row=0, column=1, sticky="nsew")
        self.upload_button = ttk.Button(right, text="LEDs auf Pad speichern",
                                        command=self.upload_lighting,
                                        state="disabled" if self.usb_busy else "normal")
        self.upload_button.pack(fill="x", pady=(0, 10))
        self.text(right, "LED-Bereich", color=MUTED, size=10).pack(anchor="w")
        self.zone_option = ttk.Combobox(right, state="readonly",
                                        values=[NAMES[z] for z in BASE_GROUPS])
        self.zone_option.pack(fill="x", pady=(4, 10))
        self.zone_option.current(BASE_GROUPS.index(self.zone))
        self.zone_option.bind("<<ComboboxSelected>>", self.change_zone)
        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)
        animation_page = ScrollFrame(notebook)
        reaction_page = ScrollFrame(notebook)
        notebook.add(animation_page, text="Animation & Farben")
        notebook.add(reaction_page, text="Reaktion & Trigger")
        notebook.select(self.led_tab)
        notebook.bind("<<NotebookTabChanged>>",
                      lambda _: setattr(self, "led_tab", notebook.index("current")))
        form = animation_page.body
        self.light_vars = {
            "enabled": tk.BooleanVar(),
            "animation": tk.StringVar(),
            "brightness": tk.IntVar(),
            "speed": tk.IntVar(),
            "reverse": tk.BooleanVar(),
            "color_a": tk.StringVar(),
            "color_b": tk.StringVar(),
            "color_a_mode": tk.StringVar(),
            "color_b_mode": tk.StringVar(),
            "color_a_brightness": tk.IntVar(),
            "color_b_brightness": tk.IntVar(),
        }
        v = self.light_vars
        ttk.Checkbutton(form, text="Grundanimation aktiv", variable=v["enabled"]).pack(anchor="w")
        ttk.Combobox(form, state="readonly", textvariable=v["animation"],
                     values=EFFECTS).pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(form, text="Richtung umkehren", variable=v["reverse"]).pack(
            anchor="w", pady=(4, 6))
        for key, title in (("color_a", "Farbe A"), ("color_b", "Farbe B")):
            self.text(form, title, color=MUTED, size=10).pack(anchor="w", pady=(5, 0))
            row = tk.Frame(form, bg=PANEL)
            row.pack(fill="x", pady=(2, 3))
            ttk.Button(row, textvariable=v[key],
                       command=lambda k=key: self.pick_color(v[k], v[k + "_mode"])).pack(
                           side="left", padx=(0, 4))
            for mode in COLOR_MODES:
                ttk.Radiobutton(row, text=mode, variable=v[key + "_mode"], value=mode).pack(
                    side="left")
            self.make_scale(form, f"Helligkeit {title} (%)", v[key + "_brightness"], 0, 100)
        self.make_scale(form, "Gesamthelligkeit (%)", v["brightness"], 0, 100)
        self.make_scale(form, "Geschwindigkeit", v["speed"], 0, 100)

        form = reaction_page.body
        self.reaction_vars = {
            "enabled": tk.BooleanVar(),
            "palette": tk.StringVar(),
            "duration": tk.IntVar(),
        }
        r = self.reaction_vars
        ttk.Checkbutton(form, text="Reaktion aktiv", variable=r["enabled"]).pack(anchor="w")
        self.text(form, "Trigger", size=11, bold=True).pack(anchor="w", pady=(8, 3))
        trigger_grid = tk.Frame(form, bg=PANEL)
        trigger_grid.pack(fill="x")
        self.trigger_vars = {}
        for index, trigger in enumerate(TRIGGERS):
            var = self.trigger_vars[trigger] = tk.BooleanVar()
            ttk.Checkbutton(trigger_grid, text=trigger, variable=var).grid(
                row=index // 2, column=index % 2, sticky="w", padx=(0, 6))
        self.text(form, "Farbprofil", color=MUTED, size=10).pack(anchor="w", pady=(5, 3))
        ttk.Combobox(form, state="readonly", textvariable=r["palette"],
                     values=REACTION_PALETTES).pack(fill="x")
        self.make_scale(form, "Dauer (ms)", r["duration"], 50, 2000)
        for var in (*v.values(), *r.values(), *self.trigger_vars.values()):
            var.trace_add("write", self.write_light)
        animation_page.bind_contents()
        reaction_page.bind_contents()
        self.load_light()
        self.draw_led_shapes()

    def make_scale(self, parent, title, variable, start, end):
        self.text(parent, title, color=MUTED, size=10).pack(anchor="w", pady=(9, 2))
        scale = tk.Scale(parent, from_=start, to=end, variable=variable,
                         orient="horizontal", resolution=1, bg=PANEL, fg=TEXT,
                         troughcolor=CARD, activebackground=ACCENT,
                         highlightthickness=0, relief="flat", bd=0)
        scale.pack(fill="x", pady=(0, 2))

    def edit_target(self):
        return self.project["layers"][self.layer]

    def load_light(self):
        self._loading = True
        try:
            light = self.edit_target()["groups"][self.zone]
            for key, variable in self.light_vars.items():
                variable.set(light[key])
            reaction = light["reactive"]
            for key, variable in self.reaction_vars.items():
                variable.set(reaction[key])
            for trigger, variable in self.trigger_vars.items():
                variable.set(trigger in reaction["triggers"])
        finally:
            self._loading = False

    def change_zone(self, _event=None):
        self.zone = BASE_GROUPS[self.zone_option.current()]
        self.load_light()

    def write_light(self, *_args):
        if self._loading or self.view != "LEDs":
            return
        light = self.edit_target()["groups"][self.zone]
        light.update({key: var.get() for key, var in self.light_vars.items()})
        reaction = light["reactive"]
        reaction.update({key: var.get() for key, var in self.reaction_vars.items()})
        reaction["triggers"] = [trigger for trigger, var in self.trigger_vars.items() if var.get()]
        self.mark_changed()

    def pick_color(self, variable, mode=None):
        selected = colorchooser.askcolor(color=variable.get(), parent=self.root,
                                         title="LED-Farbe")[1]
        if selected:
            variable.set(selected.upper())
            if mode is not None:
                mode.set(COLOR_MODES[0])

    def simulate(self, trigger, at=None):
        now = time.monotonic() - self.started if at is None else at
        self.reaction_hue = (self.reaction_hue + 73) % 256
        self.events.append(Pulse(trigger, now, self.layer, self.reaction_hue / 256))
        self.events = self.events[-25:]

    def draw_led_shapes(self):
        if self.view != "LEDs" or not hasattr(self, "preview_canvas"):
            return
        c = self.preview_canvas
        if not c.winfo_exists():
            return
        c.delete("all")
        w, h = max(c.winfo_width(), 450), max(c.winfo_height(), 355)
        self.render_items = {}
        x1, y1, x2, y2 = 31, 31, w - 32, h - 30
        c.create_rectangle(x1, y1, x2, y2, outline="#425C6A", width=2)
        c.create_text(w / 2, 60, text="OMNIPAD / DISPLAY",
                      fill=MUTED, font=("Consolas", 10, "bold"))
        # Outer 43 LEDs along the perimeter, each with a distinct canvas item.
        total = 2 * ((x2 - x1) + (y2 - y1))
        for index in range(43):
            s = index / 43 * total
            width = x2 - x1
            height = y2 - y1
            if s < width:
                x, y = x1 + s, y1
            elif s < width + height:
                x, y = x2, y1 + s - width
            elif s < 2 * width + height:
                x, y = x2 - (s - width - height), y2
            else:
                x, y = x1, y2 - (s - 2 * width - height)
            i = 30 + index
            item = c.create_oval(x - 6, y - 6, x + 6, y + 6,
                                 fill="#314350", outline="")
            self.render_items[i] = item
        x0, y0 = w / 2 - 96, h / 2 - 100
        for i in range(30):
            row, col = divmod(i, 5)
            x, y = x0 + col * 48, y0 + row * 35
            item = c.create_oval(x - 9, y - 9, x + 9, y + 9,
                                 fill="#314350", outline="")
            self.render_items[i] = item
        self.update_led_colors()

    def update_led_colors(self):
        if self.view != "LEDs" or not self.render_items:
            return
        if not self.preview_canvas.winfo_exists():
            return
        now = time.monotonic() - self.started
        self.events = [event for event in self.events if now - event.at < 2.1]
        colors = render(self.project, self.layer, now, self.events)
        for i, item in self.render_items.items():
            self.preview_canvas.itemconfigure(item, fill=hexrgb(colors[i]))
        return colors

    def upload_lighting(self):
        if self.usb_busy:
            return
        try:
            prepare_lighting(self.project)  # Validate before opening USB.
        except (ProtocolError, ValueError, KeyError) as exc:
            messagebox.showerror("LEDs ans Pad", str(exc), parent=self.root)
            return
        if not messagebox.askyesno(
            "LEDs auf Pad speichern",
            "Die LED-Einstellungen aller acht Layer werden auf dem Gerät ersetzt.\n"
            "Firmware-Tasten, Menüs und App-Profil bleiben unverändert. Fortfahren?",
            parent=self.root):
            return
        self.start_upload("LED-Einstellungen")

    def upload_keys(self):
        if self.usb_busy:
            return
        if messagebox.askyesno(
            "Belegung auf Pad speichern",
            "Eigene Belegungen und zugewiesene Snippets/Makros auf das Pad übertragen?\n"
            "Zum Verwenden am Pad unter Settings → Config Source → App Profile wählen.",
            parent=self.root,
        ):
            self.start_upload("Tastenbelegung", assignments=True)

    def start_upload(self, title, *, assignments=False):
        self.usb_busy = True
        self.upload_title = title
        self.live_status.set("Live-Vorschau pausiert während der Übertragung")
        self.status.set(f"{title} wird übertragen …")
        self.upload_button.configure(state="disabled")
        self.usb_future = self.usb_worker.submit(
            self.usb.upload, copy.deepcopy(self.project), assignments=assignments)

    def update_live_inputs(self, info, now):
        self.device_status.set(f"{info.status}\n{info.detail}" if info.detail else info.status)
        inputs = info.inputs
        if inputs is None:
            self.held_keys = 0
            self.pad_layer = None
            self.key_flash_until.clear()
            self.live_status.set(info.status)
            return
        self.held_keys = inputs.held
        self.key_flash_until = {key: end for key, end in self.key_flash_until.items() if end > now}
        for index, key in enumerate(LIVE_KEYS):
            if inputs.pressed & (1 << index):
                self.key_flash_until[key] = now + .16
        triggers = inputs.triggers
        if self.pad_layer is not None and inputs.layer != self.pad_layer:
            triggers |= 1 << (len(TRIGGERS) - 1)
        self.pad_layer = inputs.layer
        if self.view == "LEDs":
            for bit, trigger in enumerate(TRIGGERS):
                if triggers & (1 << bit):
                    self.simulate(trigger, now)
            if info.preview:
                self.live_status.set("Live am Pad")
            elif not inputs.preview_allowed:
                self.live_status.set("Pad-Vorschau pausiert · Beleuchtung oder Matrixtester prüfen")
            else:
                self.live_status.set("Pad-Vorschau startet …")
        else:
            self.live_status.set(f"Tastenfeedback aktiv · Pad-Layer {inputs.layer}")

    def animate(self):
        now = time.monotonic() - self.started
        if self.usb_future is not None and self.usb_future.done():
            future, self.usb_future = self.usb_future, None
            if self.usb_busy:
                self.usb_busy = False
                if hasattr(self, "upload_button") and self.upload_button.winfo_exists():
                    self.upload_button.configure(state="normal")
                try:
                    self.status.set(future.result())
                except (ImportError, OSError, RuntimeError, ValueError) as exc:
                    self.status.set("Übertragung fehlgeschlagen")
                    messagebox.showerror(self.upload_title, str(exc), parent=self.root)
            else:
                self.update_live_inputs(future.result(), now)
        colors = self.update_led_colors() if self.view == "LEDs" else None
        if self.view == "Belegung":
            self.update_key_highlights(now)
        if self.usb_future is None:
            self.usb_future = self.usb_worker.submit(self.usb.poll, colors,
                                                     reconnect=self.usb_refresh)
            self.usb_refresh = False
        self.animation_tick = self.root.after(40, self.animate)

    def update_key_highlights(self, now):
        for index, key in enumerate(LIVE_KEYS):
            button = self.key_buttons[key]
            pressed = self.held_keys & (1 << index) or self.key_flash_until.get(key, 0) > now
            background = KEY_FLASH if pressed else ACCENT if self.selected_key == key else CARD
            if button.cget("bg") != background:
                button.configure(bg=background, fg=TEXT if background == CARD else BG,
                                 activebackground=background,
                                 activeforeground=TEXT if background == CARD else BG)

    def build_keys_page(self):
        content = tk.Frame(self.content, bg=BG)
        content.pack(fill="both", expand=True)
        content.grid_columnconfigure(0, weight=2, minsize=380)
        content.grid_columnconfigure(1, weight=2, minsize=360)
        content.grid_rowconfigure(0, weight=1)
        left = self.card(content)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.frame_header(left, "App-Belegungen",
                          "Die Originalfirmware bleibt schreibgeschützt. Gesperrte "
                          "Systemgesten sind auf dem Pad fest hinterlegt.")
        tk.Label(left, textvariable=self.live_status, bg=PANEL, fg=ACCENT,
                 anchor="w").pack(fill="x")
        self.key_buttons = {}
        matrix = tk.Frame(left, bg=PANEL)
        matrix.pack(anchor="w", pady=(8, 20))
        for i, key in enumerate(LAYER_DATA["physical_keys"]):
            name = f"K{i + 1}"
            btn = tk.Button(matrix, text=name, font=("Segoe UI", 11, "bold"),
                            width=8, height=2, bd=0, relief="flat",
                            bg=ACCENT if self.selected_key == name else CARD,
                            fg=BG if self.selected_key == name else TEXT,
                            command=lambda target=name: self.select_key(target))
            btn.grid(row=key["y"], column=key["x"],
                     rowspan=key.get("h", 1), columnspan=key.get("w", 1),
                     sticky="nsew", padx=4, pady=4)
            self.key_buttons[name] = btn
        self.text(left, "Weitere Eingaben", size=13, bold=True).pack(anchor="w", pady=(7, 6))
        extra = tk.Frame(left, bg=PANEL)
        extra.pack(fill="x")
        for index, name in enumerate((*ROTATION_ACTIONS, "Encoder kurz", *SLIDER_ACTIONS, "K0")):
            button = tk.Button(extra, text=name, font=("Segoe UI", 9),
                               bg=ACCENT if self.selected_key == name else CARD,
                               fg=BG if self.selected_key == name else TEXT,
                               relief="flat", padx=5, pady=9,
                               command=lambda target=name: self.select_key(target))
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=3, pady=3)
            self.key_buttons[name] = button
            extra.grid_columnconfigure(index % 3, weight=1)
        right = self.card(content)
        right.grid(row=0, column=1, sticky="nsew")
        self.upload_button = ttk.Button(
            right, text="Belegung auf Pad speichern", command=self.upload_keys,
            state="disabled" if self.usb_busy else "normal")
        self.upload_button.pack(fill="x", pady=(0, 9))
        self.key_panel = tk.Frame(right, bg=PANEL)
        self.key_panel.pack(fill="both", expand=True)
        self.update_key_panel()
        self.update_key_highlights(time.monotonic() - self.started)

    def select_key(self, key):
        self.selected_key = key
        self.selected_gesture = GESTURES[0]
        self.build_page()

    def update_key_panel(self):
        body = self.key_panel
        for child in body.winfo_children():
            child.destroy()
        key = self.selected_key
        self.frame_header(body, key)
        if key == "K0":
            for name, action in PROTECTED.items():
                if name.startswith("K0"):
                    self.text(body, f"{name} → {action}   [GESPERRT]",
                              color=ACCENT).pack(anchor="w", pady=6)
            self.text(body, "Diese Systemaktionen sind nicht neu belegbar.",
                      color=MUTED, wrap=315).pack(anchor="w", pady=15)
            return
        if key == "Encoder kurz":
            self.text(body, "Encoder lang → Layerliste [GESPERRT]",
                      color=ACCENT).pack(anchor="w", pady=8)
        if key in KEY_NAMES:
            index = int(key[1:]) - 1
            source = LAYER_DATA["layers"][self.layer]["keys"][index]["tap"]
            self.text(body, f"Werkseinstellung: {source}",
                      color=MUTED, wrap=320).pack(anchor="w", pady=(8, 15))
            if locked_key(self.layer, key):
                self.text(body, "Diese Taste ist auf diesem Layer fest belegt.",
                          color=ACCENT).pack(anchor="w")
                return
        target = self.edit_target()
        slots = target["actions"].get(key, {})
        gestures = GESTURES[:1]
        mode = "Direkt"
        if key in KEY_NAMES:
            self.text(body, "Tastenmodus", color=MUTED, size=10).pack(anchor="w")
            mode = target.get("key_modes", {}).get(key, inferred_mode(slots))
            mode_picker = ttk.Combobox(body, values=KEY_MODES, state="readonly")
            mode_picker.set(mode)
            mode_picker.pack(fill="x", pady=(3, 10))
            mode_picker.bind("<<ComboboxSelected>>", lambda _: self.change_key_mode(mode_picker.get()))
            gestures = GESTURES[:(1, 5, 4)[KEY_MODES.index(mode)]]
        if self.selected_gesture not in gestures:
            self.selected_gesture = "1×"
        if len(gestures) > 1:
            hint = ("Je Druck der nächste belegte Schritt." if mode == "Durchschalten" else
                    "Eine eigene Aktion für jede Anzahl von Tipps oder für Halten.")
            self.text(body, hint, color=MUTED, size=9).pack(anchor="w")
            gesture = tk.Frame(body, bg=PANEL)
            gesture.pack(fill="x", pady=(5, 13))
            for index, g in enumerate(gestures):
                tk.Button(gesture, text=f"Schritt {index + 1}" if mode == "Durchschalten" else g,
                          font=("Segoe UI", 10), bd=0,
                          bg=ACCENT if self.selected_gesture == g else CARD,
                          fg=BG if self.selected_gesture == g else TEXT,
                          padx=9, pady=8, command=lambda v=g: self.select_gesture(v)).pack(
                              side="left", padx=(0, 3))
        current = slots.get(self.selected_gesture, LEGACY_EMPTY)
        if current == LEGACY_EMPTY:
            current = DEFAULT_ACTION if self.selected_gesture == "1×" and mode != "Durchschalten" else NO_ACTION
        self.action_options = {name: name for name in BUILTINS}
        categories = {"Tasten": (*LETTERS, *NUMBERS, *FUNCTIONS, *NAVIGATION),
                      "Medien": tuple(MEDIA), "Shortcuts": tuple(SHORTCUTS), "Maus": tuple(MOUSE),
                      "Makros": [], "Text-Snippets": []}
        for index, entry in enumerate(self.project.get("library", []), 1):
            category = "Text-Snippets" if entry["kind"] == "text" else "Makros"
            display = f"{index}. {entry['name']}"
            categories[category].append(display)
            self.action_options[display] = LIBRARY_PREFIX + entry["id"]
        selected = next((label for label, value in self.action_options.items() if value == current), DEFAULT_ACTION)
        category = next((name for name, options in categories.items() if selected in options), "Tasten")
        self.text(body, "Aktion", color=MUTED, size=10).pack(anchor="w")
        action_category = ttk.Combobox(body, values=tuple(categories), state="readonly")
        action_category.set(category)
        action_category.pack(fill="x", pady=(3, 4))
        self.key_action = tk.StringVar(value=selected)
        picker = ttk.Combobox(body, textvariable=self.key_action, state="readonly")
        def filter_choices(_=None):
            picker.configure(values=(DEFAULT_ACTION, NO_ACTION, *categories[action_category.get()]))
        filter_choices()
        action_category.bind("<<ComboboxSelected>>", filter_choices)
        picker.pack(fill="x")
        picker.bind("<<ComboboxSelected>>", self.write_action)

    def change_key_mode(self, mode):
        self.edit_target().setdefault("key_modes", {})[self.selected_key] = mode
        self.selected_gesture = GESTURES[0]
        self.mark_changed()
        self.update_key_panel()

    def select_gesture(self, gesture):
        self.selected_gesture = gesture
        self.update_key_panel()

    def write_action(self, _event=None):
        key = self.selected_key
        if locked_key(self.layer, key):
            return
        self.edit_target()["actions"].setdefault(key, {})[self.selected_gesture] = (
            self.action_options[self.key_action.get()])
        self.mark_changed()

    def build_library_page(self):
        panel = self.card(self.content)
        panel.pack(fill="both", expand=True)
        self.frame_header(panel, "Snippetbibliothek",
                          "Textbausteine und Tastensequenzen stehen in der Aktionsauswahl bereit.")
        tools = tk.Frame(panel, bg=PANEL)
        tools.pack(fill="x", pady=(0, 10))
        for text, command in (
            ("Text-Snippet anlegen", lambda: self.edit_library_entry("text")),
            ("Makro aufnehmen", lambda: self.edit_library_entry("macro")),
            ("Bearbeiten", self.edit_library_entry),
            ("Löschen", self.delete_library_entry),
        ):
            ttk.Button(tools, text=text, command=command).pack(side="left", padx=(0, 6))
        rows = tk.Frame(panel, bg=PANEL)
        rows.pack(fill="both", expand=True)
        self.library_list = ttk.Treeview(rows, columns=("kind",), selectmode="browse")
        self.library_list.heading("#0", text="Name")
        self.library_list.heading("kind", text="Typ")
        self.library_list.column("kind", width=160, stretch=False)
        scrollbar = ttk.Scrollbar(rows, command=self.library_list.yview)
        self.library_list.configure(yscrollcommand=scrollbar.set)
        self.library_list.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for entry in self.project.get("library", []):
            self.library_list.insert("", "end", iid=entry["id"], text=entry["name"],
                                     values=("Text-Snippet" if entry["kind"] == "text" else "Makro",))
        if self.selected_entry and self.library_list.exists(self.selected_entry):
            self.library_list.selection_set(self.selected_entry)
        self.library_list.bind("<Double-Button-1>", lambda _: self.edit_library_entry())

    def get_library_entry(self):
        selected = self.library_list.selection()
        return next((item for item in self.project.get("library", []) if item["id"] in selected), None)

    def edit_library_entry(self, kind=None):
        entry = None if kind else self.get_library_entry()
        if kind or entry:
            LibraryEditor(self, kind or entry["kind"], self.store_library_entry, entry)

    def store_library_entry(self, entry):
        entries = self.project.setdefault("library", [])
        for index, old in enumerate(entries):
            if old["id"] == entry["id"]:
                entries[index] = entry
                break
        else:
            entries.append(entry)
        self.selected_entry = entry["id"]
        self.mark_changed()
        self.build_page()

    def delete_library_entry(self):
        entry = self.get_library_entry()
        if entry is None:
            return
        token = LIBRARY_PREFIX + entry["id"]
        if any(token in slots.values() for layer in self.project["layers"]
               for slots in layer["actions"].values()):
            messagebox.showinfo("Snippetbibliothek", "Entferne zuerst die zugehörigen Belegungen.",
                                parent=self.root)
            return
        if messagebox.askyesno("Snippetbibliothek", f"„{entry['name']}“ löschen?", parent=self.root):
            self.project["library"].remove(entry)
            self.selected_entry = None
            self.mark_changed()
            self.build_page()

    def build_display_page(self):
        self.screen = getattr(self, "screen", SCREENS[0])
        area = tk.Frame(self.content, bg=BG)
        area.pack(fill="both", expand=True)
        area.grid_columnconfigure(0, weight=1)
        area.grid_columnconfigure(1, weight=2)
        area.grid_rowconfigure(0, weight=1)
        left = self.card(area)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.frame_header(left, "Feste Firmware-Seiten", "Nur SVG-Vorlagen auswählen.")
        screen_titles = {"active-layer": "Aktiver Layer / Layermap",
                         "layer-list": "Layerliste", "matrix-tester": "Matrixtester",
                         "settings": "Settings"}
        for key in SCREENS:
            tk.Button(left, text=screen_titles[key], bd=0, anchor="w",
                      padx=13, pady=13,
                      bg=ACCENT if self.screen == key else CARD,
                      fg=BG if self.screen == key else TEXT,
                      command=lambda item=key: self.select_screen(item)).pack(
                          fill="x", pady=4)
        self.text(left, "SVG wird extern bearbeitet. Auf dem Pad "
                  "zeichnet die bestehende Firmware weiterhin ihre festen Ansichten.",
                  color=MUTED, wrap=310).pack(anchor="w", pady=(24, 0))
        right = self.card(area)
        right.grid(row=0, column=1, sticky="nsew")
        self.frame_header(right, screen_titles[self.screen],
                          "Vorlagenzuordnung im lokalen Projekt (noch keine Hardwareübertragung)")
        library = ROOT / "display_library" / "svg"
        choices = sorted(library.glob(f"*/{self.screen}.svg"))
        saved = self.project["display_templates"].get(self.screen, "")
        if saved and Path(saved) not in choices:
            choices.append(Path(saved))
        self.svg_paths = choices
        options = [f"{p.parent.name} · {p.name}" for p in choices]
        chosen = next((i for i, p in enumerate(choices) if str(p) == saved), 0)
        self.svg_choice = ttk.Combobox(right, state="readonly",
                                       values=options)
        self.svg_choice.pack(fill="x", pady=(12, 10))
        if choices:
            self.svg_choice.current(chosen)
        row = tk.Frame(right, bg=PANEL)
        row.pack(fill="x")
        ttk.Button(row, text="Vorlage auswählen", command=self.assign_svg).pack(
            side="left", padx=(0, 7))
        ttk.Button(row, text="Eigene SVG-Datei …", command=self.browse_svg).pack(
            side="left", padx=(0, 7))
        ttk.Button(row, text="Extern öffnen", command=self.open_svg).pack(side="left")
        self.template_info = tk.StringVar()
        tk.Label(right, textvariable=self.template_info, bg=PANEL, fg=MUTED,
                 justify="left", wraplength=490).pack(anchor="w", pady=(18, 0))
        self.show_svg_info()

    def select_screen(self, key):
        self.screen = key
        self.build_page()

    def inspect_svg(self, path):
        root = ElementTree.parse(path).getroot()
        if root.tag != "{http://www.w3.org/2000/svg}svg":
            raise ValueError("Keine gültige SVG-Datei.")
        return root

    def show_svg_info(self):
        path = self.project["display_templates"].get(self.screen, "")
        if not path:
            self.template_info.set("Für diese Seite ist noch keine Vorlage aktiviert.")
            return
        try:
            root = self.inspect_svg(Path(path))
        except (ValueError, OSError, ElementTree.ParseError) as exc:
            self.template_info.set("Vorlage kann nicht gelesen werden: " + str(exc))
            return
        self.template_info.set(
            f"Aktiv im Projekt:\n{path}\n\n"
            f"SVG-Größe: {root.get('width', '?')} × {root.get('height', '?')}\n"
            "SVG wird noch nicht auf dem RP2040 gerendert. "
            "Die bestehende Firmware unterstützt nur begrenzte Designmetadaten.")

    def assign_svg(self):
        index = self.svg_choice.current()
        if not 0 <= index < len(self.svg_paths):
            return
        path = self.svg_paths[index]
        try:
            self.inspect_svg(path)
        except (OSError, ValueError, ElementTree.ParseError) as exc:
            messagebox.showerror("SVG", str(exc))
            return
        self.project["display_templates"][self.screen] = str(path)
        self.mark_changed()
        self.show_svg_info()

    def browse_svg(self):
        file = filedialog.askopenfilename(parent=self.root, filetypes=[("SVG", "*.svg")])
        if file:
            try:
                self.inspect_svg(Path(file))
            except (OSError, ValueError, ElementTree.ParseError) as exc:
                messagebox.showerror("SVG", str(exc))
                return
            self.project["display_templates"][self.screen] = file
            self.mark_changed()
            self.build_page()

    def open_svg(self):
        path = self.project["display_templates"].get(self.screen, "")
        if not path:
            messagebox.showinfo("SVG", "Zuerst eine Vorlage auswählen.")
            return
        import os
        if not Path(path).exists():
            messagebox.showerror("SVG", "Vorlage wurde nicht gefunden.")
            return
        os.startfile(path)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
