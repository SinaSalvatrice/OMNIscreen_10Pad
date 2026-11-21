#!/usr/bin/env bash
set -euo pipefail

KEYBOARD="icst7789v"
KEYMAP="default"

# Values passed from build_uf2.bat may still be Windows paths.
to_msys_path() {
    local value="$1"
    if [[ "$value" =~ ^[A-Za-z]:[\\/] ]]; then
        cygpath -u "$value"
    else
        printf '%s\n' "$value"
    fi
}

PROJECT_ROOT="$(to_msys_path "${PROJECT_ROOT:-$(cd "$(dirname "$0")" && pwd)}")"
QMK_HOME="$(to_msys_path "${QMK_HOME:-$HOME/qmk_firmware}")"

if [[ ! -f "$QMK_HOME/Makefile" || ! -d "$QMK_HOME/keyboards" ]]; then
    echo "ERROR: QMK firmware checkout not found at: $QMK_HOME" >&2
    exit 2
fi

# QMK's make system calls the qmk CLI internally. Make sure Python can resolve
# a real home directory when this script is launched from a Windows runner.
if [[ -n "${USERPROFILE:-}" ]]; then
    export HOME="$(cygpath -u "$USERPROFILE")"
fi

# The QMK header must reflect the editable design spec before copying sources.
if command -v python3 >/dev/null 2>&1; then
    python3 "$PROJECT_ROOT/scripts/generate_layer_system.py"
    python3 "$PROJECT_ROOT/scripts/generate_editor_icons.py"
elif [[ ! -f "$PROJECT_ROOT/keyboards/$KEYBOARD/keymaps/$KEYMAP/generated_layers.h" ]]; then
    echo "ERROR: Python 3 required to generate layer metadata" >&2
    exit 4
else
    echo "WARNING: python3 unavailable here; using existing generated header"
fi

cd "$QMK_HOME"

echo "QMK_HOME: $QMK_HOME"
echo "Initializing only the submodules needed by RP2040 + USB + Quantum Painter..."
for module in \
    lib/chibios \
    lib/chibios-contrib \
    lib/pico-sdk \
    lib/lufa \
    lib/printf
do
    git submodule update --init --checkout "$module"
done

echo "Installing keyboard definition..."
rm -rf "keyboards/$KEYBOARD"
cp -R "$PROJECT_ROOT/keyboards/$KEYBOARD" "keyboards/$KEYBOARD"

# keyboard.json is the sole matrix definition, using direct RP2040 GPIOs.
echo "Keyboard JSON: direct GPIO matrix, no I2C expansion"

rm -f "${KEYBOARD}_${KEYMAP}.uf2"

echo "Building $KEYBOARD:$KEYMAP..."
# SKIP_GIT avoids QMK's normal full recursive submodule scan. The required
# RP2040 submodules were initialized explicitly above.
make SKIP_GIT=1 "$KEYBOARD:$KEYMAP"

UF2="$QMK_HOME/${KEYBOARD}_${KEYMAP}.uf2"
if [[ ! -s "$UF2" ]]; then
    echo "ERROR: Build finished without a usable UF2 at: $UF2" >&2
    exit 3
fi

build_dir="$PROJECT_ROOT/build"
mkdir -p "$build_dir"
published_uf2="$build_dir/OmniPad.uf2"
temporary_uf2="$(mktemp "$build_dir/.OmniPad.XXXXXXXX")"
trap 'rm -f -- "$temporary_uf2"' EXIT
cp -- "$UF2" "$temporary_uf2"
mv -f -- "$temporary_uf2" "$published_uf2"

# Move old project outputs aside only after the new firmware has been published.
archive_dir=""
for old_uf2 in "$build_dir"/ICST7789V.uf2 "$build_dir"/ICST7789V_*.uf2 \
               "$build_dir"/OmniPad-*.uf2 "$build_dir"/OMNIscreen_10Pad_*.uf2; do
    [[ -f "$old_uf2" ]] || continue
    if [[ -z "$archive_dir" ]]; then
        mkdir -p "$build_dir/Archiv"
        archive_dir="$(mktemp -d "$build_dir/Archiv/UF2-XXXXXXXX")"
    fi
    mv -- "$old_uf2" "$archive_dir/"
done

echo
echo "SUCCESS: $published_uf2"
