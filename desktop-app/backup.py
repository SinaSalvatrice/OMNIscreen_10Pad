"""Save a VIA backup from the connected OmniPad without changing it."""

import argparse
import json
from pathlib import Path

from via import OmniPad, ViaError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        with OmniPad.connect() as device:
            snapshot = device.snapshot()
        with args.destination.open("x", encoding="utf-8") as destination:
            json.dump(snapshot, destination, indent=2)
            destination.write("\n")
    except (OSError, ViaError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{len(snapshot['layers'])} Layer gesichert: {args.destination}")


if __name__ == "__main__":
    main()
