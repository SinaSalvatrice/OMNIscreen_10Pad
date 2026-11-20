# OmniScreen Display-Library

15 direkt importierbare `.screen.json`-Vorlagen: drei Designvarianten (Industrial, Terminal, Spectrum) für Einstellungen, Layerindex, Layerliste, Keytester und Navigation. Alle sind 320×240 Pixel, Schema `omnipad-screen` Version 1, maximal 16 Elemente.

Zusätzlich 14 kleine Bausteine in `components/`: Main- und Frame-RGB, RGB-Palette, live Schieberegler, Encoder-Modus, Encoder-Taster, aktiver Layer, letzte Taste, Key-Zähler, Key-Label, Navigationspad, Modus-Schalter, Trennlinie und Tastenmarker.

## Verwendung
OmniPad Editor → Display-Studio → **Vorlagen** öffnet die integrierte Vorlagenbibliothek. **Baustein einfügen** ergänzt ein vorhandenes Layout, solange die 16-Felder-Grenze nicht überschritten wird. Alle Dateien lassen sich auch über „Layout importieren“ einzeln laden.

## Grenzen
Die Firmware speichert gegenwärtig nur **ein aktives Displaylayout pro Profil**. Die fünf Bereiche sind deshalb einzelne importierbare Screens, keine automatisch umschaltbaren Seiten. RGB-Anzeigen, Richtungsmarker und die sieben Namen in der Layerliste sind statische Muster, solange noch keine passenden Live-Bindings vorliegen. Bereits dynamisch: Layername (Binding 1), Tastenlabel (2), Schieberegler (3), letzte Taste (4), Encoder-Modus (5), Anschlagszahl (6). Die Anzeige verwendet kein PCF8575 oder ADXL345. Vor dem Übertragen des Layouts die Funktion mit dem Pad verifizieren.
