"""Signal names, pin assignments and live hardware test table."""

import json
import re
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from profile import MATRIX, MODES, ROOT, label_for_code
from ui_helpers import BG, PANEL, MUTED, button, label
from via import UnsupportedCommand, ViaError


class Tester(tk.Frame):
    def __init__(self, parent, editor):
        super().__init__(parent, bg=BG)
        self.editor = editor
        self.active = False
        self.pending = False
        self.native = False
        self.slider_baseline = None
        definition = ROOT / "keyboards" / "icst7789v"
        keyboard = json.loads((definition / "keyboard.json").read_text(encoding="utf-8"))
        self.matrix_pins = keyboard["matrix_pins"]
        encoder = keyboard["encoder"]["rotary"][0]
        self.encoder_pins = f"{encoder['pin_a']} A · {encoder['pin_b']} B"
        config = (definition / "config.h").read_text(encoding="utf-8")
        self.pins = dict(re.findall(r"^#define\s+(\w+)\s+(GP\d+)\b", config, re.MULTILINE))
        i2c_sda = self.pins.get("I2C1_SDA_PIN")
        i2c_scl = self.pins.get("I2C1_SCL_PIN")
        self.i2c_pins = f"{i2c_sda} SDA · {i2c_scl} SCL" if i2c_sda and i2c_scl else "I²C · GPIO unbekannt"
        self.display_pins = " · ".join(f"{self.pins[name]} {signal}" for name, signal in (
            ("SPI_SCK_PIN", "SCK"), ("SPI_MOSI_PIN", "MOSI"), ("TFT_CS_PIN", "CS"),
            ("TFT_DC_PIN", "DC"), ("TFT_RST_PIN", "RST"), ("TFT_BL_PIN", "BL")))

        controls = tk.Frame(self, bg=BG)
        controls.pack(fill="x", pady=10)
        self.start = button(controls, "Tester starten", lambda: self.toggle(True))
        self.stop = button(controls, "Beenden", lambda: self.toggle(False))
        self.start.pack(side="left", padx=(0, 5))
        self.stop.pack(side="left", padx=(0, 15))
        self.outputs = []
        for mode, name in ((1, "Display"), (2, "Main-LEDs"), (3, "Frame-LEDs")):
            control = button(controls, f"{name} testen", lambda value=mode: self.preview(value))
            control.pack(side="left", padx=(0, 5))
            self.outputs.append(control)
        button(controls, "Liste leeren", self.clear).pack(side="right")

        self.status = tk.StringVar()
        label(self, textvariable=self.status, color=MUTED).pack(fill="x", padx=12, pady=(0, 6))
        container = tk.Frame(self, bg=PANEL)
        container.pack(fill="both", expand=True)
        columns = ("time", "name", "pins", "function")
        self.table = ttk.Treeview(container, columns=columns, show="headings")
        for col, title, width in zip(columns, ("Zeit", "Signal", "GPIO / Anschluss", "Funktion / Messwert"),
                                      (72, 163, 342, 285)):
            self.table.heading(col, text=title)
            self.table.column(col, width=width, stretch=col != "time", minwidth=65)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.refresh()

    def refresh(self):
        device = self.editor.device
        supported = bool(device and (self.native or self.editor.has_detection))
        ready = supported and not self.pending and not self.editor.busy()
        start_hint = ("Tester starten und ein Bedienelement betätigen" if self.native else
                      "Basis-Tester verfügbar · Für Display- und LED-Tests Firmware 6 installieren")
        self.start.configure(state="normal" if ready and not self.active else "disabled")
        self.stop.configure(state="normal" if ready and self.active else "disabled")
        for control in self.outputs:
            control.configure(state="normal" if ready and self.active and self.native else "disabled")
        if not device:
            self.active = False
            self.status.set("OmniPad per USB verbinden, um Signale zu sehen")
        elif not supported:
            self.active = False
            self.status.set("Die verbundene Firmware liefert keine Tester-Signale")
        elif self.status.get().startswith(("OmniPad per USB", "Die verbundene Firmware")) or not self.status.get():
            self.status.set(start_hint)

    def clear(self):
        entries = self.table.get_children()
        if entries:
            self.table.delete(*entries)

    def toggle(self, active):
        pad = self.editor.device
        if not pad or self.pending:
            return
        if active:
            self.clear()
            self.slider_baseline = self.editor.detection.slider_raw if self.editor.detection else None
        self.pending = True
        native = self.native

        def set_mode():
            try:
                pad.diagnose(active, tester=native)
            except UnsupportedCommand:
                if native:
                    raise
                if active and not pad.detection().enabled:
                    return "K0 am Pad dreimal drücken und den Tester erneut starten", None
                if not active:
                    return "Tester beendet · Hardware-Test bei Bedarf am Pad beenden", None
            report = pad.tester_report() if active and native else None
            if report is not None and not report[0]:
                raise ViaError("Das Pad hat den Tester nicht aktiviert.")
            return None, report

        def changed(result):
            hint, report = result
            self.pending = False
            self.active = active and hint is None
            self.status.set(hint or ("Tester aktiv · Bedienelemente am Pad betätigen" if active else "Tester beendet"))
            if report is not None:
                self.report(self.editor.detection, report)
            self.refresh()
        self.editor.submit(set_mode, changed)

    def preview(self, output):
        pad = self.editor.device
        if not pad or not self.active:
            return
        pins = self.display_pins if output == 1 else self.pins["WS2812_DI_PIN"]
        name = ("Display", "Main-LEDs", "Frame-LEDs")[output - 1]
        detail = ("Farbfelder", "LED 0–13", "LED 14–56")[output - 1]
        self.editor.submit(lambda: pad.test_output(output), lambda _: self.add(
            name, pins, f"{detail} · Testausgabe gesendet · Sichtprüfung"))

    def add(self, name, pins, function):
        self.table.insert("", 0, values=(f"{datetime.now():%H:%M:%S}", name, pins, function))
        overflow = self.table.get_children()[200:]
        if overflow:
            self.table.delete(*overflow)

    def report(self, detection, report):
        active, lost, events = report
        if lost:
            self.add("Signal nicht zugeordnet", "Unbekannt", "Weitere Ereignisse erkannt · Puffer übergelaufen")
        for source, detail, value in events:
            self.add(*self.describe(source, detail, value, detection))
        if self.active and not active:
            self.active = False
            self.status.set("Tester am Pad beendet")
            self.refresh()

    def report_detection(self, previous, current):
        if not current.enabled:
            self.report(current, (False, False, ()))
            return
        events = []
        if previous and previous.enabled:
            changed = previous.mask ^ current.mask
            for index, (row, col) in enumerate(MATRIX):
                if changed & (1 << index):
                    events.append((1, (row << 4) | col, bool(current.mask & (1 << index))))
            for index, source in ((10, 3), (11, 2)):
                if changed & (1 << index):
                    events.append((source, 0, bool(current.mask & (1 << index))))
            for before, after, direction in ((previous.clockwise, current.clockwise, 1),
                                              (previous.counterclockwise, current.counterclockwise, 0)):
                if before != after:
                    events.append((4, direction, 0))
            seen_presses = ((current.mask & ~previous.mask) & 0x3FF).bit_count()
            if current.presses - previous.presses > seen_presses:
                self.add("Signal nicht zugeordnet", "Unbekannt", "Kurzer Tastendruck zwischen zwei USB-Abfragen")
        if current.slider_raw is not None:
            if self.slider_baseline is None:
                self.slider_baseline = current.slider_raw
            elif abs(current.slider_raw - self.slider_baseline) >= 7:
                events.append((5, current.slider_percent, current.slider_raw))
                self.slider_baseline = current.slider_raw
        self.report(current, (True, False, events))

    def describe(self, source, detail, value, detection):
        edge = "Gedrückt" if value else "Losgelassen"
        if source == 1:
            row, column = detail >> 4, detail & 15
            pairs = self.matrix_pins
            caps = self.editor.capabilities
            expander = detection.expander if detection else caps and caps["expander"]
            if expander and row < 3 and column < 4:
                pins = f"{self.i2c_pins} · P0{row} / P1{column}"
            elif row < len(pairs["rows"]) and column < len(pairs["cols"]):
                pins = f"{pairs['rows'][row]} / {pairs['cols'][column]}"
            else:
                pins = "Unbekannt"
            if (row, column) in MATRIX:
                index = MATRIX.index((row, column))
                label_text = self.editor.key_name(index)
                profile = self.editor.active_profile
                if profile and detection and detection.active_layer < len(profile["layers"]):
                    key = profile["layers"][detection.active_layer]["keys"][index]
                    action = key["label"] or label_for_code(key["codes"][0])
                    edge += f" · {MODES[key['mode']]}: {action}"
                return label_text, pins, f"{edge} · Matrix R{row + 1}/C{column + 1}"
            return "Signal nicht zugeordnet", pins, f"{edge} · unbelegte Matrixposition R{row + 1}/C{column + 1}"
        if source == 2:
            return "K0", self.pins["TFT_K0_PIN"], f"{edge} · Modultaste"
        if source == 3:
            return "Encoder-Druck", self.pins["ENCODER_PUSH_PIN"], f"{edge} · Encoder-Taster"
        if source == 4:
            return "Encoder-Drehung", self.encoder_pins, "Rechts" if detail else "Links"
        if source == 5:
            return "Schieberegler", self.pins["SLIDER_ADC_PIN"], f"{detail} % · ADC {value}"
        if source == 6:
            function = "Bewegung" if detail else "Sensor antwortet"
            if detection:
                x, y, z = detection.sensor_xyz
                function += f" · X {x} / Y {y} / Z {z}"
            return "ADXL345", self.i2c_pins, function
        if source == 7:
            return "PCF8575", self.i2c_pins, "Matrix-Expander antwortet auf 0x20"
        if source == 8 and detail < 16:
            return "Signal nicht zugeordnet", f"{self.i2c_pins} · P{detail // 8}{detail % 8}", "Freier PCF8575-Eingang wurde LOW"
        return "Signal nicht zugeordnet", "Unbekannt", f"Signaltyp {source} erkannt"
