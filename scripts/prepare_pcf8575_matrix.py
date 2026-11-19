#!/usr/bin/env python3
"""Convert the human-readable PCF8575 pin map into QMK's native build input.

The committed keyboard.json is the single source of truth for the seven
expander pins. QMK does not recognize P00-P17 as RP2040 MCU pin names, so
only the temporary build copy receives null GPIO placeholders.
The generated header provides the actual mapping to the I2C matrix driver.

Usage: prepare_pcf8575_matrix.py SOURCE_JSON STAGED_JSON STAGED_HEADER
"""
import json
import re
import sys
from pathlib import Path

PIN_RE = re.compile(r"^P([01])([0-7])$")


def parse_pin(name):
    if not isinstance(name, str):
        raise ValueError("PCF8575 matrix pins must be explicit P00..P17 strings")
    match = PIN_RE.fullmatch(name)
    if not match:
        raise ValueError(f"Invalid PCF8575 pin {name!r}; expected P00..P07 or P10..P17")
    return 8 * int(match.group(1)) + int(match.group(2))


def prepare(source_path, staged_json_path, staged_header_path):
    config = json.loads(Path(source_path).read_text(encoding="utf-8"))
    matrix = config["matrix_pins"]
    if matrix.get("custom_lite") is not True:
        raise ValueError("PCF8575 requires matrix_pins.custom_lite=true")
    rows = matrix["rows"]
    cols = matrix["cols"]
    if len(rows) != 3 or len(cols) != 4:
        raise ValueError("OMNIscreen requires exactly 3 rows and 4 columns")
    row_bits = [parse_pin(pin) for pin in rows]
    col_bits = [parse_pin(pin) for pin in cols]
    if len(set(row_bits + col_bits)) != 7:
        raise ValueError("PCF8575 row/column pins must be unique")

    for item in config["layouts"]["LAYOUT"]["layout"]:
        row, col = item["matrix"]
        if not (0 <= row < 3 and 0 <= col < 4):
            raise ValueError(f"Key uses invalid matrix position R{row}C{col}")

    used_mask = sum(1 << bit for bit in row_bits + col_bits)
    free_mask = 0xFFFF & ~used_mask
    # Only rewrite the *staged* QMK input. Never touch the source JSON.
    matrix["rows"] = [None] * len(rows)
    matrix["cols"] = [None] * len(cols)
    Path(staged_json_path).write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    header = (
        "// AUTO-GENERATED FROM keyboards/icst7789v/keyboard.json - DO NOT EDIT.\n"
        "// P00-P17 are PCF8575 ports, not physical RP2040 MCU pins.\n"
        "#pragma once\n"
        "#include <stdint.h>\n"
        f"#define CC_PCF_ROW_COUNT {len(rows)}\n"
        f"#define CC_PCF_COL_COUNT {len(cols)}\n"
        f"#define CC_PCF_UNASSIGNED_MASK 0x{free_mask:04X}u\n"
        "static const uint8_t cc_pcf_row_bits[CC_PCF_ROW_COUNT] = {"
        + ", ".join(f"{p}u" for p in row_bits) + "};\n"
        "static const uint8_t cc_pcf_col_bits[CC_PCF_COL_COUNT] = {"
        + ", ".join(f"{p}u" for p in col_bits) + "};\n"
    )
    Path(staged_header_path).write_text(header, encoding="utf-8")
    print("PCF8575 matrix: rows " + ", ".join(rows)
          + " | cols " + ", ".join(cols))
    print("QMK staging: null MCU GPIOs + generated PCF8575 bit mapping")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: prepare_pcf8575_matrix.py SOURCE_JSON STAGED_JSON STAGED_HEADER")
    try:
        prepare(*sys.argv[1:])
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: PCF8575 pin mapping: {exc}")
