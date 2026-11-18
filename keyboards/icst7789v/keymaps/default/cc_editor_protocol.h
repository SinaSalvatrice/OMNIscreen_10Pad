// Transactional VIA extension on custom channel 0, IDs 0x71..0x75.
#pragma once
#include "via.h"

static bool omp_command(uint8_t *data, uint8_t length) {
    if (length != 32 || data[1] != 0 ||
        (data[0] != id_custom_get_value && data[0] != id_custom_set_value) ||
        data[2] < 0x71 || data[2] > 0x76) return false;
    const bool get = data[0] == id_custom_get_value;
    const uint8_t id = data[2];
    if (id == 0x76 && !get && data[3] <= 1) {
        omp_release_all();
        clear_keyboard();
        if (data[3]) cc_matrix_test_enter();
        else cc_matrix_test_exit();
        return true;
    }
    if (id == 0x71 && get) {
        memcpy(&data[3], "OMP2", 4);
        data[7] = omp_enabled;
        data[8] = OMP_LAYERS;
        data[9] = sizeof(omp_profile) & 255u;
        data[10] = sizeof(omp_profile) >> 8;
        memcpy(&data[11], &omp_generation, 4);
        data[15] = CC_PCF8575_MATRIX;
        return true;
    }
    if (id == 0x72 && get && omp_enabled) {
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
                cc_activate_layer(omp_profile.default_layer);
                omp_layer_changed();
                cc_dirty = true;
                return true;
            }
        }
    }
    data[0] = id_unhandled;
    return true;
}
