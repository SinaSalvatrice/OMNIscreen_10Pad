// ICST7789V - QMK independent GPIO diagnostic for ST7789 (240x320 native).
// Deliberately bypasses Quantum Painter and hardware SPI. No rewiring required.
// SPI mode 0, write-only on GP2 SCK / GP3 MOSI, 3.3V signals.
#include QMK_KEYBOARD_H
#include "gpio.h"
#include "timer.h"
#include "spi_master.h"
#include "analog.h"
#include "generated_layers.h"
#include "dynamic_keymap.h"
#include "eeconfig.h"
#include "via.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef RGBLIGHT_ENABLE
#    include "rgblight.h"
#endif

// Seven real QMK layers. VIA writes each layer's keycodes independently to EEPROM.
// K5/K9/K10 are physical fixed modifiers (handled in process_record_user).
const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    [0] = LAYOUT(KC_Z, KC_Y, KC_G, KC_R, KC_LSFT, KC_Q, KC_S, KC_NO, KC_LCTL, KC_LALT),
    [1] = LAYOUT(KC_NO, KC_NO, KC_UP, KC_NO, KC_LSFT, KC_LEFT, KC_DOWN, KC_RGHT, KC_LCTL, KC_LALT),
    [2] = LAYOUT(KC_HOME, KC_PGUP, KC_UP, KC_END, KC_LSFT, KC_LEFT, KC_DOWN, KC_RGHT, KC_LCTL, KC_LALT),
    [3] = LAYOUT(LCTL(KC_Z), LCTL(KC_Y), LCTL(KC_B), LCTL(KC_I), KC_LSFT, LCTL(KC_C), LCTL(KC_V), LCTL(KC_X), KC_LCTL, KC_LALT),
    [4] = LAYOUT(LCTL(KC_C), LCTL(KC_V), LCTL(KC_X), LCTL(KC_A), KC_LSFT, LGUI(LSFT(KC_S)), LCTL(KC_S), LGUI(KC_V), KC_LCTL, KC_LALT),
    [5] = LAYOUT(KC_NO, KC_NO, KC_NO, KC_NO, KC_LSFT, KC_NO, KC_NO, KC_NO, KC_LCTL, KC_LALT),
    [6] = LAYOUT(UG_TOGG, UG_NEXT, UG_HUEU, UG_HUED, KC_LSFT, UG_VALU, UG_VALD, UG_SATU, KC_LCTL, KC_LALT),
};

// VIA-compatible independently editable rotation per layer.
const uint16_t PROGMEM encoder_map[][NUM_ENCODERS][NUM_DIRECTIONS] = {
    [0] = { ENCODER_CCW_CW(MS_WHLU, MS_WHLD) },
    [1] = { ENCODER_CCW_CW(KC_VOLD, KC_VOLU) },
    [2] = { ENCODER_CCW_CW(KC_PGUP, KC_PGDN) },
    [3] = { ENCODER_CCW_CW(KC_LEFT, KC_RGHT) },
    [4] = { ENCODER_CCW_CW(LCTL(KC_Z), LCTL(KC_Y)) },
    [5] = { ENCODER_CCW_CW(KC_NO, KC_NO) },
    [6] = { ENCODER_CCW_CW(UG_VALD, UG_VALU) },
};

#define LCD_SCK   GP2
#define LCD_MOSI  GP3
#define LCD_RST   GP4
#define LCD_DC    GP5
#define LCD_CS    GP6
#define LCD_BL    GP7
#define ENCODER_SW GP10
#define K0_SW      GP11

#define LCD_W 320
#define LCD_H 240

// RGB565 color values.
#define C_BLACK   0x0000u
#define C_WHITE   0xFFFFu
#define C_RED     0xF800u
#define C_GREEN   0x07E0u
#define C_BLUE    0x001Fu
#define C_YELLOW  0xFFE0u
#define C_CYAN    0x07FFu
#define C_MAGENTA 0xF81Fu

static bool panel_ready = false;

// Always bootstrap ST7789 over proven GPIO bit-banging after any MCU reset.
// Only switch GP2/GP3 into hardware SPI after panel reset, initialization,
// and a visible software-SPI diagnostic square are complete.
#if ICST_USE_HW_SPI
static bool lcd_hw_active = false;
#endif

static void lcd_gpio_bus_init(void) {
    gpio_set_pin_output(LCD_SCK);
    gpio_set_pin_output(LCD_MOSI);
    gpio_write_pin_low(LCD_SCK);
    gpio_write_pin_low(LCD_MOSI);
}

static bool lcd_bus_begin(void) {
#if ICST_USE_HW_SPI
    if (lcd_hw_active) {
        if (spi_start(LCD_CS, false, 0, ICST_SPI_DIVISOR)) {
            return true;
        }
        // If QMK refuses to start a transfer, return to software GPIO.
        lcd_hw_active = false;
        lcd_gpio_bus_init();
    }
#endif
    gpio_write_pin_low(LCD_CS);
    return true;
}

static void lcd_bus_end(void) {
#if ICST_USE_HW_SPI
    if (lcd_hw_active) {
        spi_stop();
        return;
    }
#endif
    gpio_write_pin_high(LCD_CS);
}

static void lcd_write_byte(uint8_t value) {
#if ICST_USE_HW_SPI
    if (lcd_hw_active) {
        (void)spi_write(value);
        return;
    }
#endif
    for (uint8_t bit = 0; bit < 8; ++bit) {
        gpio_write_pin_low(LCD_SCK);
        gpio_write_pin(LCD_MOSI, (value & 0x80u) != 0);
        gpio_write_pin_high(LCD_SCK);
        value <<= 1;
    }
    gpio_write_pin_low(LCD_SCK);
}

static void lcd_write_bulk(const uint8_t *data, uint16_t size) {
#if ICST_USE_HW_SPI
    if (lcd_hw_active) {
        (void)spi_transmit(data, size);
        return;
    }
#endif
    for (uint16_t i = 0; i < size; ++i) {
        lcd_write_byte(data[i]);
    }
}
static void lcd_command(uint8_t cmd) {
    if (!lcd_bus_begin()) return;
    gpio_write_pin_low(LCD_DC);
    lcd_write_byte(cmd);
    lcd_bus_end();
}
static void lcd_command_data(uint8_t cmd, const uint8_t *data, uint8_t length) {
    if (!lcd_bus_begin()) return;
    gpio_write_pin_low(LCD_DC);
    lcd_write_byte(cmd);
    if (length) {
        gpio_write_pin_high(LCD_DC);
        lcd_write_bulk(data, length);
    }
    lcd_bus_end();
}

static void lcd_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
    const uint8_t cols[] = {x0 >> 8, x0 & 0xFFu, x1 >> 8, x1 & 0xFFu};
    const uint8_t rows[] = {y0 >> 8, y0 & 0xFFu, y1 >> 8, y1 & 0xFFu};
    lcd_command_data(0x2Au, cols, 4);
    lcd_command_data(0x2Bu, rows, 4);
}

static void lcd_fill(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t rgb565) {
    if (!panel_ready || !w || !h || x >= LCD_W || y >= LCD_H) {
        return;
    }
    if (w > LCD_W - x) w = LCD_W - x;
    if (h > LCD_H - y) h = LCD_H - y;

    lcd_window(x, y, x + w - 1, y + h - 1);
    if (!lcd_bus_begin()) return;
    gpio_write_pin_low(LCD_DC);
    lcd_write_byte(0x2Cu); // RAMWR
    gpio_write_pin_high(LCD_DC);

    uint8_t row_pixels[128]; // 64 RGB565 pixels, no large framebuffer needed.
    for (uint8_t i = 0; i < sizeof(row_pixels); i += 2) {
        row_pixels[i] = (uint8_t)(rgb565 >> 8);
        row_pixels[i + 1] = (uint8_t)rgb565;
    }
    uint32_t remaining = (uint32_t)w * (uint32_t)h;
    while (remaining > 0) {
        uint16_t count = remaining >= 64 ? 64 : (uint16_t)remaining;
        lcd_write_bulk(row_pixels, count * 2);
        remaining -= count;
    }
    lcd_bus_end();
}

// Hardware reset and standard ST7789 16-bit initialization.
// MADCTL=0x60 corresponds to landscape orientation (320x240).
static void lcd_init(void) {
    gpio_set_pin_output(LCD_BL);
    gpio_write_pin_low(LCD_BL); // QMK heartbeat: visible 1-second backlight OFF phase.
    wait_ms(1000);
    gpio_set_pin_output(LCD_CS);
    gpio_set_pin_output(LCD_DC);
    gpio_set_pin_output(LCD_RST);
    gpio_write_pin_high(LCD_CS);
    gpio_write_pin_high(LCD_DC);
    lcd_gpio_bus_init(); // GPIO transport first, on cold AND warm MCU boot.

    gpio_write_pin_high(LCD_RST);
    wait_ms(20);
    gpio_write_pin_low(LCD_RST);
    wait_ms(40);
    gpio_write_pin_high(LCD_RST);
    wait_ms(160);

    lcd_command(0x01u); // SWRESET
    wait_ms(160);
    lcd_command(0x11u); // SLPOUT
    wait_ms(160);
    const uint8_t pixel_format = 0x55u; // RGB565
    lcd_command_data(0x3Au, &pixel_format, 1);
    const uint8_t orientation = 0x60u; // MY=0 MX=1 MV=1, RGB
    lcd_command_data(0x36u, &orientation, 1);
    lcd_command(0x20u); // INVOFF: panel showed complementary RGB colors with INVON
    lcd_command(0x13u); // NORON
    wait_ms(15);
    lcd_command(0x29u); // DISPON
    wait_ms(100);
    panel_ready = true;
    gpio_write_pin_high(LCD_BL);

#if ICST_USE_HW_SPI
    // This 28x28 red probe is painted BEFORE hardware SPI takes control.
    // If it appears but the four quadrants do not, the QMK SPI transfer
    // path failed even though the panel was initialized correctly.
    lcd_fill(0, 0, 28, 28, C_RED);

    // Hand over the already-initialized ST7789 to the RP2040's SPI0.
    // Keep the panel reset pin untouched during this transition.
    gpio_write_pin_high(LCD_CS);
    spi_init();
    lcd_hw_active = true;
#endif
}

// Layer UI implementation follows hardware SPI bootstrap (known good).
#include "cc_runtime.h"
