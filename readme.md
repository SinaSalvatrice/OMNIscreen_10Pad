# ICST7789V — Waveshare RP2040-Zero / ST7789 hardware tester

## Hardware-SPI with reliable reset bootstrap (current)

Previous builds could render the four colors after flashing, but showed a
white display following a controller reset. This build now **initializes
the ST7789 using the previously proven GPIO bit-bang transport on every boot**,
draws a red 28×28 probe in the upper-left corner, and **only then switches**
GP2/GP3 to QMK's hardware SPI0 for the fast four-quadrant redraw.

Visual diagnosis after flashing and then restarting the controller:
- **Four quadrants + magenta center stripe**: GPIO bootstrap and hardware SPI
  both worked at least for this startup.
- **Just a small red field, not the rest**: GPIO initialization worked,
  but the handover to hardware SPI did not complete correctly.
- **Completely white**: this GPIO initialization also did not produce pixels,
  or firmware did not reach the display routine. Check the short backlight
  blackout at startup before drawing conclusions.

The firmware falls back to bit-banged GPIO automatically if QMK's
`spi_start()` explicitly fails, but the ST7789 is a **write-only panel**:
a successful `spi_start()` cannot prove that pixels actually appeared.
A full visual restart check is therefore still essential.

Use **only local builds** (never GitHub Actions):

```powershell
git pull --ff-only origin main
.\build_uf2.bat
```

The working GPIO-only firmware is protected on
[`backup/qmk-st7789-gpio-working`](https://github.com/SinaSalvatrice/ICST7789V/tree/backup/qmk-st7789-gpio-working),
and the first experimental hardware-SPI firmware is preserved on
[`backup/qmk-st7789-spi-before-reset-fix`](https://github.com/SinaSalvatrice/ICST7789V/tree/backup/qmk-st7789-spi-before-reset-fix).
To disable hardware SPI without changing wiring, set
`#define ICST_USE_HW_SPI 0` in `keyboards/icst7789v/config.h`.

## Earlier hardware-SPI test (superseded)

The working firmware is saved as
[`backup/qmk-st7789-gpio-working`](https://github.com/SinaSalvatrice/ICST7789V/tree/backup/qmk-st7789-gpio-working).
This version keeps the exact same ST7789 init, four quadrants, encoder/PUSH/K0
and matrix logic, but sends data using QMK's `spi_master.h` over SPI0 GP2/GP3.
No change in wiring. Quantum Painter remains off.

A **magenta stripe** through the middle distinguishes this firmware from the
previous GPIO-only build. On a successful flash you should see the original
red/green/blue/black quadrants with that stripe. If still white, the QMK SPI
path is suspect. No GitHub Actions are used.

Local build:
```powershell
git pull --ff-only origin main
.\build_uf2.bat
```

For instant code-level rollback, in `keyboards/icst7789v/config.h` change
`#define ICST_USE_HW_SPI 1` to `#define ICST_USE_HW_SPI 0` and rebuild.
For a full unchanged rollback, use the saved backup branch.


## Current firmware: QMK direct-GPIO ST7789 isolation test

**Why:** The prior Quantum Painter firmware produced a white screen despite the
same hardware working with an Arduino sketch. The current default QMK keymap
therefore sends ST7789 commands and RGB565 pixels on GP2 (SCK) and GP3 (MOSI)
using direct GPIO output, avoiding QMK hardware SPI and Quantum Painter entirely.

**Wiring remains unchanged:** GND/3V3, SCK GP2, MOSI GP3, RST GP4,
DC GP5, CS GP6, BL GP7, encoder A GP8/B GP9/PUSH GP10, K0 GP11.

**Expected after flashing:** four colored quadrants:
red top left, green top right, blue bottom left, black bottom right.
This deliberate simple firmware is not the final Layer Map UI.

- Turn encoder: lower-right quadrant cycles through colors.
- Press encoder: same quadrant advances, and top-left yellow indicator toggles.
- Press K0: lower-right quadrant resets to black; top-right cyan indicator toggles.
- Later attach 11-key 3×4 matrix: bottom-left square changes between white
  and magenta on each matrix key press.
- Optional external NeoPixels on GP29: set `RGBLIGHT_ENABLE = yes` in
  `rules.mk` after wiring an LED and power; QMK RGB lighting stays independent.

This diagnostic operates deliberately slower than hardware SPI and redraws
only small areas after boot. Matrix and NeoPixel allocations remain reserved.

Build locally (NO GitHub Actions):
```powershell
git pull --ff-only origin main
.\build_uf2.bat
```

If the screen still stays all white, confirm that **this new UF2** was flashed.
A white screen would mean that even basic GPIO toggling is not reaching the
controller, or that QMK initialization is not running; do not guess which
without further evidence.

The earlier Quantum Painter implementation is preserved in git history and
can be reinstated once the GPIO isolation test has succeeded.


The **QMK module diagnostic** in `keyboards/icst7789v/` targets the **new 320×240 landscape ST7789 with EC11 encoder + PUSH + K0**. It is intentionally separate from the older **135×240 8-pin Arduino test** in `arduino/`, which remains untouched as a reference.

## Hardware already connected

Use the GPIO labels printed on the RP2040-Zero board, **not Raspberry Pi Pico 40-pin header numbers**.

| Module signal | RP2040-Zero | Notes |
|---|---|---|
| GND | GND | Common ground |
| VCC | 3V3 | Safe 3.3-V supply |
| SCL / SCK | GP2 | SPI0 clock |
| SDA / MOSI | GP3 | SPI0 TX, **not I2C** |
| RES / RST | GP4 | Display reset |
| DC | GP5 | Data / Command |
| CS | GP6 | SPI chip select |
| BLK | GP7 | Backlight driven HIGH |
| Encoder A | GP8 | EC11 |
| Encoder B | GP9 | EC11 |
| Encoder PUSH | GP10 | Switch to GND |
| K0 | GP11 | Switch to GND |

**The display uses native 240×320 geometry and QP rotation 90° for 320×240 landscape.** The GP4/GP6 CS/RST mapping is for the **new module**, not the old Arduino sketch.

## What the QMK test firmware does

- **Status:** display boot/init, encoder CW/CCW counters, encoder push count, K0 count, and matrix key events. The display only redraws on events (no continual full-screen flashing).
- **Colors:** RED / GREEN / BLUE / WHITE / BLACK. Rotate the encoder to enter the page and press its shaft to advance the color.
- **Geometry:** borders, diagonals, and all four corners to check display rotation/clipping.
- **Matrix:** a 3×4 grid for **eleven keys** and event counter. It is already defined but does not require switches to be wired at boot.
- **NeoPixel:** an optional WS2812/SK6812 chain on GP29. The screen shows 'not enabled' until RGBLIGHT is enabled. Press the encoder shaft on this page to cycle colors after LEDs are connected.
- **K0** always returns to the status page. Rotate the encoder to change pages.

The diagnostics firmware still uses normal QMK key scanning. When you attach switches, they send the default keycodes defined in `keymaps/default/keymap.c` (currently number keys / Enter). The dedicated panel buttons are **not** part of the keyboard matrix.

## GPIO expansion plan

| Function | GPIOs | Status |
|---|---|---|
| TFT SPI + control | GP2–GP7 | Active |
| Encoder A/B + PUSH + K0 | GP8–GP11 | Active |
| Matrix rows (3) | GP12, GP13, GP14 | Reserved/configured |
| Matrix columns (4) | GP15, GP26, GP27, GP28 | Reserved/configured |
| Optional external NeoPixel DIN | GP29 | Reserved; disabled in firmware |
| Spare | GP0, GP1 | Unused |

**Matrix diode direction: COL2ROW.** The diode cathode (stripe) faces the row wire. Matrix key positions are 4 + 4 + 3; the last key is wide physically but electrically still a single switch, with [row 2, column 3] unused. This is a provisional electrical layout and can be adapted to the eventual enclosure.

NeoPixels require a proper shared ground, adequate **external power** for the number of LEDs, and preferably a 3.3-to-5 V logic-level shifter if powered at 5 V. **Do not feed 5 V into RP2040 GPIO.**

## QMK UF2 build

The repository is a **QMK keyboard definition**, not a full QMK checkout. The Windows self-hosted CI and `build_uf2.bat`/`build_uf2.sh` copy `keyboards/icst7789v` into a separate QMK checkout. Windows:

```bat
build_uf2.bat
```

With an already configured QMK checkout, after copying `keyboards/icst7789v` into its `keyboards/` folder:

```sh
qmk compile -kb icst7789v -km default
```

This produces a UF2 file (the Windows script copies to `build/ICST7789V.uf2`). To flash, unplug the RP2040-Zero, hold BOOT while plugging USB in, and copy the UF2 to the RPI-RP2 drive.

### Optional NeoPixels

Only **after wiring the LED data line to GP29**, change `RGBLIGHT_ENABLE = no` to `RGBLIGHT_ENABLE = yes` in `keyboards/icst7789v/rules.mk`. The RP2040 uses the **PIO WS2812 driver** (`WS2812_DRIVER = vendor`). Set the real LED count in `config.h` (`RGBLIGHT_LED_COUNT`, initially 1). Rebuild and flash. Matrix and NeoPixels have non-overlapping pins.

### Troubleshooting

- **Black screen**: verify 3V3/GND, BLK=GP7, SPI0 GP2/GP3, DC=GP5, CS=GP6 and RST=GP4. If the Arduino sketch runs but QMK doesn't, check the QMK SPI/Quantum Painter build logs before moving wires.
- **Screen rotated wrong**: change `QP_ROTATION_90` to `QP_ROTATION_270` in `keymap.c`.
- **Encoder backwards**: swap GP8/GP9 wiring or add `#define ENCODER_DIRECTION_FLIP` in `config.h`.
- **No encoder steps**: try changing `resolution` from 4 to 2 in `keyboard.json`.
- **Build fails**: the original keymap had a duplicated device variable, stray statements outside a function, mismatched panel size, and the wrong SPI driver. Those have been corrected in this branch.

## Legacy independent tests

The old `arduino/ST7789V_RP2040_Zero_Test/ST7789V_RP2040_Zero_Test.ino` still targets a **different 135×240 panel** with different CS/RES wiring. `diag_pico/` is also preserved.

## VIA — aktuelle 10Pad-Belegung (2026-11)

**Firmware-Stand:** Die sieben Layer werden in `design/layer_system.json` gepflegt;
`scripts/generate_layer_system.py` aktualisiert den Anzeigecode. Die statischen
Keymaps bilden die VIA-Startbelegung, VIA speichert spätere Änderungen pro Layer
im QMK-EEPROM. Nach neuem Flashen bleiben ältere EEPROM-Belegungen ggf. erhalten;
bei Bedarf in VIA die Belegung zurücksetzen (vorher sichern).

| Layer | Nummer | Verwendung |
|---|---:|---|
| CCSTUDIO | 0 | Z Y G R / Shift Q S frei / Ctrl Alt |
| DEFAULT | 1 | Pfeile wie Foto; übrige Felder frei; Shift/Ctrl/Alt |
| NAV | 2 | Home, Page Up, Pfeile, End |
| TEXT | 3 | Undo, Redo, Fett, Kursiv, Kopieren, Einfügen, Ausschneiden |
| SHORTCUT | 4 | Zwischenablage, Windows-Screenshot, Speichern |
| MACROS | 5 | alle sieben Nutz-Tasten leer; über VIA frei belegen |
| SETTINGS | 6 | RGB an/aus, Effekte, Farbton, Sättigung, Helligkeit |

**Feste Tasten:** K5 = Shift, K9 = Ctrl, K10 = Alt; unabhängig vom VIA-Layer
und mit sofortigem Key-Down/Up. K9 **zweimal kurz tippen** (ohne andere
Taste dazwischen) aktiviert CCSTUDIO. K0 **zweimal tippen** aktiviert DEFAULT.
K0 einmal wechselt Anzeige/Encoder-Modus, lang öffnet das Menü, dreimal
öffnet den Matrix-Test. Im Anzeige-Modus Layer per Encoder auswählen und
per Encoder-Druck aktivieren; im Encoder-Modus lässt VIA CCW/CW pro Layer
belegen. K0 und Encoder-Druck sind separate GPIO-Taster und *keine*
Matrix-Tasten in VIA. Das physische K9-Tap-Dance und die Modifikatoren sind
bewusst nicht umprogrammierbar, auch wenn VIA an den Matrixpositionen
andere gespeicherte Keycodes anzeigen kann.

**VIA laden:** Firmware lokal mit `build_uf2.bat` bauen/flashen.
Anschließend in [usevia.app](https://usevia.app) unter Einstellungen
"Show Design tab" aktivieren, in "Design" die `via.json` aus dem
Repository laden, Gerät verbinden. `VIA_ENABLE=yes`, sieben dynamische
Layer und ein separater Encoder-Map sind im Standard-Keymap aktiv.

**RGB:** 14 WS2812/SK6812 auf GP29, auf Helligkeit 64 begrenzt.
VIA > Lighting > QMK Effects steuert die QMK-Animationen.
VIA > Lighting > One / Two Colors bietet **eine Farbe**, **abwechselnd zwei**,
**7+7 geteilte Farben** und **wandernde Zweifarbpalette**. Farben und
Chase-Geschwindigkeit werden bei VIA-Save im EEPROM gespeichert.
Für Standardanimationen zuerst Palette mode = "Use QMK Effects" auswählen.

**Kein GitHub Actions Build:** nur lokal bauen. Dies ist eine QMK-Änderung;
die Funktion von Display, RGB und USB/VIA ist erst nach Flashen am 10Pad
hardwareseitig verifiziert.

**CC Studio analog:** Encoder CCW/CW = Mausrad hoch/runter (QMK Mouse Keys),
Encoder-Druck = F11. Der GP28-Schieberegler gibt beim Verschieben relative
Windows-Zoom-Schritte (Strg + Ziffernblock Plus/Minus) aus, je ca. 64 ADC-Werte.
Nach dem Aktivieren des CC-Studio-Layers gilt die aktuelle Schieberposition
als Ausgangswert, damit der PC nicht plötzlich zoomt. Für Programme ohne
Strg+Plus/Minus-Zoom ist ggf. eine eigene App-Kombination nötig.

**Tastaturlayout:** Z/Y und Undo/Redo sind für einen Windows-PC mit deutschem
QWERTZ-Layout ausgelegt: QMK sendet für „Z“ die US-HID-Position `KC_Y`.
Bei Umstellung des PC-Layouts auf US müssen die beiden Belegungen in VIA
entsprechend angepasst werden.

## Additional 43 Frame LEDs — second independent RGB zone

The single GP29 WS2812/SK6812 chain now has **57 LEDs**:

| Logical zone | Physical LED index (zero-based) | Count | Driver |
|---|---|---:|---|
| Original main LEDs (keys/display) | 0–13 | 14 | QMK RGBLight / existing VIA main palette |
| Frame LEDs, appended after the original 14 | 14–56 | **43** | Independent custom Frame renderer |

**Wiring:** connect the DIN of the first Frame LED to the DOUT of LED 13,
then daisy-chain the remaining 42 Frame LEDs. Common GND is mandatory.
All LEDs still use the existing GP29 data output; **no second GPIO** needed.
The two zones are logically separate, not two electrically independent ports.

**Power supply warning:** 57 RGB LEDs can theoretically require around
**3.42 A at 5 V** at maximum full-white (57 × 60 mA), of which the Frame
alone could use about **2.58 A**. Provide a correctly sized external regulated
5 V supply, common ground, suitable wiring / power injection and preferably a
3.3 V to 5 V data level shifter. Do **not** power this array through the
RP2040-Zero 3V3 pin. The firmware caps both zones at 64/255 brightness,
but this is not a substitute for correctly rated hardware.

In VIA > **Lighting** there are three submenus:
1. Main LEDs (0–13) – QMK: normal QMK effect, RGB color, speed and brightness.
2. Main LEDs (0–13) – Palette: existing one/two-color choices.
3. **Frame LEDs (14–56):** independent on/off, effect (solid, alternating,
   21+22 split, moving two-color chase, rainbow, breathing), own brightness,
   two colors, speed and reverse direction.

The default Frame state is **enabled, solid warm color, brightness 24/255**.
Switching off the main QMK RGBLight does **not** switch off the Frame LEDs,
and the Frame can be switched off without affecting the main LEDs.

**Configuration persistence:** Frame and existing main palette settings are
stored together in the QMK user EEPROM datablock (v2, 17 bytes). The first
8 bytes match the old v1 layout, allowing the main palette to be migrated.
QMK's VIA keymap storage location may shift after the datablock expansion;
**export the current VIA keymap/macros before flashing** and reload as needed.

The Frame uses a single buffered WS2812 flush for all 43 LEDs per animation
frame instead of one chain flush for each LED, to avoid excessive key latency.
QMK's built-in effect range is limited to 14 LEDs and does not animate the
Frame accidentally. No GitHub Actions or remote flashing are used.


## PCF8575 expander + ADXL345 sensor (optional I2C upgrade)

**Actual photographed hardware:** the blue 16-channel expander breakout is a
**PCF8575**, not an MCP23017. The two chips are NOT software-compatible:
PCF8575 has 16 quasi-bidirectional I/O lines (`P00..P07`, `P10..P17`)
and two-byte read/write port transfers, not MCP23017 configuration registers.

The original firmware uses GP0 as matrix column 3. GP1 is the only unused
RP2040 GPIO. **Do not attach I2C SDA to GP0 until the old matrix wire has
been physically moved to the PCF8575.** The PR adds two build variants:
- `PCF8575_MATRIX=no` (default): preserve original RP2040 GPIO keyboard
  matrix; ADXL345 remains disabled. Display says `GPIO MATRIX`.
- `PCF8575_MATRIX=yes`: use PCF8575 for all seven keyboard matrix wires;
  enable ADXL345 I2C diagnostics.

Both devices share RP2040-Zero **GP0 SDA + GP1 SCL**, plus 3V3/GND.

### PCF8575 breakout connections shown in photo

The five pins on the **left edge of the pictured board** read from top
to bottom: **GND, VCC, SDA, SCL, INT**. Wire as follows:

| PCF8575 photo marking | RP2040-Zero |
| --- | --- |
| GND | GND |
| VCC | 3V3 (not 5V) |
| SDA | GP0 |
| SCL | GP1 |
| INT | Leave unconnected: matrix is polled |

On the photo the **bottom row** reads `GND VDD P00 P01 P02 P03 P04 P05 P06 P07`
from left to right. The **top row** reads `GND VDD P17 P16 P15 P14 P13 P12 P11 P10`
from left to right. You can wire the five left-edge contacts for bus/power;
there is no need to solder both 3V3/GND connections.

### Rewire the existing 3x4 key matrix

Move the seven physical matrix wires from the RP2040 to these markings
on the PCF8575. This retains the existing QMK row/column and VIA layout:

| Original RP2040 pin | New PCF8575 pad | Purpose |
| --- | --- | --- |
| GP12 | P00 | Row R0 |
| GP13 | P01 | Row R1 |
| GP14 | P02 | Row R2 |
| GP15 | P10 | Column C0 |
| GP26 | P11 | Column C1 |
| GP27 | P12 | Column C2 |
| GP0 | P13 | Column C3 |

**The old GP0 -> matrix-column wire must be disconnected at RP2040 GP0**
before attaching I2C SDA there. The existing keyboard diodes remain where
they are. The custom scanner uses the existing `ROW2COL` direction,
pulling one of P10..P13 LOW and reading the weakly pulled-up P00..P02.
The unused PCF pins are left HIGH/released, not driven.

### ADXL345 on the same GP0/GP1 bus

| ADXL345 photo marking | Connect to |
| --- | --- |
| SDA | GP0 (same net as PCF8575 SDA) |
| SCL | GP1 (same net as PCF8575 SCL) |
| VCC | 3V3 |
| GND | GND |
| CS | 3V3 (I2C mode) |
| SDO | GND (I2C address 0x53) |
| INT1, INT2 | Leave unconnected |

The PCF8575 normally responds at 7-bit I2C address `0x20` with all address
jumpers A0/A1/A2 low; inspect this particular board's solder jumpers to
confirm. The ADXL345 address will be `0x53` when SDO=GND.
Use 3.3V I2C pull-ups (typically one pair 4.7k on SDA/SCL for the bus).
Check whether the two modules already include pull-ups, and avoid any
installed pull-up connected to 5V. PCF8575 P00..P02 additionally provide
weak released/high inputs; optional external 10k-to-3V3 pull-ups on
those three row lines may improve noise immunity if needed.

### Local firmware build and Detection mode

Keep the original GPIO wiring:
```bat
set PCF8575_MATRIX=no
build_uf2.bat
```

**Only after all seven matrix wires are moved to the PCF8575:**
```bat
set PCF8575_MATRIX=yes
build_uf2.bat
```

For this upgraded build, QMK reads all 10 keys through the PCF8575
custom matrix scanner, preserving the seven VIA layers and fixed
Shift/Ctrl/Alt keys. No I2C module may share the 3.3V SDA/SCL lines while
powered at 5V. If PCF8575 is disconnected, all key signals are released
and no matrix keys will register.

Enter the Detection/MATRIX screen with **K0 three times**. Top status displays
`PCF OK` or `PCF ERROR`; the bottom area shows ADXL345 status plus
signed live X/Y/Z acceleration readings when connected and functioning.
The ADXL345 only polls while Detection is visible; no motion gestures or
host macros are enabled yet.

**Not hardware-validated or compiled in this session.** Test the new build
locally and confirm all matrix keys plus the sensor readings before merging.
No GitHub Actions, no automatic flashing.
