# OmniPad Editor

Unter Windows `desktop-app\launch.cmd` öffnen. Der Starter benötigt Python 3
mit Tkinter und installiert `hidapi` in einer eigenen virtuellen Umgebung.

Das angeschlossene OMNIscreen 10Pad wird über seine VIA-Schnittstelle ausgelesen.
Die Reiter entsprechen den gemeldeten Layern. Rechts eine Aktion auswählen oder
auf einen Key ziehen, dann mit **Auf Gerät speichern** bestätigen. Der Editor
liest die Änderung zurück. K5, K9, K10, K0 und der Encoder-Druck sind in der
bestehenden Firmware fest belegt. Die Encoder-Drehrichtungen sind bearbeitbar.

**VIA-Sicherung** exportiert Matrix, Encoder, VIA-Makros und lesbare
Beleuchtungswerte. Für eine Sicherung ohne Fenster gibt es `backup.py DATEI`.
Der Export verwendet das OmniPad-Sicherungsformat.

Mit der Firmware aus diesem Branch zeigt der Live-Inspektor den aktiven
Layer. K0 am Pad dreimal drücken, um die Hardware-Eingaben im Matrix-Test
anzuzeigen. Encoder-Druck beendet den Test.
