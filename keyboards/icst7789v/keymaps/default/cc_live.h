// Volatile LED preview frames and physical input feedback over VIA HID.
#pragma once

#define CC_LIVE_RGB_BYTES (RGBLIGHT_LED_COUNT * 3u)
#define CC_LIVE_CHUNK_BYTES 27u
#define CC_LIVE_CHUNKS ((CC_LIVE_RGB_BYTES + CC_LIVE_CHUNK_BYTES - 1u) / CC_LIVE_CHUNK_BYTES)
#define CC_LIVE_TIMEOUT_MS 500u

static uint8_t cc_live_staging[CC_LIVE_RGB_BYTES], cc_live_frame[CC_LIVE_RGB_BYTES];
static uint8_t cc_live_chunk, cc_live_sequence, cc_live_triggers;
static uint16_t cc_live_presses;
static uint32_t cc_live_received_at;
static bool cc_live_active, cc_live_dirty;

static bool cc_live_preview_allowed(void) {
    return cc_rgb_master_enabled && !cc_matrix_test_view;
}

static bool cc_live_preview_enabled(void) {
    if (!cc_live_preview_allowed() ||
        (cc_live_active && timer_elapsed32(cc_live_received_at) >= CC_LIVE_TIMEOUT_MS)) {
        cc_live_active = false;
        cc_live_chunk = 0;
    }
    return cc_live_active;
}

static void cc_live_draw(void) {
    if (!cc_live_dirty) return;
    for (uint8_t i = 0; i < RGBLIGHT_LED_COUNT; ++i) {
        const uint8_t *rgb = &cc_live_frame[i * 3u];
        rgblight_driver.set_color(i, rgb[0] * RGBLIGHT_LIMIT_VAL / 255u,
                                rgb[1] * RGBLIGHT_LIMIT_VAL / 255u,
                                rgb[2] * RGBLIGHT_LIMIT_VAL / 255u);
    }
    rgblight_driver.flush();
    cc_live_dirty = false;
}

static bool cc_live_command(uint8_t *data, uint8_t length) {
    if (length != 32 || data[1] != 0) return false;
    if (data[2] == 0x7F && data[0] == id_custom_get_value) {
        // Read the debounced physical matrix, independently of the assigned keycodes.
        uint16_t held = (!cc_encoder_button.stable ? 1u << 10 : 0) |
                        (!cc_k0.stable ? 1u << 11 : 0);
        for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
            if (matrix_get_row(cc_matrix_row[i]) & (1u << cc_matrix_col[i])) held |= 1u << i;
        }
        memcpy(&data[3], "NL01", 4);
        memcpy(&data[7], &held, sizeof(held));
        memcpy(&data[9], &cc_live_presses, sizeof(cc_live_presses));
        data[11] = cc_active;
        data[12] = cc_live_triggers;
        data[13] = cc_live_preview_allowed();
        cc_live_presses = 0;
        cc_live_triggers = 0;
        return true;
    }
    if (data[2] != 0x7E || data[0] != id_custom_set_value) return false;

    const uint8_t chunk = data[3], sequence = data[4];
    if (chunk == UINT8_MAX) {
        cc_live_active = false;
        cc_live_chunk = 0;
        return true;
    }
    if (chunk == 0) {
        cc_live_sequence = sequence;
        cc_live_chunk = 0;
    }
    if (!cc_live_preview_allowed()) {
        cc_live_active = false;
        cc_live_chunk = 0;
        data[3] = UINT8_MAX;
        return true;
    }
    if (chunk >= CC_LIVE_CHUNKS || chunk != cc_live_chunk || sequence != cc_live_sequence) {
        data[0] = id_unhandled;
        return true;
    }
    const uint16_t offset = chunk * CC_LIVE_CHUNK_BYTES;
    const uint8_t size = MIN(CC_LIVE_CHUNK_BYTES, CC_LIVE_RGB_BYTES - offset);
    memcpy(&cc_live_staging[offset], &data[5], size);
    if (++cc_live_chunk == CC_LIVE_CHUNKS) {
        cc_live_chunk = 0;
        cc_live_dirty = !cc_live_active || cc_live_dirty ||
                        memcmp(cc_live_frame, cc_live_staging, sizeof(cc_live_frame)) != 0;
        memcpy(cc_live_frame, cc_live_staging, sizeof(cc_live_frame));
        cc_live_received_at = timer_read32();
        cc_live_active = true;
    }
    return true;
}
