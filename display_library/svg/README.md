# OmniPad SVG-Displayvorlagen

Die vier festen Firmware-Ansichten heißen:
- `active-layer`: Aktiver Layer / Layermap (Startbildschirm)
- `layer-list`: Layerliste (Encoder lang)
- `matrix-tester`: Matrixtester (K0 dreimal)
- `settings`: Einstellungen (K0 lang)

Jeder Stil (`industrial`, `terminal`, `spectrum`) enthält je eine SVG-Datei.
Die Dateien können in Inkscape, Illustrator oder jedem anderen SVG-Editor extern geändert werden.

## Technischer Umfang der aktuellen Übertragung

Der RP2040 rendert **keine vollständige SVG-Datei**. Das bestehende 6124-Byte-HID-Profil
überträgt aus der SVG-Vorlage derzeit ausschließlich die folgenden Metadaten:

- `data-omnipad-view`: welcher der vier festen Bildschirme
- `data-omnipad-preset`: 0 Industrial, 1 Terminal, 2 Spectrum
- `data-omnipad-background`: Hintergrundfarbe in #RRGGBB
- `data-omnipad-accent`: Akzentfarbe in #RRGGBB

Alle dynamischen Bedienelemente wie Tasten-Hervorhebung, Layernamen und Menüs werden weiterhin
von der Firmware gezeichnet. Änderungen an SVG-Geometrie oder SVG-Text sind daher **nicht**
automatisch auf dem Gerät sichtbar. Für pixelgenaue eigene SVG-Layouts wäre ein gesonderter
SVG-Rasterisierungs- und Übertragungspfad erforderlich. Die Vorlagen in diesem Ordner sind
optische Entwürfe und Farbvorgaben, keine vollständigen Hardware-Screenshots.

## Bedienung

1. Im OmniPad Editor `Display-Vorlagen` öffnen.
2. Seite wählen, SVG auswählen (oder das gewünschte Stilpreset), `Vorlage aktivieren`.
3. Mit `Auf Pad speichern` die übertragbaren Theme-Daten sichern.
4. Bearbeiten der SVG-Datei ausschließlich in externen Programmen.

Alte frei platzierte Display-Zusatzelemente werden bei der Aktivierung deaktiviert, ohne
im Profil gelöscht zu werden.
