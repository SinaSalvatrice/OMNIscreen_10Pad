// Read-only editor telemetry. Button activity is shared only while the user
// has entered the physical MATRIX test, which suppresses host key output.
#pragma once

static uint8_t cc_detect_clockwise;
static uint8_t cc_detect_counterclockwise;
static uint8_t cc_detect_encoder_pushes;

static bool cc_detect_via_snapshot(uint8_t *data, uint8_t length) {
    if (length < 18 || data[0] != id_custom_get_value ||
        data[1] != id_custom_channel || data[2] != 0x70) {
        return false;
    }

    const bool enabled = cc_matrix_test_view;
    uint16_t down = 0;
    if (enabled) {
        for (uint8_t key = 0; key < CC_KEY_COUNT; ++key) {
            if (cc_matrix_down[key]) down |= (uint16_t)(1u << key);
        }
    }

    data[3] = 'O';
    data[4] = 'M';
    data[5] = 'N';
    data[6] = 'I';
    data[7] = 1;
    data[8] = cc_active;
    data[9] = enabled;
    data[10] = (uint8_t)down;
    data[11] = (uint8_t)(down >> 8);
    data[12] = enabled ? cc_matrix_last_key : UINT8_MAX;
    data[13] = enabled ? (uint8_t)cc_matrix_hits : 0;
    data[14] = enabled ? (uint8_t)(cc_matrix_hits >> 8) : 0;
    data[15] = enabled ? cc_detect_clockwise : 0;
    data[16] = enabled ? cc_detect_counterclockwise : 0;
    // The encoder push ends MATRIX test; expose its count so the UI can
    // acknowledge the exit even though the test is already inactive.
    data[17] = cc_detect_encoder_pushes;
    return true;
}
