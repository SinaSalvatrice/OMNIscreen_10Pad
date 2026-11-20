"""Graphical .screen.json editor and bound-data preview."""

from copy import deepcopy
from pathlib import Path
import json
import tkinter as tk
from tkinter import filedialog, messagebox

from icons import PIXELS
from profile import BINDINGS, ICONS, MAX_FIELDS, ascii_text, atomic_json, new_field, validate_screen
from ui_helpers import BG, PANEL, TEXT, MUTED, ACCENT, Form, ScrollPanel, button, label


class ScreenEditor(tk.Frame):
    def __init__(self, parent, editor):
        super().__init__(parent, bg=BG)
        self.editor = editor
        self.selected = None
        self.drag = None
        self.drag_field = None
        self.zoom = 2
        self.origin = (22, 22)
        tools = tk.Frame(self, bg=BG)
        tools.pack(fill="x", pady=(8, 8))
        for text, kind in (("+ Feld", 0), ("+ Text", 1), ("+ Icon", 2)):
            button(tools, text, lambda k=kind: self.add(k)).pack(side="left", padx=(0, 6))
        button(tools, "Vorlagen", self.import_builtin).pack(side="right", padx=(0, 6))
        button(tools, "Baustein einfügen", self.import_component).pack(side="left", padx=(6, 0))
        button(tools, "Layout importieren", self.import_screen).pack(side="right")
        button(tools, "Layout exportieren", self.export_screen).pack(side="right", padx=6)
        workspace = tk.Frame(self, bg=BG)
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

    def refresh(self):
        fields = self.screen["fields"]
        if self.selected is not None and self.selected >= len(fields):
            self.selected = None
        self.listbox.delete(0, "end")
        for index, field in enumerate(fields):
            title = ["Feld", "Text", "Icon"][field["type"]]
            self.listbox.insert("end", f"{index + 1}  {title}  {field['text'] if field['type'] == 1 else ''}")
        if self.selected is not None:
            self.listbox.selection_set(self.selected)
        self.inspector.clear()
        self.form = form = Form(self.inspector.content)
        if self.selected is None:
            form.title("Displaylayout")
            form.check("enabled", "Eigenes Layout auf dem Pad anzeigen", self.screen["enabled"])
            form.color("background", "Hintergrundfarbe", self.screen["background"])
            form.note("Die Vorschau verwendet den ausgewählten Layer und die Live-Werte des Pads. "
                      "Layouts und ihre Abhängigkeiten werden mit dem Profil aufs Pad übertragen.")
            form.apply(self.apply)
            button(form.parent, "Standardlayout einsetzen", self.standard_layout).pack(
                fill="x", padx=14, pady=5)
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
        if chosen and chosen[0] != self.selected:
            self.select(chosen[0])

    def apply(self):
        try:
            values = self.form.values()
            if self.selected is None:
                self.editor.change(lambda p: p["screen"].update(values))
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
        if len(self.screen["fields"]) >= MAX_FIELDS:
            messagebox.showerror("Displaylayout", f"Bis zu {MAX_FIELDS} Elemente passen auf das Pad.", parent=self)
            return
        field = new_field(kind)
        field.update(binding=binding, key=key)
        self.selected = len(self.screen["fields"])
        self.editor.change(lambda p: p["screen"]["fields"].append(field))

    def standard_layout(self):
        fields = []
        background = new_field(0)
        background.update(x=0, y=0, width=320, height=34, background="#324351")
        fields.append(background)
        title = new_field(1)
        title.update(x=12, y=8, width=250, height=22, binding=1, scale=2)
        fields.append(title)
        for index in range(10):
            text = new_field(1)
            text.update(x=14 + (index % 4) * 76, y=54 + (index // 4) * 44,
                        width=72, height=24, binding=2, key=index, scale=1)
            fields.append(text)
        slider = new_field(1)
        slider.update(x=14, y=208, width=280, height=20, binding=3, scale=2)
        fields.append(slider)
        self.selected = None
        self.editor.change(lambda p: p["screen"].update(enabled=True, fields=fields))

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

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 370), max(canvas.winfo_height(), 280)
        self.zoom = min((width - 44) / 320, (height - 44) / 240, 2.5)
        self.origin = ((width - 320 * self.zoom) / 2, (height - 240 * self.zoom) / 2)
        ox, oy = self.origin
        z = self.zoom
        canvas.create_rectangle(ox, oy, ox + 320 * z, oy + 240 * z, fill=self.screen["background"], outline="#55606c")
        for index, stored in enumerate(self.screen["fields"]):
            field = self.drag_field if self.drag_field is not None and index == self.selected else stored
            if field["layer"] not in (-1, self.editor.layer):
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
                if f["layer"] in (-1, self.editor.layer) and f["x"] <= x <= f["x"] + f["width"] and f["y"] <= y <= f["y"] + f["height"]:
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

    def import_builtin(self):
        directory = Path(__file__).resolve().parent.parent / "display_library" / "templates"
        path = filedialog.askopenfilename(
            title="Display-Vorlage auswählen", initialdir=str(directory),
            filetypes=[("OmniScreen Layout", "*.screen.json")], parent=self)
        if path:
            try:
                loaded = validate_screen(json.loads(Path(path).read_text(encoding="utf-8-sig")))
                self.selected = None
                self.editor.change(lambda p: p.__setitem__("screen", loaded))
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
            self.editor.change(lambda p: p["screen"]["fields"].extend(parts))
        except (OSError, KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Baustein einfügen", str(error), parent=self)

    def import_screen(self):
        path = filedialog.askopenfilename(filetypes=[("Displaylayout", "*.screen.json"), ("JSON", "*.json")], parent=self)
        if path:
            try:
                screen = validate_screen(json.loads(Path(path).read_text(encoding="utf-8-sig")))
                self.selected = None
                self.editor.change(lambda p: p.__setitem__("screen", screen))
            except (OSError, KeyError, TypeError, ValueError) as error:
                messagebox.showerror("Displaylayout", str(error), parent=self)

    def export_screen(self):
        path = filedialog.asksaveasfilename(defaultextension=".screen.json", initialfile="omnipad.screen.json",
                                           filetypes=[("Displaylayout", "*.screen.json")], parent=self)
        if path:
            try:
                atomic_json(path, self.screen)
            except OSError as error:
                messagebox.showerror("Displaylayout", str(error), parent=self)
