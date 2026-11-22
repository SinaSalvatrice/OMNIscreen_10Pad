"""Read-only SVG template selector for the four protected OmniPad firmware screens.

The MCU's current HID profile protocol can transfer themes (colors/preset), not
arbitrary SVG geometry. SVG files are editable externally. Selecting one applies
its metadata to the on-device native screen; it does not promise SVG rasterization.
"""
from pathlib import Path
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from xml.etree import ElementTree as ET

from profile import ROOT, default_screen_themes
from ui_helpers import BG, PANEL, TEXT, MUTED, ACCENT, button, label

SCREENS = (
    ("active-layer", "Aktiver Layer / Layermap", 2),
    ("layer-list", "Layerliste", 1),
    ("matrix-tester", "Matrixtester", 5),
    ("settings", "Settings", 3),
)
SVG_DIR = ROOT / "display_library" / "svg"
STYLES = ("industrial", "terminal", "spectrum")


def svg_metadata(path, slug):
    p = Path(path)
    if not p.is_file() or p.suffix.lower() != ".svg":
        raise ValueError("Bitte eine vorhandene SVG-Datei auswählen.")
    if p.stat().st_size > 1024 * 1024:
        raise ValueError("SVG ist größer als 1 MiB.")
    root = ET.parse(p).getroot()
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("Datei enthält kein SVG.")
    if root.get("data-omnipad-view") != slug:
        raise ValueError(f"SVG ist nicht für '{slug}' gekennzeichnet.")
    try:
        preset = int(root.attrib["data-omnipad-preset"])
        bg = root.attrib["data-omnipad-background"]
        accent = root.attrib["data-omnipad-accent"]
    except (KeyError, ValueError) as error:
        raise ValueError("SVG benötigt data-omnipad-preset/background/accent.") from error
    if preset not in range(3):
        raise ValueError("Preset muss zwischen 0 und 2 liegen.")
    for color in (bg, accent):
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError("Farbe muss #RRGGBB sein.")
        try:
            int(color[1:], 16)
        except ValueError as error:
            raise ValueError("SVG enthält einen ungültigen Hex-Farbwert.") from error
    return {"preset": preset, "background": bg, "accent": accent}


class ScreenEditor(tk.Frame):
    """Drop-in replacement for the old drag/drop canvas; only choose/activate SVG."""
    def __init__(self, parent, editor):
        super().__init__(parent, bg=BG)
        self.editor = editor
        # Old app code expects an assignment panel, but display editing is gone.
        self.assignments = editor.layer_entries
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill="both", expand=True, pady=(8, 0))
        tab = tk.Frame(self.pages, bg=BG)
        self.pages.add(tab, text="SVG-Vorlagen")
        label(tab, "Display-Vorlagen", color=TEXT).pack(anchor="w", padx=18, pady=(18, 6))
        label(tab, "Nur Auswahl und Aktivierung; SVG extern bearbeiten.", color=MUTED).pack(
            anchor="w", padx=18, pady=(0, 12))
        row = tk.Frame(tab, bg=BG)
        row.pack(fill="x", padx=18, pady=8)
        label(row, "Seite", color=MUTED).pack(side="left", padx=(0, 8))
        self.view_choice = ttk.Combobox(row, values=[name for _, name, _ in SCREENS],
                                        state="readonly", width=32)
        self.view_choice.current(0)
        self.view_choice.pack(side="left", padx=(0, 15))
        self.view_choice.bind("<<ComboboxSelected>>", self.refresh)
        label(row, "Vorlage", color=MUTED).pack(side="left", padx=(0, 8))
        self.style_choice = ttk.Combobox(row, values=STYLES, state="readonly", width=22)
        self.style_choice.current(0)
        self.style_choice.pack(side="left", padx=(0, 8))
        actions = tk.Frame(tab, bg=BG)
        actions.pack(fill="x", padx=18, pady=10)
        button(actions, "SVG auswählen", self.choose_svg).pack(side="left", padx=(0, 8))
        button(actions, "SVG extern öffnen", self.open_svg).pack(side="left", padx=(0, 8))
        button(actions, "Vorlage aktivieren", self.activate).pack(side="left", padx=(0, 8))
        self.path_text = tk.StringVar()
        label(tab, textvariable=self.path_text, color=MUTED).pack(
            anchor="w", padx=18, pady=(5, 8))
        self.status = tk.StringVar()
        label(tab, textvariable=self.status, color=ACCENT).pack(
            anchor="w", padx=18, pady=8)
        self.canvas = tk.Canvas(tab, bg=PANEL, highlightthickness=0, height=380)
        self.canvas.pack(fill="both", expand=True, padx=18, pady=12)
        self.style_choice.bind("<<ComboboxSelected>>", self.refresh)
        self.external_svg = {}
        self.refresh()

    def view(self):
        return SCREENS[self.view_choice.current()]

    def selected_path(self):
        slug, _, _ = self.view()
        chosen = self.external_svg.get(slug)
        if chosen:
            return Path(chosen)
        return SVG_DIR / self.style_choice.get() / (slug + ".svg")

    def choose_svg(self):
        slug, _, _ = self.view()
        path = filedialog.askopenfilename(parent=self, title="Extern erstellte SVG auswählen",
                                          filetypes=[("SVG-Vorlage", "*.svg")])
        if not path:
            return
        try:
            svg_metadata(path, slug)
        except (ValueError, OSError, ET.ParseError) as error:
            messagebox.showerror("SVG-Vorlage", str(error), parent=self)
            return
        self.external_svg[slug] = path
        self.refresh()

    def open_svg(self):
        path = self.selected_path()
        if not path.is_file():
            messagebox.showerror("SVG-Vorlage", "Vorlage fehlt.", parent=self)
            return
        os.startfile(str(path))

    def activate(self):
        slug, title, index = self.view()
        path = self.selected_path()
        try:
            values = svg_metadata(path, slug)
        except (ValueError, OSError, ET.ParseError) as error:
            messagebox.showerror("SVG-Vorlage", str(error), parent=self)
            return
        def apply(profile):
            screen = profile["screen"]
            themes = screen.setdefault("themes", default_screen_themes())
            themes[index].update(values)
            screen["enabled"] = False  # prevent old free-form editor overlays
            screen.setdefault("svg_templates", {})[slug] = str(path)
        self.editor.change(apply)
        self.status.set(f"{title}: SVG-Metadaten aktiviert. Zum Pad: 'Auf Pad speichern'.")
        self.draw()

    def refresh(self, _event=None):
        path = self.selected_path()
        self.path_text.set(str(path))
        self.draw()

    def add(self, *args, **kwargs):
        # Compatibility with old key context menu: redirect instead of editing.
        self.pages.select(0)

    def draw(self):
        if not hasattr(self, "canvas"):
            return
        c = self.canvas
        c.delete("all")
        try:
            meta = svg_metadata(self.selected_path(), self.view()[0])
        except (OSError, ValueError, ET.ParseError):
            c.create_text(20, 25, text="SVG fehlt oder ungültig",
                          fill=TEXT, anchor="nw")
            return
        x0,y0=40,15
        bg,accent=meta["background"],meta["accent"]
        c.create_rectangle(x0,y0,x0+640,y0+480,fill=bg,outline="")
        c.create_rectangle(x0,y0,x0+640,y0+54,fill="#24303a",outline="")
        c.create_rectangle(x0,y0,x0+640,y0+5,fill=accent,outline="")
        c.create_text(x0+24,y0+22,text=self.view()[1].upper(),fill=accent,
                      anchor="w",font=("Consolas",19,"bold"))
        c.create_text(x0+24,y0+110,text="FESTES FIRMWARE-LAYOUT",
                      anchor="w",fill=TEXT,font=("Consolas",16,"bold"))
        c.create_text(x0+24,y0+155,text="Live-Felder / Tastensymbole: vom RP2040 erzeugt",
                      anchor="w",fill=TEXT)
        c.create_text(x0+24,y0+200,text="Diese Vorschau zeigt Farben und Preset, nicht die SVG-Geometrie.",
                      anchor="w",fill=TEXT)
        c.create_text(x0+24,y0+430,text=f"Preset {meta['preset']}   |   320 x 240",
                      anchor="w",fill=accent)
