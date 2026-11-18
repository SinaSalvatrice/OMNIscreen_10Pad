// OMNIscreen 10Pad: 14 main LEDs + 43 independently controlled Frame LEDs.
// Single WS2812/SK6812 data line on GP29, indexed 0..56.
// Main: QMK RGBLight effects or legacy custom one/two-color palette (VIA channel 0 ids 1-4).
// Frame: own enabled/effect/brightness/colors/speed/direction (VIA channel 0 ids 5-11).
#pragma once
#include "eeconfig.h"
#include "via.h"
#include "rgblight.h"
#include "rgblight_drivers.h"
#include "color.h"

#define CC_FRAME_EFFECT_SOLID       0
#define CC_FRAME_EFFECT_ALTERNATE   1
#define CC_FRAME_EFFECT_SPLIT       2
#define CC_FRAME_EFFECT_CHASE       3
#define CC_FRAME_EFFECT_RAINBOW     4
#define CC_FRAME_EFFECT_BREATHE     5
#define CC_FRAME_EFFECT_MAX         CC_FRAME_EFFECT_BREATHE

// Keep the first eight bytes compatible with the original v1 palette data.
typedef struct __attribute__((packed)) {
    uint8_t signature;          // 0xCC
    uint8_t mode;               // main: 0 QMK / 1 solid / 2 alternating / 3 split / 4 chase
    uint8_t hue1;               // main color 1
    uint8_t sat1;
    uint8_t hue2;               // main color 2
    uint8_t sat2;
    uint8_t speed;              // main chase
    uint8_t version;            // 2
    uint8_t frame_enabled;      // independent of QMK/main enabled state
    uint8_t frame_effect;       // 0..5
    uint8_t frame_brightness;   // 0..RGBLIGHT_LIMIT_VAL
    uint8_t frame_hue1;
    uint8_t frame_sat1;
    uint8_t frame_hue2;
    uint8_t frame_sat2;
    uint8_t frame_speed;
    uint8_t frame_reverse;
} cc_rgb_settings_t;

_Static_assert(sizeof(cc_rgb_settings_t) == EECONFIG_USER_DATA_SIZE, "RGB settings / EEPROM size mismatch");
_Static_assert(CC_RGB_MAIN_LED_COUNT + CC_RGB_FRAME_LED_COUNT == RGBLIGHT_LED_COUNT, "LED zones must total 57");

static const cc_rgb_settings_t cc_rgb_defaults = {
    0xCC, 0, 14, 255, 150, 255, 128, 2,
    1, CC_FRAME_EFFECT_SOLID, 24, 14, 255, 150, 255, 128, 0
};
static cc_rgb_settings_t cc_rgb = {
    0xCC, 0, 14, 255, 150, 255, 128, 2,
    1, CC_FRAME_EFFECT_SOLID, 24, 14, 255, 150, 255, 128, 0
};
static bool cc_main_dirty = true;
static bool cc_frame_dirty = true;
static uint8_t cc_main_phase = 0;
static uint8_t cc_frame_phase = 0;
static uint16_t cc_main_frame_time = 0;
static uint16_t cc_frame_frame_time = 0;
static uint8_t cc_last_main_brightness = 0xFF;
static bool cc_last_main_enabled = false;

void eeconfig_init_user_datablock(void) {
    eeconfig_update_user_datablock(&cc_rgb_defaults, 0, sizeof(cc_rgb_defaults));
}

static void cc_rgb_load(void) {
    cc_rgb_settings_t stored;
    eeconfig_read_user_datablock(&stored, 0, sizeof(stored));

    // v1 migration: preserve the original 14-LED colors/mode/speed and
    // initialize only the new Frame zone. Persist next time VIA saves.
    if (stored.signature == 0xCC && stored.version == 1 && stored.mode <= 4) {
        cc_rgb = cc_rgb_defaults;
        cc_rgb.mode = stored.mode;
        cc_rgb.hue1 = stored.hue1;
        cc_rgb.sat1 = stored.sat1;
        cc_rgb.hue2 = stored.hue2;
        cc_rgb.sat2 = stored.sat2;
        cc_rgb.speed = stored.speed;
    } else if (stored.signature == 0xCC && stored.version == 2 &&
               stored.mode <= 4 && stored.frame_effect <= CC_FRAME_EFFECT_MAX &&
               stored.frame_enabled <= 1 && stored.frame_reverse <= 1) {
        cc_rgb = stored;
    } else {
        cc_rgb = cc_rgb_defaults;
    }
    if (cc_rgb.frame_brightness > RGBLIGHT_LIMIT_VAL) {
        cc_rgb.frame_brightness = RGBLIGHT_LIMIT_VAL;
    }
    // Built-in QMK RGB effects must never write to LED 14..56.
    rgblight_set_effect_range(0, CC_RGB_MAIN_LED_COUNT);
    cc_main_dirty = true;
    cc_frame_dirty = true;
}

static rgb_t cc_rgb_color(uint8_t hue, uint8_t sat, uint8_t brightness) {
    if (brightness > RGBLIGHT_LIMIT_VAL) brightness = RGBLIGHT_LIMIT_VAL;
    return hsv_to_rgb((hsv_t){hue, sat, brightness});
}

// Access the QMK RGBLight driver's buffered LED API, then flush once per zone.
// The public rgblight_sethsv_at() function flushes the entire chain on EVERY
// LED update; on a 57-LED chain that would stall the keyboard badly.
static void cc_rgb_set_led(uint8_t index, uint8_t hue, uint8_t sat, uint8_t brightness) {
    const rgb_t c = cc_rgb_color(hue, sat, brightness);
    rgblight_driver.set_color(index, c.r, c.g, c.b);
}

static void cc_rgb_main_paint(void) {
    if (cc_rgb.mode == 0 || !rgblight_is_enabled()) return;
    if (rgblight_get_mode() != RGBLIGHT_MODE_STATIC_LIGHT) {
        rgblight_mode_noeeprom(RGBLIGHT_MODE_STATIC_LIGHT);
    }

    const uint8_t brightness = rgblight_get_val();
    for (uint8_t i = 0; i < CC_RGB_MAIN_LED_COUNT; ++i) {
        bool second = false;
        if (cc_rgb.mode == 2) second = (i & 1u) != 0;
        if (cc_rgb.mode == 3) second = i >= CC_RGB_MAIN_LED_COUNT / 2;
        if (cc_rgb.mode == 4) {
            second = ((i + cc_main_phase) % CC_RGB_MAIN_LED_COUNT) >= (CC_RGB_MAIN_LED_COUNT / 2);
        }
        cc_rgb_set_led(i, second ? cc_rgb.hue2 : cc_rgb.hue1,
                          second ? cc_rgb.sat2 : cc_rgb.sat1, brightness);
    }
    rgblight_set();
    cc_last_main_brightness = brightness;
    cc_main_dirty = false;
}

static uint8_t cc_frame_wave_brightness(void) {
    const uint8_t wave = cc_frame_phase < 128 ? cc_frame_phase * 2u
                                               : (255u - cc_frame_phase) * 2u;
    return (uint8_t)(((uint16_t)cc_rgb.frame_brightness * wave) / 255u);
}

static void cc_rgb_frame_paint(void) {
    const bool off = !cc_rgb.frame_enabled || cc_rgb.frame_brightness == 0;
    for (uint8_t i = 0; i < CC_RGB_FRAME_LED_COUNT; ++i) {
        const uint8_t led = CC_RGB_FRAME_LED_START + i;
        if (off) {
            rgblight_driver.set_color(led, 0, 0, 0);
            continue;
        }

        uint8_t hue = cc_rgb.frame_hue1;
        uint8_t sat = cc_rgb.frame_sat1;
        uint8_t brightness = cc_rgb.frame_brightness;
        bool second = false;

        switch (cc_rgb.frame_effect) {
            case CC_FRAME_EFFECT_ALTERNATE:
                second = (i & 1u) != 0;
                break;
            case CC_FRAME_EFFECT_SPLIT:
                second = i >= CC_RGB_FRAME_LED_COUNT / 2; // 21 + 22
                break;
            case CC_FRAME_EFFECT_CHASE: {
                const uint8_t phase = cc_frame_phase % CC_RGB_FRAME_LED_COUNT;
                const uint8_t pos = cc_rgb.frame_reverse
                    ? (i + CC_RGB_FRAME_LED_COUNT - phase) % CC_RGB_FRAME_LED_COUNT
                    : (i + phase) % CC_RGB_FRAME_LED_COUNT;
                second = pos >= 8; // Eight-LED moving window of color 1.
                break;
            }
            case CC_FRAME_EFFECT_RAINBOW: {
                const uint8_t pos = cc_rgb.frame_reverse
                    ? (CC_RGB_FRAME_LED_COUNT - 1 - i) : i;
                hue = (uint8_t)(hue + ((uint16_t)pos * 256u) / CC_RGB_FRAME_LED_COUNT
                                + cc_frame_phase);
                break;
            }
            case CC_FRAME_EFFECT_BREATHE:
                brightness = cc_frame_wave_brightness();
                break;
            default: // Solid
                break;
        }

        if (second) {
            hue = cc_rgb.frame_hue2;
            sat = cc_rgb.frame_sat2;
        }
        cc_rgb_set_led(led, hue, sat, brightness);
    }

    // rgblight_set() flushes the entire single chain. In QMK's disabled state
    // only the *main effect range* is blanked, so Frame remains independent.
    rgblight_set();
    cc_frame_dirty = false;
}

static uint16_t cc_frame_interval(uint8_t speed) {
    return (uint16_t)(25u + ((uint16_t)(255u - speed) * 4u) / 5u);
}

static void cc_rgb_tick(void) {
    const uint16_t now = timer_read();
    const bool main_enabled = rgblight_is_enabled();
    const uint8_t main_brightness = rgblight_get_val();
    if (cc_last_main_enabled != main_enabled) {
        cc_last_main_enabled = main_enabled;
        cc_main_dirty = true;
    }
    if (cc_rgb.mode == 4 && main_enabled &&
        timer_elapsed(cc_main_frame_time) >= cc_frame_interval(cc_rgb.speed)) {
        cc_main_frame_time = now;
        ++cc_main_phase;
        cc_main_dirty = true;
    }
    if (cc_rgb.mode && main_enabled &&
        (cc_main_dirty || cc_last_main_brightness != main_brightness ||
         rgblight_get_mode() != RGBLIGHT_MODE_STATIC_LIGHT)) {
        cc_rgb_main_paint();
    }

    const bool animated = cc_rgb.frame_enabled &&
        (cc_rgb.frame_effect == CC_FRAME_EFFECT_CHASE ||
         cc_rgb.frame_effect == CC_FRAME_EFFECT_RAINBOW ||
         cc_rgb.frame_effect == CC_FRAME_EFFECT_BREATHE);

    if (animated && timer_elapsed(cc_frame_frame_time) >= cc_frame_interval(cc_rgb.frame_speed)) {
        cc_frame_frame_time = now;
        cc_frame_phase += (cc_rgb.frame_effect == CC_FRAME_EFFECT_BREATHE ? 2u : 1u);
        cc_frame_dirty = true;
    }
    if (cc_frame_dirty) cc_rgb_frame_paint();
}

// VIA channel 0 preserves the previous four custom main-palette IDs (1..4).
// New Frame values use 5..11, so existing saved VIA definitions remain valid.
void via_custom_value_command_kb(uint8_t *data, uint8_t length) {
    if (length < 2 || data[1] != id_custom_channel) {
        data[0] = id_unhandled;
        return;
    }
    if (data[0] == id_custom_save) {
        cc_rgb.version = 2;
        eeconfig_update_user_datablock(&cc_rgb, 0, sizeof(cc_rgb));
        return;
    }
    if (length < 4) {
        data[0] = id_unhandled;
        return;
    }

    const uint8_t id = data[2];
    if (data[0] == id_custom_set_value) {
        switch (id) {
            case 1:
                if (data[3] > 4) break;
                cc_rgb.mode = data[3];
                cc_main_dirty = true;
                if (cc_rgb.mode == 0) rgblight_reload_from_eeprom();
                return;
            case 2:
                if (length < 5) break;
                cc_rgb.hue1 = data[3];
                cc_rgb.sat1 = data[4];
                cc_main_dirty = true;
                return;
            case 3:
                if (length < 5) break;
                cc_rgb.hue2 = data[3];
                cc_rgb.sat2 = data[4];
                cc_main_dirty = true;
                return;
            case 4:
                cc_rgb.speed = data[3];
                cc_main_dirty = true;
                return;
            case 5:
                if (data[3] > 1) break;
                cc_rgb.frame_enabled = data[3];
                cc_frame_dirty = true;
                return;
            case 6:
                if (data[3] > CC_FRAME_EFFECT_MAX) break;
                cc_rgb.frame_effect = data[3];
                cc_frame_dirty = true;
                return;
            case 7:
                cc_rgb.frame_brightness = data[3] > RGBLIGHT_LIMIT_VAL
                    ? RGBLIGHT_LIMIT_VAL : data[3];
                cc_frame_dirty = true;
                return;
            case 8:
                if (length < 5) break;
                cc_rgb.frame_hue1 = data[3];
                cc_rgb.frame_sat1 = data[4];
                cc_frame_dirty = true;
                return;
            case 9:
                if (length < 5) break;
                cc_rgb.frame_hue2 = data[3];
                cc_rgb.frame_sat2 = data[4];
                cc_frame_dirty = true;
                return;
            case 10:
                cc_rgb.frame_speed = data[3];
                cc_frame_dirty = true;
                return;
            case 11:
                if (data[3] > 1) break;
                cc_rgb.frame_reverse = data[3];
                cc_frame_dirty = true;
                return;
            default:
                break;
        }
    } else if (data[0] == id_custom_get_value) {
        switch (id) {
            case 1: data[3] = cc_rgb.mode; return;
            case 2:
                if (length < 5) break;
                data[3] = cc_rgb.hue1; data[4] = cc_rgb.sat1; return;
            case 3:
                if (length < 5) break;
                data[3] = cc_rgb.hue2; data[4] = cc_rgb.sat2; return;
            case 4: data[3] = cc_rgb.speed; return;
            case 5: data[3] = cc_rgb.frame_enabled; return;
            case 6: data[3] = cc_rgb.frame_effect; return;
            case 7: data[3] = cc_rgb.frame_brightness; return;
            case 8:
                if (length < 5) break;
                data[3] = cc_rgb.frame_hue1; data[4] = cc_rgb.frame_sat1; return;
            case 9:
                if (length < 5) break;
                data[3] = cc_rgb.frame_hue2; data[4] = cc_rgb.frame_sat2; return;
            case 10: data[3] = cc_rgb.frame_speed; return;
            case 11: data[3] = cc_rgb.frame_reverse; return;
            default:
                break;
        }
    }
    data[0] = id_unhandled;
}
