// OMNIscreen 10Pad: optional MCP23017 matrix on the same I2C0 bus as ADXL345.
// Select with MCP23017_MATRIX=yes at build time. GPIO matrix remains the default.
// Wiring: rows R0..R2 -> GPA0..GPA2, columns C0..C3 -> GPB0..GPB3.
// Existing diode direction ROW2COL: select one column LOW, read pulled-up rows.
// The I2C expander at 0x20 uses A0/A1/A2=GND; ADXL345 uses 0x53.
#include "matrix.h"
#include "i2c_master.h"
#include "timer.h"
#include <stdbool.h>
#include <stdint.h>

#define CC_MCP_ADDRESS        (0x20u << 1) // QMK I2C API expects shifted address.
#define CC_MCP_TIMEOUT_MS     5
#define CC_MCP_IODIRA         0x00u
#define CC_MCP_IODIRB         0x01u
#define CC_MCP_IOCON          0x0Au
#define CC_MCP_GPPUA          0x0Cu
#define CC_MCP_GPIOA          0x12u
#define CC_MCP_OLATB          0x15u
#define CC_MCP_ROW_MASK       0x07u
#define CC_MCP_COLUMN_COUNT   4u
#define CC_MCP_RETRY_MS       500u

static bool cc_mcp_ready = false;
static uint16_t cc_mcp_last_retry = 0;

bool cc_mcp23017_online(void) {
    return cc_mcp_ready;
}

static bool cc_mcp_write(uint8_t reg, uint8_t data) {
    return i2c_write_register(CC_MCP_ADDRESS, reg, &data, 1,
                              CC_MCP_TIMEOUT_MS) == I2C_STATUS_SUCCESS;
}

static bool cc_mcp_read(uint8_t reg, uint8_t *data) {
    return i2c_read_register(CC_MCP_ADDRESS, reg, data, 1,
                             CC_MCP_TIMEOUT_MS) == I2C_STATUS_SUCCESS;
}

// When initialization fails, do not lock the keyboard in a long retry loop.
// Retry at most twice per second; never emit stale pressed keys.
static bool cc_mcp_configure(void) {
    cc_mcp_last_retry = timer_read();
    // IOCON default BANK=0; disable SEQOP changes. Reset pin must be held HIGH.
    // All columns start as inputs; setting the output latch LOW ahead of time
    // makes an individual column drive low immediately after enabling it.
    cc_mcp_ready =
        cc_mcp_write(CC_MCP_IOCON, 0x00u) &&
        cc_mcp_write(CC_MCP_IODIRA, 0xFFu) &&
        cc_mcp_write(CC_MCP_IODIRB, 0xFFu) &&
        cc_mcp_write(CC_MCP_OLATB, 0x00u) &&
        cc_mcp_write(CC_MCP_GPPUA, CC_MCP_ROW_MASK);
    return cc_mcp_ready;
}

void matrix_init_custom(void) {
    i2c_init();
    cc_mcp_configure();
}

static bool cc_mcp_store(matrix_row_t matrix[], const matrix_row_t samples[]) {
    bool changed = false;
    for (uint8_t row = 0; row < MATRIX_ROWS; row++) {
        if (matrix[row] != samples[row]) {
            matrix[row] = samples[row];
            changed = true;
        }
    }
    return changed;
}

bool matrix_scan_custom(matrix_row_t matrix[]) {
    matrix_row_t next[MATRIX_ROWS] = {0};

    if (!cc_mcp_ready) {
        if (timer_elapsed(cc_mcp_last_retry) >= CC_MCP_RETRY_MS) {
            cc_mcp_configure();
        }
        if (!cc_mcp_ready) return cc_mcp_store(matrix, next);
    }

    bool success = true;
    // ROW2COL: scanning columns in turn, rows are HIGH when no key is pressed.
    for (uint8_t column = 0; column < CC_MCP_COLUMN_COUNT; column++) {
        const uint8_t directions = (uint8_t)~(1u << column);
        uint8_t row_level;
        if (!cc_mcp_write(CC_MCP_IODIRB, directions) ||
            !cc_mcp_read(CC_MCP_GPIOA, &row_level)) {
            success = false;
            break;
        }
        for (uint8_t row = 0; row < MATRIX_ROWS; row++) {
            if (!(row_level & (1u << row))) next[row] |= (matrix_row_t)(1u << column);
        }
    }
    // Always release the selected column. All other expander pins are inputs.
    if (!cc_mcp_write(CC_MCP_IODIRB, 0xFFu)) success = false;
    if (!success) {
        cc_mcp_ready = false;
        cc_mcp_last_retry = timer_read();
        for (uint8_t row = 0; row < MATRIX_ROWS; row++) next[row] = 0;
    }
    return cc_mcp_store(matrix, next);
}
