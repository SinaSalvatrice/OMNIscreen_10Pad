"""Visible layer management panel for the OmniPad editor."""

import tkinter as tk
from tkinter import ttk

from ui_helpers import BG, PANEL, MUTED, button, label


class LayerManager(tk.Frame):
    def __init__(self, parent, editor):
        super().__init__(parent, bg=PANEL)
        self.editor = editor
        self.updating = False
        title = tk.Frame(self, bg=PANEL)
        title.pack(fill="x", padx=18, pady=(14, 7))
        label(title, "Layer verwalten", size=15).pack(anchor="w")
        label(title, "Rechtsklick auf einen Layer funktioniert weiterhin. Änderungen bleiben zunächst im Entwurf.",
              color=MUTED).pack(anchor="w", pady=(4, 0))

        container = tk.Frame(self, bg=PANEL)
        container.pack(fill="both", expand=True, padx=18, pady=(4, 8))
        columns = ("number", "name", "role", "color")
        self.table = ttk.Treeview(container, show="headings", columns=columns, selectmode="browse", height=12)
        for name, caption, width in zip(
                columns, ("Nr.", "Name", "Startlayer", "Farbe"),
                (62, 330, 115, 120)):
            self.table.heading(name, text=caption)
            self.table.column(name, width=width, minwidth=55, stretch=name == "name")
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")
        self.table.bind("<<TreeviewSelect>>", self.choose)

        controls = tk.Frame(self, bg=PANEL)
        controls.pack(fill="x", padx=18, pady=(5, 8))
        for caption, action in (
                ("+ Neu", lambda: editor.add_layer()),
                ("Duplizieren", lambda: editor.add_layer(copy=True)),
                ("Umbenennen", editor.rename_layer),
                ("Farbe", editor.color_layer),
                ("↑ Nach oben", lambda: editor.move_layer(-1)),
                ("↓ Nach unten", lambda: editor.move_layer(1)),
                ("Startlayer setzen", editor.set_default_layer),
                ("Löschen", editor.delete_layer)):
            button(controls, caption, action).pack(side="left", padx=(0, 7))

        self.info = tk.StringVar()
        label(self, textvariable=self.info, color=MUTED, wraplength=1010).pack(
            anchor="w", padx=18, pady=(0, 15))
        self.refresh()

    def choose(self, _event):
        if self.updating:
            return
        selection = self.table.selection()
        if not selection:
            return
        index = int(selection[0])
        if index != self.editor.layer:
            self.editor.select_layer(index)

    def refresh(self):
        if not self.table.winfo_exists():
            return
        profile = self.editor.profile
        self.updating = True
        try:
            self.table.delete(*self.table.get_children())
            for index, layer in enumerate(profile["layers"]):
                self.table.insert(
                    "", "end", iid=str(index),
                    values=(f"{index + 1:02d}", layer["name"],
                            "Ja" if index == profile["default_layer"] else "",
                            layer["color"]))
            if 0 <= self.editor.layer < len(profile["layers"]):
                current = str(self.editor.layer)
                self.table.selection_set(current)
                self.table.focus(current)
                self.table.see(current)
            self.info.set(
                f"{len(profile['layers'])}/12 Layer · Der Startlayer ist "
                f"{profile['default_layer'] + 1} {profile['layers'][profile['default_layer']]['name']}. "
                "Beim Löschen werden Verweise auf den entfernten Layer deaktiviert, "
                "beim Verschieben bleiben Ziele erhalten. Mit ↶ kannst du Änderungen rückgängig machen.")
        finally:
            self.updating = False
