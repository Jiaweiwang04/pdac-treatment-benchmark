"""Reproduce v2.0 audit and checks from any working directory."""
import argparse
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "code/src"))
from pdac_benchmark.v2_0.audit import run
from pdac_benchmark.v2_0.documentation import check_documents
from pdac_benchmark.v2_0.phase02 import run as run_timeline
from pdac_benchmark.v2_0.screening import run as run_candidates
from pdac_benchmark.v2_0.candidate_review import run as run_review
from pdac_benchmark.v2_0.candidate_cohort import run as run_cohort
from pdac_benchmark.v2_0.patient_split import run as run_split


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["all", "audit", "timeline", "candidates", "review", "cohort", "split", "check"], nargs="?", default="all")
    parser.add_argument("--config", type=Path, default=BASE / "code/config/v2.0/source.json")
    args = parser.parse_args()
    config_path = args.config if args.config.is_absolute() else BASE / args.config
    if args.action in {"all", "audit"}:
        result = run(config_path)
        if result or args.action == "audit":
            return result
    if args.action in {"all", "timeline"}:
        result = run_timeline(BASE / "code/config/v2.0/decision_points.json")
        if result or args.action == "timeline":
            return result
    if args.action in {"all", "candidates"}:
        result = run_candidates(BASE / "code/config/v2.0/screening.json")
        if result or args.action == "candidates":
            return result
    if args.action in {"all", "review"}:
        result = run_review(BASE / "code/config/v2.0/candidate_review.json")
        if result or args.action == "review":
            return result
    if args.action in {"all", "cohort"}:
        result = run_cohort(BASE / "code/config/v2.0/candidate_cohort.json")
        if result or args.action == "cohort":
            return result
    if args.action in {"all", "split"}:
        result = run_split(BASE / "code/config/v2.0/patient_split.json")
        if result or args.action == "split":
            return result
    suite = unittest.defaultTestLoader.discover(str(BASE / "code/tests/v2_0"))
    tests = unittest.TextTestRunner(verbosity=2).run(suite)
    checked = check_documents(BASE)
    checked["tests_run"] = tests.testsRun
    checked["tests_passed"] = tests.wasSuccessful()
    if not tests.wasSuccessful():
        checked["errors"].append("Data processing or directory protection tests failed")
        checked["status"] = "failed"
    output = BASE / "code/results/v2.0/documentation_check_v2.0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(checked, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(checked, ensure_ascii=False, indent=2))
    return int(checked["status"] != "passed")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
