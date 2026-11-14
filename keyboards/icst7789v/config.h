#pragma once

// RP2040-Zero, ST7789 240x320 native / 320x240 landscape.
// ST7789 pin labels SCL/SDA are SPI clock/data, NOT I2C.
// GP0/GP1 are not a valid RP2040 hardware SPI clock/TX pair.
// Run the display over GPIO bit-banged SPI so these two pins can be used.
#define ICST_LCD_SCK_PIN GP0   // TFT SCL / CLK
#define ICST_LCD_MOSI_PIN GP1  // TFT SDA / DIN
#define ICST_USE_HW_SPI 0

// Optional hardware SPI fallback for a later GP2/GP3 wiring revision.
// Unused by the GP0/GP1 software-SPI build.
#define SPI_DRIVER SPID0
#define SPI_SCK_PIN GP2
#define SPI_MOSI_PIN GP3
#define SPI_MISO_PIN NO_PIN
#define ICST_SPI_DIVISOR 32

// Tap Dance window: double taps must land within 200ms.
#define TAPPING_TERM 200

#define TFT_CS_PIN GP6
#define TFT_DC_PIN GP5
#define TFT_RST_PIN GP4
#define TFT_BL_PIN GP7

#define TFT_WIDTH 240
#define TFT_HEIGHT 320

// Both button contacts switch to GND.
#define ENCODER_PUSH_PIN GP10
#define TFT_K0_PIN GP11

// Keep the QP display awake while diagnosing the hardware.
#define QUANTUM_PAINTER_DISPLAY_TIMEOUT 0

// External ten-pixel WS2812/SK6812 string (first pixel DIN on GP29).
// For bring-up, keep power demand modest; RGBLight clips values at 64/255.
#define WS2812_DI_PIN GP29
#define RGBLIGHT_LED_COUNT 10
#define RGBLIGHT_LIMIT_VAL 64
// Every LED displays a different hue and the rainbow moves automatically.
#define RGBLIGHT_EFFECT_RAINBOW_SWIRL
