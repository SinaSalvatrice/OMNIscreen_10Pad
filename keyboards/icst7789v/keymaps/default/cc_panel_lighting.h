#pragma once
#include "hal.h"

#define CC_LIGHT_LEVELS 10u

static bool cc_display_light_on = true;
static uint8_t cc_display_level = CC_LIGHT_LEVELS;
static uint8_t cc_led_level = CC_LIGHT_LEVELS;

static const PWMConfig cc_display_pwm = {
    .frequency = 1000000u,
    .period = 1000u,
    .channels = {{.mode = PWM_OUTPUT_DISABLED}, {.mode = PWM_OUTPUT_ACTIVE_HIGH}},
};

static void cc_display_backlight_apply(bool awake) {
    const uint8_t level = cc_display_light_on && awake ? cc_display_level : 0;
    // Quadratic steps give finer control at low brightness.
    pwmEnableChannel(&PWMD3, 1, 10u * level * level);
}

static void cc_display_backlight_init(void) {
    pwmStart(&PWMD3, &cc_display_pwm);
    cc_display_backlight_apply(true);
    palSetPadMode(PAL_PORT(LCD_BL), PAL_PAD(LCD_BL), PAL_MODE_ALTERNATE(4));
}

// Scale at the last output stage so QMK, preview and stored effects share one dimmer.
static rgb_t cc_led_pixels[RGBLIGHT_LED_COUNT];

void __real_ws2812_set_color(int index, uint8_t red, uint8_t green, uint8_t blue);
void __real_ws2812_flush(void);

void __wrap_ws2812_set_color(int index, uint8_t red, uint8_t green, uint8_t blue) {
    if (index >= 0 && index < RGBLIGHT_LED_COUNT)
        cc_led_pixels[index] = (rgb_t){red, green, blue};
}

void __wrap_ws2812_set_color_all(uint8_t red, uint8_t green, uint8_t blue) {
    for (uint8_t i = 0; i < RGBLIGHT_LED_COUNT; ++i)
        cc_led_pixels[i] = (rgb_t){red, green, blue};
}

void __wrap_ws2812_flush(void) {
    const uint8_t level = cc_rgb_master_enabled ? cc_led_level : 0;
    for (uint8_t i = 0; i < RGBLIGHT_LED_COUNT; ++i) {
        const rgb_t c = cc_led_pixels[i];
        __real_ws2812_set_color(i, (c.r * level + 5u) / CC_LIGHT_LEVELS,
                               (c.g * level + 5u) / CC_LIGHT_LEVELS,
                               (c.b * level + 5u) / CC_LIGHT_LEVELS);
    }
    __real_ws2812_flush();
}

static uint8_t cc_adjust_level(uint8_t level, bool clockwise) {
    if (clockwise && level < CC_LIGHT_LEVELS) return level + 1u;
    if (!clockwise && level > 1u) return level - 1u;
    return level;
}
