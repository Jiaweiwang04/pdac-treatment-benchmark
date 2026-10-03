"""Build or verify the internal development split without rebuilding Core/Pilot."""
import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "code/src"))
from pdac_benchmark.v2_0.development_split import check, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only integrity and split audit")
    args = parser.parse_args()
    if args.check:
        result = check(BASE)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return run(BASE)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
