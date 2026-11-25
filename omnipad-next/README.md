# OmniPad Next – lokaler Windows-Editor

**Start:** `C:\GitHub\OMNIscreen_10Pad\OmniPad_Next.cmd` oder Desktopverknüpfung **OmniPad Next**.

## Aufbau

- **Gerät:** USB/HID erkennen und den LED-Protokollstand anzeigen.
- **LEDs:** 30 Matrix-LEDs und 43 Rahmen-LEDs mit getrennten Grundanimationen für acht Layer.
- **Belegung:** App-Entwurf für Tasten, Mehrfachaktionen, Encoder und Regler. Firmware-Tasten und K0-/Encoder-Systemgesten bleiben unberührt.
- **Display:** Vier Seiten mit extern bearbeitbaren SVG-Designvorlagen. Keine SVG-Geometrie auf der Firmware.

## Grundanimation und Reaktion

Du stellst die Animation für Matrix und Rahmen getrennt ein. Farbe A und B können fest bleiben, zeitlich wechseln oder als Regenbogen über die LEDs laufen.

Bei **Reaktion aktiv** startet die eingestellte Animation nach einer Eingabe in der zugehörigen Zone und stoppt nach der eingestellten Dauer. Tasten, Encoder, Regler und Zusatzbutton haben feste Zonen. Ein Layerwechsel startet Displayzone und Rahmen. Das Farbprofil gilt für den gesamten Layer und verwendet bei einer oder zwei Farben die eingestellten Farben der jeweiligen Grundanimation.

## Licht direkt am Pad

| Tasten halten | Encoder drehen | Encoder drücken |
|---|---|---|
| K5 + K9 | Displayhelligkeit ändern | Displaybeleuchtung ein oder aus |
| K9 + K10 | LED-Helligkeit ändern | LEDs ein oder aus |

Die Kombinationen gelten unabhängig vom gewählten Layer. Die Helligkeitsschritte gelten für die laufende Sitzung.

## Projekt speichern vs. LED-Einstellungen aufs Pad

**Projekt speichern** legt ausschließlich ein lokales JSON unter `omnipad-next/data/projekt.json` ab.

**LEDs auf Pad speichern** schreibt die Beleuchtung aller acht Layer im aktuellen Format. Die App prüft zuerst die Firmware-Version und liest die übertragenen Werte nach dem Speichern zurück. Die bestehende physische LED-Zuordnung wird übernommen. Die Live-Vorschau schreibt nicht ins EEPROM.

Die neue Firmware wird über `C:\GitHub\OMNIscreen_10Pad\build\OmniPad.uf2` geflasht. Die vorhandene QMK-`keymap.c` wird **nicht geändert**; auch der Wechsel zwischen Firmware- und App-Profil bleibt eine Aktion direkt in den Geräteeinstellungen.

## Grenzen und Sicherheit

- Das neue App-Tastenprofil und SVG-Dateien werden **noch nicht** auf das Pad übertragen.
- Das Projekt und eine vor dem Update nur lesend erstellte Sicherung der bisherigen MZ01-Zonen bleiben lokal. Die Sicherung ist `omnipad-next/data/backups/leds_mz01_pre_update_2026-11-24.json`.
- Für HID wird der mit `hidapi` installierte kompilierte Windows-Treiber direkt geladen; das kollidierende Python-Paket `hid` muss nicht global deinstalliert werden.
