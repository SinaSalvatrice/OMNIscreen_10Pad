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
    python3 "$PROJECT_ROOT/scripts/generate_layer_system.py" --no-previews
    python3 "$PROJECT_ROOT/scripts/generate_editor_icons.py"
elif [[ ! -f "$PROJECT_ROOT/keyboards/$KEYBOARD/keymaps/$KEYMAP/generated_layers.h" ]]; then
    echo "ERROR: Python 3 required to generate layer metadata" >&2
    exit 4
else
    echo "WARNING: python3 unavailable here; using existing generated header"
fi

python3 "$PROJECT_ROOT/scripts/check_standalone_keymap.py"

cd "$QMK_HOME"

echo "QMK_HOME: $QMK_HOME"
echo "Checking RP2040/QMK submodules (offline when already present)..."
# Running `git submodule update --checkout` on every single build may contact
# the network or stall even when the five pinned dependencies are ready.
# Check their actual HEAD against the parent QMK gitlink first.
for module in \
    lib/chibios \
    lib/chibios-contrib \
    lib/pico-sdk \
    lib/lufa \
    lib/printf
do
    expected="$(git ls-tree HEAD -- "$module" | awk '{print $3}')"
    if [[ -z "$expected" ]]; then
        echo "ERROR: Missing QMK submodule definition for $module" >&2
        exit 6
    fi
    actual=""
    if [[ -e "$module/.git" ]]; then
        actual="$(git -C "$module" rev-parse HEAD 2>/dev/null || true)"
    fi
    if [[ "$actual" == "$expected" ]]; then
        echo "  OK (already initialized): $module"
    else
        echo "  Initializing/repairing $module; this may require network access..."
        GIT_TERMINAL_PROMPT=0 git submodule update --init --checkout -- "$module"
        actual="$(git -C "$module" rev-parse HEAD 2>/dev/null || true)"
        if [[ "$actual" != "$expected" ]]; then
            echo "ERROR: $module remains at $actual; expected $expected" >&2
            exit 7
        fi
    fi
done

echo "Synchronizing keyboard definition (changed files only)..."
source_keyboard="$PROJECT_ROOT/keyboards/$KEYBOARD"
target_keyboard="keyboards/$KEYBOARD"
mkdir -p "$target_keyboard"
# Remove deleted sources, without invalidating unrelated object files.
while IFS= read -r -d '' oldfile; do
    relative="${oldfile#"$target_keyboard/"}"
    if [[ ! -f "$source_keyboard/$relative" ]]; then
        rm -f -- "$oldfile"
    fi
done < <(find "$target_keyboard" -type f -print0)
# Preserve mtime for identical sources, making incremental QMK builds possible.
while IFS= read -r -d '' srcfile; do
    relative="${srcfile#"$source_keyboard/"}"
    dest="$target_keyboard/$relative"
    if ! cmp -s -- "$srcfile" "$dest"; then
        mkdir -p -- "$(dirname "$dest")"
        cp -- "$srcfile" "$dest"
    fi
done < <(find "$source_keyboard" -type f -print0)

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

# Publish atomically to the one shared output directory, including when
# invoked from a detached development worktree.
build_dir="$(to_msys_path "${BUILD_OUTPUT_DIR:-$PROJECT_ROOT/build}")"
mkdir -p "$build_dir"
published_uf2="$build_dir/OmniPad.uf2"
temporary_uf2="$(mktemp "$build_dir/.OmniPad.XXXXXXXX.tmp")"
trap 'rm -f -- "$temporary_uf2"' EXIT
cp -- "$UF2" "$temporary_uf2"
test -s "$temporary_uf2"
mv -f -- "$temporary_uf2" "$published_uf2"

# QMK intermediate copies must not linger as alternate flash files.
rm -f -- "$UF2" "$QMK_HOME/.build/${KEYBOARD}_${KEYMAP}.uf2"
# Retain only the canonical UF2 and single build log; never create an Archiv.
find "$build_dir" -maxdepth 1 -type f \( -iname '*.uf2' -o -iname '*.log' \) \
    ! -path "$published_uf2" ! -path "$build_dir/OmniPad.log" -delete
echo
echo "SUCCESS: $published_uf2"
