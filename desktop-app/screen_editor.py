"""Graphical .screen.json editor and bound-data preview."""

from copy import deepcopy
from pathlib import Path
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from assignment_panel import AssignmentPanel
from icons import PIXELS
from profile import (BINDINGS, ICONS, MAX_FIELDS, SCREEN_VIEWS, SCREEN_PRESETS,
                     ascii_text, atomic_json, new_field, validate_screen, default_screen_themes)
from ui_helpers import BG, PANEL, TEXT, MUTED, ACCENT, Form, ScrollPanel, button, label


class ScreenEditor(tk.Frame):
    def __init__(self, parent, editor):
        super().__init__(parent, bg=BG)
        self.editor = editor
        self.selected = None
        self.view_index = 2  # Layerdetails: backward-compatible existing custom screen
        self.visible_ids = []
        self.drag = None
        self.drag_field = None
        self.zoom = 2
        self.origin = (22, 22)
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill="both", expand=True, pady=(8, 0))
        layout = tk.Frame(self.pages, bg=BG)
        self.pages.add(layout, text="Layout")
        self.assignments = AssignmentPanel(self.pages, editor, display=True)
        self.pages.add(self.assignments, text="Tasten & Auslöser")
        selector = tk.Frame(layout, bg=PANEL)
        selector.pack(fill="x", pady=(8, 4))
        label(selector, "Bildschirm", color=MUTED).pack(side="left", padx=(12, 6))
        self.view_choice = ttk.Combobox(selector, state="readonly", width=20, values=SCREEN_VIEWS)
        self.view_choice.current(self.view_index)
        self.view_choice.pack(side="left", padx=(0, 12), pady=8)
        self.view_choice.bind("<<ComboboxSelected>>", self.change_view)
        self.pool_status = tk.StringVar()
        label(selector, textvariable=self.pool_status, color=MUTED).pack(side="right", padx=12)
        tools = tk.Frame(layout, bg=BG)
        tools.pack(fill="x", pady=(8, 8))
        for text, kind in (("+ Feld", 0), ("+ Text", 1), ("+ Icon", 2)):
            button(tools, text, lambda k=kind: self.add(k)).pack(side="left", padx=(0, 6))
        button(tools, "Vorlagen", self.import_builtin).pack(side="right", padx=(0, 6))
        button(tools, "Baustein einfügen", self.import_component).pack(side="left", padx=(6, 0))
        button(tools, "Layout importieren", self.import_screen).pack(side="right")
        button(tools, "Layout exportieren", self.export_screen).pack(side="right", padx=6)
        workspace = tk.Frame(layout, bg=BG)
        workspace.pack(fill="both", expand=True)
        left = tk.Frame(workspace, bg=PANEL)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.draw())
        self.canvas.bind("<Button-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.move)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Delete>", lambda _: self.delete())
        label(left, "320 × 240 px · Ziehen verschiebt · Griff unten rechts ändert die Größe",
              9, color=MUTED).pack(anchor="w", padx=16, pady=(0, 12))
        self.listbox = tk.Listbox(left, height=4, bg="#303740", fg=TEXT,
                                  selectbackground="#73503d", exportselection=False)
        self.listbox.pack(fill="x", padx=16, pady=(0, 10))
        self.listbox.bind("<<ListboxSelect>>", self.select_list)
        self.inspector = ScrollPanel(workspace, 305)
        self.inspector.pack(side="right", fill="y", padx=(12, 0))
        self.refresh()

    @property
    def screen(self):
        return self.editor.profile["screen"]

    @property
    def theme(self):
        themes = self.screen.get("themes", default_screen_themes())
        return themes[self.view_index]

    def is_visible_field(self, field):
        return field.get("view", 2) == self.view_index

    def change_view(self, _event=None):
        index = self.view_choice.current()
        if index < 0 or index == self.view_index:
            return
        self.view_index = index
        self.selected = None
        self.drag = self.drag_field = None
        self.refresh()

    def refresh(self):
        self.assignments.refresh()
        fields = self.screen["fields"]
        self.view_choice.current(self.view_index)
        self.visible_ids = [i for i, field in enumerate(fields) if self.is_visible_field(field)]
        if self.selected is not None and self.selected not in self.visible_ids:
            self.selected = None
        self.pool_status.set(
            f"{len(fields)}/{MAX_FIELDS} Zusatzelemente gesamt · "
            f"{len(self.visible_ids)} auf {SCREEN_VIEWS[self.view_index]}")
        self.listbox.delete(0, "end")
        for visible_index, index in enumerate(self.visible_ids):
            field = fields[index]
            title = ["Feld", "Text", "Icon"][field["type"]]
            self.listbox.insert("end", f"{visible_index + 1}  {title}  {field['text'] if field['type'] == 1 else ''}")
        if self.selected is not None:
            self.listbox.selection_set(self.visible_ids.index(self.selected))
        self.inspector.clear()
        self.form = form = Form(self.inspector.content)
        if self.selected is None:
            form.title(SCREEN_VIEWS[self.view_index])
            form.choice("preset", "Stilvorlage", self.theme["preset"], SCREEN_PRESETS)
            form.color("theme_background", "Hintergrund", self.theme["background"])
            form.color("theme_accent", "Akzentfarbe", self.theme["accent"])
            form.check("enabled", "Zusatzelemente am Pad aktivieren", self.screen["enabled"])
            form.note("Jeder Bildschirm hat eigene Farben und eine eigene Stilvorlage. "
                      "Home, Layerindex, Navigation und Layerdetails können zusätzliche "
                      "Texte und Icons erhalten. Die Bedienelemente in Einstellungen und "
                      "Keytester bleiben aus Sicherheitsgründen geschützt.")
            form.apply(self.apply, "Bildschirmdesign übernehmen")
            if self.view_index not in (3, 5):
                button(form.parent, "Zusatzelemente für diesen Bildschirm einsetzen",
                       self.standard_layout).pack(fill="x", padx=14, pady=5)
        else:
            field = fields[self.selected]
            form.title(["Feld", "Text", "Icon"][field["type"]])
            for name, caption in (("x", "X"), ("y", "Y"), ("width", "Breite"), ("height", "Höhe")):
                form.entry(name, caption, field[name], kind=int)
            if field["type"] == 1:
                form.entry("text", "Text", field["text"])
                form.choice("binding", "Inhalt", field["binding"], BINDINGS)
                form.entry("key", "Taste für Beschriftung / Abhängigkeit (1–12)", field["key"] + 1, kind=int)
            if field["type"] == 2:
                form.choice("icon", "Icon", field["icon"], ICONS)
            if field["type"] != 0:
                form.choice("scale", "Pixelgröße", field["scale"] - 1, ["1", "2", "3", "4"])
                form.color("foreground", "Vordergrundfarbe", field["foreground"])
            if field["type"] == 0:
                form.color("background", "Flächenfarbe", field["background"])
            names = ["Alle Layer"] + [layer["name"] for layer in self.editor.profile["layers"]]
            visible = min(field["layer"] + 1, len(names) - 1)
            form.choice("layer", "Sichtbar auf", visible, names)
            form.check("pressed_only", "Nur beim Drücken der zugeordneten Taste", field["pressed_only"])
            if field["type"] != 1:
                form.entry("key", "Zugeordnete Taste (1–12)", field["key"] + 1, kind=int)
            form.apply(self.apply)
            for caption, command in (("Duplizieren", self.duplicate), ("Nach vorne", lambda: self.reorder(1)),
                                     ("Nach hinten", lambda: self.reorder(-1)), ("Entfernen", self.delete),
                                     ("Auswahl aufheben", lambda: self.select(None))):
                button(form.parent, caption, command).pack(fill="x", padx=14, pady=3)
        self.draw()

    def select(self, index):
        self.selected = index
        self.refresh()

    def select_list(self, _):
        chosen = self.listbox.curselection()
        if chosen and self.visible_ids[chosen[0]] != self.selected:
            self.select(self.visible_ids[chosen[0]])

    def apply(self):
        try:
            values = self.form.values()
            if self.selected is None:
                def update_theme(p):
                    themes = p["screen"].setdefault("themes", default_screen_themes())
                    themes[self.view_index].update(
                        preset=values["preset"], background=values["theme_background"],
                        accent=values["theme_accent"])
                    p["screen"]["enabled"] = values["enabled"]
                self.editor.change(update_theme)
            else:
                if "scale" in values:
                    values["scale"] += 1
                if "key" in values:
                    values["key"] -= 1
                values["layer"] -= 1
                self.editor.change(lambda p: p["screen"]["fields"][self.selected].update(values))
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Displaylayout", str(error), parent=self)

    def add(self, kind, *, binding=0, key=0):
        if self.view_index in (3, 5):
            messagebox.showinfo("Geschützter Bildschirm",
                                "Einstellungen und Keytester erlauben Farb- und Stiländerungen, "
                                "keine frei platzierten Elemente über funktionalen Bedienelementen.",
                                parent=self)
            return
        if len(self.screen["fields"]) >= MAX_FIELDS:
            messagebox.showerror("Displaylayout", f"Bis zu {MAX_FIELDS} Elemente passen auf das Pad.", parent=self)
            return
        field = new_field(kind)
        field.update(binding=binding, key=key, view=self.view_index)
        self.selected = len(self.screen["fields"])
        def add_field(p):
            p["screen"]["enabled"] = True
            p["screen"]["fields"].append(field)
        self.editor.change(add_field)

    def standard_layout(self):
        if self.view_index in (3, 5):
            return
        # The firmware already renders complete usable native screens. Only
        # lightweight decorations consume the shared 16-element overlay pool.
        headers = ("OMNIPAD", "LAYERS", "LAYER", "SETTINGS", "NAVIGATION", "KEYTESTER")
        existing = [field for field in self.screen["fields"]
                    if not self.is_visible_field(field)]
        if len(existing) + 2 > MAX_FIELDS:
            messagebox.showwarning("Display", "Nicht genügend freie Zusatzelemente.", parent=self)
            return
        bar = new_field(0)
        bar.update(view=self.view_index, x=8, y=31, width=304, height=3,
                   background=self.theme["accent"])
        caption = new_field(1)
        caption.update(view=self.view_index, x=16, y=37, width=265, height=20,
                       text=headers[self.view_index], scale=2,
                       foreground=self.theme["accent"])
        self.selected = None
        def apply(p):
            p["screen"]["fields"] = existing + [bar, caption]
            p["screen"]["enabled"] = True
        self.editor.change(apply)

    def duplicate(self):
        if self.selected is None or len(self.screen["fields"]) >= MAX_FIELDS:
            return
        copied = deepcopy(self.screen["fields"][self.selected])
        copied["x"] = min(320 - copied["width"], copied["x"] + 8)
        copied["y"] = min(240 - copied["height"], copied["y"] + 8)
        self.selected = len(self.screen["fields"])
        self.editor.change(lambda p: p["screen"]["fields"].append(copied))

    def delete(self):
        if self.selected is None:
            return
        selected = self.selected
        self.selected = None
        self.editor.change(lambda p: p["screen"]["fields"].pop(selected))

    def reorder(self, direction):
        if self.selected is None:
            return
        start, end = self.selected, self.selected + direction
        if not 0 <= end < len(self.screen["fields"]):
            return
        self.selected = end
        def move(p):
            p["screen"]["fields"].insert(end, p["screen"]["fields"].pop(start))
        self.editor.change(move)

    def bound_text(self, field):
        layer = self.editor.current_layer
        detection = self.editor.detection
        binding = field["binding"]
        if binding == 1:
            return layer["name"]
        if binding == 2:
            return layer["keys"][field["key"]]["label"]
        if binding == 3:
            value = detection.slider_percent if detection and detection.slider_percent is not None else 50
            return f"{value} / 100"
        if binding == 4:
            index = detection.last_key if detection else 0
            return f"K{index + 1}" if index < 10 else ("PUSH" if index == 10 else "K0")
        if binding == 5:
            return "DISPLAY" if not detection or detection.display_mode else "ENCODER"
        if binding == 6:
            return str(detection.presses if detection else 0)
        if binding in (7, 8, 9):
            return str(detection.sensor_xyz[binding - 7] if detection else 0)
        return field["text"]

    def draw_native_preview(self, canvas, ox, oy, z):
        theme = self.theme
        bg, accent = theme["background"], theme["accent"]
        dark = "#000000" if theme["preset"] == 1 else "#23303b"
        x = lambda n: ox + n * z
        y = lambda n: oy + n * z
        def rect(a,b,w,h,color):
            canvas.create_rectangle(x(a),y(b),x(a+w),y(b+h),fill=color,outline="")
        def text(a,b,value,size=10,color="#e9eef4"):
            canvas.create_text(x(a),y(b),anchor="nw",text=value,
                               fill=color,font=("Consolas",max(7,round(size*z/1.4)),"bold"))
        rect(0,0,320,240,bg)
        rect(0,0,320,27,dark)
        rect(0,0,320,2,accent)
        rect(0,216,320,24,dark)
        text(7,8,"CC / OMNIPAD",9)
        text(12,226,"K0 MODE  /  HOLD MENU",8,accent)
        view = self.view_index
        layers = self.editor.profile["layers"]
        name = self.editor.current_layer["name"]
        if view == 0:
            rect(12,43,296,133,dark)
            rect(12,43,296,5,accent)
            text(27,65,"OMNIPAD",24,accent)
            text(27,113,"ACTIVE",10)
            text(27,136,name[:15],16)
            text(18,190,"ENC TURN: LAYERS",10)
        elif view == 1:
            text(10,36,"LAYER INDEX",16,accent)
            for i,layer in enumerate(layers[:12]):
                cx,cy=10+(i//6)*152,70+(i%6)*23
                rect(cx,cy,146,21,accent if i==self.editor.layer else dark)
                text(cx+6,cy+4,layer["name"][:15],8)
        elif view == 2:
            rect(7,33,109,171,dark)
            rect(7,33,109,4,accent)
            text(13,151,name[:12],15)
            text(12,192,"ACTIVE LAYER",8,accent)
            for i,key in enumerate(self.editor.current_layer["keys"][:10]):
                cx,cy=124+(i%4)*46,36+(i//4)*48
                rect(cx,cy,43,43,dark)
                text(cx+3,cy+6,f"K{i+1}",8,accent)
                text(cx+3,cy+22,key["label"][:5],8)
        elif view == 3:
            rect(7,33,109,171,dark)
            text(17,64,"MODULE",15,accent)
            for i,title in enumerate(("DISPLAY","ENCODER","HOME","MATRIX","HELP","COLORS")):
                rect(125,34+i*29,187,25,accent if i==0 else dark)
                text(141,41+i*29,title,9)
        elif view == 4:
            rect(16,50,288,132,dark)
            rect(16,50,288,5,accent)
            text(26,70,"NAVIGATION",16,accent)
            text(26,113,name[:15],15)
            text(26,154,"TURN SELECT  PUSH ENTER",9)
        else:
            text(13,38,"KEY TESTER",17,accent)
            for i in range(10):
                rect(17+(i%5)*59,85+(i//5)*48,53,40,dark)
                text(25+(i%5)*59,95+(i//5)*48,f"K{i+1}",10)
            text(14,196,"PUSH / MATRIX",10,accent)

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 370), max(canvas.winfo_height(), 280)
        self.zoom = min((width - 44) / 320, (height - 44) / 240, 2.5)
        self.origin = ((width - 320 * self.zoom) / 2, (height - 240 * self.zoom) / 2)
        ox, oy = self.origin
        z = self.zoom
        self.draw_native_preview(canvas, ox, oy, z)
        for index, stored in enumerate(self.screen["fields"]):
            field = self.drag_field if self.drag_field is not None and index == self.selected else stored
            if not self.is_visible_field(field) or field["layer"] not in (-1, self.editor.layer):
                continue
            x, y = ox + field["x"] * z, oy + field["y"] * z
            right, bottom = x + field["width"] * z, y + field["height"] * z
            if field["type"] == 0:
                canvas.create_rectangle(x, y, right, bottom, fill=field["background"], outline="")
            elif field["type"] == 1:
                scale = field["scale"]
                text = ascii_text(self.bound_text(field), 60).split(b"\0", 1)[0].decode()
                max_chars = field["width"] // (6 * scale)
                canvas.create_text(x, y, anchor="nw", text=text[:max_chars], fill=field["foreground"],
                                   font=("Consolas", max(1, int(8 * scale * z)), "bold"))
            else:
                scale = field["scale"] * z
                for row, bits in enumerate(PIXELS[field["icon"]]):
                    for col in range(8):
                        if bits & (128 >> col) and (col + 1) * scale <= right - x and (row + 1) * scale <= bottom - y:
                            canvas.create_rectangle(x + col * scale, y + row * scale, x + (col + 1) * scale,
                                                     y + (row + 1) * scale, fill=field["foreground"], outline="")
            if field["pressed_only"]:
                canvas.create_rectangle(x, y, right, bottom, outline="#607788", dash=(3, 3))
            if index == self.selected:
                canvas.create_rectangle(x, y, right, bottom, outline=ACCENT, width=2)
                canvas.create_rectangle(right - 8, bottom - 8, right + 3, bottom + 3, fill=ACCENT, outline="")

    def press(self, event):
        x, y = (event.x - self.origin[0]) / self.zoom, (event.y - self.origin[1]) / self.zoom
        fields = self.screen["fields"]
        selected = None
        resize = False
        if self.selected is not None:
            f = fields[self.selected]
            if abs(x - f["x"] - f["width"]) <= 6 / self.zoom and abs(y - f["y"] - f["height"]) <= 6 / self.zoom:
                selected, resize = self.selected, True
        if selected is None:
            for index in reversed(range(len(fields))):
                f = fields[index]
                if self.is_visible_field(f) and f["layer"] in (-1, self.editor.layer) and f["x"] <= x <= f["x"] + f["width"] and f["y"] <= y <= f["y"] + f["height"]:
                    selected = index
                    break
        self.select(selected)
        if selected is not None:
            self.drag = (x, y, resize, deepcopy(fields[selected]))
            self.canvas.focus_set()

    def move(self, event):
        if not self.drag:
            return
        start_x, start_y, resize, field = self.drag
        x, y = (event.x - self.origin[0]) / self.zoom, (event.y - self.origin[1]) / self.zoom
        changed = deepcopy(field)
        if resize:
            changed["width"] = max(1, min(320 - field["x"], round(field["width"] + x - start_x)))
            changed["height"] = max(1, min(240 - field["y"], round(field["height"] + y - start_y)))
        else:
            changed["x"] = max(0, min(320 - field["width"], round(field["x"] + x - start_x)))
            changed["y"] = max(0, min(240 - field["height"], round(field["y"] + y - start_y)))
        self.drag_field = changed
        self.draw()

    def release(self, _):
        changed = self.drag_field
        self.drag = self.drag_field = None
        if changed is not None and self.selected is not None:
            self.editor.change(lambda p: p["screen"]["fields"].__setitem__(self.selected, changed))

    def import_to_view(self, loaded):
        if self.view_index in (3, 5):
            raise ValueError("Geschützte Menüs können keine freien Elemente übernehmen.")
        other = [field for field in self.screen["fields"] if not self.is_visible_field(field)]
        new = deepcopy(loaded["fields"])
        if len(other) + len(new) > MAX_FIELDS:
            raise ValueError(f"Über 16 Zusatzelemente. Frei: {MAX_FIELDS-len(other)}.")
        for field in new:
            field["view"] = self.view_index
        self.selected = None
        def apply(p):
            p["screen"]["fields"] = other + new
            p["screen"]["enabled"] = True
        self.editor.change(apply)

    def import_builtin(self):
        directory = Path(__file__).resolve().parent.parent / "display_library" / "templates"
        path = filedialog.askopenfilename(
            title="Display-Vorlage auswählen", initialdir=str(directory),
            filetypes=[("OmniScreen Layout", "*.screen.json")], parent=self)
        if path:
            try:
                loaded = validate_screen(json.loads(Path(path).read_text(encoding="utf-8-sig")))
                self.selected = None
                self.import_to_view(loaded)
            except (OSError, KeyError, TypeError, ValueError) as error:
                messagebox.showerror("Vorlage laden", str(error), parent=self)

    def import_component(self):
        directory = Path(__file__).resolve().parent.parent / "display_library" / "components"
        path = filedialog.askopenfilename(
            title="Display-Baustein einfügen", initialdir=str(directory),
            filetypes=[("OmniScreen Baustein", "*.screen.json")], parent=self)
        if not path:
            return
        try:
            source = validate_screen(json.loads(Path(path).read_text(encoding="utf-8-sig")))
            parts = deepcopy(source["fields"])
            for part in parts:
                part["view"] = self.view_index
            existing = self.screen["fields"]
            if not parts:
                raise ValueError("Der Baustein enthält keine Elemente.")
            if len(parts) + len(existing) > MAX_FIELDS:
                raise ValueError(f"Baustein passt nicht: {len(existing)} + {len(parts)} Elemente, maximal {MAX_FIELDS}.")
            left = min(f["x"] for f in parts)
            top = min(f["y"] for f in parts)
            width = max(f["x"] + f["width"] for f in parts) - left
            height = max(f["y"] + f["height"] for f in parts) - top
            def collides(x, y):
                return any(x < f["x"]+f["width"] and x+width > f["x"] and
                           y < f["y"]+f["height"] and y+height > f["y"]
                           for f in existing if f["layer"] in (-1, self.editor.layer))
            candidates = ((x,y) for y in range(8, 241-height, 8)
                          for x in range(8, 321-width, 8))
            dest = next(((x,y) for x,y in candidates if not collides(x,y)), None)
            if dest is None:
                dest = ((320-width)//2, (240-height)//2)
            for f in parts:
                f["x"] += dest[0]-left
                f["y"] += dest[1]-top
            self.selected = None
            def append_parts(p):
                p["screen"]["fields"].extend(parts)
                p["screen"]["enabled"] = True
            self.editor.change(append_parts)
        except (OSError, KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Baustein einfügen", str(error), parent=self)

    def import_screen(self):
        path = filedialog.askopenfilename(filetypes=[("Displaylayout", "*.screen.json"), ("JSON", "*.json")], parent=self)
        if path:
            try:
                screen = validate_screen(json.loads(Path(path).read_text(encoding="utf-8-sig")))
                self.selected = None
                self.import_to_view(screen)
            except (OSError, KeyError, TypeError, ValueError) as error:
                messagebox.showerror("Displaylayout", str(error), parent=self)

    def export_screen(self):
        path = filedialog.asksaveasfilename(defaultextension=".screen.json", initialfile="omnipad.screen.json",
                                           filetypes=[("Displaylayout", "*.screen.json")], parent=self)
        if path:
            try:
                export = deepcopy(self.screen)
                export["fields"] = [field for field in export["fields"] if self.is_visible_field(field)]
                atomic_json(path, export)
            except OSError as error:
                messagebox.showerror("Displaylayout", str(error), parent=self)
