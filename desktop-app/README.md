# OmniPad Editor

Im Repo `C:\GitHub\OMNIscreen_10Pad` liegt der Starter unter
`desktop-app\launch.cmd`. Python 3 mit Tkinter wird benötigt.
Der Starter richtet die USB-Bibliothek in einer eigenen Python-Umgebung ein.

## Bedienung

- Über den Layer-Reiter den Bearbeitungslayer wählen. Die Markierung mit Punkt zeigt den am Pad aktiven Layer.
- Gedrückte Tasten leuchten in der Layeransicht auch im Normalbetrieb grün auf, unabhängig von ihrer Belegung.
- In der Layeransicht eine Taste und rechts die gewünschte Aktion anklicken. Die Aktionsliste lässt sich nach Kategorie und Suchtext filtern.
- Unter dem Pad zwischen **Direkt**, **Multi-Push / Tap Dance** und **Durchschalten** wählen. Die belegten und freien Slots stehen direkt daneben. Einen Slot anklicken und anschließend seine Aktion wählen. **Details** enthält Displaytext, Zeitfenster und manuelle Keycodes.
- **Layer-Zugänge** zeigt alle aktiven Wechsel, Umschalter und Haltebelegungen mit Quelllayer, Taste oder Regler, Geste und Ziel. Zum Ändern eines Tastenzugangs die Zeile anklicken. **Aktuell** zeigt die Aktion, die durch die neue Zuordnung ersetzt wird.
- Rechtsklick auf eine Taste öffnet Displaytext, Kopieren, Einfügen und die Verknüpfung zum Display-Studio.
- Rechtsklick auf einen Layer öffnet Name, Farbmarkierung, Duplizieren und Startlayer. **+ Layer** fügt einen Layer hinzu.
- Der Schieberegler an **GPIO28 / ADC2** erhält seine eigene Belegung pro Layer. Er kann Auf-/Abwärtsaktionen oder Main-/Frame-Helligkeit steuern. Minimum, Maximum, Schrittweite, Totzone und Richtung sind einstellbar. Firmwareversion 5 dreht die Grundrichtung um. Die Option „Richtung umkehren“ bleibt als Override pro Layer verfügbar.
- Die Firmware hält den Reglerwert bei Schwankungen bis etwa 1 % des kalibrierten Wegs stabil. Anzeige, Tester und Regleraktionen verwenden denselben gefilterten Wert. Die kalibrierten Endpunkte bleiben bei 0 % und 100 % erreichbar.
- **Beleuchtung** bietet neun Effekte, zwei Farben und unabhängige Einstellungen für die 14 Main- und 43 Frame-LEDs. Trigger reagieren auf Taste, Encoder, Layer oder Regler.
- **Live am Pad** zeigt mit Firmware 6 die Einstellungen des ausgewählten Layers beim Bearbeiten direkt auf beiden LED-Gruppen. Beim Verlassen des Reiters, während eines Tests oder nach USB-Trennung erscheint wieder die gespeicherte Beleuchtung. **Übernehmen** behält die Änderungen im App-Entwurf, **Auf Pad speichern** überträgt sie dauerhaft.
- **Quadratische 1:1-Vorschau:** Die LED-Anordnung wird in einem mittig platzierten Quadrat dargestellt, auch wenn das Beleuchtungsfenster breit ist. Drag-and-drop, Tastaturbewegung und die gespeicherten X/Y-Koordinaten nutzen dieselbe quadratische Fläche. Vorhandene LED-Anordnungen bleiben unverändert.
- **Physische LED-Anordnung:** In der Beleuchtungs-Vorschau jede LED (0–56) einzeln anklicken und frei verschieben. Die Nummer bleibt die **echte Position im Datenstrang**, unabhängig von den Bildschirmkoordinaten. Main = 0–13, Frame = 14–56. Optional Nummern einblenden; selektierte LED mit Pfeiltasten um 1 px, mit Shift+Pfeiltasten um 5 px bewegen.
- Die Editor-Anordnung wird sofort nach dem Loslassen lokal in `desktop-app/user-data/led-layout.json` gespeichert und gilt für alle Layer. **Anordnung laden**, **Speichern unter**, **Rückgängig** und **Zurücksetzen** stehen direkt unter der Vorschau. Import/Export verwenden `omnipad-led-layout` v1 mit 57 festen X/Y-Positionen (0–1). Diese Koordinaten sind reine **Editor-Metadaten**, keine firmwareseitige LED-Neuzuordnung und werden **nicht** aufs Pad geflasht. Für die Sicherung auf einem zweiten PC `Speichern unter` verwenden.

- **Snippet-Bibliothek** verwaltet Text, Tasten, gedrückte/gehaltene Tasten und Pausen. Der Schritt-Editor akzeptiert Aktionsnamen wie `tap Kopieren` und `down Strg` sowie Hex-Keycodes. Texte werden für deutsches Tastaturlayout übersetzt.
- **Display-Studio** erstellt Felder, Texte und Icons auf 320 × 240 Pixeln. Ziehen verschiebt, der Eckgriff ändert die Größe. Der Reiter **Tasten & Auslöser** ordnet Tasten und Gesten auf dem gewählten Layer den Geräteansichten zu. Er zeigt auch die K0-Standardgesten. Das Displaylayout wird als `.screen.json` exportiert. Die Auslöser gehören zum OmniPad-Profil.
- **Tester** protokolliert beobachtete Signale mit GPIO oder Anschluss, Funktion und Messwert.
  Unbelegte Matrixpositionen werden als nicht zugeordnet angezeigt.
  Display, Main-LEDs und Frame-LEDs lassen sich separat ausgeben und am Pad per Sichtprüfung beurteilen.
  Der vollständige Tester ist ab Firmwareversion 5 verfügbar. Mit älterer Firmware, die den Inspektor unterstützt, sind Live-Eingänge im Basis-Tester verfügbar. Ohne Signal bleibt die Liste leer.
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
Die Standardgeste **K0 halten** öffnet das Modulmenü. Im Display-Studio kann die Geste einer anderen Ansicht zugeordnet werden.
Encoder-Druck beendet den am Pad gestarteten Matrix-Test.

Ab Firmware 6 setzt **Encoder-Taster und K0 gleichzeitig fünf Sekunden halten**
die QMK-/VIA-Belegung und beide OmniPad-Profilspeicher auf Werkseinstellungen zurück.
Das Pad startet neu. Vor Ablauf der fünf Sekunden loslassen, um abzubrechen.
Die zuweisbare Aktion **Clear EEPROM …** öffnet eine Bestätigung auf dem Pad.
Ein neuer Druck auf den Encoder bestätigt, K0 bricht ab. Die aktuelle Firmware
mit Display- und Geräteaktionen liegt nach dem Build als `build/OmniPad.uf2` vor.

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

## Geräteprofil prüfen und konkurrierende Editor-Fenster

**Pad / Entwurf prüfen** liest das aktuelle 6084-Byte-Geräteprofil über USB aus und vergleicht es mit dem Entwurf. Bei Unterschieden werden Startlayer, 1×/2×/3×/4×/Halten-Aktionen, Tastenmodi und Encoderbelegungen getrennt ausgewiesen. Der Vergleich ändert weder den Entwurf noch das Pad. Bei identischen Bytes liegt ein Nicht-Auslösen von Layerwechseln oder Mehrfachtipps nicht an der Übertragung, sondern an der Eingabe-/Firmware-Ausführung.

Die USB-Schnittstelle wird jetzt exklusiv für eine OmniPad-Editor-Instanz reserviert. Ein weiteres Editorfenster kann nicht gleichzeitig auf dieselbe USB-Antwortwarteschlange zugreifen. Bereits laufende ältere Programmversionen oder externe USB-Programme (z. B. VIA) respektieren diese Sperre nicht: Vor dem Test die alten OmniPad-Editorfenster schließen und den aktualisierten Editor neu starten. Bereits gespeicherte Entwürfe bleiben erhalten.

**Wichtig:** „Entwurf gespeichert“ bedeutet nur auf dem PC gespeichert. Erst „Auf Pad speichern“ überträgt und verifiziert den Entwurf. Die neue Prüffunktion liefert den unabhängigen Live-Abgleich.
