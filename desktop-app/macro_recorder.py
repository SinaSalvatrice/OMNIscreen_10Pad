"""Focus-scoped keyboard macro recorder for OmniPad Snippets.

No global keyboard hook, clipboard reading, background capture or execution.
Only captures keys received by the explicit Tk recording surface.
"""

from time import monotonic
import tkinter as tk
from tkinter import messagebox, ttk

from profile import BASIC_CODES, compile_snippet, german_key, label_for_code
from ui_helpers import BG, PANEL, KEY, TEXT, MUTED, ACCENT, button, label


MODIFIER_KEYSYMS = {
    "Control_L": 224, "Control_R": 228,
    "Shift_L": 225, "Shift_R": 229,
    "Alt_L": 226, "Alt_R": 230, "ISO_Level3_Shift": 230,
    "Meta_L": 227, "Meta_R": 231, "Super_L": 227,
    "Super_R": 231, "Win_L": 227, "Win_R": 231,
}

KEYSYMS = {
    "Return": 40, "KP_Enter": 40, "Escape": 41,
    "BackSpace": 42, "Tab": 43, "ISO_Left_Tab": 43, "space": 44,
    "Insert": 73, "Home": 74, "Prior": 75, "Delete": 76,
    "End": 77, "Next": 78, "Right": 79, "Left": 80,
    "Down": 81, "Up": 82, "Print": 70, "Pause": 72,
    "Caps_Lock": 57, "Num_Lock": 83, "Scroll_Lock": 71,
    "KP_Divide": 84, "KP_Multiply": 85, "KP_Subtract": 86,
    "KP_Add": 87, "KP_Decimal": 99,
    "KP_0": 98, "KP_1": 89, "KP_2": 90, "KP_3": 91,
    "KP_4": 92, "KP_5": 93, "KP_6": 94,
    "KP_7": 95, "KP_8": 96, "KP_9": 97,
}
SYMBOLS = {
    "comma": ",", "period": ".", "minus": "-", "plus": "+",
    "numbersign": "#", "less": "<", "greater": ">",
    "ssharp": "ß", "adiaeresis": "ä",
    "odiaeresis": "ö", "udiaeresis": "ü",
    "asterisk": "*", "semicolon": ";", "colon": ":",
    "underscore": "_", "exclam": "!", "question": "?",
}


def keysym_code(keysym):
    if keysym in MODIFIER_KEYSYMS:
        return MODIFIER_KEYSYMS[keysym]
    if keysym in KEYSYMS:
        return KEYSYMS[keysym]
    if len(keysym) == 1:
        if keysym.upper() in BASIC_CODES and keysym.isalnum():
            return BASIC_CODES[keysym.upper()]
        try:
            return german_key(keysym) & 0xFFFF
        except ValueError:
            return None
    if keysym in SYMBOLS:
        try:
            return german_key(SYMBOLS[keysym]) & 0xFFFF
        except ValueError:
            return None
    if keysym in BASIC_CODES:
        return BASIC_CODES[keysym]
    if keysym.startswith("F") and keysym[1:].isdigit():
        return BASIC_CODES.get(keysym)
    return None


def parse_snippet_lines(text):
    result = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        kind, separator, value = line.partition(" ")
        if not separator or kind not in ("text", "tap", "down", "up", "delay"):
            raise ValueError(f"Zeile {lineno}: Ungültiger Makroschritt „{line}“.") 
        if kind == "text":
            result.append({"type": kind, "value": value})
            continue
        value = value.strip()
        if not value:
            raise ValueError(f"Zeile {lineno}: Kein Wert angegeben.")
        try:
            number = int(value, 10) if kind == "delay" else BASIC_CODES.get(value, None)
            if number is None:
                number = int(value, 16)
        except ValueError as error:
            raise ValueError(f"Zeile {lineno}: Unbekannter Keycode „{value}“.") from error
        result.append({"type": kind, "value": number})
    return result


def format_snippet_lines(steps):
    lines = []
    for step in steps:
        kind, value = step["type"], step["value"]
        if kind in ("tap", "down", "up"):
            value = label_for_code(value)
        lines.append(f"{kind} {value}")
    return "\n".join(lines)


class MacroCapture:
    """Ordered key-down/up events; physical key ID handles shifted key releases."""

    MAX_EVENTS = 260

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.steps = []
        self.pressed = {}  # Tk hardware keycode -> QMK keycode
        self.last_time = None

    def _append(self, kind, value, now):
        if len(self.steps) + len(self.pressed) + 2 >= self.MAX_EVENTS:
            raise ValueError("Aufnahmelimit erreicht. Bitte Aufnahme beenden und kürzen.")
        if self.last_time is not None:
            elapsed = max(0, round((now - self.last_time) * 1000))
            # Noise below 20 ms is not useful and consumes the tiny macro pool.
            while elapsed >= 20:
                duration = min(elapsed, 60000)
                self.steps.append({"type": "delay", "value": duration})
                elapsed -= duration
                if len(self.steps) + len(self.pressed) + 2 >= self.MAX_EVENTS:
                    raise ValueError("Aufnahmelimit erreicht.")
        self.steps.append({"type": kind, "value": value})
        self.last_time = now

    def press(self, keysym, physical=None, now=None):
        code = keysym_code(keysym)
        if code is None:
            raise ValueError(f"Taste „{keysym}“ wird noch nicht unterstützt.")
        identifier = physical if physical is not None else keysym
        if identifier in self.pressed:
            return False  # Ignore Windows keyboard auto-repeat.
        moment = self.clock() if now is None else now
        self._append("down", code, moment)
        self.pressed[identifier] = code
        return True

    def release(self, keysym, physical=None, now=None):
        identifier = physical if physical is not None else keysym
        if identifier not in self.pressed:
            return False
        code = self.pressed.pop(identifier)
        moment = self.clock() if now is None else now
        self._append("up", code, moment)
        return True

    def finish(self):
        # A stop click or focus loss can occur with Ctrl/Shift still held.
        # Emit their release events without recording the stop-click delay.
        for code in reversed(list(self.pressed.values())):
            self.steps.append({"type": "up", "value": code})
        self.pressed.clear()
        return list(self.steps)


class MacroRecorder(tk.Toplevel):
    """Explicit opt-in recorder. Does not listen to other applications."""

    def __init__(self, parent, *, default_name, target_description, on_save):
        super().__init__(parent)
        self.title("OmniPad · Makro aufnehmen")
        self.geometry("750x680")
        self.minsize(650, 565)
        self.configure(bg=BG)
        self.transient(parent)
        self.on_save = on_save
        self.capture = MacroCapture()
        self.recording = False
        self.name_value = tk.StringVar(value=default_name)
        self.status = tk.StringVar(value="Bereit. Aufnahme starten und im Aufnahmefeld tippen.")
        self.protocol("WM_DELETE_WINDOW", self.close)

        header = tk.Frame(self, bg=PANEL)
        header.pack(fill="x", padx=15, pady=(12, 8))
        label(header, "Tastenkombinationen und Tastenfolgen aufzeichnen", size=13).pack(
            anchor="w", padx=12, pady=(9, 4))
        label(header, "Nur dieses Fenster wird aufgenommen. Keine systemweite Tastaturüberwachung. "
              "Keine Passwörter aufnehmen.", color=MUTED, wraplength=690).pack(
            anchor="w", padx=12, pady=(0, 9))

        name_row = tk.Frame(self, bg=PANEL)
        name_row.pack(fill="x", padx=15, pady=5)
        label(name_row, "Name").pack(side="left", padx=10)
        ttk.Entry(name_row, textvariable=self.name_value).pack(side="left", fill="x", expand=True, padx=12, pady=8)

        self.record_surface = tk.Frame(self, bg=KEY, height=108, takefocus=True,
                                       highlightthickness=2, highlightbackground="#516071",
                                       highlightcolor=ACCENT)
        self.record_surface.pack(fill="x", padx=18, pady=(10, 5))
        self.record_surface.pack_propagate(False)
        label(self.record_surface, "HIER TASTEN AUFNEHMEN", size=13, color=ACCENT).pack(
            anchor="center", pady=(24, 2))
        label(self.record_surface, "Strg+V, Alt+Tab, mehrere Tasten und Pausen. Esc beendet die Aufnahme.",
              size=9, color=MUTED).pack(anchor="center")
        self.record_surface.bind("<KeyPress>", self.key_pressed)
        self.record_surface.bind("<KeyRelease>", self.key_released)
        self.record_surface.bind("<FocusOut>", self.lost_focus)

        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", padx=18, pady=8)
        self.start_button = button(actions, "Aufnahme starten", self.start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = button(actions, "Aufnahme stoppen", self.stop)
        self.stop_button.pack(side="left")
        self.stop_button.configure(state="disabled")
        label(self, textvariable=self.status, color=MUTED, wraplength=690).pack(
            fill="x", padx=18, pady=(0, 6))
        label(self, "Aufgenommene Schritte (nach dem Stoppen editierbar):", color=MUTED).pack(
            anchor="w", padx=18)
        self.preview = tk.Text(self, height=14, bg=KEY, fg=TEXT,
                               insertbackground=TEXT, font=("Consolas", 11),
                               undo=True, relief="flat")
        self.preview.pack(fill="both", expand=True, padx=18, pady=(6, 10))
        self.preview.configure(state="disabled")
        self.target_description = target_description
        label(self, f"Ausgewählte Pad-Taste: {target_description}", color=MUTED).pack(
            anchor="w", padx=18, pady=(0, 5))
        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=18, pady=(0, 15))
        self.save_button = button(footer, "In Bibliothek speichern", lambda: self.save(False))
        self.save_button.pack(side="left", padx=(0, 8))
        self.assign_button = button(footer, "Speichern + Taste belegen", lambda: self.save(True))
        self.assign_button.pack(side="left", padx=(0, 8))
        button(footer, "Verwerfen", self.close).pack(side="right")
        self.save_button.configure(state="disabled")
        self.assign_button.configure(state="disabled")
        self.grab_set()

    def start(self):
        self.capture = MacroCapture()
        self.recording = True
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.save_button.configure(state="disabled")
        self.assign_button.configure(state="disabled")
        self.status.set("AUFNAHME LÄUFT · nur Tasten innerhalb des Aufnahmefelds · Esc = Stopp")
        self.record_surface.focus_set()

    def _render(self):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", format_snippet_lines(self.capture.steps))
        if self.recording:
            self.preview.configure(state="disabled")
        self.status.set(f"{len(self.capture.steps)} Schritte · {len(self.capture.steps) * 3} Byte Rohdaten")

    def key_pressed(self, event):
        if not self.recording:
            return "break"
        if event.keysym == "Escape":
            self.stop()
            return "break"
        try:
            if self.capture.press(event.keysym, event.keycode):
                self._render()
        except ValueError as error:
            self.stop()
            messagebox.showwarning("Aufnahme beendet", str(error), parent=self)
        return "break"

    def key_released(self, event):
        if self.recording:
            try:
                if self.capture.release(event.keysym, event.keycode):
                    self._render()
            except ValueError as error:
                self.stop()
                messagebox.showwarning("Aufnahme beendet", str(error), parent=self)
        return "break"

    def lost_focus(self, _event):
        # Keep key capture opt-in and focus-scoped even if another widget wins focus.
        if self.recording:
            self.stop()

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        self.capture.finish()
        self._render()
        self.preview.configure(state="normal")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.save_button.configure(state="normal")
        self.assign_button.configure(state="normal")
        self.status.set("Aufnahme beendet. Schritte kontrollieren oder bearbeiten, dann speichern.")

    def save(self, assign):
        if self.recording:
            self.stop()
        try:
            name = self.name_value.get().strip()
            if not name:
                raise ValueError("Bitte einen Namen für das Makro angeben.")
            steps = parse_snippet_lines(self.preview.get("1.0", "end-1c"))
            if not steps:
                raise ValueError("Keine Schritte aufgenommen.")
            compile_snippet({"name": name, "steps": steps})
            if self.on_save(name, steps, assign):
                self.close()
        except (TypeError, ValueError) as error:
            messagebox.showerror("Makro prüfen", str(error), parent=self)

    def close(self):
        self.recording = False
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
