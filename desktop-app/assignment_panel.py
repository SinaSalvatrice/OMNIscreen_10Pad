"""Editor for the gestures that enter layers or open displays on the pad."""

import tkinter as tk
from tkinter import ttk

from bindings import (
    DISPLAY_ACTIONS, K0_DEFAULTS, SLOTS, action_for_slot, action_name,
    default_k0, layer_action, layer_choices, set_key_action,
)
from profile import KEY_COUNT
from ui_helpers import BG, PANEL, MUTED, button, label


GESTURES = [(mode, slot) for mode, slots in enumerate(SLOTS) for slot in range(len(slots))]


def gesture_name(mode, slot):
    return SLOTS[mode][slot]


class AssignmentPanel(tk.Frame):
    def __init__(self, parent, editor, *, display=False):
        super().__init__(parent, bg=PANEL)
        self.editor = editor
        self.display = display
        self.rows = []
        self.destination_codes = []

        form = tk.Frame(self, bg=PANEL)
        form.pack(fill="x", padx=14, pady=(14, 8))
        for index in range(4):
            form.grid_columnconfigure(index, weight=2 if index in (0, 3) else 1)
        self.source = self.choice(form, 0, "Auf Layer")
        self.key = self.choice(form, 1, "Taste",
                               [editor.key_name(i) for i in range(KEY_COUNT)])
        self.gesture = self.choice(form, 2, "Geste", [gesture_name(*item) for item in GESTURES])
        self.destination = self.choice(form, 3, "Display / Aktion" if display else "Ziel / Verhalten")
        self.key.current(11 if display else 0)
        self.gesture.current(1 if display else 0)

        self.existing = tk.StringVar()
        label(self, textvariable=self.existing, color=MUTED, wraplength=950).pack(
            fill="x", padx=14, pady=(0, 6))
        commands = tk.Frame(self, bg=PANEL)
        commands.pack(fill="x", padx=14, pady=(0, 10))
        button(commands, "Zuordnen", self.assign).pack(side="left")
        button(commands, "Zuordnung entfernen", lambda: self.assign(0)).pack(side="left", padx=7)
        if not display:
            self.start_layer = tk.StringVar()
            button(commands, "Als Startlayer", self.set_start_layer).pack(side="left")
            label(commands, textvariable=self.start_layer, color=MUTED).pack(side="left", padx=10)

        table = tk.Frame(self, bg=BG)
        table.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        columns = ("layer", "source", "gesture", "destination")
        self.table = ttk.Treeview(table, columns=columns, show="headings", height=6)
        for name, heading, width in zip(columns, ("Auf Layer", "Taste", "Geste", "Ziel / Aktion"),
                                        (135, 110, 100, 360)):
            self.table.heading(name, text=heading)
            self.table.column(name, width=width, minwidth=75, stretch=name in ("layer", "destination"))
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", self.open_row)
        self.refresh()

    def choice(self, parent, column, caption, values=()):
        label(parent, caption, size=9, color=MUTED).grid(row=0, column=column, sticky="w", padx=4)
        widget = ttk.Combobox(parent, state="readonly", width=13, values=values)
        widget.grid(row=1, column=column, sticky="ew", padx=4, pady=(4, 0))
        widget.bind("<<ComboboxSelected>>", self.selection_changed)
        return widget

    @staticmethod
    def update_choices(widget, items, index):
        widget.configure(values=items)
        widget.current(min(max(index, 0), len(items) - 1))

    def refresh(self):
        profile = self.editor.profile
        layers = profile["layers"]
        source = self.source.current()
        self.update_choices(self.source, [f"{i + 1} · {layer['name']}" for i, layer in enumerate(layers)],
                            source if source >= 0 else self.editor.layer)
        selected = self.destination.current()
        previous_code = self.destination_codes[selected] if selected >= 0 else None
        choices = list(DISPLAY_ACTIONS.items()) if self.display else layer_choices(profile)
        self.destination_codes = [code for code, _ in choices]
        default = 0 if self.display else self.editor.layer
        self.update_choices(self.destination, [title for _, title in choices],
                            self.destination_codes.index(previous_code) if previous_code in self.destination_codes else default)
        if not self.display:
            index = profile["default_layer"]
            self.start_layer.set(f"Startlayer · {index + 1} {layers[index]['name']}")
        self.render_rows()
        self.describe_slot()

    def selection_changed(self, event):
        if self.display and event.widget == self.source:
            self.render_rows()
        self.describe_slot()

    def set_selection(self, layer, index, mode, slot):
        self.source.current(layer)
        self.key.current(index)
        self.gesture.current(GESTURES.index((mode, slot)))
        if self.display:
            self.render_rows()
        self.describe_slot()

    def selected_slot(self):
        layer = self.source.current()
        index = self.key.current()
        mode, slot = GESTURES[self.gesture.current()]
        return layer, index, mode, slot

    def describe_slot(self):
        layer, index, mode, slot = self.selected_slot()
        key = self.editor.profile["layers"][layer]["keys"][index]
        code = action_for_slot(key, index, mode, slot)
        name = action_name(self.editor.profile, code) if code else "Unbelegt"
        current = f"Aktuell · {name}"
        if mode != 1 and default_k0(key, index):
            current += " · Diese Zuordnung ersetzt die K0-Standardgesten"
        elif mode != key["mode"] and not default_k0(key, index):
            current += " · Zuordnen ändert den Tastenmodus"
        self.existing.set(current)

    def lists_action(self, code):
        return code in DISPLAY_ACTIONS if self.display else layer_action(code) is not None

    def render_rows(self):
        self.table.delete(*self.table.get_children())
        self.rows.clear()
        profile = self.editor.profile
        for number, layer in enumerate(profile["layers"]):
            if self.display and number != self.source.current():
                continue
            title = f"{number + 1} · {layer['name']}"
            for index, key in enumerate(layer["keys"]):
                built_in = default_k0(key, index)
                mode = 1 if built_in else key["mode"]
                codes = K0_DEFAULTS if built_in else key["codes"][:len(SLOTS[mode])]
                for slot, code in enumerate(codes):
                    if self.lists_action(code):
                        self.append_row(title, self.editor.key_name(index), gesture_name(mode, slot),
                                        action_name(profile, code) + (" · Standard" if built_in else ""),
                                        (number, index, mode, slot, code))
            if not self.display:
                for index, code in enumerate(layer["encoders"]):
                    if layer_action(code):
                        self.append_row(title, ("Encoder links", "Encoder rechts")[index], "Drehen",
                                        action_name(profile, code), None)
                if layer["slider"]["mode"] == 1:
                    for name, key in (("Regler abwärts", "low"), ("Regler aufwärts", "high")):
                        code = layer["slider"][key]
                        if layer_action(code):
                            self.append_row(title, name, "Pro Schritt", action_name(profile, code), None)

    def append_row(self, layer, source, gesture, description, assignment):
        index = len(self.rows)
        self.rows.append(assignment)
        self.table.insert("", "end", iid=str(index), values=(layer, source, gesture, description))

    def open_row(self, _event):
        selected = self.table.selection()
        if not selected:
            return
        row = self.rows[int(selected[0])]
        if row is None:
            self.existing.set("Encoder-Drehung und Regler sind im Reiter Tasten & Regler bearbeitbar.")
            return
        layer, index, mode, slot, code = row
        # The selected row already belongs to the visible source layer in the display view.
        self.source.current(layer)
        self.key.current(index)
        self.gesture.current(GESTURES.index((mode, slot)))
        self.destination.current(self.destination_codes.index(code))
        self.describe_slot()

    def assign(self, code=None):
        source, index, mode, slot = self.selected_slot()
        key = self.editor.profile["layers"][source]["keys"][index]
        if code is None:
            code = self.destination_codes[self.destination.current()]
        if code == 0 and not self.lists_action(action_for_slot(key, index, mode, slot)):
            return
        self.editor.change(lambda profile: set_key_action(profile["layers"][source]["keys"][index], index, mode, slot, code))

    def set_start_layer(self):
        target = layer_action(self.destination_codes[self.destination.current()])[1]
        self.editor.change(lambda profile: profile.__setitem__("default_layer", target))
