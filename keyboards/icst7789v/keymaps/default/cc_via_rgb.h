// OMNIscreen 10Pad: 30 matrix LEDs plus original 43 Frame LEDs, GP29, 0..72.
// Main: QMK RGBLight effects or legacy custom one/two-color palette (VIA channel 0 ids 1-4).
// Frame: own enabled/effect/brightness/colors/speed/direction (VIA channel 0 ids 5-11).
#pragma once
#include "eeconfig.h"
#include "via.h"
#include "rgblight.h"
#include "rgblight_drivers.h"
#include "cc_lighting_effects.h"
#include "cc_live.h"

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
    uint8_t zone_magic[4];
    omp_zone_t matrix_zones[OMP_LAYERS][OMP_MATRIX_ZONE_COUNT]; // Keys, Slider, Encoder, K0, Display
    uint8_t zone_map[CC_RGB_MAIN_LED_COUNT];
} cc_rgb_settings_t;

_Static_assert(sizeof(omp_zone_t) == 10, "Zone storage format");
_Static_assert(CC_NEXT_TINT_OFFSET + CC_NEXT_COLOR_BYTES <=
               sizeof(((cc_rgb_settings_t *)0)->matrix_zones), "Lighting palette storage");
_Static_assert(sizeof(cc_rgb_settings_t) == EECONFIG_USER_DATA_SIZE, "RGB settings / EEPROM size mismatch");
_Static_assert(CC_RGB_MAIN_LED_COUNT + CC_RGB_FRAME_LED_COUNT == RGBLIGHT_LED_COUNT, "Matrix plus Frame must total 73");

static const cc_rgb_settings_t cc_rgb_defaults = {
    0xCC, 0, 14, 255, 150, 255, 128, 2,
    1, CC_FRAME_EFFECT_SOLID, 24, 14, 255, 150, 255, 128, 0
};
static cc_rgb_settings_t cc_rgb = {
    0xCC, 0, 14, 255, 150, 255, 128, 2,
    1, CC_FRAME_EFFECT_SOLID, 24, 14, 255, 150, 255, 128, 0
};
static uint8_t cc_default_matrix_zone(uint8_t index, bool serpentine) {
    const uint8_t row = index / 5u;
    uint8_t col = index % 5u;
    if (serpentine && (row & 1u)) col = 4u - col;
    if ((row == 0 && col <= 3) || (row == 1 && col <= 2)) return OMP_ZONE_DISPLAY;
    if (col == 4 && row <= 1) return OMP_ZONE_ENCODER;
    if ((row == 1 && col == 3) || (row == 2 && col == 4)) return OMP_ZONE_K0;
    if (col == 4 && row >= 3) return OMP_ZONE_SLIDER;
    return OMP_ZONE_KEYS;
}

static void cc_fix_matrix_map(uint8_t *map) {
    bool serpentine = true;
    for (uint8_t i = 0; i < CC_RGB_MAIN_LED_COUNT; ++i)
        serpentine &= map[i] == cc_default_matrix_zone(i, true);
    for (uint8_t i = 0; i < CC_RGB_MAIN_LED_COUNT; ++i)
        map[i] = cc_default_matrix_zone(i, serpentine);
}
static void cc_matrix_zones_reset(void) {
    memcpy(cc_rgb.zone_magic, "MZ01", 4);
    for (uint8_t i = 0; i < CC_RGB_MAIN_LED_COUNT; ++i)
        cc_rgb.zone_map[i] = cc_default_matrix_zone(i, false);
    for (uint8_t layer = 0; layer < OMP_LAYERS; ++layer) {
        for (uint8_t zone = 0; zone < OMP_MATRIX_ZONE_COUNT; ++zone) {
            omp_zone_t *z = &cc_rgb.matrix_zones[layer][zone];
            z->effect = 0; z->brightness = 24; z->speed = 128; z->flags = 1;
            z->color_a = 0xCC2B; z->color_b = 0x74F7;
            z->triggers = 7; z->duration = 50;
        }
    }
}
static uint8_t cc_matrix_version(void) {
    if (!memcmp(cc_rgb.zone_magic, "MZ04", 4)) return 4;
    if (!memcmp(cc_rgb.zone_magic, "MZ03", 4)) return 3;
    if (!memcmp(cc_rgb.zone_magic, "MZ02", 4)) return 2;
    return !memcmp(cc_rgb.zone_magic, "MZ01", 4);
}

static bool cc_matrix_zone_record_valid(const omp_zone_t *zone, uint8_t version) {
    if (version >= 3) {
        return (zone->effect & 15u) < 13u && (zone->effect >> 4) < 9u &&
               zone->brightness <= RGBLIGHT_LIMIT_VAL && ((zone->flags >> 3) & 3u) < 3u &&
               zone->triggers <= 63u && zone->duration;
    }
    return omp_zone_valid(zone) && (version < 2 || zone->effect <= 5u);
}

static bool cc_matrix_zone_data_valid(
    const omp_zone_t zones[OMP_LAYERS][OMP_MATRIX_ZONE_COUNT], uint8_t version) {
    if (!version) return false;
    const uint8_t count = version >= 2 ? 48u : OMP_LAYERS * OMP_MATRIX_ZONE_COUNT;
    for (uint8_t i = 0; i < count; ++i) {
        if (!cc_matrix_zone_record_valid(
                &zones[i / OMP_MATRIX_ZONE_COUNT][i % OMP_MATRIX_ZONE_COUNT], version))
            return false;
    }
    if (version >= 3) {
        const uint8_t *colors = (const uint8_t *)zones + CC_NEXT_TINT_OFFSET;
        const uint8_t *palettes = colors + CC_NEXT_TINT_BYTES;
        const uint8_t palette_count = version >= 4 ? CC_NEXT_PALETTE_BYTES : 8u;
        for (uint8_t i = 0; i < palette_count; ++i)
            if (palettes[i] > 3u) return false;
        if (version >= 4) {
            for (uint8_t i = 0; i < CC_NEXT_LEVEL_BYTES; ++i)
                if (colors[i] > 100u) return false;
        }
    }
    return true;
}

static bool cc_matrix_zones_valid(void) {
    return cc_matrix_zone_data_valid(cc_rgb.matrix_zones, cc_matrix_version());
}
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
    // Original 17 Frame/Main bytes are unchanged on migration.
    if (!cc_matrix_zones_valid()) cc_matrix_zones_reset();
    cc_fix_matrix_map(cc_rgb.zone_map);
    if (cc_rgb.frame_brightness > RGBLIGHT_LIMIT_VAL) {
        cc_rgb.frame_brightness = RGBLIGHT_LIMIT_VAL;
    }
    // Built-in QMK RGB effects must never write to LED 30..72.
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

static void cc_rgb_tick(void) {
    const uint16_t now = timer_read();
    const bool main_enabled = rgblight_is_enabled();
    const uint8_t main_brightness = rgblight_get_val();
    if (cc_last_main_enabled != main_enabled) {
        cc_last_main_enabled = main_enabled;
        cc_main_dirty = true;
    }
    if (cc_rgb.mode == 4 && main_enabled &&
        timer_elapsed(cc_main_frame_time) >= cc_light_interval(cc_rgb.speed)) {
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

    if (animated && timer_elapsed(cc_frame_frame_time) >= cc_light_interval(cc_rgb.frame_speed)) {
        cc_frame_frame_time = now;
        cc_frame_phase += (cc_rgb.frame_effect == CC_FRAME_EFFECT_BREATHE ? 2u : 1u);
        cc_frame_dirty = true;
    }
    if (cc_frame_dirty) cc_rgb_frame_paint();
}

static bool cc_tester_preview_leds(void) {
    static uint8_t previous;
    uint8_t output = cc_matrix_test_view && timer_elapsed(cc_tester_output_at) < 1800
        ? cc_tester_output : 0;
    if (output < 2) {
        if (previous) {
            if (!cc_visual_profile_available)
                rgblight_sethsv_noeeprom(rgblight_get_hue(), rgblight_get_sat(), rgblight_get_val());
            cc_main_dirty = cc_frame_dirty = true;
            previous = 0;
        }
        return false;
    }
    if (previous != output) {
        // Drive only the selected zone at a low test brightness.
        uint8_t first = output == 2 ? 0 : CC_RGB_FRAME_LED_START;
        uint8_t end = output == 2 ? CC_RGB_MAIN_LED_COUNT : RGBLIGHT_LED_COUNT;
        for (uint8_t led = 0; led < RGBLIGHT_LED_COUNT; ++led)
            rgblight_driver.set_color(led, led >= first && led < end ? 18 : 0, 0, 0);
        // Flush the driver directly so a saved "off" setting cannot mask the test.
        rgblight_driver.flush();
        previous = output;
    }
    return true;
}

// Stage edits before making them visible to the renderer and EEPROM.
static omp_zone_t cc_pending_matrix_zones[OMP_LAYERS][OMP_MATRIX_ZONE_COUNT];
static uint8_t cc_pending_matrix_map[CC_RGB_MAIN_LED_COUNT];
static uint32_t cc_matrix_transfer_at;
static bool cc_matrix_transfer;

static void cc_stage_matrix_zones(void) {
    if (!cc_matrix_transfer || timer_elapsed32(cc_matrix_transfer_at) >= 15000u) {
        memcpy(cc_pending_matrix_zones, cc_rgb.matrix_zones, sizeof(cc_pending_matrix_zones));
        memcpy(cc_pending_matrix_map, cc_rgb.zone_map, sizeof(cc_pending_matrix_map));
    }
    cc_matrix_transfer_at = timer_read32();
    cc_matrix_transfer = true;
}

// VIA channel 0 preserves the previous four custom main-palette IDs (1..4).
// New Frame values use 5..11, so existing saved VIA definitions remain valid.
void via_custom_value_command_kb(uint8_t *data, uint8_t length) {
    if (cc_live_command(data, length)) return;
    // 0x7A: read/write matrix and frame zones; 0x7D: color settings;
    // 0x7B: atomic staging commit. Original MZ01 remains readable.
    if (length == 32 && data[1] == 0 &&
        (data[0] == id_custom_get_value || data[0] == id_custom_set_value)) {
        bool get = data[0] == id_custom_get_value;
        if (data[2] == 0x7A) {
            if (data[3] < OMP_LAYERS && data[4] < OMP_MATRIX_ZONE_COUNT) {
                const omp_zone_t *zone = &cc_rgb.matrix_zones[data[3]][data[4]];
                if (get) { memcpy(&data[5], zone, sizeof(*zone)); return; }
                omp_zone_t candidate;
                memcpy(&candidate, &data[5], sizeof(candidate));
                if (omp_zone_valid(&candidate) || cc_matrix_zone_record_valid(&candidate, 3)) {
                    cc_stage_matrix_zones();
                    cc_pending_matrix_zones[data[3]][data[4]] = candidate;
                    return;
                }
            } else if (data[3] == 255 && data[4] < 2) {
                const uint8_t offset = data[4] * 15u;
                if (get) { memcpy(&data[5], cc_rgb.zone_map + offset, 15); return; }
                bool valid = true;
                for (uint8_t i = 0; i < 15; ++i)
                    if (data[5 + i] >= OMP_MATRIX_ZONE_COUNT) valid = false;
                if (valid) {
                    cc_stage_matrix_zones();
                    memcpy(cc_pending_matrix_map + offset, &data[5], 15);
                    return;
                }
            }
            if (!get) cc_matrix_transfer = false;
            data[0] = id_unhandled;
            return;
        }
        if (data[2] == 0x7D) {
            if (get && data[3] == 255u) {
                memcpy(&data[3], "LX02", 4);
                data[7] = 8; // Configured QMK layers
                data[8] = 6; // Five matrix subzones + frame
                data[9] = CC_NEXT_TINT_BYTES;
                data[10] = 4; // Highest supported lighting format.
                data[11] = cc_matrix_version();
                return;
            }
            const uint8_t offset = data[3], size = data[4];
            if (size > 0 && size <= 25u && (uint16_t)offset + size <= CC_NEXT_COLOR_BYTES) {
                uint8_t *tints = (uint8_t *)cc_rgb.matrix_zones + CC_NEXT_TINT_OFFSET;
                if (get) memcpy(&data[5], tints + offset, size);
                else {
                    cc_stage_matrix_zones();
                    uint8_t *pending = (uint8_t *)cc_pending_matrix_zones + CC_NEXT_TINT_OFFSET;
                    memcpy(pending + offset, &data[5], size);
                }
                return;
            }
            data[0] = id_unhandled;
            return;
        }
        if (data[2] == 0x7B) {
            if (get) {
                memcpy(&data[3], "MZ01", 4);
                data[7] = OMP_MATRIX_ZONE_COUNT;
                data[8] = CC_RGB_MAIN_LED_COUNT;
                data[9] = CC_RGB_FRAME_LED_COUNT;
                return;
            }
            const uint8_t version = data[3] == 1 ? cc_matrix_version() : data[3];
            if (data[3] >= 1 && data[3] <= 4 && cc_matrix_transfer &&
                timer_elapsed32(cc_matrix_transfer_at) < 15000u &&
                cc_matrix_zone_data_valid(cc_pending_matrix_zones, version)) {
                cc_matrix_transfer = false;
                cc_fix_matrix_map(cc_pending_matrix_map);
                memcpy(cc_rgb.matrix_zones, cc_pending_matrix_zones, sizeof(cc_rgb.matrix_zones));
                memcpy(cc_rgb.zone_map, cc_pending_matrix_map, sizeof(cc_rgb.zone_map));
                if (data[3] == 2) memcpy(cc_rgb.zone_magic, "MZ02", 4);
                if (data[3] == 3) memcpy(cc_rgb.zone_magic, "MZ03", 4);
                if (data[3] == 4) memcpy(cc_rgb.zone_magic, "MZ04", 4);
                eeconfig_update_user_datablock(&cc_rgb, 0, sizeof(cc_rgb));
                return;
            }
            cc_matrix_transfer = false;
            data[0] = id_unhandled;
            return;
        }
    }
    if (omp_command(data, length)) return;
    if (cc_detect_via_snapshot(data, length)) return;
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
