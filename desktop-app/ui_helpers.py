"""Small reusable Tk controls for the OmniPad editor."""

import tkinter as tk
from tkinter import ttk, colorchooser

BG, PANEL, KEY = "#17191d", "#21262d", "#303740"
TEXT, MUTED, ACCENT = "#f0eee9", "#aab5c2", "#e7a57c"


def label(parent, text="", size=10, color=TEXT, **options):
    return tk.Label(parent, text=text, bg=PANEL, fg=color, font=("Segoe UI", size),
                    anchor="w", justify="left", **options)


def button(parent, text, command, **options):
    return ttk.Button(parent, text=text, command=command, **options)


class ScrollPanel(tk.Frame):
    def __init__(self, parent, width=300):
        super().__init__(parent, bg=PANEL, width=width)
        self.pack_propagate(False)
        canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.content = tk.Frame(canvas, bg=PANEL)
        handle = canvas.create_window((0, 0), window=self.content, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(handle, width=event.width))
        # Bind locally so scrolling elsewhere keeps its own behavior.
        self.content.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", self._wheel))
        self.content.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))
        self.canvas = canvas

    def _wheel(self, event):
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def clear(self):
        for widget in self.content.winfo_children():
            widget.destroy()


class Form:
    def __init__(self, parent):
        self.parent = parent
        self.readers = {}
        self.widgets = {}

    def title(self, text):
        label(self.parent, text, 13).pack(anchor="w", padx=14, pady=(14, 8))

    def note(self, text):
        label(self.parent, text, 9, color=MUTED, wraplength=265).pack(
            anchor="w", padx=14, pady=(4, 10))

    def entry(self, name, caption, value, *, kind=str):
        label(self.parent, caption, 9, color=MUTED).pack(anchor="w", padx=14, pady=(5, 2))
        variable = tk.StringVar(value=str(value))
        widget = ttk.Entry(self.parent, textvariable=variable)
        widget.pack(fill="x", padx=14, pady=(0, 3))
        def read():
            text = variable.get()
            if kind is int:
                try:
                    return int(text)
                except ValueError:
                    raise ValueError(f"„{caption}“ benötigt eine ganze Zahl.")
            if kind == "code":
                from profile import BASIC_CODES
                if text in BASIC_CODES:
                    return BASIC_CODES[text]
                try:
                    code = int(text, 16)
                except ValueError:
                    raise ValueError(f"„{caption}“ benötigt einen Hex-Keycode.")
                if not 0 <= code <= 65535:
                    raise ValueError("Keycode liegt außerhalb des gültigen Bereichs.")
                return code
            return text
        self.readers[name], self.widgets[name] = read, widget
        return variable

    def choice(self, name, caption, value, choices):
        label(self.parent, caption, 9, color=MUTED).pack(anchor="w", padx=14, pady=(5, 2))
        variable = tk.StringVar(value=choices[value])
        widget = ttk.Combobox(self.parent, values=choices, textvariable=variable, state="readonly")
        widget.pack(fill="x", padx=14, pady=(0, 3))
        self.readers[name] = lambda: choices.index(variable.get())
        self.widgets[name] = widget
        return variable

    def check(self, name, caption, value):
        variable = tk.BooleanVar(value=value)
        widget = ttk.Checkbutton(self.parent, text=caption, variable=variable)
        widget.pack(anchor="w", padx=14, pady=5)
        self.readers[name] = variable.get
        self.widgets[name] = widget
        return variable

    def color(self, name, caption, value):
        variable = tk.StringVar(value=value)
        row = tk.Frame(self.parent, bg=PANEL)
        row.pack(fill="x", padx=14, pady=5)
        swatch = tk.Button(row, text=caption, bg=value, fg="#ffffff", relief="flat")
        def pick():
            chosen = colorchooser.askcolor(variable.get(), parent=self.parent)[1]
            if chosen:
                variable.set(chosen)
                swatch.configure(bg=chosen)
        swatch.configure(command=pick)
        swatch.pack(fill="x")
        self.readers[name] = variable.get
        self.widgets[name] = swatch
        return variable

    def values(self):
        return {name: read() for name, read in self.readers.items()}

    def apply(self, command, caption="Übernehmen"):
        button(self.parent, caption, command).pack(fill="x", padx=14, pady=(14, 10))


def style(root):
    root.configure(bg=BG)
    root.option_add("*Font", ("Segoe UI", 10))
    theme = ttk.Style(root)
    theme.theme_use("clam")
    theme.configure(".", background=PANEL, foreground=TEXT, fieldbackground=KEY)
    theme.configure("TButton", background=KEY, foreground=TEXT, padding=(10, 5))
    theme.map("TButton", background=[("active", "#4b4140")], foreground=[("disabled", "#72808a")])
    theme.configure("TEntry", fieldbackground=KEY, foreground=TEXT, insertcolor=TEXT)
    theme.configure("TCombobox", fieldbackground=KEY, foreground=TEXT)
    theme.map("TCombobox", fieldbackground=[("readonly", KEY)], foreground=[("readonly", TEXT)])
    theme.configure("TNotebook", background=BG, borderwidth=0)
    theme.configure("TNotebook.Tab", background=KEY, foreground=MUTED, padding=(14, 8))
    theme.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", ACCENT)])
    theme.configure("Treeview", background=KEY, fieldbackground=KEY, foreground=TEXT, rowheight=27)
    theme.map("Treeview", background=[("selected", "#73503d")])
