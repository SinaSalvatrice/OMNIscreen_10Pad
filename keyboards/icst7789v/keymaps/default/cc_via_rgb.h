// VIA channel 0: persistent one/two-color WS2812 palette on GP29.
// QMK's built-in channel 2 provides ordinary rainbow/breathing/etc. modes.
#pragma once
#include "eeconfig.h"
#include "via.h"
#include "rgblight.h"

typedef struct {
    uint8_t signature;
    uint8_t mode;       // 0 QMK effect, 1 solid, 2 alternating, 3 split, 4 chase
    uint8_t hue1;
    uint8_t sat1;
    uint8_t hue2;
    uint8_t sat2;
    uint8_t speed;
    uint8_t version;
} cc_palette_t;
static cc_palette_t cc_palette = {0xCC, 0, 14, 255, 150, 255, 128, 1};
static bool cc_rgb_dirty = true;
static uint8_t cc_rgb_last_brightness = 0xFF;
static uint8_t cc_rgb_phase = 0;
static uint16_t cc_rgb_last_frame = 0;

void eeconfig_init_user_datablock(void) {
    const cc_palette_t defaults = {0xCC, 0, 14, 255, 150, 255, 128, 1};
    eeconfig_update_user_datablock(&defaults, 0, sizeof(defaults));
}

static void cc_rgb_load(void) {
    cc_palette_t config;
    eeconfig_read_user_datablock(&config, 0, sizeof(config));
    if (config.signature == 0xCC && config.version == 1 && config.mode <= 4) {
        cc_palette = config;
    }
    cc_rgb_dirty = true;
}

static void cc_rgb_paint(void) {
    if (cc_palette.mode == 0 || !rgblight_is_enabled()) return;
    rgblight_mode_noeeprom(RGBLIGHT_MODE_STATIC_LIGHT);
    const uint8_t brightness = rgblight_get_val();
    for (uint8_t i = 0; i < RGBLIGHT_LED_COUNT; ++i) {
        bool second = false;
        if (cc_palette.mode == 2) second = (i & 1u) != 0;
        if (cc_palette.mode == 3) second = i >= (RGBLIGHT_LED_COUNT / 2);
        if (cc_palette.mode == 4) second = ((i + cc_rgb_phase) % RGBLIGHT_LED_COUNT) < (RGBLIGHT_LED_COUNT / 2);
        rgblight_sethsv_at(second ? cc_palette.hue2 : cc_palette.hue1,
                           second ? cc_palette.sat2 : cc_palette.sat1,
                           brightness, i);
    }
    cc_rgb_last_brightness = brightness;
    cc_rgb_dirty = false;
}

static void cc_rgb_tick(void) {
    if (cc_palette.mode == 0) return; // leave QMK/VIA effects entirely alone
    uint8_t brightness = rgblight_get_val();
    if (cc_palette.mode == 4) {
        const uint16_t interval = (uint16_t)(300u - cc_palette.speed);
        if (timer_elapsed(cc_rgb_last_frame) >= interval) {
            cc_rgb_last_frame = timer_read();
            ++cc_rgb_phase;
            cc_rgb_dirty = true;
        }
    }
    if (cc_rgb_dirty || cc_rgb_last_brightness != brightness ||
        rgblight_get_mode() != RGBLIGHT_MODE_STATIC_LIGHT) {
        cc_rgb_paint();
    }
}

void via_custom_value_command_kb(uint8_t *data, uint8_t length) {
    if (length < 2 || data[1] != 0) {
        data[0] = id_unhandled;
        return;
    }
    if (data[0] == id_custom_save) {
        eeconfig_update_user_datablock(&cc_palette, 0, sizeof(cc_palette));
        return;
    }
    if (length < 4) { data[0] = id_unhandled; return; }
    const uint8_t id = data[2];
    if (data[0] == id_custom_set_value) {
        if (id == 1 && data[3] <= 4) cc_palette.mode = data[3];
        else if (id == 2 && length >= 5) { cc_palette.hue1 = data[3]; cc_palette.sat1 = data[4]; }
        else if (id == 3 && length >= 5) { cc_palette.hue2 = data[3]; cc_palette.sat2 = data[4]; }
        else if (id == 4) cc_palette.speed = data[3];
        else { data[0] = id_unhandled; return; }
        cc_rgb_dirty = true;
        if (cc_palette.mode == 0) rgblight_reload_from_eeprom();
        return;
    }
    if (data[0] == id_custom_get_value) {
        if (id == 1) data[3] = cc_palette.mode;
        else if (id == 2 && length >= 5) { data[3] = cc_palette.hue1; data[4] = cc_palette.sat1; }
        else if (id == 3 && length >= 5) { data[3] = cc_palette.hue2; data[4] = cc_palette.sat2; }
        else if (id == 4) data[3] = cc_palette.speed;
        else data[0] = id_unhandled;
        return;
    }
    data[0] = id_unhandled;
}
