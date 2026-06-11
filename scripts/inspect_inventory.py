from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from codescent.engine.inventory import build_file_inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    inventory = build_file_inventory(args.repo)
    payload = [item.model_dump() for item in inventory]

    if args.json_output:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    for item in inventory:
        sys.stdout.write(f"{item.language}\t{item.path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
