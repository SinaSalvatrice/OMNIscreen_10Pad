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
// v2 custom lighting data stores the original 14-LED palette plus Frame settings.
#define EECONFIG_USER_DATA_SIZE 17
#define VIA_FIRMWARE_VERSION 3

#define TFT_CS_PIN GP6
#define TFT_DC_PIN GP5
#define TFT_RST_PIN GP4
#define TFT_BL_PIN GP7

#define SLIDER_ADC_PIN GP28  // ADC2; slide potentiometer signal

// ADXL345 diagnostic I2C bus: GP0 (SDA) / GP1 (SCL), 0x53 when SDO=GND.
// IMPORTANT: keyboard.json currently uses GP0 as matrix column 3!
// Leave this off until that column is physically moved to an I2C expander
// and the keyboard matrix implementation has been changed accordingly.
// Enabling both uses of GP0 would break keyboard scanning.
#define CC_ADXL345_ENABLE 0
#define CC_ADXL345_GP0_RELEASED 0
#if CC_ADXL345_ENABLE && !CC_ADXL345_GP0_RELEASED
#    error "ADXL345 cannot use GP0: keyboard matrix still owns GP0. Rework the matrix first."
#endif
#define I2C_DRIVER I2CD0
#define I2C1_SDA_PIN GP0
#define I2C1_SCL_PIN GP1
// RP2040 GPIO function 3 is hardware I2C; QMK's generic names are I2C1_*.
#define I2C1_SDA_PAL_MODE 3
#define I2C1_SCL_PAL_MODE 3

#define TFT_WIDTH 240
#define TFT_HEIGHT 320

// Both button contacts switch to GND.
#define ENCODER_PUSH_PIN GP10
#define TFT_K0_PIN GP11

// Keep the QP display awake while diagnosing the hardware.
#define QUANTUM_PAINTER_DISPLAY_TIMEOUT 0

// 57 addressable RGB LEDs on ONE serial data chain (GP29):
// LED 0..13 = original 14 key/display LEDs; LED 14..56 = 43 Frame LEDs.
// Frame DIN connects after LED 13 DOUT. Only the logical zones are separate.
// Supply high-current LEDs from an adequately rated external 5V rail.
#define WS2812_DI_PIN GP29
#define CC_RGB_MAIN_LED_COUNT 14
#define CC_RGB_FRAME_LED_COUNT 43
#define CC_RGB_FRAME_LED_START CC_RGB_MAIN_LED_COUNT
#define RGBLIGHT_LED_COUNT 57
#define RGBLIGHT_LIMIT_VAL 64
// Built-in QMK effects are restricted in firmware to the first 14 LEDs.
// Frame LEDs have independent power/effect/brightness/colors via VIA channel 0.
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
