"""OmniPad configuration, lighting, macro library and screen editor."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import queue
from time import monotonic
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

from assignment_panel import AssignmentPanel
from layer_manager import LayerManager
from layer_operations import (valid_layer_name, rename_layer as update_layer_name,
                              duplicate_layer as copy_layer, move_layer as reorder_layer,
                              delete_layer as remove_layer, layer_references)
from profile_audit import action_differences
from macro_recorder import MacroRecorder, parse_snippet_lines
from bindings import (
    DISPLAY_ACTIONS, SLOTS, action_name, change_key_mode, layer_choices,
    requires_device_actions, set_key_action,
)
from profile import (
    ROOT, USER_DATA, BASIC_CODES, MAX_LAYERS, MAX_SNIPPETS, MACRO_POOL_SIZE, MATRIX,
    MODES, EFFECTS, SLIDER_MODES, atomic_json, compile_snippet, decode_profile,
    default_profile, encode_lighting, encode_profile, zone_config, key_config, label_for_code, layer_config,
)
from screen_editor import ScreenEditor
from led_layout import (LED_COUNT, MAIN_COUNT, LED_LAYOUT_PATH, default_positions,
                        read_positions, write_positions, to_canvas, from_canvas, square_bounds)
from led_zones import (ZONE_NAMES, MATRIX_ZONES, MATRIX_COUNT, default_zone_map,
                       validate_zone_map, matrix_positions)
from tester import Tester
from ui_helpers import BG, PANEL, KEY, TEXT, MUTED, ACCENT, Form, ScrollPanel, button, label, style
from via import OmniPad, ViaError, UnsupportedCommand
from windows_volume import set_master_volume_percent, WindowsVolumeError


class Editor:
    def __init__(self, window):
        self.window = window
        window.title("OmniPad Editor")
        window.geometry("1240x820")
        window.minsize(1080, 720)
        style(window)
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.tasks = {}
        self.polling = False
        self.device = None
        self.capabilities = None
        self.generation = None
        self.detection = None
        self.has_detection = False
        self.next_connection_check = 0
        self.closing = False
        self.progress = queue.SimpleQueue()
        self.history, self.future = [], []
        self.layer, self.target, self.action_slot = 0, ("key", 0), 0
        self.clipboard = None
        self.snippet_selection = 0
        self.autosave_id = None
        self.on_device = None
        self.active_profile = None
        self.preview_phase = 0
        self.volume_last_sent = None
        self.preview_sent = None
        self.preview_renew_at = 0
        self.led_selected = None
        self.led_drag_start = None
        self.led_drag_changed = False
        self.led_undo = []
        try:
            self.led_positions = read_positions()
            self.led_layout_warning = None
        except (OSError, ValueError) as error:
            self.led_positions = default_positions()
            self.led_layout_warning = str(error)
        self.profile = default_profile()
        self.disk_draft = False
        draft = USER_DATA / "draft.omnipad.json"
        if draft.exists():
            try:
                loaded = json.loads(draft.read_text(encoding="utf-8"))
                encode_profile(loaded)
                self.profile, self.disk_draft = loaded, True
            except (OSError, KeyError, TypeError, ValueError):
                pass
        self.led_zone_map = validate_zone_map(
            self.profile.get("led_zone_map", default_zone_map()))
        self.keys = json.loads((ROOT / "keyboards/icst7789v/keyboard.json").read_text())[
            "layouts"]["LAYOUT"]["layout"]

        toolbar = tk.Frame(window, bg=BG)
        toolbar.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(toolbar, text="OmniPad", bg=BG, fg=TEXT, font=("Segoe UI", 24, "bold")).pack(side="left", padx=(0, 16))
        self.undo_button = button(toolbar, "↶", self.undo)
        self.undo_button.pack(side="left", padx=3)
        self.redo_button = button(toolbar, "↷", self.redo)
        self.redo_button.pack(side="left", padx=3)
        button(toolbar, "Import", self.import_profile).pack(side="left", padx=(12, 3))
        button(toolbar, "Export", self.export_profile).pack(side="left", padx=3)
        self.write_button = button(toolbar, "Auf Pad speichern", self.write_profile)
        self.write_button.pack(side="right", padx=(6, 0))
        self.verify_button = button(toolbar, "Pad / Entwurf prüfen", self.verify_device_profile)
        self.verify_button.pack(side="right", padx=6)
        self.connect_button = button(toolbar, "Verbinden", self.connect)
        self.connect_button.pack(side="right", padx=3)
        button(toolbar, "Vom Pad laden", lambda: self.connect(replace=True)).pack(side="right", padx=3)
        button(toolbar, "VIA-Sicherung", self.backup).pack(side="right", padx=3)
        self.status = tk.StringVar(value="Profil wird vorbereitet …")
        tk.Label(window, textvariable=self.status, bg=BG, fg=MUTED, anchor="w").pack(fill="x", padx=22)
        self.layer_bar = tk.Frame(window, bg=BG)
        self.layer_bar.pack(fill="x", padx=20, pady=(14, 8))
        self.layer_tabs = tk.Frame(self.layer_bar, bg=BG)
        self.layer_tabs.pack(side="left", fill="x", expand=True)
        button(self.layer_bar, "+ Layer", self.add_layer).pack(side="right")
        button(self.layer_bar, "Layer verwalten", self.open_layer_manager).pack(side="right", padx=(0, 8))
        self.notebook = ttk.Notebook(window)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 18))
        self.key_page = tk.Frame(self.notebook, bg=BG)
        self.light_page = tk.Frame(self.notebook, bg=BG)
        self.snippet_page = tk.Frame(self.notebook, bg=BG)
        self.detect_page = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.key_page, text="Tasten & Regler")
        self.layer_entries = AssignmentPanel(self.notebook, self)
        self.notebook.add(self.layer_entries, text="Layer-Zugänge")
        self.layer_manager = LayerManager(self.notebook, self)
        self.notebook.add(self.layer_manager, text="Layer verwalten")
        self.notebook.add(self.light_page, text="Beleuchtung")
        self.notebook.add(self.snippet_page, text="Snippet-Bibliothek")
        self.screen_page = ScreenEditor(self.notebook, self)
        self.notebook.add(self.screen_page, text="Display-Vorlagen")
        self.notebook.add(self.detect_page, text="Erkennung")
        self.tester_page = Tester(self.notebook, self)
        self.notebook.add(self.tester_page, text="Tester")
        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self.refresh_selected_page())
        self.create_keys()
        self.create_lighting()
        self.create_snippets()
        self.create_detection()
        self.refresh()
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(100, self.tick)

    @property
    def current_layer(self):
        return self.profile["layers"][self.layer]

    def busy(self):
        return any(not polling for _, polling in self.tasks.values())

    def submit(self, task, callback, *, polling=False):
        if self.closing:
            return
        future = self.worker.submit(task)
        self.tasks[future] = callback, polling
        if polling:
            self.polling = True
        self.refresh_buttons()

    def tick(self):
        while not self.progress.empty():
            done, size = self.progress.get()
            self.status.set(f"Profil wird übertragen · {round(done * 100 / size)} %")
        for future in list(self.tasks):
            if not future.done():
                continue
            callback, polling = self.tasks.pop(future)
            if polling:
                self.polling = False
            try:
                result = future.result()
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                self.status.set(str(error))
                if isinstance(error, OSError) or (polling and not isinstance(error, UnsupportedCommand)):
                    if self.device:
                        self.device.close()
                    self.device = None
                    self.has_detection = False
                    self.detection = None
                    self.preview_sent = None
                    self.key_live.set("Regler GP28 · USB-Verbindung getrennt")
                    self.detect_text.set("USB-Verbindung getrennt · Das Pad wird erneut gesucht.")
                    self.next_connection_check = monotonic() + 2
                if isinstance(error, UnsupportedCommand) and polling:
                    self.has_detection = False
                if not polling and hasattr(self, "tester_page"):
                    self.tester_page.pending = False
                if not polling and not (isinstance(error, ViaError) and self.device is None):
                    messagebox.showerror("OmniPad", str(error), parent=self.window)
            else:
                try:
                    callback(result)
                except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                    self.status.set(str(error))
                    messagebox.showerror("OmniPad", str(error), parent=self.window)
            self.refresh_buttons()
        if not self.closing and not self.polling and not self.busy():
            if self.device:
                self.poll_device()
            elif monotonic() >= self.next_connection_check:
                self.connect(automatic=True)
        if not self.closing or self.tasks:
            self.window.after(100, self.tick)

    def poll_device(self):
        pad = self.device
        read_detection = self.has_detection
        read_tester = self.tester_page.active and self.tester_page.native
        payload = self.lighting_preview_payload()
        send_preview = payload != self.preview_sent or (
            payload is not None and monotonic() >= self.preview_renew_at)
        if not (read_detection or read_tester or send_preview):
            return

        def poll():
            preview_rejected = False
            if send_preview:
                try:
                    pad.preview_lighting(payload)
                except UnsupportedCommand:
                    preview_rejected = True
            try:
                detection = pad.detection() if read_detection else None
            except UnsupportedCommand:
                detection = None
            report = pad.tester_report() if read_tester else None
            return detection, report, preview_rejected

        def ready(result):
            if self.device is not pad:
                return
            detection, report, preview_rejected = result
            if preview_rejected:
                self.preview_sent = None
                if detection is None or not detection.enabled:
                    self.capabilities["light_preview"] = False
                    self.status.set("Das Pad hat die Hardwarevorschau abgelehnt")
            elif send_preview:
                self.preview_sent = payload
                self.preview_renew_at = monotonic() + 0.5
            self.has_detection &= detection is not None
            if detection is not None:
                previous = self.detection
                self.detected(detection)
                if self.tester_page.active and not self.tester_page.native:
                    self.tester_page.report_detection(previous, detection)
            if report is not None and self.tester_page.active:
                self.tester_page.report(detection, report)

        self.submit(poll, ready, polling=True)

    def connect(self, replace=False, *, automatic=False):
        if self.busy():
            return
        if replace and self.dirty() and not messagebox.askyesno(
                "Profil vom Pad laden", "Den aktuellen Entwurf durch die Einstellungen des Pads ersetzen?",
                parent=self.window):
            return
        previous = self.device
        was_diagnosing = self.tester_page.active or (self.detection and self.detection.enabled)
        was_previewing = self.preview_sent is not None
        self.tester_page.active = False
        self.device = None
        self.has_detection = False
        self.detection = None
        self.preview_sent = None
        if not automatic or self.next_connection_check == 0:
            self.status.set("USB-Verbindung wird geprüft …")
        self.next_connection_check = monotonic() + 2
        metadata = deepcopy(self.profile)

        def read():
            if previous:
                try:
                    if was_diagnosing:
                        previous.diagnose(False)
                    if was_previewing:
                        previous.preview_lighting(None)
                except (OSError, RuntimeError):
                    pass
                finally:
                    previous.close()
            try:
                pad = OmniPad.connect()
            except OSError as error:
                raise ViaError(f"Die VIA-Schnittstelle konnte nicht geöffnet werden · {error}") from error
            try:
                warnings = []
                try:
                    caps = pad.capabilities()
                except UnsupportedCommand:
                    caps = None
                try:
                    detection = pad.detection()
                except UnsupportedCommand:
                    detection = None
                try:
                    pad.tester_report()
                except UnsupportedCommand:
                    native_tester = False
                else:
                    native_tester = True
                raw = None
                snapshot = None
                matrix_data = None
                try:
                    raw = pad.read_profile() if caps and caps["enabled"] else None
                except ViaError:
                    warnings.append("Geräteprofil konnte nicht geladen werden")
                if caps and caps.get("matrix_zones"):
                    try:
                        matrix_data = pad.read_matrix_zones()
                    except (ViaError, ValueError):
                        warnings.append("LED-Zonen konnten nicht gelesen werden")
                try:
                    snapshot = pad.snapshot()
                except ViaError:
                    warnings.append("VIA-Sicherung konnte nicht gelesen werden")
                return pad, caps, raw, snapshot, detection, native_tester, matrix_data, warnings
            except OSError as error:
                pad.close()
                raise ViaError(f"Die USB-Verbindung wurde beim Auslesen unterbrochen · {error}") from error
            except Exception:
                pad.close()
                raise
        def ready(result):
            self.device, self.capabilities, raw, snapshot, detection, native_tester, matrix_data, warnings = result
            self.tester_page.native = native_tester
            self.generation = self.capabilities["generation"] if self.capabilities else None
            self.on_device = raw
            self.has_detection = detection is not None
            self.active_profile = None
            if raw:
                try:
                    self.active_profile = decode_profile(raw, metadata)
                except (ValueError, KeyError, TypeError):
                    warnings.append("Geräteprofil konnte nicht ausgewertet werden")
            if matrix_data is not None and self.active_profile:
                matrix, zone_map = matrix_data
                try:
                    atomic_json(
                        USER_DATA / "backups" / f"led-zones-{datetime.now():%Y%m%d-%H%M%S}.json",
                        {"schema": "omnipad-matrix-zones", "version": 1,
                         "layers": matrix, "zone_map": zone_map})
                except OSError:
                    warnings.append("LED-Zonen-Backup konnte nicht gespeichert werden")
                for idx, layer in enumerate(self.active_profile["layers"]):
                    layer["matrix_zones"] = deepcopy(matrix[idx])
                self.active_profile["led_zone_map"] = list(zone_map)
            if snapshot is not None:
                try:
                    atomic_json(USER_DATA / "backups" / f"via-{datetime.now():%Y%m%d-%H%M%S}.json", snapshot)
                except OSError:
                    warnings.append("VIA-Sicherung konnte nicht gespeichert werden")
            if (replace or not self.disk_draft) and (self.active_profile or snapshot is not None):
                self.profile = deepcopy(self.active_profile) if self.active_profile else default_profile(snapshot)
                self.disk_draft = True
                self.history.clear()
                self.future.clear()
                self.save_draft()
            self.layer = min(self.layer, len(self.profile["layers"]) - 1)
            self.led_zone_map = validate_zone_map(
                self.profile.get("led_zone_map", default_zone_map()))
            version = f"Firmware {self.device.firmware}" if self.device.firmware else "Firmwareversion unbekannt"
            message = f"USB verbunden · {version} · {len(self.profile['layers'])} eingerichtete Layer"
            if not self.capabilities:
                message += " · Erweiterte Funktionen benötigen die neue Firmware"
            self.status.set(" · ".join((message, *warnings)))
            self.refresh()
            if detection is not None:
                self.detected(detection)
            else:
                self.detect_text.set("Diese Firmware liefert keine Live-Eingangsdaten für den Inspektor.")
        self.submit(read, ready)

    def change(self, mutator):
        candidate = deepcopy(self.profile)
        try:
            mutator(candidate)
            encode_profile(candidate)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            messagebox.showerror("Einstellung prüfen", str(error), parent=self.window)
            return False
        if candidate == self.profile:
            return True
        self.history.append(deepcopy(self.profile))
        self.history = self.history[-100:]
        self.future.clear()
        self.profile = candidate
        self.layer = min(self.layer, len(candidate["layers"]) - 1)
        self.save_draft()
        self.refresh()
        self.status.set("Entwurf gespeichert · Mit „Auf Pad speichern“ übertragen")
        return True

    def save_draft(self):
        if self.autosave_id:
            self.window.after_cancel(self.autosave_id)
        self.autosave_id = self.window.after(500, self._save_draft)

    def _save_draft(self):
        self.autosave_id = None
        try:
            atomic_json(USER_DATA / "draft.omnipad.json", self.profile)
        except OSError as error:
            self.status.set(f"Entwurf konnte nicht gespeichert werden · {error}")

    def dirty(self):
        try:
            return encode_profile(self.profile) != self.on_device
        except (ValueError, KeyError, TypeError):
            return True

    def undo(self):
        if self.history:
            self.future.append(deepcopy(self.profile))
            self.profile = self.history.pop()
            self.layer = min(self.layer, len(self.profile["layers"]) - 1)
            self.save_draft()
            self.refresh()

    def redo(self):
        if self.future:
            self.history.append(deepcopy(self.profile))
            self.profile = self.future.pop()
            self.save_draft()
            self.refresh()

    def refresh_buttons(self):
        if not hasattr(self, "write_button"):
            return
        self.undo_button.configure(state="normal" if self.history else "disabled")
        self.redo_button.configure(state="normal" if self.future else "disabled")
        self.connect_button.configure(state="disabled" if self.busy() else "normal",
                                      text="Neu verbinden" if self.device else "Verbinden")
        testing = hasattr(self, "tester_page") and self.tester_page.active
        self.write_button.configure(state="normal" if self.device and not self.busy() and not testing else "disabled")
        self.verify_button.configure(state="normal" if self.device and not self.busy() and not testing else "disabled")
        if hasattr(self, "tester_page"):
            self.tester_page.refresh()
        if hasattr(self, "light_live_status"):
            self.refresh_light_live_status()

    def refresh(self):
        if not hasattr(self, "key_canvas"):
            return
        self.refresh_layers()
        self.refresh_key_form()
        self.refresh_key_shortcuts()
        self.refresh_actions()
        self.layer_entries.refresh()
        self.layer_manager.refresh()
        self.draw_keys()
        self.refresh_light_form()
        self.refresh_snippets()
        self.screen_page.refresh()
        self.draw_light_preview()
        self.refresh_buttons()

    def refresh_selected_page(self):
        if hasattr(self, "key_canvas"):
            self.draw_keys()
            self.screen_page.draw()
            self.draw_light_preview()

    def refresh_layers(self):
        for widget in self.layer_tabs.winfo_children():
            widget.destroy()
        active = self.detection.active_layer if self.detection else None
        for index, layer in enumerate(self.profile["layers"]):
            text = layer["name"]
            if index == active:
                text = "● " + text
            tab = tk.Button(self.layer_tabs, text=text, relief="flat", padx=8, pady=6,
                            bg=layer["color"] if index == self.layer else KEY,
                            fg=BG if index == self.layer else layer["color"],
                            activebackground=layer["color"], command=lambda i=index: self.select_layer(i))
            tab.pack(side="left", padx=(0, 4))
            tab.bind("<Button-3>", lambda event, i=index: self.layer_menu(event, i))

    def select_layer(self, index):
        self.layer = index
        self.refresh_layers()
        self.refresh_key_form()
        self.refresh_key_shortcuts()
        self.draw_keys()
        self.refresh_light_form()
        self.refresh_actions()
        self.screen_page.refresh()
        self.draw_light_preview()
        self.layer_manager.refresh()

    def open_layer_manager(self):
        self.notebook.select(self.layer_manager)

    def layer_menu(self, event, index):
        self.layer = index
        self.select_layer(index)
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label="Umbenennen", command=self.rename_layer)
        menu.add_command(label="Farbmarkierung wählen", command=self.color_layer)
        menu.add_command(label="Duplizieren", command=lambda: self.add_layer(copy=True))
        menu.add_command(label="Als Startlayer festlegen", command=self.set_default_layer)
        menu.add_separator()
        menu.add_command(label="Nach oben verschieben", command=lambda: self.move_layer(-1),
                         state="normal" if index > 0 else "disabled")
        menu.add_command(label="Nach unten verschieben", command=lambda: self.move_layer(1),
                         state="normal" if index < len(self.profile["layers"]) - 1 else "disabled")
        menu.add_command(label="Layer löschen", command=self.delete_layer,
                         state="normal" if len(self.profile["layers"]) > 1 else "disabled")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _sync_layer_selections(self):
        """Selectors hold numeric indices; reset them after topology changes."""
        for panel in (self.layer_entries, self.screen_page.assignments):
            panel.source.current(self.layer)

    def rename_layer(self):
        current = self.layer
        name = simpledialog.askstring(
            "Layer umbenennen", "Neuer Layername (maximal 15 Zeichen):",
            initialvalue=self.current_layer["name"], parent=self.window)
        if name is not None:
            self.change(lambda p: update_layer_name(p, current, name))

    def color_layer(self):
        color = colorchooser.askcolor(self.current_layer["color"], parent=self.window)[1]
        if color:
            current = self.layer
            self.change(lambda p: p["layers"][current].__setitem__("color", color))

    def set_default_layer(self):
        index = self.layer
        self.change(lambda p: p.__setitem__("default_layer", index))

    def add_layer(self, copy=False):
        index = self.layer
        new_index = len(self.profile["layers"])
        if len(self.profile["layers"]) >= MAX_LAYERS:
            messagebox.showinfo("Layer", f"Diese Firmware unterstützt {MAX_LAYERS} Layer.", parent=self.window)
            return
        def add(p):
            if copy:
                copy_layer(p, index, MAX_LAYERS)
            else:
                fresh = layer_config(len(p["layers"]))
                name = fresh["name"]
                # The default name must also be unique after rename/duplicate.
                try:
                    valid_layer_name(p, name)
                except ValueError:
                    counter = len(p["layers"]) + 1
                    while any(layer["name"].casefold() == f"Layer {counter}".casefold()
                              for layer in p["layers"]):
                        counter += 1
                    fresh["name"] = f"Layer {counter}"
                p["layers"].append(fresh)
        if self.change(add):
            self.layer = new_index
            self._sync_layer_selections()
            self.refresh()

    def move_layer(self, offset):
        before = self.layer
        target = before + offset
        if not (0 <= target < len(self.profile["layers"])):
            return
        if self.change(lambda p: reorder_layer(p, before, target)):
            self.layer = target
            self._sync_layer_selections()
            self.refresh()

    def delete_layer(self):
        count = len(self.profile["layers"])
        if count < 2:
            messagebox.showinfo("Layer", "Der letzte Layer kann nicht gelöscht werden.", parent=self.window)
            return
        index = self.layer
        layer_name = self.current_layer["name"]
        affected, fields = layer_references(self.profile, index, exclude_layer=index)
        warning = (
            f"Layer {index + 1} „{layer_name}“ wirklich löschen?\n\n"
            f"• {affected} Verweise auf diesen Layer werden auf „Keine Aktion“ gesetzt.\n"
            f"• {fields} Displayelemente, die nur auf diesem Layer sichtbar sind, werden gelöscht.\n"
            "• Andere Layerziele und der Startlayer werden passend umnummeriert.\n\n"
            "Das betrifft zunächst nur den Entwurf und kann mit Rückgängig widerrufen werden."
        )
        if not messagebox.askyesno("Layer löschen", warning, parent=self.window):
            return
        if self.change(lambda p: remove_layer(p, index)):
            self.layer = min(index, len(self.profile["layers"]) - 1)
            self._sync_layer_selections()
            self.refresh()

    def create_keys(self):
        workspace = tk.Frame(self.key_page, bg=BG)
        workspace.pack(fill="both", expand=True, pady=(8, 0))
        left = tk.Frame(workspace, bg=PANEL)
        left.pack(side="left", fill="both", expand=True)
        self.key_canvas = tk.Canvas(left, bg=PANEL, height=380, highlightthickness=0)
        self.key_canvas.pack(fill="both", expand=True)
        self.key_canvas.bind("<Configure>", lambda _: self.draw_keys())
        self.key_canvas.bind("<Button-1>", self.select_at)
        self.key_canvas.bind("<Button-3>", self.context_key)
        self.key_rectangles = {}
        self.key_live = tk.StringVar(value="Regler GP28 · Live-Wert erscheint nach Verbindung mit der neuen Firmware")
        label(left, textvariable=self.key_live, color=MUTED, wraplength=660).pack(
            fill="x", padx=18, pady=(0, 14))
        self.key_shortcuts = tk.Frame(left, bg=PANEL)
        self.key_shortcuts.pack(fill="x", padx=14, pady=(0, 12))
        side = ttk.Notebook(workspace, width=320)
        side.pack(side="right", fill="y", padx=(12, 0))
        palette = tk.Frame(side, bg=PANEL)
        self.key_settings = ScrollPanel(side, 320)
        side.add(palette, text="Aktionen")
        side.add(self.key_settings, text="Details")
        self.key_palette = palette
        self.key_side = side
        self.action_target = tk.StringVar()
        label(palette, textvariable=self.action_target, size=10, color=MUTED, wraplength=278).pack(
            fill="x", padx=10, pady=10)
        self.category = ttk.Combobox(palette, state="readonly",
                                     values=("Alle Aktionen", "Tasten", "Shortcuts & Medien",
                                             "Layer", "Display & Gerät", "Snippets"))
        self.category.current(0)
        self.category.pack(fill="x", padx=10, pady=(0, 4))
        self.category.bind("<<ComboboxSelected>>", lambda _: self.refresh_actions())
        self.search = tk.StringVar()
        search = ttk.Entry(palette, textvariable=self.search)
        search.pack(fill="x", padx=10, pady=(0, 4))
        search.insert(0, "")
        self.search.trace_add("write", lambda *_: self.refresh_actions())
        self.actions = tk.Listbox(palette, height=7, bg=KEY, fg=TEXT, selectbackground="#73503d",
                                   exportselection=False, relief="flat", highlightthickness=0)
        self.actions.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.actions.bind("<Return>", lambda _: self.choose_action())
        self.actions.bind("<ButtonRelease-1>", self.click_action)

    def refresh_key_shortcuts(self):
        for widget in self.key_shortcuts.winfo_children():
            widget.destroy()
        kind, index = self.target
        if kind != "key":
            title = "Schieberegler" if kind == "slider" else ("Encoder links", "Encoder rechts")[index]
            label(self.key_shortcuts, title, size=12).pack(side="left")
            button(self.key_shortcuts, "Details", lambda: self.key_side.select(self.key_settings)).pack(side="right")
            self.refresh_action_target()
            return

        key = self.current_layer["keys"][index]
        mode = key["mode"]
        self.action_slot = min(self.action_slot, len(SLOTS[mode]) - 1)
        bar = tk.Frame(self.key_shortcuts, bg=PANEL)
        bar.pack(fill="x", pady=(0, 5))
        label(bar, self.key_name(index), size=12).pack(side="left", padx=(0, 12))
        for value, title in enumerate(("Direkt", "Multi-Push / Tap Dance", "Durchschalten")):
            control = button(bar, title, lambda m=value: self.select_key_mode(m))
            control.pack(side="left", padx=(0, 4))
            if value == mode:
                control.state(("disabled",))
        button(bar, "Details", lambda: self.key_side.select(self.key_settings)).pack(side="right")
        slots = tk.Frame(self.key_shortcuts, bg=PANEL)
        slots.pack(fill="x")
        for slot, name in enumerate(SLOTS[mode]):
            action = action_name(self.profile, key["codes"][slot])
            control = tk.Button(slots, text=f"{name}\n{action}", wraplength=105, height=3,
                                bg=ACCENT if slot == self.action_slot else KEY,
                                fg=BG if slot == self.action_slot else TEXT, relief="flat",
                                command=lambda i=slot: self.select_action_slot(i))
            control.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.refresh_action_target()

    def select_key_mode(self, mode):
        index = self.target[1]
        self.action_slot = 0
        self.change(lambda p: change_key_mode(p["layers"][self.layer]["keys"][index], index, mode))
        self.key_side.select(self.key_palette)

    def select_action_slot(self, slot):
        self.action_slot = slot
        self.refresh_key_shortcuts()
        self.key_side.select(self.key_palette)

    def refresh_action_target(self):
        kind, index = self.target
        if kind == "key":
            key = self.current_layer["keys"][index]
            caption = f"{self.key_name(index)} · {SLOTS[key['mode']][self.action_slot]}"
            prior = action_name(self.profile, key["codes"][self.action_slot])
        elif kind == "encoder":
            caption = ("Encoder links", "Encoder rechts")[index]
            prior = action_name(self.profile, self.current_layer["encoders"][index])
        else:
            self.action_target.set("Die Regler-Belegung steht unter Details.")
            return
        self.action_target.set(f"{caption}\nAktuell · {prior}\nKlick auf eine Aktion zum Belegen.")

    def refresh_key_form(self):
        self.key_settings.clear()
        form = self.key_form = Form(self.key_settings.content)
        kind, index = self.target
        if kind == "key":
            key = self.current_layer["keys"][index]
            form.title(self.key_name(index))
            form.entry("label", "Displaytext", key["label"])
            if key["mode"] == 1:
                form.entry("term", "Zeitfenster für Tipps und Halten (ms)", key["term"], kind=int)
            for number, name in enumerate(SLOTS[key["mode"]]):
                form.entry(f"code{number}", f"{name} · {action_name(self.profile, key['codes'][number])}",
                           f"0x{key['codes'][number]:04X}", kind="code")
            if index == 11:
                form.note("Die Standardgesten von K0 stehen im Display-Studio unter Tasten & Auslöser.")
        elif kind == "encoder":
            form.title("Encoder links" if index == 0 else "Encoder rechts")
            form.entry("code", "Aktion", f"0x{self.current_layer['encoders'][index]:04X}", kind="code")
            form.note("Die Belegung wirkt im Encoder-Modus. Im Display-Modus wählt die Drehung den Layer.")
        else:
            slider = self.current_layer["slider"]
            form.title("Schieberegler · GPIO28")
            form.choice("mode", "Aktion", slider["mode"], SLIDER_MODES)
            form.check("reverse", "Richtung umkehren", slider["reverse"])
            form.entry("min", "Kalibrierung Minimum (ADC)", slider["min"], kind=int)
            form.entry("max", "Kalibrierung Maximum (ADC)", slider["max"], kind=int)
            form.entry("deadband", "Totzone gegen Zittern (0–64)", slider["deadband"], kind=int)
            form.entry("step", "Abstand pro Tastenschritt (1–255)", slider["step"], kind=int)
            form.entry("low", "Aktion abwärts", f"0x{slider['low']:04X}", kind="code")
            form.entry("high", "Aktion aufwärts", f"0x{slider['high']:04X}", kind="code")
            for caption, mode, low, high in (("Zoom (relativ)", 1, 0x0156, 0x0157),
                                            ("Lautstärke (relativ)", 1, 0xAA, 0xA9),
                                            ("Lautstärke Windows 0-100 %", 5, 0, 0),
                                            ("Mausrad", 1, 0xDB, 0xDA)):
                button(form.parent, caption, lambda m=mode, lo=low, hi=high:
                       self.change(lambda p: p["layers"][self.layer]["slider"].update(mode=m, low=lo, high=hi))).pack(
                           fill="x", padx=14, pady=3)
            form.note("Windows 0-100 %: setzt die Lautstärke exakt nach Reglerposition.\n"
                      "Benötigt die laufende OmniPad-App und die neue Firmware.\n"
                      "Ohne App funktionieren weiterhin nur relative Lauter/Leiser-Tasten.")
            button(form.parent, "Live-Wert als Minimum", lambda: self.calibrate("min")).pack(fill="x", padx=14, pady=3)
            button(form.parent, "Live-Wert als Maximum", lambda: self.calibrate("max")).pack(fill="x", padx=14, pady=3)
        form.apply(self.apply_key_form)

    def apply_key_form(self):
        try:
            values = self.key_form.values()
            kind, index = self.target
            if kind == "key":
                key = deepcopy(self.current_layer["keys"][index])
                key["label"] = values["label"]
                if "term" in values:
                    key["term"] = values["term"]
                for number in range(len(SLOTS[key["mode"]])):
                    key["codes"][number] = values[f"code{number}"]
                self.change(lambda p: p["layers"][self.layer]["keys"].__setitem__(index, key))
            elif kind == "encoder":
                self.change(lambda p: p["layers"][self.layer]["encoders"].__setitem__(index, values["code"]))
            else:
                self.change(lambda p: p["layers"][self.layer]["slider"].update(values))
        except ValueError as error:
            messagebox.showerror("Einstellung prüfen", str(error), parent=self.window)

    def calibrate(self, endpoint):
        if not self.detection or self.detection.slider_raw is None:
            messagebox.showinfo("Kalibrierung", "Für die Kalibrierung wird ein Live-Wert des Pads benötigt.", parent=self.window)
            return
        self.change(lambda p: p["layers"][self.layer]["slider"].__setitem__(endpoint, self.detection.slider_raw))

    @staticmethod
    def key_name(index):
        return f"K{index + 1}" if index < 10 else ("Encoder-Druck" if index == 10 else "K0")

    def draw_keys(self):
        if not hasattr(self, "key_canvas"):
            return
        canvas = self.key_canvas
        canvas.delete("all")
        self.key_rectangles.clear()
        width = max(560, canvas.winfo_width())
        step = min(122, (width - 155) / 4)
        for index, key in enumerate(self.keys):
            x, y = 20 + key["x"] * step, 24 + key["y"] * 79
            self.draw_key(("key", index), x, y, key.get("w", 1) * step - 8,
                          key.get("h", 1) * 79 - 8, self.key_name(index),
                          self.key_caption(index), index)
        x = 20 + 4 * step + 12
        for index, title in ((11, "K0"), (10, "Druck")):
            y = 24 if index == 11 else 83
            self.draw_key(("key", index), x, y, 98, 51, title,
                          self.key_caption(index), index)
        for direction, title in enumerate(("↶ Links", "↷ Rechts")):
            self.draw_key(("encoder", direction), x, 142 + direction * 59, 98, 51,
                          title, label_for_code(self.current_layer["encoders"][direction]))
        slider_y = 24 + 3 * 79 + 16
        self.draw_key(("slider", 0), 20, slider_y, width - 48, 54, "Schieberegler · GP28",
                      SLIDER_MODES[self.current_layer["slider"]["mode"]])
        if self.detection and self.detection.slider_percent is not None:
            value = self.detection.slider_percent
            canvas.create_rectangle(30, slider_y + 45, 30 + (width - 68) * value / 100,
                                     slider_y + 49, fill=ACCENT, outline="")

    def key_caption(self, index):
        key = self.current_layer["keys"][index]
        if key["mode"]:
            assigned = sum(code > 1 for code in key["codes"][:len(SLOTS[key["mode"]])])
            return f"{MODES[key['mode']]} · {assigned} Aktionen"
        return key["label"] or action_name(self.profile, key["codes"][0])

    def draw_key(self, target, x, y, width, height, title, detail, physical=None):
        down = physical is not None and self.detection and self.detection.mask & (1 << physical)
        self.key_rectangles[target] = (x, y, x + width, y + height)
        canvas = self.key_canvas
        canvas.create_rectangle(x, y, x + width, y + height,
                                 fill="#2e6656" if down else KEY, width=2,
                                 outline=ACCENT if target == self.target else "#424e5c")
        canvas.create_text(x + 8, y + 7, text=title, fill=MUTED, anchor="nw", font=("Segoe UI", 9))
        max_chars = max(5, int(width / 7))
        canvas.create_text(x + 8, y + height - 8, text=detail[:max_chars], fill=TEXT,
                            anchor="sw", font=("Segoe UI", 10, "bold"))

    def target_at(self, x, y):
        return next((target for target, (left, top, right, bottom) in self.key_rectangles.items()
                     if left <= x <= right and top <= y <= bottom), None)

    def select_target(self, target):
        self.target = target
        self.action_slot = 0
        self.refresh_key_form()
        self.refresh_key_shortcuts()
        if target[0] == "slider":
            self.key_side.select(self.key_settings)
        else:
            self.key_side.select(self.key_palette)
        self.draw_keys()

    def select_at(self, event):
        target = self.target_at(event.x, event.y)
        if target:
            self.select_target(target)

    def context_key(self, event):
        target = self.target_at(event.x, event.y)
        if not target:
            return
        self.select_target(target)
        menu = tk.Menu(self.window, tearoff=False)
        if target[0] == "key":
            menu.add_command(label="Displaytext bearbeiten", command=self.focus_label)
            menu.add_command(label="Im Display-Studio anzeigen", command=self.display_key)
            menu.add_command(label="Display-Auslöser zuordnen", command=self.display_trigger)
            menu.add_command(label="Layer-Zugang zuordnen", command=self.layer_trigger)
            menu.add_command(label="Belegung kopieren", command=lambda: self.copy_key())
            if self.clipboard:
                menu.add_command(label="Belegung einfügen", command=self.paste_key)
            menu.add_command(label="Auf anderen Layer kopieren", command=self.copy_key_layer)
            menu.add_separator()
            menu.add_command(label="Makro aufnehmen & zuweisen", command=lambda: self.record_macro(assign_default=True))
        menu.add_command(label="Erkennung öffnen", command=lambda: self.notebook.select(self.detect_page))
        menu.tk_popup(event.x_root, event.y_root)

    def focus_label(self):
        self.key_side.select(self.key_settings)
        widget = self.key_form.widgets["label"]
        widget.focus_set()
        widget.selection_range(0, "end")

    def copy_key(self):
        self.clipboard = deepcopy(self.current_layer["keys"][self.target[1]])

    def paste_key(self):
        if self.clipboard and self.target[0] == "key":
            self.change(lambda p: p["layers"][self.layer]["keys"].__setitem__(self.target[1], deepcopy(self.clipboard)))

    def copy_key_layer(self):
        target = simpledialog.askinteger("Belegung kopieren", "Ziel-Layernummer (1–12)",
                                         minvalue=1, maxvalue=len(self.profile["layers"]), parent=self.window)
        if target:
            value = deepcopy(self.current_layer["keys"][self.target[1]])
            self.change(lambda p: p["layers"][target - 1]["keys"].__setitem__(self.target[1], value))

    def display_key(self):
        self.notebook.select(self.screen_page)
        self.screen_page.pages.select(0)
        self.screen_page.add(1, binding=2, key=self.target[1])

    def display_trigger(self):
        # Display layout editing was removed. Key gestures remain in Layer-Zugänge.
        self.layer_trigger()

    def layer_trigger(self):
        self.notebook.select(self.layer_entries)
        key = self.current_layer["keys"][self.target[1]]
        self.layer_entries.set_selection(self.layer, self.target[1], key["mode"], self.action_slot)

    def refresh_actions(self):
        if not hasattr(self, "actions"):
            return
        query = self.search.get().casefold()
        keys = [(name, code) for name, code in BASIC_CODES.items() if code < 0xA0 or 224 <= code <= 231]
        shortcuts = [(name, code) for name, code in BASIC_CODES.items() if code >= 0xA0 and not 224 <= code <= 231]
        categories = [
            keys, shortcuts, [(name, code) for code, name in layer_choices(self.profile)],
            [(name, code) for code, name in DISPLAY_ACTIONS.items()],
            [(f"Snippet · {item['name']}", 0x7700 + i) for i, item in enumerate(self.profile["snippets"])],
        ]
        category = self.category.current()
        entries = categories[category - 1] if category > 0 else [item for items in categories for item in items]
        matching = [(name, code) for name, code in entries if query in name.casefold() or query in f"0x{code:04x}"]
        if matching == getattr(self, "action_entries", None):
            return
        self.action_entries = matching
        self.actions.delete(0, "end")
        for name, code in self.action_entries:
            self.actions.insert("end", name)

    def choose_action(self, row=None):
        if row is None:
            selected = self.actions.curselection()
            if not selected:
                return
            row = selected[0]
        code = self.action_entries[row][1]
        kind, index = self.target
        if kind == "key":
            slot = self.action_slot
            mode = self.current_layer["keys"][index]["mode"]
            self.change(lambda p: set_key_action(p["layers"][self.layer]["keys"][index], index, mode, slot, code))
        elif kind == "encoder":
            self.change(lambda p: p["layers"][self.layer]["encoders"].__setitem__(index, code))
        else:
            self.status.set("Die Regleraktionen werden rechts im Regler-Menü eingestellt.")

    def click_action(self, event):
        row = self.actions.nearest(event.y)
        bounds = self.actions.bbox(row) if self.action_entries else None
        if bounds and bounds[1] <= event.y < bounds[1] + bounds[3]:
            self.choose_action(row)

    def create_lighting(self):
        left = tk.Frame(self.light_page, bg=PANEL)
        left.pack(side="left", fill="both", expand=True, pady=(8, 0))
        self.light_canvas = tk.Canvas(left, bg=PANEL, highlightthickness=0)
        self.light_canvas.pack(fill="both", expand=True)
        self.light_canvas.bind("<Configure>", lambda _: self.draw_light_preview())
        self.light_canvas.bind("<Button-1>", self.led_button_down)
        self.light_canvas.bind("<B1-Motion>", self.led_drag_move)
        self.light_canvas.bind("<ButtonRelease-1>", self.led_button_up)
        self.light_canvas.bind("<Left>", lambda _: self.nudge_led(-1, 0))
        self.light_canvas.bind("<Right>", lambda _: self.nudge_led(1, 0))
        self.light_canvas.bind("<Up>", lambda _: self.nudge_led(0, -1))
        self.light_canvas.bind("<Down>", lambda _: self.nudge_led(0, 1))
        self.light_canvas.bind("<Shift-Left>", lambda _: self.nudge_led(-5, 0))
        self.light_canvas.bind("<Shift-Right>", lambda _: self.nudge_led(5, 0))
        self.light_canvas.bind("<Shift-Up>", lambda _: self.nudge_led(0, -5))
        self.light_canvas.bind("<Shift-Down>", lambda _: self.nudge_led(0, 5))
        actions = tk.Frame(left, bg=PANEL)
        actions.pack(fill="x", padx=12, pady=(6, 2))
        self.led_show_numbers = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="LED-Nummern", variable=self.led_show_numbers,
                        command=self.draw_light_preview).pack(side="left")
        button(actions, "Anordnung laden", self.import_led_layout).pack(side="left", padx=(9, 0))
        button(actions, "Speichern unter", self.export_led_layout).pack(side="left", padx=(5, 0))
        button(actions, "Rückgängig", self.undo_led_layout).pack(side="left", padx=(5, 0))
        button(actions, "Zurücksetzen", self.reset_led_layout).pack(side="left", padx=(5, 0))
        self.led_status = tk.StringVar(value="LED anklicken und ziehen · Pfeiltasten: 1 px · Shift: 5 px")
        label(left, "", color=MUTED, textvariable=self.led_status).pack(anchor="w", padx=18, pady=(3, 0))
        label(left, "1:1 · Matrix 0–29 (6×5) · Frame 30–72 (43 unverändert)",
              color=MUTED).pack(anchor="w", padx=18, pady=(0, 6))
        assign_tools = tk.Frame(left, bg=PANEL)
        assign_tools.pack(fill="x", padx=12, pady=(0, 8))
        button(assign_tools, "LED → gewählte Zone", self.assign_led_zone).pack(side="left")
        button(assign_tools, "Zeilenweise", lambda: self.set_matrix_order("rows")).pack(
            side="left", padx=4)
        button(assign_tools, "Zickzack", lambda: self.set_matrix_order("serpentine")).pack(side="left")
        if self.led_layout_warning:
            self.led_status.set("LED-Layout ungültig – Standardpositionen geladen")
        self.light_settings = ScrollPanel(self.light_page, 320)
        self.light_settings.pack(side="right", fill="y", padx=(12, 0), pady=(8, 0))
        self.light_live = tk.BooleanVar(value=True)
        self.light_live_status = tk.StringVar()
        self.zone = 0
        self.window.after(80, self.animate_lights)

    def refresh_light_form(self):
        self.light_settings.clear()
        form = self.light_form = Form(self.light_settings.content)
        form.title("Beleuchtung pro Layer")
        ttk.Checkbutton(form.parent, text="Live am Pad", variable=self.light_live,
                        command=self.refresh_light_live_status).pack(anchor="w", padx=14)
        label(form.parent, textvariable=self.light_live_status, size=9, color=MUTED,
              wraplength=270).pack(anchor="w", padx=14, pady=(4, 8))
        chosen = form.choice("zone", "LED-Zone", self.zone,
                             [f"{name} · {self.led_zone_map.count(index)} LEDs"
                              if index < 5 else "Frame · 43 LEDs (unverändert)"
                              for index, name in enumerate(ZONE_NAMES)])
        chosen.trace_add("write", lambda *_: self.select_zone(chosen))
        zone = (self.current_layer.get("matrix_zones", [zone_config() for _ in MATRIX_ZONES])[self.zone]
                if self.zone < 5 else self.current_layer["lighting"][1])
        form.check("enabled", "LED-Gruppe einschalten", zone["enabled"])
        form.choice("effect", "Animation", zone["effect"], EFFECTS)
        form.color("color_a", "Farbe A", zone["color_a"])
        form.color("color_b", "Farbe B", zone["color_b"])
        form.entry("brightness", "Helligkeit (0–64)", zone["brightness"], kind=int)
        form.entry("speed", "Geschwindigkeit (0–255)", zone["speed"], kind=int)
        form.check("reverse", "Animationsrichtung umkehren", zone["reverse"])
        form.title("Animationstrigger")
        for bit, caption in ((1, "Tastendruck"), (2, "Encoder · Lauflicht in Drehrichtung"),
                             (4, "Layer-Wechsel"), (8, "Reglerbewegung")):
            form.check(f"trigger{bit}", caption, bool(zone["triggers"] & bit))
        form.entry("duration", "Triggerdauer in 10 ms (1–255)", zone["duration"], kind=int)
        form.apply(self.apply_lighting)
        button(form.parent, "Layerfarbe als Farbe A",
               lambda: self.change(lambda p: (
                   p["layers"][self.layer].setdefault(
                       "matrix_zones", [zone_config() for _ in MATRIX_ZONES])[self.zone]
                   if self.zone < 5 else p["layers"][self.layer]["lighting"][1]
               ).__setitem__("color_a", p["layers"][self.layer]["color"]))).pack(
                   fill="x", padx=14, pady=4)

    def select_zone(self, variable):
        choice = variable.get()
        self.zone = next((i for i, name in enumerate(ZONE_NAMES)
                          if choice.startswith(name)), 0)
        self.refresh_light_form()
        self.refresh_light_live_status()
        self.draw_light_preview()

    def lighting_form_values(self):
        values = self.light_form.values()
        values.pop("zone")
        values["triggers"] = sum(bit for bit in (1, 2, 4, 8) if values.pop(f"trigger{bit}"))
        return values

    def lighting_preview_zones(self):
        saved = self.current_layer["lighting"]
        try:
            zones = deepcopy(saved)
            if self.zone == 5:
                zones[1] = self.lighting_form_values()
            elif self.zone < 5:
                zones[0] = self.lighting_form_values()
            return zones, encode_lighting(zones)
        except ValueError:
            # A number can be temporarily empty or out of range while typing.
            return saved, encode_lighting(saved)

    def refresh_light_live_status(self):
        if not self.device:
            text = "Livevorschau wartet auf USB"
        elif not (self.capabilities and self.capabilities["light_preview"]):
            text = "Livevorschau am Pad benötigt Firmware 6"
        elif self.tester_page.active or (self.detection and self.detection.enabled):
            text = "Livevorschau pausiert während des Tests"
        elif self.light_live.get() and self.zone < 5:
            text = "Matrix-Zonen: PC-Vorschau live · Pad nach „Auf Pad speichern“"
        elif self.light_live.get():
            text = "Frame-Vorschau live am Pad · Übernehmen behält sie im Entwurf"
        else:
            text = "Livevorschau am Pad ausgeschaltet"
        if self.light_live_status.get() != text:
            self.light_live_status.set(text)

    def lighting_preview_payload(self):
        if (not self.capabilities or not self.capabilities["light_preview"] or not self.light_live.get()
                or self.tester_page.active or self.tester_page.pending
                or (self.detection and self.detection.enabled)
                or self.notebook.select() != str(self.light_page)):
            return None
        # Legacy 0x79 previews the entire Main group, not a single matrix
        # zone. Do not present a misleading hardware preview for zones 0..4.
        if self.zone < 5:
            return None
        return self.lighting_preview_zones()[1]

    def apply_lighting(self):
        try:
            values = self.lighting_form_values()
            def apply(p):
                layer = p["layers"][self.layer]
                if self.zone < 5:
                    layer.setdefault("matrix_zones", [zone_config() for _ in MATRIX_ZONES])[self.zone].update(values)
                else:
                    layer["lighting"][1].update(values)
            self.change(apply)
        except ValueError as error:
            messagebox.showerror("Beleuchtung", str(error), parent=self.window)

    def animate_lights(self):
        if self.closing:
            return
        self.preview_phase += 1
        if self.notebook.select() == str(self.light_page):
            self.draw_light_preview()
        self.window.after(60, self.animate_lights)

    def update_led_status(self):
        if self.led_selected is None:
            self.led_status.set("LED anklicken und ziehen · Pfeiltasten: 1 px · Shift: 5 px")
            return
        x, y = self.led_positions[self.led_selected]
        group = ZONE_NAMES[self.led_zone_map[self.led_selected]] if self.led_selected < MAIN_COUNT else "Frame"
        self.led_status.set(
            f"LED {self.led_selected:02d} · {group} · X {x*100:.1f} % / Y {y*100:.1f} %")

    def led_button_down(self, event):
        self.light_canvas.focus_set()
        width = self.light_canvas.winfo_width()
        height = self.light_canvas.winfo_height()
        hits = []
        for index, point in enumerate(self.led_positions):
            x, y = to_canvas(point, width, height)
            distance2 = (event.x-x)**2 + (event.y-y)**2
            limit = 12 if index < MAIN_COUNT else 13
            if distance2 <= limit**2:
                hits.append((distance2, index))
        self.led_selected = min(hits)[1] if hits else None
        self.led_drag_start = deepcopy(self.led_positions) if hits else None
        self.led_drag_changed = False
        self.update_led_status()
        self.draw_light_preview()

    def led_drag_move(self, event):
        if self.led_selected is None or self.led_drag_start is None:
            return
        point = from_canvas(event.x, event.y,
                            self.light_canvas.winfo_width(),
                            self.light_canvas.winfo_height())
        if point != self.led_positions[self.led_selected]:
            self.led_positions[self.led_selected] = point
            self.led_drag_changed = True
            self.update_led_status()
            self.draw_light_preview()

    def commit_led_positions(self, previous):
        if previous == self.led_positions:
            return
        try:
            write_positions(self.led_positions)
        except (OSError, ValueError) as error:
            self.led_positions = previous
            messagebox.showerror("LED-Anordnung", str(error), parent=self.window)
            self.draw_light_preview()
            self.update_led_status()
            return
        self.led_undo.append(previous)
        self.led_undo = self.led_undo[-50:]
        self.update_led_status()
        self.draw_light_preview()

    def led_button_up(self, _):
        previous = self.led_drag_start
        self.led_drag_start = None
        if previous is not None and self.led_drag_changed:
            self.commit_led_positions(previous)
        self.led_drag_changed = False

    def nudge_led(self, dx, dy):
        if self.led_selected is None:
            return
        previous = deepcopy(self.led_positions)
        x, y = to_canvas(self.led_positions[self.led_selected],
                         self.light_canvas.winfo_width(), self.light_canvas.winfo_height())
        self.led_positions[self.led_selected] = from_canvas(
            x + dx, y + dy, self.light_canvas.winfo_width(), self.light_canvas.winfo_height())
        self.commit_led_positions(previous)

    def undo_led_layout(self):
        if not self.led_undo:
            return
        previous = self.led_undo.pop()
        try:
            write_positions(previous)
        except (OSError, ValueError) as error:
            self.led_undo.append(previous)
            messagebox.showerror("LED-Anordnung", str(error), parent=self.window)
            return
        self.led_positions = previous
        self.update_led_status()
        self.draw_light_preview()

    def reset_led_layout(self):
        if not messagebox.askyesno(
                "LED-Anordnung zurücksetzen",
                "Alle 73 LED-Positionen auf die Ausgangsansicht zurücksetzen?\n"
                "Die 43 Frame-LEDs bleiben in ihrer bisherigen Nummernfolge.",
                parent=self.window):
            return
        previous = deepcopy(self.led_positions)
        self.led_positions = default_positions()
        self.commit_led_positions(previous)

    def import_led_layout(self):
        path = filedialog.askopenfilename(
            title="LED-Anordnung laden",
            filetypes=[("OmniPad LED-Layout", "*.json")], parent=self.window)
        if not path:
            return
        try:
            positions = read_positions(Path(path))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("LED-Anordnung", str(error), parent=self.window)
            return
        previous = deepcopy(self.led_positions)
        self.led_positions = positions
        self.commit_led_positions(previous)

    def export_led_layout(self):
        path = filedialog.asksaveasfilename(
            title="LED-Anordnung speichern",
            initialfile="omnipad.led-layout.json", defaultextension=".json",
            filetypes=[("OmniPad LED-Layout", "*.json")], parent=self.window)
        if path:
            try:
                write_positions(self.led_positions, Path(path))
            except (OSError, ValueError) as error:
                messagebox.showerror("LED-Anordnung", str(error), parent=self.window)

    def assign_led_zone(self):
        if self.led_selected is None or self.led_selected >= MAIN_COUNT:
            messagebox.showinfo("LED-Zone", "Bitte eine der Matrix-LEDs 0–29 auswählen.",
                                parent=self.window)
            return
        if self.zone == 5:
            messagebox.showinfo("LED-Zone", "Die Frame-Gruppe bleibt LED 30–72. "
                                "Wähle eine der fünf Matrix-Zonen.", parent=self.window)
            return
        index = self.led_selected
        if self.change(lambda p: p.setdefault("led_zone_map", default_zone_map()).__setitem__(
                index, self.zone)):
            self.led_zone_map = validate_zone_map(self.profile["led_zone_map"])
            self.update_led_status()
            self.draw_light_preview()

    def set_matrix_order(self, order):
        if not messagebox.askyesno(
                "Matrix-Datenrichtung",
                "Die ersten 30 LED-Positionen und Zonenzuordnungen werden neu "
                "geordnet. Die 43 Frame-LEDs bleiben unverändert. Fortfahren?",
                parent=self.window):
            return
        previous = deepcopy(self.led_positions)
        desired = matrix_positions(order)
        base_map = default_zone_map()
        if order == "serpentine":
            mapped = [base_map[row * 5 + (4-col if row % 2 else col)]
                      for row in range(6) for col in range(5)]
        else:
            mapped = base_map
        if self.change(lambda p: p.__setitem__("led_zone_map", mapped)):
            self.led_zone_map = list(mapped)
            self.led_positions = desired + self.led_positions[MAIN_COUNT:]
            self.commit_led_positions(previous)
            self.draw_light_preview()

    def draw_light_preview(self):
        if not hasattr(self, "light_canvas"):
            return
        canvas = self.light_canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        left, top, right, bottom = square_bounds(width, height)
        canvas.create_rectangle(left, top, right, bottom,
                                fill="#192028", outline="#3c4855", width=2)
        layer = self.current_layer
        matrix = layer.get("matrix_zones", [zone_config() for _ in MATRIX_ZONES])
        for zone_index in range(6):
            if zone_index < 5:
                indices = [i for i in range(MAIN_COUNT) if self.led_zone_map[i] == zone_index]
                zone = matrix[zone_index]
            else:
                indices = list(range(MAIN_COUNT, LED_COUNT))
                zone = layer["lighting"][1]
            if zone_index == self.zone and hasattr(self, "light_form"):
                try:
                    zone = self.lighting_form_values()
                except (ValueError, KeyError, TypeError):
                    pass
            count = len(indices)
            if not count:
                continue
            for local, led_number in enumerate(indices):
                phase = self.preview_phase * (zone["speed"] + 16) / 200
                position = count - 1 - local if zone["reverse"] else local
                blend, level = 0, zone["brightness"] / 64
                effect = zone["effect"]
                if effect == 1:
                    blend = position % 2
                elif effect == 2:
                    blend = int(position >= count // 2)
                elif effect == 3:
                    blend = position / max(1, count - 1)
                elif effect == 4:
                    blend = int((position + int(phase)) % count >= 4)
                elif effect == 5:
                    wave = phase % 256
                    level *= (32 + (wave * 2 if wave < 128 else (255 - wave) * 2) * 7 / 8) / 255
                elif effect == 6:
                    distance = (position + count - int(phase) % count) % count
                    level *= (8 - distance) / 8 if distance < 8 else 1 / 16
                elif effect == 7:
                    blend = int((position * 37 + int(phase) * 13) % 97 < 8)
                a, b = zone["color_a"], zone["color_b"]
                rgb = [round((int(a[i:i + 2], 16) * (1 - blend) +
                              int(b[i:i + 2], 16) * blend) * level)
                       for i in (1, 3, 5)]
                if effect == 8:
                    import colorsys
                    rgb = [round(channel * level * 255) for channel in colorsys.hsv_to_rgb(
                        (position / count + phase / 255) % 1, 1, 1)]
                color = "#" + "".join(f"{max(0, min(255, channel)):02x}"
                                    for channel in rgb) if zone["enabled"] else "#293039"
                x, y = to_canvas(self.led_positions[led_number], width, height)
                radius = 9 if led_number < MAIN_COUNT else 8
                selected = led_number == self.led_selected
                canvas.create_oval(
                    x-radius, y-radius, x+radius, y+radius, fill=color,
                    outline=ACCENT if selected else "#50606e",
                    width=3 if selected else 1,
                    tags=(f"led-{led_number}",))
                if self.led_show_numbers.get():
                    ink = "#11171e" if sum(rgb) > 380 and zone["enabled"] else "#f0eee9"
                    canvas.create_text(
                        x, y, text=str(led_number), fill=ink,
                        font=("Segoe UI", 7, "bold"),
                        tags=(f"led-{led_number}",))
        canvas.create_text(width / 2, top + 13, text=self.current_layer["name"], fill=TEXT,
                           font=("Segoe UI", 14, "bold"))
        canvas.create_text(width / 2, bottom - 12,
                           text=f"{ZONE_NAMES[self.zone]} · Matrix 0–29 / Frame 30–72",
                           fill=MUTED, font=("Segoe UI", 9))

    def create_snippets(self):
        left = tk.Frame(self.snippet_page, bg=PANEL, width=240)
        left.pack(side="left", fill="y", pady=(8, 0))
        left.pack_propagate(False)
        label(left, "Snippets", 14).pack(anchor="w", padx=14, pady=14)
        self.snippet_list = tk.Listbox(left, bg=KEY, fg=TEXT, selectbackground="#73503d",
                                       exportselection=False, relief="flat")
        self.snippet_list.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.snippet_list.bind("<<ListboxSelect>>", self.select_snippet)
        button(left, "+ Snippet", self.add_snippet).pack(fill="x", padx=14, pady=(0, 6))
        button(left, "Duplizieren", self.duplicate_snippet).pack(fill="x", padx=14, pady=(0, 7))
        button(left, "Makro aufnehmen", self.record_macro).pack(fill="x", padx=14, pady=(0, 14))
        self.snippet_body = tk.Frame(self.snippet_page, bg=PANEL)
        self.snippet_body.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(8, 0))

    def refresh_snippets(self):
        if not hasattr(self, "snippet_list"):
            return
        self.snippet_list.delete(0, "end")
        snippets = self.profile["snippets"]
        for index, item in enumerate(snippets):
            self.snippet_list.insert("end", f"{index + 1}  {item['name']}")
        for child in self.snippet_body.winfo_children():
            child.destroy()
        if not snippets:
            label(self.snippet_body, "Lege dein erstes Snippet an.", 16).pack(anchor="w", padx=20, pady=20)
            label(self.snippet_body, "Die Einträge stehen anschließend in der Aktionsauswahl zur Verfügung.",
                  color=MUTED).pack(anchor="w", padx=20)
            return
        self.snippet_selection = min(self.snippet_selection, len(snippets) - 1)
        self.snippet_list.selection_set(self.snippet_selection)
        snippet = snippets[self.snippet_selection]
        self.snippet_form = form = Form(self.snippet_body)
        form.title("Snippet bearbeiten")
        self.snippet_name = form.entry("name", "Name", snippet["name"])
        form.note("Ein Schritt pro Zeile. Beispiele stehen unter dem Eingabefeld. "
                  "Text wird für ein deutsches Tastaturlayout übersetzt.")
        self.snippet_steps = tk.Text(self.snippet_body, height=12, bg=KEY, fg=TEXT,
                                     insertbackground=TEXT, relief="flat", undo=True, font=("Consolas", 11))
        self.snippet_steps.pack(fill="both", expand=True, padx=14, pady=(2, 6))
        lines = []
        for step in snippet["steps"]:
            value = str(step["value"]) if step["type"] in ("text", "delay") else label_for_code(step["value"])
            lines.append(f"{step['type']} {value}")
        self.snippet_steps.insert("1.0", "\n".join(lines))
        builder = tk.Frame(self.snippet_body, bg=PANEL)
        builder.pack(fill="x", padx=14, pady=5)
        kind = tk.StringVar(value="text")
        ttk.Combobox(builder, textvariable=kind, state="readonly",
                     values=["text", "tap", "down", "up", "delay"], width=7).pack(side="left")
        value = tk.StringVar()
        ttk.Combobox(builder, textvariable=value, values=list(BASIC_CODES), width=25).pack(
            side="left", fill="x", expand=True, padx=5)
        def append():
            text = value.get()
            if text:
                current = self.snippet_steps.get("1.0", "end-1c")
                self.snippet_steps.insert("end", ("\n" if current and not current.endswith("\n") else "") + kind.get() + " " + text)
                value.set("")
        button(builder, "+ Schritt", append).pack(side="right")
        label(self.snippet_body, "text Hallo Sina!\ntap Kopieren\ndown Strg\n"
              "delay 150   · Pause in ms\nup Strg", 9, color=MUTED).pack(
                  anchor="w", padx=14, pady=6)
        usage = sum(len(compile_snippet(item)) for item in snippets)
        label(self.snippet_body, f"Gerätespeicher für Snippets · {usage} / {MACRO_POOL_SIZE} Byte",
              color=MUTED).pack(anchor="w", padx=14, pady=6)
        form.apply(self.apply_snippet)

    def select_snippet(self, _):
        selected = self.snippet_list.curselection()
        if selected and selected[0] != self.snippet_selection:
            self.snippet_selection = selected[0]
            self.refresh_snippets()

    def add_snippet(self):
        if len(self.profile["snippets"]) >= MAX_SNIPPETS:
            messagebox.showinfo("Snippets", f"Bis zu {MAX_SNIPPETS} Snippets können gespeichert werden.", parent=self.window)
            return
        self.snippet_selection = len(self.profile["snippets"])
        self.change(lambda p: p["snippets"].append({"name": f"Snippet {self.snippet_selection + 1}", "steps": []}))

    def duplicate_snippet(self):
        if not self.profile["snippets"] or len(self.profile["snippets"]) >= MAX_SNIPPETS:
            return
        copied = deepcopy(self.profile["snippets"][self.snippet_selection])
        copied["name"] += " Kopie"
        self.snippet_selection = len(self.profile["snippets"])
        self.change(lambda p: p["snippets"].append(copied))

    def record_macro(self, assign_default=False):
        """Record to a new existing-format Snippet and optionally assign it to a key."""
        if len(self.profile["snippets"]) >= MAX_SNIPPETS:
            messagebox.showinfo(
                "Makro aufnehmen", f"Maximal {MAX_SNIPPETS} Snippets möglich. "
                "Bitte erst Platz in der Bibliothek schaffen.", parent=self.window)
            return
        selected_layer = self.layer
        selected_key = self.target[1] if self.target[0] == "key" else None
        if selected_key is not None:
            selected_mode = self.profile["layers"][selected_layer]["keys"][selected_key]["mode"]
            selected_slot = min(self.action_slot, len(SLOTS[selected_mode]) - 1)
            display_target = (f"{self.profile['layers'][selected_layer]['name']} · "
                              f"{self.key_name(selected_key)} · {SLOTS[selected_mode][selected_slot]}")
        else:
            selected_mode, selected_slot = 0, 0
            display_target = "Keine Taste ausgewählt (nur Bibliothek)"
        new_index = len(self.profile["snippets"])

        def on_save(name, steps, assign):
            if assign and selected_key is None:
                messagebox.showwarning(
                    "Keine Pad-Taste", "Wähle zuerst eine Taste im Bereich Tasten & Regler "
                    "oder speichere das Makro nur in der Bibliothek.", parent=self.window)
                return False
            if len(self.profile["snippets"]) >= MAX_SNIPPETS:
                messagebox.showerror("Makrospeicher", "Die Snippet-Bibliothek ist voll.",
                                     parent=self.window)
                return False

            def apply(profile):
                if len(profile["snippets"]) >= MAX_SNIPPETS:
                    raise ValueError("Maximal 16 Makros/ Snippets.")
                index = len(profile["snippets"])
                profile["snippets"].append({"name": name, "steps": steps})
                if assign:
                    key = profile["layers"][selected_layer]["keys"][selected_key]
                    set_key_action(key, selected_key, selected_mode, selected_slot,
                                   0x7700 + index)
                # This validates the global 1152-byte macro pool, not just one macro.
                encode_profile(profile)

            if not self.change(apply):
                return False
            self.snippet_selection = new_index
            self.notebook.select(self.snippet_page)
            self.refresh()
            if assign:
                self.status.set(
                    f"Makro '{name}' auf {display_target} im Entwurf belegt · "
                    "Jetzt 'Auf Pad speichern' verwenden.")
            else:
                self.status.set(
                    f"Makro '{name}' in der Snippet-Bibliothek gespeichert · "
                    "In Tasten & Regler als Aktion zuweisen.")
            return True

        MacroRecorder(self.window, default_name=f"Makro {new_index + 1}",
                      target_description=display_target, on_save=on_save)

    def apply_snippet(self):
        try:
            steps = parse_snippet_lines(self.snippet_steps.get("1.0", "end-1c"))
            snippet = {"name": self.snippet_name.get(), "steps": steps}
            compile_snippet(snippet)
            self.change(lambda p: p["snippets"].__setitem__(self.snippet_selection, snippet))
        except ValueError as error:
            messagebox.showerror("Snippet prüfen", str(error), parent=self.window)

    def create_detection(self):
        actions = tk.Frame(self.detect_page, bg=BG)
        actions.pack(fill="x", pady=10)
        button(actions, "Hardware-Test starten", lambda: self.diagnose(True)).pack(side="left")
        button(actions, "Hardware-Test beenden", lambda: self.diagnose(False)).pack(side="left", padx=8)
        self.detect_text = tk.StringVar(value="OmniPad verbinden, um Eingaben zu erkennen.")
        label(self.detect_page, textvariable=self.detect_text, size=13, wraplength=920).pack(
            anchor="w", fill="x", padx=18, pady=18)
        self.detect_log = tk.Listbox(self.detect_page, bg=PANEL, fg=TEXT, relief="flat", font=("Consolas", 11))
        self.detect_log.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def diagnose(self, enabled):
        if not self.device or not self.capabilities or self.busy():
            self.status.set("Der Hardware-Test in der App benötigt die erweiterte OmniPad-Firmware.")
            return
        self.submit(lambda: self.device.diagnose(enabled),
                    lambda _: self.status.set("Hardware-Test aktiv · Tasten lösen hier keine PC-Aktionen aus"
                                              if enabled else "Hardware-Test beendet"))

    def detected(self, value):
        previous = self.detection
        self.detection = value
        # Absolute Windows volume is an explicitly opted-in host-side mode.
        # A new connection or layer change must not cause a volume jump.
        if (self.active_profile and value.enabled and not self.tester_page.active and
                value.slider_raw is not None and
                value.active_layer < len(self.active_profile["layers"])):
            selected_slider = self.active_profile["layers"][value.active_layer]["slider"]
            if selected_slider["mode"] == 5 and previous is not None and (
                    previous.active_layer == value.active_layer and
                    previous.slider_raw is not None):
                target = value.slider_percent
                if (target != previous.slider_percent and
                        (self.volume_last_sent is None or target != self.volume_last_sent)):
                    try:
                        set_master_volume_percent(target)
                        self.volume_last_sent = target
                    except (OSError, WindowsVolumeError) as error:
                        self.status.set(f"Windows-Lautstärke konnte nicht gesetzt werden: {error}")
            else:
                self.volume_last_sent = None
        else:
            self.volume_last_sent = None
        if previous == value:
            return
        if previous is None or previous.active_layer != value.active_layer:
            self.refresh_layers()
        slider = "Regler GP28 · Live-Wert benötigt die erweiterte Firmware"
        if value.slider_raw is not None:
            slider = f"Regler GP28 · {value.slider_percent} % · ADC {value.slider_raw}"
        self.key_live.set(slider)
        text = f"Layer {value.active_layer + 1} · {'Hardware-Test aktiv' if value.enabled else 'Normalbetrieb'}\n{slider}"
        if value.last_key < 12:
            gestures = ["Drücken", "Einzeltipp", "Doppeltipp", "Dreifachtipp", "Vierfachtipp", "Halten"]
            gesture = gestures[min(value.gesture, 5)]
            text += f"\nZuletzt {self.key_name(value.last_key)} · {gesture}"
        sensor_states = ["ADXL deaktiviert", "ADXL wird gesucht", "ADXL erkannt", "ADXL fehlt",
                         "ADXL falsche Kennung", "ADXL I²C-Fehler"]
        text += f"\n{sensor_states[min(value.sensor_status, 5)]} · XYZ {value.sensor_xyz}"
        text += f"\nMatrix über {'PCF8575' if value.expander else 'GPIO'}"
        self.detect_text.set(text)
        events = []
        if previous:
            newly_pressed = value.mask & ~previous.mask
            for index in range(12):
                if newly_pressed & (1 << index):
                    events.append(f"{self.key_name(index)} gedrückt")
            if value.clockwise != previous.clockwise:
                events.append("Encoder rechts")
            if value.counterclockwise != previous.counterclockwise:
                events.append("Encoder links")
            if value.encoder_pushes != previous.encoder_pushes:
                events.append("Encoder-Druck")
            if value.gesture != previous.gesture and value.gesture:
                events.append(f"{self.key_name(value.last_key)} · Geste {value.gesture}")
        for event in events:
            self.detect_log.insert(0, f"{datetime.now():%H:%M:%S}  {event}")
        if self.detect_log.size() > 200:
            self.detect_log.delete(200, "end")
        self.draw_keys()
        if self.notebook.select() == str(self.screen_page):
            self.screen_page.draw()

    def verify_device_profile(self):
        """Compare the live USB profile without modifying either copy."""
        if not self.device or self.busy() or self.tester_page.active:
            return
        try:
            expected = encode_profile(self.profile)
        except (ValueError, KeyError, TypeError) as error:
            messagebox.showerror("Profil prüfen", str(error), parent=self.window)
            return
        draft = deepcopy(self.profile)
        device = self.device

        def check():
            return device.read_profile(), device.capabilities()

        def show(result):
            if self.device is not device:
                return
            raw, capabilities = result
            self.on_device = raw
            self.capabilities = capabilities
            self.generation = capabilities["generation"]
            try:
                actual = decode_profile(raw, draft)
            except (ValueError, KeyError, TypeError) as error:
                messagebox.showerror("Profil prüfen", str(error), parent=self.window)
                return
            self.active_profile = actual
            if raw == expected:
                self.status.set("Pad und Entwurf sind bytegenau identisch")
                messagebox.showinfo(
                    "Profil geprüft", "Pad und Entwurf stimmen vollständig überein. "
                    "Wenn Gesten trotzdem nicht reagieren, ist die Ausführung bzw. "
                    "Tastenerkennung zu prüfen.", parent=self.window)
            else:
                differences = action_differences(draft, actual)
                shown = "\n".join(differences[:20])
                if len(differences) > 20:
                    shown += "\n... {} weitere".format(len(differences) - 20)
                if not differences:
                    shown = "Tasten, Layer und Gesten stimmen überein, andere Einstellungen unterscheiden sich."
                self.status.set("Abweichung: Entwurf und Pad unterscheiden sich")
                messagebox.showwarning(
                    "Profilabweichungen",
                    "Entwurf / Pad:\n\n" + shown +
                    "\n\nEs wurde nichts überschrieben. "
                    "Erst 'Auf Pad speichern' überträgt den Entwurf.",
                    parent=self.window)
            self.refresh_buttons()

        self.submit(check, show)

    def write_profile(self):
        if not self.device or self.busy() or self.tester_page.active:
            return
        if not self.capabilities:
            messagebox.showinfo("Firmware aktualisieren",
                                "Das Pad benötigt die erweiterte Firmware für dieses Profil. "
                                "Dein Entwurf ist lokal gespeichert und kann als Profil exportiert werden.",
                                parent=self.window)
            return
        if not self.capabilities.get("matrix_zones"):
            messagebox.showinfo(
                "Neue LED-Firmware benötigt",
                "Dieses Profil verwendet die 30+43-LED-Konfiguration mit fünf "
                "Matrix-Zonen. Bitte zuerst die passende UF2 flashen. "
                "Vorher OmniPad-Profil und VIA-Belegung sichern. "
                "Die App hat nichts auf das Pad geschrieben.",
                parent=self.window)
            return
        if requires_device_actions(self.profile) and not self.capabilities.get("device_actions"):
            messagebox.showinfo("Firmware aktualisieren",
                                "Dieses Profil verwendet Display-/Geräteaktionen. Bitte die UF2 mit Belegungseditor flashen.",
                                parent=self.window)
            return
        payload = encode_profile(self.profile)
        captured = deepcopy(self.profile)
        generation = self.generation
        def write():
            atomic_json(USER_DATA / "backups" / f"profile-before-{datetime.now():%Y%m%d-%H%M%S}.json",
                        decode_profile(self.device.read_profile()) if self.capabilities["enabled"] else captured)
            caps = self.device.write_profile(payload, generation, lambda done, size: self.progress.put((done, size)))
            if not caps.get("matrix_zones"):
                raise ViaError("Firmware unterstützt die 30-Matrix-LED-Zonen noch nicht. "
                               "Das Geräteprofil ist gespeichert, aber die LED-Zonen fehlen.")
            self.device.write_matrix_zones(captured)
            return caps
        def saved(capabilities):
            self.capabilities = capabilities
            self.generation = capabilities["generation"]
            self.on_device = payload
            self.active_profile = captured
            self.led_zone_map = list(captured.get("led_zone_map", default_zone_map()))
            atomic_json(USER_DATA / "last-device.omnipad.json", captured)
            start = captured["default_layer"]
            name = captured["layers"][start]["name"]
            self.status.set(f"Profil auf dem Pad gespeichert und geprüft · Startlayer {start + 1} {name} aktiviert")
        self.submit(write, saved)

    def import_profile(self):
        path = filedialog.askopenfilename(filetypes=[("OmniPad / VIA Profil", "*.json")], parent=self.window)
        if not path:
            return
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if value.get("schema") == "omnipad-via-backup":
                value = default_profile(value)
            encode_profile(value)
            self.change(lambda p: (p.clear(), p.update(value)))
        except (OSError, ValueError, KeyError, TypeError) as error:
            messagebox.showerror("Profil importieren", str(error), parent=self.window)

    def export_profile(self):
        path = filedialog.asksaveasfilename(defaultextension=".omnipad.json", initialfile="omnipad.omnipad.json",
                                           filetypes=[("OmniPad Profil", "*.omnipad.json")], parent=self.window)
        if path:
            try:
                atomic_json(path, self.profile)
                self.status.set(f"Profil exportiert · {path}")
            except OSError as error:
                messagebox.showerror("Export", str(error), parent=self.window)

    def backup(self):
        if not self.device or self.busy():
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="omnipad-via-backup.json",
                                           filetypes=[("VIA-Sicherung", "*.json")], parent=self.window)
        if path:
            self.submit(self.device.snapshot, lambda snapshot: self.backup_done(path, snapshot))

    def backup_done(self, path, snapshot):
        atomic_json(path, snapshot)
        self.status.set(f"VIA-Sicherung gespeichert · {path}")

    def close(self):
        self.closing = True
        if self.tasks:
            self.window.after(100, self.close)
            return
        if self.autosave_id:
            self.window.after_cancel(self.autosave_id)
            self._save_draft()
        if self.led_drag_start is not None and self.led_drag_changed:
            self.commit_led_positions(self.led_drag_start)
        if self.device:
            try:
                if self.capabilities and (self.tester_page.active or (self.detection and self.detection.enabled)):
                    self.device.diagnose(False)
                if self.preview_sent is not None:
                    self.device.preview_lighting(None)
            except (OSError, RuntimeError):
                pass
            self.device.close()
        self.worker.shutdown(wait=False)
        self.window.destroy()


def main():
    # Multiple windows would compete for the same USB response stream.
    if __import__("sys").platform == "win32":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.CreateMutexW.restype = ctypes.c_void_p
        instance = kernel.CreateMutexW(None, False, "Local\\OmniPadEditor")
        if kernel.GetLastError() == 183:
            existing = ctypes.windll.user32.FindWindowW(None, "OmniPad Editor")
            if existing:
                ctypes.windll.user32.ShowWindow(existing, 9)
                ctypes.windll.user32.SetForegroundWindow(existing)
            kernel.CloseHandle(ctypes.c_void_p(instance))
            return
    root = tk.Tk()
    Editor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
