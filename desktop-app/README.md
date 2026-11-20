# OmniPad Editor

Im Repo `C:\GitHub\OMNIscreen_10Pad` liegt der Starter unter
`desktop-app\launch.cmd`. Python 3 mit Tkinter wird benötigt.
Der Starter richtet die USB-Bibliothek in einer eigenen Python-Umgebung ein.

## Bedienung

- Über den Layer-Reiter den Bearbeitungslayer wählen. Die Markierung mit Punkt zeigt den am Pad aktiven Layer.
- Aktionen rechts suchen und auf eine Taste ziehen. Unter **Taste / Regler** die Details bearbeiten und **Übernehmen** drücken.
- Pro Taste stehen **Direkt**, **Tap Dance** mit bis zu vier Tipps und Halten sowie **Durchschalten** mit vier Aktionen bereit.
- Rechtsklick auf eine Taste öffnet Displaytext, Kopieren, Einfügen und die Verknüpfung zum Display-Studio.
- Rechtsklick auf einen Layer öffnet Name, Farbmarkierung, Duplizieren und Startlayer. **+ Layer** fügt einen Layer hinzu.
- Der Schieberegler an **GPIO28 / ADC2** erhält seine eigene Belegung pro Layer. Er kann Auf-/Abwärtsaktionen oder Main-/Frame-Helligkeit steuern. Minimum, Maximum, Schrittweite, Totzone und Richtung sind einstellbar. Firmwareversion 5 dreht die Grundrichtung um. Die Option „Richtung umkehren“ bleibt als Override pro Layer verfügbar.
- **Beleuchtung** bietet neun Effekte, zwei Farben und unabhängige Einstellungen für die 14 Main- und 43 Frame-LEDs. Trigger reagieren auf Taste, Encoder, Layer oder Regler.
- **Quadratische 1:1-Vorschau:** Die LED-Anordnung wird in einem mittig platzierten Quadrat dargestellt, auch wenn das Beleuchtungsfenster breit ist. Drag-and-drop, Tastaturbewegung und die gespeicherten X/Y-Koordinaten nutzen dieselbe quadratische Fläche. Vorhandene LED-Anordnungen bleiben unverändert.
- **Physische LED-Anordnung:** In der Beleuchtungs-Vorschau jede LED (0–56) einzeln anklicken und frei verschieben. Die Nummer bleibt die **echte Position im Datenstrang**, unabhängig von den Bildschirmkoordinaten. Main = 0–13, Frame = 14–56. Optional Nummern einblenden; selektierte LED mit Pfeiltasten um 1 px, mit Shift+Pfeiltasten um 5 px bewegen.
- Die Editor-Anordnung wird sofort nach dem Loslassen lokal in `desktop-app/user-data/led-layout.json` gespeichert und gilt für alle Layer. **Anordnung laden**, **Speichern unter**, **Rückgängig** und **Zurücksetzen** stehen direkt unter der Vorschau. Import/Export verwenden `omnipad-led-layout` v1 mit 57 festen X/Y-Positionen (0–1). Diese Koordinaten sind reine **Editor-Metadaten**, keine firmwareseitige LED-Neuzuordnung und werden **nicht** aufs Pad geflasht. Für die Sicherung auf einem zweiten PC `Speichern unter` verwenden.

- **Snippet-Bibliothek** verwaltet Text, Tasten, gedrückte/gehaltene Tasten und Pausen. Der Schritt-Editor akzeptiert Aktionsnamen wie `tap Kopieren` und `down Strg` sowie Hex-Keycodes. Texte werden für deutsches Tastaturlayout übersetzt.
- **Display-Studio** erstellt Felder, Texte und Icons auf 320 × 240 Pixeln. Ziehen verschiebt, der Eckgriff ändert die Größe. Datenquellen und Sichtbarkeitsregeln lassen sich rechts einstellen. Der Export verwendet `.screen.json`.
- **Tester** protokolliert beobachtete Signale mit GPIO oder Anschluss, Funktion und Messwert.
  Unbelegte Matrixpositionen werden als nicht zugeordnet angezeigt.
  Display, Main-LEDs und Frame-LEDs lassen sich separat ausgeben und am Pad per Sichtprüfung beurteilen.
  Der Tester braucht Firmwareversion 5. Ohne Signal bleibt die Liste leer.
- **Erkennung** zeigt Tasten, Encoder und Regler. Der Hardware-Test unterdrückt PC-Aktionen des Pads.
- **Auf Pad speichern** überträgt das gesamte Profil und liest es zur Prüfung vollständig zurück. Import/Export und Rückgängig/Wiederholen beziehen sich auf den gesamten Entwurf.

Der Editor speichert den Entwurf und USB-Sicherungen in `desktop-app/user-data`.
Dieser Ordner ist in Git ausgeschlossen.

## Firmware und bestehende Belegungen

Die erweiterten Gerätefunktionen benötigen Firmwareversion 4 oder neuer. Der Tester ist ab Version 5 verfügbar.
Vorhandene Firmwareversion 3 lässt sich auslesen und sichern. Beim Verbinden legt
der Editor eine VIA-Sicherung an und übernimmt die vorhandenen Belegungen in den
ersten Entwurf. **Vom Pad laden** ersetzt den Entwurf ausdrücklich.

Vor dem ersten Flashen der Version 4 das gewünschte Profil exportieren.
Der vergrößerte Flash-Speicherbereich und die erweiterte Layerkapazität ändern
die Speicheraufteilung. Nach dem Flashen das exportierte Profil importieren
und **Auf Pad speichern** drücken. Dieser Schritt stellt die Belegung,
Snippets und die weiteren Profileinstellungen her.

Die Firmware wird lokal über build_uf2.bat gebaut. Die einzige
Matrixbelegung steht in keyboards/icst7789v/keyboard.json:
Reihen GP12/GP13/GP14, Spalten GP15/GP26/GP27/GP0.
Kein PCF8575, kein ADXL345; der Schieberegler bleibt an GP28.

K0 ohne zugewiesene Aktion bedient das Modul wie bisher.
K0 zwei Sekunden halten öffnet bei aktivem Editorprofil immer das Modulmenü.
Encoder-Druck beendet den Matrix-Test.

## Gerätespeicher

Die erste Firmwareausbaustufe reserviert zwölf Layer, sechzehn Snippets mit
gemeinsam 1152 Byte Makrocode und sechzehn Displayelemente. Die App zeigt
die eingerichteten Layer an. Das Display verwendet die vorhandene Pixelschrift
mit Großbuchstaben und transliterierten Umlauten. Layernamen haben auf dem
Display fünfzehn, Tastenbeschriftungen elf und statische Feldtexte neunzehn
ASCII-Zeichen. In den Projektdateien bleiben die vollständigen Texte erhalten.

Das erweiterte Profil liegt in zwei geprüften Speicherplätzen.
USB-Daten werden zunächst im RAM gesammelt. Erst ein vollständig empfangenes
und geprüftes Profil wird gespeichert. Makropausen laufen zeitgesteuert,
damit sie die Tastenabfrage nicht anhalten.
