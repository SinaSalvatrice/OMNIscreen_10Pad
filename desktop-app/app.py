"""Windows editor for the OMNIscreen 10Pad."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from via import FIXED_KEYS, OmniPad, UnsupportedCommand


ROOT = Path(__file__).resolve().parent.parent
BG, PANEL, KEY = "#17191d", "#21252b", "#303640"
TEXT, MUTED, ACCENT = "#f0eee9", "#aeb3bc", "#edac84"
ACTIONS = {
    "Leer": 0x0000,
    "Transparent": 0x0001,
    "Enter": 0x0028,
    "Esc": 0x0029,
    "Leertaste": 0x002C,
    "Pfeil links": 0x0050,
    "Pfeil rechts": 0x004F,
    "Pfeil hoch": 0x0052,
    "Pfeil runter": 0x0051,
    "Kopieren": 0x0106,
    "Einfügen": 0x0119,
    "Speichern": 0x0116,
    "F24": 0x0073,
}
ACTION_LABELS = {code: label for label, code in ACTIONS.items()}


def keycode_label(code):
    if code in ACTION_LABELS:
        return ACTION_LABELS[code]
    if 4 <= code <= 29:
        return chr(ord("A") + code - 4)
    return f"0x{code:04X}"


class Editor:
    def __init__(self, window):
        self.window = window
        self.window.title("OmniPad Editor")
        self.window.geometry("970x620")
        self.window.minsize(900, 590)
        self.window.configure(bg=BG)
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.after_poll = None
        self.closing = False
        self.device = None
        self.keys = json.loads((ROOT / "keyboards/icst7789v/keyboard.json").read_text())[
            "layouts"]["LAYOUT"]["layout"]
        self.layers = json.loads((ROOT / "design/layer_system.json").read_text())["layers"]
        self.keymap, self.encoders = [], []
        self.layer = 0
        self.target = ("key", *self.keys[0]["matrix"])
        self.undo = []
        self.detect_supported = False
        self.detect_last = None
        self.rectangles = {}

        header = tk.Frame(window, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 14))
        self.label(header, "OmniPad Editor", 24).pack(side="left")
        self.connect_button = ttk.Button(header, text="Verbinden", command=self.connect)
        self.connect_button.pack(side="right")
        self.backup_button = ttk.Button(header, text="VIA-Sicherung", command=self.backup)
        self.backup_button.pack(side="right", padx=8)
        self.status = tk.StringVar(value="USB-Verbindung wird geprüft …")
        self.label(window, variable=self.status, color=MUTED).pack(anchor="w", padx=24)
        self.tabs = tk.Frame(window, bg=BG)
        self.tabs.pack(fill="x", padx=24, pady=(18, 8))

        workspace = tk.Frame(window, bg=BG)
        workspace.pack(fill="both", expand=True, padx=24, pady=(0, 22))
        left = tk.Frame(workspace, bg=PANEL)
        left.pack(side="left", fill="both", expand=True)
        self.label(left, "Tastenlayout", 14, bg=PANEL).pack(anchor="w", padx=18, pady=(14, 4))
        self.canvas = tk.Canvas(left, width=555, height=320, bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10)
        self.canvas.bind("<Button-1>", self.select_at)
        self.canvas.bind("<Configure>", lambda _: self.draw())
        self.detect_message = tk.StringVar(value="Live-Inspektor wartet auf das OmniPad.")
        self.label(left, variable=self.detect_message, bg=PANEL, color=MUTED, wraplength=540).pack(
            anchor="w", padx=18, pady=(4, 16))

        sidebar = tk.Frame(workspace, bg=PANEL, width=265)
        sidebar.pack(side="right", fill="y", padx=(12, 0))
        sidebar.pack_propagate(False)
        self.selection = tk.StringVar(value="K1")
        self.label(sidebar, variable=self.selection, size=14, bg=PANEL).pack(
            anchor="w", padx=16, pady=(14, 3))
        self.details = tk.StringVar()
        self.label(sidebar, variable=self.details, bg=PANEL, color=MUTED, wraplength=220).pack(
            anchor="w", padx=16)
        self.code = tk.StringVar()
        self.entry = ttk.Entry(sidebar, textvariable=self.code)
        self.entry.pack(fill="x", padx=16, pady=(12, 6))
        self.entry.bind("<Return>", lambda _: self.save())
        self.save_button = ttk.Button(sidebar, text="Auf Gerät speichern", command=self.save)
        self.save_button.pack(fill="x", padx=16)
        self.undo_button = ttk.Button(sidebar, text="Letzte Änderung rückgängig", command=self.revert)
        self.undo_button.pack(fill="x", padx=16, pady=(5, 12))
        self.label(sidebar, "Aktionen", bg=PANEL).pack(anchor="w", padx=16)
        self.label(sidebar, "Doppelklick oder auf eine Taste ziehen.", 9, bg=PANEL, color=MUTED).pack(
            anchor="w", padx=16, pady=(0, 5))
        self.palette = tk.Listbox(
            sidebar, bg=KEY, fg=TEXT, selectbackground="#805b49", relief="flat",
            highlightthickness=0, exportselection=False)
        self.palette.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        for action in ACTIONS:
            self.palette.insert("end", action)
        self.palette.bind("<Double-Button-1>", lambda _: self.choose_action())
        self.palette.bind("<ButtonRelease-1>", self.drop_action)

        self.refresh_selection()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.after(120, self.connect)
        self.window.after(60, self.tick)

    @staticmethod
    def label(parent, text="", size=10, bg=BG, color=TEXT, variable=None, **options):
        return tk.Label(parent, text=text, textvariable=variable, bg=bg, fg=color,
                        font=("Segoe UI", size), justify="left", **options)

    def submit(self, task, done, *, polling=False):
        if self.pending:
            if self.pending[2] and not polling and not self.after_poll:
                self.after_poll = lambda: self.submit(task, done)
                self.refresh_buttons()
            return
        self.pending = self.worker.submit(task), done, polling
        if not polling:
            self.refresh_buttons()

    def tick(self):
        if self.pending:
            future, done, polling = self.pending
            if future.done():
                self.pending = None
                after_poll, self.after_poll = self.after_poll, None
                try:
                    result = future.result()
                except (OSError, RuntimeError, ValueError) as error:
                    if self.device:
                        self.device.close()
                        self.device = None
                        self.keymap, self.encoders = [], []
                        self.undo.clear()
                        self.detect_supported = False
                        self.detect_last = None
                        self.refresh_tabs()
                        self.refresh_selection()
                        self.draw()
                    self.status.set(str(error))
                    self.detect_message.set("Live-Inspektor wartet auf eine USB-Verbindung.")
                else:
                    done(result)
                    if after_poll and not self.closing:
                        after_poll()
                if not polling or after_poll:
                    self.refresh_buttons()
        elif self.device and self.detect_supported and not self.closing:
            self.submit(self.device.detection, self.update_detection, polling=True)
        self.window.after(90, self.tick)

    def connect(self):
        if self.pending:
            if self.pending[2] and not self.after_poll:
                self.after_poll = self.connect
                self.refresh_buttons()
            return
        if self.device:
            self.device.close()
            self.device = None
            self.detect_supported = False
            self.detect_last = None
            self.keymap, self.encoders = [], []
            self.refresh_tabs()
            self.refresh_selection()
            self.draw()
        self.status.set("OmniPad wird ausgelesen …")

        def read():
            device = OmniPad.connect()
            try:
                keys, encoders = device.keymap(), device.encoder_map()
                try:
                    detection = device.detection()
                except UnsupportedCommand:
                    detection = None
                return device, keys, encoders, detection
            except Exception:
                device.close()
                raise

        def connected(result):
            self.device, self.keymap, self.encoders, detection = result
            self.detect_supported = detection is not None
            self.detect_last = None
            self.layer = min(self.layer, len(self.keymap) - 1)
            self.undo.clear()
            self.status.set(
                f"USB verbunden  ·  {len(self.keymap)} Layer  ·  "
                f"VIA {self.device.protocol}  ·  Firmware {self.device.firmware}")
            if self.detect_supported:
                self.update_detection(detection)
            else:
                self.detect_message.set("Live-Inspektor verfügbar mit der neuen OmniPad-Firmware.")
            self.refresh_tabs()
            self.refresh_selection()
            self.draw()

        self.submit(read, connected)

    def refresh_tabs(self):
        for child in self.tabs.winfo_children():
            child.destroy()
        active = self.detect_last.active_layer if self.detect_last else None
        for index in range(len(self.keymap)):
            data = self.layers[index] if index < len(self.layers) else {}
            text = data.get("name", f"Layer {index + 1}")
            if index == active:
                text = f"● {text}"
            color = data.get("accent", ACCENT)
            button = tk.Button(
                self.tabs, text=text, bg=color if index == self.layer else KEY,
                fg=BG if index == self.layer else color, activebackground=color,
                activeforeground=BG, relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                command=lambda i=index: self.select_layer(i))
            button.pack(side="left", padx=(0, 5))

    def select_layer(self, index):
        self.layer = index
        self.refresh_tabs()
        self.refresh_selection()
        self.draw()

    def refresh_buttons(self):
        busy = bool(self.after_poll or (self.pending and not self.pending[2]))
        editable = self.value() is not None and self.target[1:] not in FIXED_KEYS
        self.connect_button.configure(state="disabled" if busy else "normal",
                                      text="Neu verbinden" if self.device else "Verbinden")
        self.backup_button.configure(state="normal" if self.device and not busy else "disabled")
        self.entry.configure(state="normal" if editable and not busy else "disabled")
        self.save_button.configure(state="normal" if editable and not busy else "disabled")
        self.undo_button.configure(state="normal" if self.undo and not busy else "disabled")

    def value(self, target=None):
        if not self.device:
            return None
        kind, *position = target or self.target
        if kind == "key":
            row, col = position
            return self.keymap[self.layer][row][col]
        if kind == "encoder":
            return self.encoders[self.layer][position[0]]
        return None

    def refresh_selection(self):
        kind, *position = self.target
        if kind == "key":
            index = next(i for i, key in enumerate(self.keys, 1) if key["matrix"] == position)
            self.selection.set(f"K{index}")
            fixed = FIXED_KEYS.get(tuple(position))
            self.details.set(f"Fest belegt · {fixed}" if fixed else
                             f"Matrixzeile {position[0]} · Spalte {position[1]}")
        elif kind == "encoder":
            self.selection.set("Encoder links" if position[0] == 0 else "Encoder rechts")
            self.details.set("Drehung · Belegung für diesen Layer")
        else:
            self.selection.set("K0" if kind == "k0" else "Encoder-Druck")
            self.details.set("Aktion ist in dieser Firmware fest eingebaut.")
        code = self.value()
        self.code.set("" if code is None else f"0x{code:04X}")
        self.refresh_buttons()

    def draw(self):
        c = self.canvas
        c.delete("all")
        self.rectangles.clear()
        step = min(105, max(74, (c.winfo_width() - 155) // 4))
        x_offset, y_offset = 20, 31
        detect = self.detect_last
        for index, key in enumerate(self.keys):
            target = ("key", *key["matrix"])
            x, y = x_offset + key["x"] * step, y_offset + key["y"] * 76
            w, h = key.get("w", 1) * step - 8, key.get("h", 1) * 76 - 8
            value = self.value(target)
            fixed = FIXED_KEYS.get(tuple(key["matrix"]))
            down = bool(detect and detect.enabled and detect.mask & (1 << index))
            last = bool(detect and detect.enabled and detect.last_key == index)
            detail = fixed or ("—" if value is None else keycode_label(value))
            self.draw_key(target, x, y, w, h, f"K{index + 1}", detail, down, last)
        x = x_offset + 4 * step + 12
        self.draw_key(("k0",), x, 31, 94, 50, "K0", "Modul")
        self.draw_key(("push",), x, 88, 94, 50, "Encoder", "Drücken")
        for direction, label in enumerate(("Links", "Rechts")):
            target = ("encoder", direction)
            value = self.value(target)
            self.draw_key(target, x, 145 + direction * 57, 94, 50, label,
                          "—" if value is None else keycode_label(value))

    def draw_key(self, target, x, y, w, h, title, detail, down=False, last=False):
        self.rectangles[target] = (x, y, x + w, y + h)
        self.canvas.create_rectangle(
            x, y, x + w, y + h, fill="#2d6353" if down else KEY,
            outline=ACCENT if target == self.target else "#3b444e", width=2)
        if last:
            self.canvas.create_oval(x + w - 15, y + 8, x + w - 7, y + 16,
                                    fill="#8be3ba", outline="")
        self.canvas.create_text(x + 8, y + 8, text=title, fill=MUTED, anchor="nw",
                                font=("Segoe UI", 9))
        self.canvas.create_text(x + 8, y + h - 8, text=detail, fill=TEXT, anchor="sw",
                                font=("Segoe UI", 11, "bold"))

    def target_at(self, x, y):
        for target, (left, top, right, bottom) in self.rectangles.items():
            if left <= x <= right and top <= y <= bottom:
                return target
        return None

    def select_target(self, target):
        self.target = target
        self.refresh_selection()
        self.draw()

    def select_at(self, event):
        target = self.target_at(event.x, event.y)
        if target:
            self.select_target(target)

    def choose_action(self):
        selected = self.palette.curselection()
        if selected and self.value() is not None and self.target[1:] not in FIXED_KEYS:
            self.code.set(f"0x{ACTIONS[self.palette.get(selected[0])]:04X}")

    def drop_action(self, event):
        x = event.x_root - self.canvas.winfo_rootx()
        y = event.y_root - self.canvas.winfo_rooty()
        target = self.target_at(x, y)
        if target:
            self.select_target(target)
            self.choose_action()

    def save(self):
        if self.pending and not self.pending[2]:
            return
        if self.value() is None or self.target[1:] in FIXED_KEYS:
            return
        try:
            code = int(self.code.get(), 16)
            if not 0 <= code <= 0xFFFF:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Ungültiger Keycode", "Bitte einen Hex-Wert von 0x0000 bis 0xFFFF eingeben.")
            return
        layer, target, previous = self.layer, self.target, self.value()
        if code != previous:
            self.change(layer, target, previous, code)

    def change(self, layer, target, previous, code, undoing=False):
        def written(_):
            if target[0] == "key":
                _, row, col = target
                self.keymap[layer][row][col] = code
            else:
                self.encoders[layer][target[1]] = code
            if undoing:
                self.undo.pop()
            else:
                self.undo.append((layer, target, previous, code))
            self.status.set(f"Layer {layer + 1} · 0x{code:04X} gespeichert und ausgelesen.")
            self.refresh_selection()
            self.draw()

        self.submit(lambda: self.device.set_binding(layer, target, previous, code), written)

    def revert(self):
        if self.undo:
            layer, target, previous, current = self.undo[-1]
            self.change(layer, target, current, previous, undoing=True)

    def backup(self):
        if not self.device:
            return
        destination = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile="omnipad-via-backup.json",
            filetypes=[("JSON", "*.json")])
        if destination:
            def write():
                data = json.dumps(self.device.snapshot(), indent=2) + "\n"
                path = Path(destination)
                temporary = path.with_name(path.name + ".tmp")
                temporary.write_text(data, encoding="utf-8")
                temporary.replace(path)

            self.submit(write, lambda _: self.status.set(f"VIA-Sicherung gespeichert · {destination}"))

    def update_detection(self, detection):
        old = self.detect_last
        if old == detection:
            return
        self.detect_last = detection
        if old is None or old.active_layer != detection.active_layer:
            self.refresh_tabs()
        message = "Am Pad K0 dreimal drücken, um den Matrix-Test zu öffnen."
        if detection.enabled:
            message = f"Matrix-Test aktiv  ·  {detection.presses} Tastenanschläge"
            if detection.last_key < len(self.keys):
                message += f"  ·  zuletzt K{detection.last_key + 1}"
            if old and old.enabled:
                if old.clockwise != detection.clockwise:
                    message += "  ·  Encoder rechts"
                if old.counterclockwise != detection.counterclockwise:
                    message += "  ·  Encoder links"
        elif old and old.encoder_pushes != detection.encoder_pushes:
            message = "Encoder-Druck erkannt  ·  Matrix-Test beendet"
        self.detect_message.set(message)
        self.draw()

    def close(self):
        self.closing = True
        if self.pending:
            self.window.after(100, self.close)
            return
        if self.device:
            self.device.close()
        self.worker.shutdown(wait=False)
        self.window.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Editor(root)
    root.mainloop()
