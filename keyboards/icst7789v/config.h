#pragma once

// RP2040-Zero, ST7789 240x320 native / 320x240 landscape.
// These pins match the working Arduino Layer Map wiring.
// SPI0: GP2 SCK, GP3 MOSI. This is a write-only panel.
#define SPI_DRIVER SPID0
#define SPI_SCK_PIN GP2
#define SPI_MOSI_PIN GP3
#define SPI_MISO_PIN NO_PIN

// 1 = hardware SPI0, 0 = proven software-GPIO implementation.
#define ICST_USE_HW_SPI 1
// Conservative initial SPI clock divider (125 MHz / 32 ~ 3.9 MHz).
#define ICST_SPI_DIVISOR 32

// K9 (Ctrl) detects two clean taps within this window without delaying Ctrl.
#define CC_K9_DOUBLE_TAP_MS 240
#define EECONFIG_USER_DATA_SIZE 8
#define VIA_FIRMWARE_VERSION 3

#define TFT_CS_PIN GP6
#define TFT_DC_PIN GP5
#define TFT_RST_PIN GP4
#define TFT_BL_PIN GP7

#define SLIDER_ADC_PIN GP28  // ADC2; slide potentiometer signal

#define TFT_WIDTH 240
#define TFT_HEIGHT 320

// Both button contacts switch to GND.
#define ENCODER_PUSH_PIN GP10
#define TFT_K0_PIN GP11

// Keep the QP display awake while diagnosing the hardware.
#define QUANTUM_PAINTER_DISPLAY_TIMEOUT 0

// 14 WS2812/SK6812 LEDs in one data chain: original 10 plus 4 under TFT. First DIN on GP29.
// For bring-up, keep power demand modest; RGBLight clips values at 64/255.
#define WS2812_DI_PIN GP29
#define RGBLIGHT_LED_COUNT 14
#define RGBLIGHT_LIMIT_VAL 64
// Every LED displays a different hue and the rainbow moves automatically.
#define RGBLIGHT_EFFECT_RAINBOW_SWIRL

#define RGBLIGHT_EFFECT_BREATHING
#define RGBLIGHT_EFFECT_RAINBOW_MOOD
#define RGBLIGHT_EFFECT_SNAKE
#define RGBLIGHT_EFFECT_KNIGHT
#define RGBLIGHT_EFFECT_CHRISTMAS
#define RGBLIGHT_EFFECT_STATIC_GRADIENT
#define RGBLIGHT_EFFECT_RGB_TEST
#define RGBLIGHT_EFFECT_ALTERNATING
#define RGBLIGHT_EFFECT_TWINKLE
