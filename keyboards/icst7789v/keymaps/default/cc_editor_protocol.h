// Transactional VIA extension on custom channel 0, IDs 0x71..0x79.
#pragma once
#include "via.h"

static bool omp_command(uint8_t *data, uint8_t length) {
    if (length != 32 || data[1] != 0 ||
        (data[0] != id_custom_get_value && data[0] != id_custom_set_value) ||
        data[2] < 0x71 || data[2] > 0x79) return false;
    const bool get = data[0] == id_custom_get_value;
    const uint8_t id = data[2];
    if (id == 0x79 && !get) {
        if (data[3] == 0) {
            omp_preview_active = false;
            return true;
        }
        if ((data[3] == 1 || data[3] == 2) && !cc_matrix_test_view) {
            omp_zone_t zones[2];
            const bool extended = data[3] == 2;
            if (extended) {
                const uint8_t size = sizeof(omp_zone_t) - 2u;
                for (uint8_t i = 0; i < 2; ++i) {
                    memcpy(&zones[i], &data[4 + i * size], size);
                    zones[i].triggers = 0;
                    zones[i].duration = 1;
                }
            } else {
                memcpy(zones, &data[4], sizeof(zones));
            }
            if (omp_zone_valid(&zones[0]) && omp_zone_valid(&zones[1])) {
                memcpy(omp_preview_zones, zones, sizeof(zones));
                if (extended)
                    memcpy(omp_preview_tints, &data[4 + sizeof(zones) - 4u], sizeof(omp_preview_tints));
                else
                    omp_preview_zones[0].flags &= ~OMP_LIGHT_REACTIVE;
                omp_preview_at = timer_read();
                omp_preview_active = true;
                return true;
            }
        }
    }
    if (id == 0x77 && get) return cc_tester_report(data);
    if (id == 0x78 && !get && cc_tester_active && cc_matrix_test_view && data[3] <= 3) {
        if (cc_tester_output == 1) cc_matrix_full_redraw = true;
        cc_tester_output = data[3];
        cc_tester_output_at = timer_read();
        cc_dirty = true;
        return true;
    }
    if (id == 0x76 && !get && data[3] <= 2) {
        omp_preview_active = false;
        omp_release_all();
        clear_keyboard();
        cc_tester_active = data[3] == 2;
        cc_tester_last_poll = timer_read();
        cc_k0_tap_count = 0;
        if (cc_tester_output == 1) cc_matrix_full_redraw = true;
        cc_tester_output = 0;
        cc_dirty = true;
        cc_signal_head = cc_signal_count = 0;
        cc_signal_overflow = false;
        if (data[3]) cc_matrix_test_enter();
        else cc_matrix_test_exit();
        return true;
    }
    if (id == 0x71 && get) {
        memcpy(&data[3], "OMP2", 4);
        data[7] = cc_visual_profile_available;
        data[8] = OMP_LAYERS;
        data[9] = sizeof(omp_profile) & 255u;
        data[10] = sizeof(omp_profile) >> 8;
        memcpy(&data[11], &omp_generation, 4);
        data[15] = CC_PCF8575_MATRIX;
        data[16] = 31; // LED preview, device actions, screens, matrix zones, simplified lighting.
        return true;
    }
    if (id == 0x72 && get && cc_visual_profile_available) {
        uint16_t offset = data[3] | ((uint16_t)data[4] << 8);
        uint8_t count = data[5];
        if (count <= 25 && (uint32_t)offset + count <= sizeof(omp_profile)) {
            memcpy(&data[6], (const uint8_t *)&omp_profile + offset, count);
            return true;
        }
    } else if (id == 0x73 && !get) {
        uint32_t expected_generation;
        memcpy(&expected_generation, &data[7], 4);
        if (expected_generation != omp_generation) {
            data[0] = id_unhandled;
            return true;
        }
        omp_receiving = true;
        omp_received = 0;
        omp_transfer_timer = timer_read();
        memcpy(&omp_expected_checksum, &data[3], 4);
        memset(&omp_incoming, 0, sizeof(omp_incoming));
        return true;
    } else if (id == 0x74 && !get && omp_receiving) {
        uint16_t offset = data[3] | ((uint16_t)data[4] << 8);
        uint8_t count = data[5];
        if (timer_elapsed(omp_transfer_timer) < 15000u && count > 0 && count <= 25 &&
            offset == omp_received && (uint32_t)offset + count <= sizeof(omp_incoming)) {
            memcpy((uint8_t *)&omp_incoming + offset, &data[6], count);
            omp_received += count;
            omp_transfer_timer = timer_read();
            return true;
        }
        omp_receiving = false;
    } else if (id == 0x75 && !get && omp_receiving) {
        omp_receiving = false;
        if (omp_received == sizeof(omp_incoming) && omp_profile_valid(&omp_incoming) &&
            omp_checksum(&omp_incoming, sizeof(omp_incoming)) == omp_expected_checksum) {
            omp_release_all();
            if (omp_store()) {
                cc_screen_selection = CC_SCREEN_AUTO;
                omp_screen_invalid = true;
                cc_visual_profile_available = true;
                if (!cc_use_app_profile) omp_enabled = false;
                omp_last_layer = 255; // A replacement profile also resets temporary lighting controls.
                cc_activate_layer(omp_enabled ? omp_profile.default_layer : 1);
                omp_layer_changed();
                cc_dirty = true;
                return true;
            }
        }
    }
    data[0] = id_unhandled;
    return true;
}
