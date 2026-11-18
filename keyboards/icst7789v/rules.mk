# Waveshare RP2040-Zero ST7789 GPIO diagnostic.
BOARD = GENERIC_RP_RP2040

# Keep the working QMK display logic but use the SPI master directly.
# Quantum Painter stays disabled until native hardware SPI is confirmed.
QUANTUM_PAINTER_ENABLE = no
SPI_DRIVER_REQUIRED = yes
I2C_DRIVER_REQUIRED = yes

# Normal firmware keeps the existing GPIO matrix and the ADXL345 disabled.
# After wiring all 7 matrix lines to an MCP23017, compile with:
#   MCP23017_MATRIX=yes (build_uf2.bat or QMK make command).
ifeq ($(MCP23017_MATRIX),yes)
CUSTOM_MATRIX = lite
SRC += matrix.c
OPT_DEFS += -DCC_MCP23017_MATRIX=1
else
OPT_DEFS += -DCC_MCP23017_MATRIX=0
endif
ANALOG_DRIVER_REQUIRED = yes
# K9 double tap handled immediately in process_record_user (no delayed modifier).

# Matrix and EC11 QMK modules remain enabled in keyboard.json.
# Optional external WS2812/SK6812 on GP29:
RGBLIGHT_ENABLE = yes
WS2812_DRIVER = vendor
