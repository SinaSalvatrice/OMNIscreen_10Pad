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
- **USB-Status** in der Kopfleiste zeigt, ob Windows das OmniPad erkennt und ob die VIA-Verbindung steht. Bei aktiver Verbindung steht dort auch die Firmware-Version.
- **Beleuchtung** gliedert sich pro Layer in Frame, Matrix und Reaktive Zonen. Frame und Matrix besitzen eigene Schalter, Effekte, Farben, Helligkeit und Tempo.
- **Live am Pad** zeigt die gewählte Beleuchtung samt Zonenreaktionen auf dem Gerät. **Übernehmen** speichert den Entwurf. **Auf Pad speichern** übernimmt auch die gerade sichtbaren Änderungen im Beleuchtungseditor und speichert sie dauerhaft auf dem Gerät.
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

## GP28 – absolute Windows-Lautstärke

Bisherige `Lauter`/`Leiser`-Tasten sind relative Schritte. Sie können den
Windows-Wert nicht auf eine bestimmte Reglerposition setzen und erreichen
deshalb oft schon vor dem Ende des Wegs 100 %.

Für eine echte **0–100-%-Abbildung** in **Tasten & Regler → Schieberegler** den
Preset **„Lautstärke Windows 0-100 %“** wählen und **Auf Pad speichern**
anklicken. Das Pad muss dafür die aktualisierte Firmware mit Regler-Modus 5
verwenden.

Solange die Windows-OmniPad-App läuft und verbunden ist, liest sie die
Live-Position des GP28-Reglers und setzt die Standard-Wiedergabelautstärke
über die Windows-Core-Audio-Schnittstelle. Es wird **keine** zusätzliche
Python-Abhängigkeit und kein Autostart-Hintergrunddienst installiert.
Die tatsächliche Hardwarekalibrierung `min`/`max` und `reverse` wird
von der Firmware bereits auf den Live-Prozentwert angewandt. Beim
Verbindungsaufbau oder Layerwechsel wird die Lautstärke nicht plötzlich
verändert; erst eine neue Reglerbewegung überträgt einen Wert.

**Ohne laufende/verbundene App bleibt der Modus 5 wirkungslos.** Für
autonome Steuerung die Voreinstellung **„Lautstärke (relativ)“** verwenden.
Die Zoom-Voreinstellung bleibt relativ (z. B. Zoom 25–400 % in Anwendungen).

## Makro-Aufnahme (Tastenkombinationen und Sequenzen)

**Einzelne Shortcuts brauchst du nicht aufzunehmen:** Im Reiter **Tasten & Regler**
Taste auswählen, unter **Shortcuts & Medien** z. B. **Einfügen** (Strg+V),
**Kopieren** (Strg+C), **Rückgängig** (Strg+Z) oder **Speichern** (Strg+S)
auswählen. Das sind direkte Keycodes, keine Makros.

Für mehrere Schritte im Reiter **Snippet-Bibliothek → Makro aufnehmen**
oder über Rechtsklick auf eine Pad-Taste **Makro aufnehmen & zuweisen**:
1. Namen vergeben, **Aufnahme starten** anklicken.
2. Nur im hervorgehobenen Aufnahmefeld Tastenkombinationen und Folgen drücken.
   **Esc** stoppt, ebenso der Stoppknopf oder Fokusverlust.
3. Die Liste mit **down**, **up** und **delay** wird angezeigt und kann vor dem
   Speichern bearbeitet werden. Unerkannte Tasten werden ausdrücklich gemeldet.
4. **In Bibliothek speichern** oder **Speichern + Taste belegen** (belegt den
   aktuell ausgewählten Layer, die Taste und den Gestenslot). Erst
   **Auf Pad speichern** überträgt das Profil.

Der Recorder erfasst ausschließlich die ausdrücklich im App-Fenster
gedrückten Tasten – **kein systemweiter Hook**, keine Mausbewegungen,
keine andere Anwendung und keine Zwischenablageinhalte. Keine Passwörter,
PINs oder andere Geheimnisse aufnehmen: Makros werden als lesbare
Konfigurationsdaten gespeichert. Die vorherige deutsche Tastenabbildung wird
verwendet. Das neue Makro landet im **bestehenden Snippet-System**, nicht in
einer zweiten Bibliothek. Maximal 16 Snippets und gemeinsam 1152 Byte
Firmware-Makrospeicher. Einträge können weiter manuell angepasst werden.

## Multi-Screen Display-Studio (320 × 240)

Im Display-Studio lassen sich sechs Bildschirmtypen einzeln auswählen:
Homescreen, Layerübersicht, Layerdetails, Einstellungen, Navigation und
Keytester. Jede Ansicht hat drei Stilvorlagen (Industrial, Terminal,
Spectrum) sowie eigene Hintergrund- und Akzentfarben.

Bildschirm auswählen, eine Vorlage wählen, Farben anpassen und
„Bildschirmdesign übernehmen“ anklicken. Bei Home, Layerübersicht,
Layerdetails und Navigation dürfen zusätzliche Texte, Icons und
Flächen eingesetzt werden. Einstellungen und Keytester schützen die
funktionalen Bedienelemente und sind nur gestalterisch anpassbar.

Die sechzehn vorhandenen frei platzierbaren Displayelemente bilden
weiterhin einen **gemeinsamen Pool**. Jedes Element ist zusätzlich
einem der sechs Screens zugeordnet. Alte Layouts und deren Elemente
werden der Layerdetails-Ansicht zugeordnet; existierende Felder gehen
beim Upgrade nicht verloren.

Die sechs Theme-Profile benötigen 40 zusätzliche Bytes. Der neue
Profilblock ist 6124 statt 6084 Byte groß und passt einschließlich
16-Byte-Header weiterhin in beide vorhandenen EEPROM-Slots à 6144 Byte.
Beim Start der neuen Firmware wird eine ältere gültige Profilkopie vor
dem Verwenden um sechs Standard-Themes ergänzt. Die eigentliche
Profilübertragung erfolgt weiterhin mit „Auf Pad speichern“.

**Einmaliger Firmwarewechsel erforderlich**, um das neue
6-Screen-Profil zu verstehen. Die alte Firmware akzeptiert die neue
Profilgröße nicht. Vor dem Flashen den aktuellen Entwurf exportieren.


## Hardware 6×5-Matrix + Frame: 73 LEDs, getrennte Lichtzonen

Die serielle Datenkette an **GP29** besteht jetzt aus **30 Matrix-LEDs**
(physische LED-IDs **0–29**) und den bisherigen **43 unveränderten
Frame-LEDs** (neue IDs **30–72**, vorher 14–56). Frame-DIN wird mit dem
DOUT von LED 29 verbunden; seine eigene 43er-Reihenfolge bleibt erhalten.

Die 6×5-Matrix bekommt eine gemeinsame Grundanimation. Die fünf festen
Zonen reagieren zusätzlich auf Eingaben, sobald **Zonenreaktionen
einschalten** aktiv ist.

| Zone | LEDs | Auslöser |
| --- | ---: | --- |
| Tasten | 16 | Tastendruck |
| Regler | 3 | Reglerbewegung |
| Encoder | 2 | Drehen oder Drücken |
| K0 | 2 | K0 drücken |
| Display | 7 | Layerwechsel |

Jede Zone hat eine eigene Reaktionsfarbe und klingt in etwa 450 ms ab.
In der App prüft **Testen** die gewählte Zone in der Vorschau. Ein
vorhandenes Standard-Zickzack-Mapping bleibt als Verkabelungsreihenfolge
erhalten. Benutzerdefinierte Zonenzuordnungen aus alten Profilen werden
beim Verwenden der neuen Beleuchtung durch die feste Zuordnung ersetzt.

Frame und Matrix bieten 13 Effekte, darunter Pendel, Welle, Farbwechsel
und Doppelkomet. Das Lauflicht am Frame braucht bei Tempo 0 etwa
22 Sekunden pro Runde. **RGB POWER** im Gerätemenü schaltet die
Beleuchtung als Ganzes. Beim Einschalten gelten die gespeicherten
Frame- und Matrix-Einstellungen des Layers, auch bei Firmware-Tastenbelegung.

**Übertragen:** Ab Firmware 8 akzeptiert das Pad die neuen Effekte
und die optionalen Zonenreaktionen. Das Profil bleibt 6124 Byte groß.
Die App sichert das bisherige Profil samt Zonen und liest die neu
gespeicherten Einstellungen zur Prüfung zurück. Vor dem Firmware-Update
OmniPad-Profil und VIA-Belegung exportieren.


**Stromversorgung:** 73 RGB-LEDs dürfen nicht aus dem 3,3-V-Ausgang
des RP2040 gespeist werden. Externe, ausreichend dimensionierte
5-V-Versorgung mit gemeinsamer Masse und Strombegrenzung verwenden.
Der QMK-Helligkeitsgrenzwert bleibt vorsichtig auf 64/255.
