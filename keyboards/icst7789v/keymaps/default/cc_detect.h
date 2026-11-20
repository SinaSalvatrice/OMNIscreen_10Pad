// Read-only editor telemetry. Reports held switches independently of key assignments.
#pragma once

static uint8_t cc_detect_clockwise;
static uint8_t cc_detect_counterclockwise;
static uint8_t cc_detect_encoder_pushes;

static bool cc_detect_via_snapshot(uint8_t *data, uint8_t length) {
    if (length < 32 || data[0] != id_custom_get_value ||
        data[1] != id_custom_channel || data[2] != 0x70) {
        return false;
    }

    const bool enabled = cc_matrix_test_view;
    uint16_t down = 0;
    for (uint8_t key = 0; key < CC_KEY_COUNT; ++key) {
        const bool pressed = enabled ? cc_matrix_down[key] :
            (matrix_get_row(cc_matrix_row[key]) & ((matrix_row_t)1u << cc_matrix_col[key])) != 0;
        if (pressed) down |= (uint16_t)(1u << key);
    }

    data[3] = 'O';
    data[4] = 'M';
    data[5] = 'N';
    data[6] = 'I';
    data[7] = 2;
    data[8] = cc_active;
    data[9] = enabled;
    if (!cc_k0.stable) down |= 1u << 11;
    if (!cc_encoder_button.stable) down |= 1u << 10;
    data[10] = (uint8_t)down;
    data[11] = (uint8_t)(down >> 8);
    data[12] = enabled ? cc_matrix_last_key : (omp_enabled ? omp_last_key : UINT8_MAX);
    data[13] = enabled ? (uint8_t)cc_matrix_hits : 0;
    data[14] = enabled ? (uint8_t)(cc_matrix_hits >> 8) : 0;
    data[15] = enabled ? cc_detect_clockwise : 0;
    data[16] = enabled ? cc_detect_counterclockwise : 0;
    // The encoder push ends MATRIX test; expose its count so the UI can
    // acknowledge the exit even though the test is already inactive.
    data[17] = cc_detect_encoder_pushes;
    data[18] = (uint8_t)cc_slider_raw;
    data[19] = (uint8_t)(cc_slider_raw >> 8);
    data[20] = cc_slider_pct;
    data[21] = cc_slider_valid;
    data[22] = omp_last_gesture;
    data[23] = cc_adxl.status;
    data[24] = (uint8_t)cc_adxl.x;
    data[25] = (uint8_t)((uint16_t)cc_adxl.x >> 8);
    data[26] = (uint8_t)cc_adxl.y;
    data[27] = (uint8_t)((uint16_t)cc_adxl.y >> 8);
    data[28] = (uint8_t)cc_adxl.z;
    data[29] = (uint8_t)((uint16_t)cc_adxl.z >> 8);
    data[30] = cc_display_mode;
    data[31] = CC_PCF8575_MATRIX;
    return true;
}
