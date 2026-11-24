"""Read-only view of the layer that the OmniPad is displaying."""

import tkinter as tk
from tkinter import ttk

from ui_helpers import BG, PANEL, KEY, TEXT, MUTED, label


class DeviceLayers(ttk.Frame):
    def __init__(self, parent, keys):
        super().__init__(parent)
        self.keys = keys
        self.state = None
        self.layers = ()
        self.index = 0
        self.mask = 0

        header = tk.Frame(self, bg=PANEL)
        header.pack(fill="x", padx=14, pady=(14, 3))
        self.title = tk.StringVar(value="OmniPad per USB verbinden")
        label(header, textvariable=self.title, size=13).pack(side="left")
        self.follow = tk.BooleanVar(value=True)
        self.follow_button = ttk.Checkbutton(header, text="Pad folgen", variable=self.follow,
                                            command=self.render, state="disabled")
        self.follow_button.pack(side="right")
        self.tabs = tk.Frame(self, bg=PANEL)
        self.tabs.pack(fill="x", padx=14, pady=(3, 4))
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.canvas.bind("<Configure>", lambda _: self.draw_keys())

    def clear(self, message="OmniPad per USB verbinden"):
        if self.state is None and self.title.get() == message:
            return
        self.state = None
        self.layers = ()
        self.mask = 0
        self.title.set(message)
        self.render()

    def update_from_pad(self, state, layers, mask):
        if state is None or not layers:
            self.clear("Aktive Layer auslesen ab Firmware 9")
            return
        changed = state != self.state or layers != self.layers
        old_mask = self.mask
        self.state, self.layers, self.mask = state, layers, mask
        if changed:
            self.render()
        elif old_mask != mask:
            self.draw_keys()

    def select_layer(self, index):
        self.index = index
        self.follow.set(False)
        self.render()

    def render(self):
        for widget in self.tabs.winfo_children():
            widget.destroy()
        self.follow_button.configure(state="normal" if self.layers else "disabled")
        if self.layers:
            shown = self.state.shown
            if self.follow.get() and shown is not None and 0 <= shown < len(self.layers):
                self.index = shown
            self.index = min(self.index, len(self.layers) - 1)
            active = self.state.active
            title = self.state.source
            if active is not None and active < len(self.layers):
                title += f" · Aktiv: {self.layers[active].name}"
            if not self.state.direct and self.state.source == "Firmware":
                title += " · Standardbelegung"
            self.title.set(title)
            for index, layer in enumerate(self.layers):
                text = f"● {layer.name}" if index == active else layer.name
                tk.Button(self.tabs, text=text, bg=layer.color if index == self.index else KEY,
                          fg=BG if index == self.index else TEXT, relief="flat",
                          padx=9, pady=5, command=lambda i=index: self.select_layer(i)).grid(
                    row=index // 6, column=index % 6, sticky="ew", padx=(0, 5), pady=(0, 4))
        self.draw_keys()

    def draw_keys(self):
        canvas = self.canvas
        canvas.delete("all")
        if not self.layers:
            return
        layer = self.layers[self.index]
        width, height = canvas.winfo_width(), canvas.winfo_height()
        step_x = min(176, max(50, (width - 40) / 5))
        step_y = min(110, max(52, (height - 32) / 3))
        left = (width - step_x * 5) / 2

        def tile(index, title, column, row, columns=1, rows=1):
            x, y = left + column * step_x, 16 + row * step_y
            w, h = columns * step_x - 8, rows * step_y - 8
            down = self.state.active == self.index and self.mask & (1 << index)
            canvas.create_rectangle(x, y, x + w, y + h,
                                    fill="#2e6656" if down else KEY, outline="#424e5c")
            canvas.create_text(x + 10, y + 8, text=title, fill=MUTED, anchor="nw",
                               font=("Segoe UI", 10))
            canvas.create_text(x + 10, y + h - 8, text=layer.labels[index], width=max(30, w - 20),
                               fill=TEXT, anchor="sw", font=("Segoe UI", 12, "bold"))

        for index, key in enumerate(self.keys):
            tile(index, f"K{index + 1}", key["x"], key["y"], key.get("w", 1), key.get("h", 1))
        tile(11, "K0", 4, 0)
        tile(10, "Encoder-Druck", 4, 1)
