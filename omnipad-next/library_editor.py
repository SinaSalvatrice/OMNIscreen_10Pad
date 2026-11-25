"""Editors for reusable text snippets and focus-scoped keyboard recordings."""

import tkinter as tk
from tkinter import messagebox, ttk
from uuid import uuid4

from key_actions import MacroCapture, compile_entry, step_label


class LibraryEditor(tk.Toplevel):
    def __init__(self, app, kind, on_save, entry=None):
        super().__init__(app.root)
        self.title("Text-Snippet" if kind == "text" else "Makrorecorder")
        self.transient(app.root)
        self.minsize(500, 350)
        self.app = app
        self.kind = kind
        self.on_save = on_save
        self.identifier = entry["id"] if entry else uuid4().hex
        self.steps = entry.get("steps", []) if entry else []
        self.capture = None
        body = app.card(self)
        body.pack(fill="both", expand=True)
        app.text(body, "Name").pack(anchor="w")
        self.name = ttk.Entry(body)
        self.name.pack(fill="x", pady=(2, 10))
        if entry:
            self.name.insert(0, entry["name"])
        if kind == "text":
            app.text(body, "Text für deutsches Tastaturlayout", bold=True).pack(anchor="w")
            self.snippet = tk.Text(body, wrap="word", height=8, undo=True)
            self.snippet.pack(fill="both", expand=True, pady=(3, 9))
            if entry:
                self.snippet.insert("1.0", entry["text"])
        else:
            self.build_recorder(body)
        footer = tk.Frame(body, bg=body.cget("bg"))
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="Abbrechen", command=self.destroy).pack(side="right")
        self.save_button = ttk.Button(footer, text="Übernehmen", command=self.save)
        self.save_button.pack(side="right", padx=6)
        self.name.focus_set()
        self.grab_set()

    def build_recorder(self, body):
        toolbar = tk.Frame(body, bg=body.cget("bg"))
        toolbar.pack(fill="x", pady=(0, 8))
        self.start_button = ttk.Button(toolbar, text="Aufnahme starten", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(toolbar, text="Stopp", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        self.record_status = tk.StringVar(value="Tastendrücke im Aufnahmefeld werden aufgezeichnet.")
        ttk.Label(body, textvariable=self.record_status, wraplength=440).pack(anchor="w")
        self.record_field = ttk.Entry(body)
        self.record_field.pack(fill="x", pady=(4, 8))
        self.record_field.state(["disabled"])
        self.record_field.bind("<KeyPress>", lambda event: self.record(event, True))
        self.record_field.bind("<KeyRelease>", lambda event: self.record(event, False))
        self.record_field.bind("<FocusOut>", lambda _: self.stop())
        frame = tk.Frame(body)
        frame.pack(fill="both", expand=True)
        self.step_display = tk.Listbox(frame, height=7)
        scrollbar = ttk.Scrollbar(frame, command=self.step_display.yview)
        self.step_display.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.step_display.pack(side="left", fill="both", expand=True)
        self.show_steps(self.steps)

    def show_steps(self, steps):
        self.step_display.delete(0, "end")
        for step in steps:
            self.step_display.insert("end", step_label(step))
        self.step_display.see("end")

    def start(self):
        self.capture = MacroCapture()
        self.show_steps([])
        self.record_field.state(["!disabled"])
        self.start_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self.save_button.state(["disabled"])
        self.record_status.set("Aufnahme läuft. Zum Beenden auf Stopp klicken.")
        self.record_field.focus_force()

    def stop(self, status=None):
        if self.capture is None:
            return
        self.steps = self.capture.finish()
        self.capture = None
        self.record_field.state(["disabled"])
        self.start_button.state(["!disabled"])
        self.stop_button.state(["disabled"])
        self.save_button.state(["!disabled"])
        self.show_steps(self.steps)
        self.record_status.set(status or f"Aufnahme beendet · {len(self.steps)} Schritte")

    def record(self, event, pressed):
        if self.capture is not None:
            try:
                self.capture.event(pressed, event.keysym, event.keycode, event.char)
                self.show_steps(self.capture.steps)
            except ValueError as exc:
                self.stop(str(exc))
        return "break"

    def save(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showerror(self.title(), "Bitte einen Namen eingeben.", parent=self)
            return
        entry = {"id": self.identifier, "kind": self.kind, "name": name}
        if self.kind == "text":
            entry["text"] = self.snippet.get("1.0", "end-1c")
        else:
            entry["steps"] = self.steps
        try:
            compile_entry(entry)
        except ValueError as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return
        self.on_save(entry)
        self.destroy()
