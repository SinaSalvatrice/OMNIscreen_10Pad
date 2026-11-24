"""Hardware LED zone layout, independent of the physical serial ordering."""
MATRIX_ROWS = 6
MATRIX_COLS = 5
MATRIX_COUNT = MATRIX_ROWS * MATRIX_COLS
FRAME_COUNT = 43
LED_COUNT = MATRIX_COUNT + FRAME_COUNT
MATRIX_ZONES = ("Tasten", "Regler", "Encoder", "K0", "Display")
ZONE_NAMES = MATRIX_ZONES + ("Frame",)

def default_zone_map(order="rows"):
    result = []
    for row in range(MATRIX_ROWS):
        columns = range(MATRIX_COLS)
        if order == "serpentine" and row % 2:
            columns = reversed(columns)
        for col in columns:
            if (row == 0 and col <= 3) or (row == 1 and col <= 2):
                zone = 4  # Display
            elif col == 4 and row <= 1:
                zone = 2  # Encoder
            elif (row == 1 and col == 3) or (row == 2 and col == 4):
                zone = 3  # K0
            elif col == 4 and row >= 3:
                zone = 1  # Slider
            else:
                zone = 0  # Keys
            result.append(zone)
    return result

def validate_zone_map(value):
    if not isinstance(value, list) or len(value) != MATRIX_COUNT:
        raise ValueError("Die 6×5-Matrix benötigt genau 30 Zonenzuordnungen.")
    if any(type(item) is not int or not 0 <= item < len(MATRIX_ZONES) for item in value):
        raise ValueError("Jede Matrix-LED muss einer Zone 0–4 zugeordnet sein.")
    return list(value)

def matrix_positions(order="rows"):
    points = []
    for serial in range(MATRIX_COUNT):
        row, col = divmod(serial, MATRIX_COLS)
        if order == "serpentine" and row % 2:
            col = MATRIX_COLS - 1 - col
        points.append([round(.18 + col * .16, 5), round(.20 + row * .125, 5)])
    return points


def matrix_order(mapping):
    """Keep a previously selected serpentine wiring without custom zone edits."""
    return "serpentine" if mapping == default_zone_map("serpentine") else "rows"
