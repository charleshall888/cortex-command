#!/usr/bin/env python3
"""
Baseline-stability measurement harness for /cortex-interactive:critical-review V2 fixtures.

Usage:
    python3 tests/baseline_critical_review.py [--runs=N] [--fixture=NAME]

Default --runs=5 (full measurement); pass --runs=1 for smoke-test mode.
Default invokes both fixtures (pure_b_aggregation and straddle_case).

Output: tests/fixtures/critical-review/baseline-stability.json
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "critical-review"
OUTPUT_PATH = FIXTURE_DIR / "baseline-stability.json"

FIXTURES = {
    "pure_b_aggregation": FIXTURE_DIR / "pure_b_aggregation.md",
    "straddle_case": FIXTURE_DIR / "straddle_case.md",
}

TIMEOUT_SECONDS = 600


def get_head_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(REPO_ROOT),
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception as e:
        return f"unknown ({e})"


def invoke_critical_review(fixture_path: Path) -> tuple[bool, str]:
    """
    Invoke `claude -p "/cortex-interactive:critical-review {fixture_path}"`.
    Returns (success: bool, output: str).
    A failed/timed-out invocation returns (False, error_description).
    """
    prompt = f"/cortex-interactive:critical-review {fixture_path}"
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(REPO_ROOT),
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return False, f"exit code {result.returncode}: {output[:500]}"
        return True, output
    except subprocess.TimeoutExpired:
        return False, f"timeout after {TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        return False, "claude not found on PATH — is Claude Code CLI installed?"
    except Exception as e:
        return False, f"invocation error: {e}"


def check_pure_b_aggregation(output: str) -> tuple[bool, str]:
    """
    PASS if:
    - zero `"class": "A"` substrings in output
    - zero occurrences of 'blocks' or 'invalidates' in output

    Returns (passed: bool, reason: str).
    """
    a_class_count = output.count('"class": "A"')
    blocks_count = output.count("blocks")
    invalidates_count = output.count("invalidates")

    if a_class_count > 0:
        return False, f'found {a_class_count} occurrence(s) of "class": "A"'
    if blocks_count > 0:
        return False, f"found {blocks_count} occurrence(s) of 'blocks'"
    if invalidates_count > 0:
        return False, f"found {invalidates_count} occurrence(s) of 'invalidates'"
    return True, "ok"


def check_straddle_case(output: str) -> tuple[bool, str]:
    """
    PASS if:
    - exactly one `"class": "A"` in output
    - exactly one `"class": "B"` in output

    Returns (passed: bool, reason: str).
    """
    a_class_count = output.count('"class": "A"')
    b_class_count = output.count('"class": "B"')

    if a_class_count != 1:
        return False, f'expected exactly 1 "class": "A", found {a_class_count}'
    if b_class_count != 1:
        return False, f'expected exactly 1 "class": "B", found {b_class_count}'
    return True, "ok"


FIXTURE_CHECKERS = {
    "pure_b_aggregation": check_pure_b_aggregation,
    "straddle_case": check_straddle_case,
}


def determine_policy(
    results: dict[str, dict], runs: int
) -> tuple[str, str]:
    """
    Determine retry_policy and pass_criterion_recommendation.

    In smoke mode (runs < 5): fixed policy + deferred recommendation.
    In full mode (runs == 5): compute from per_run_probability.
    """
    if runs < 5:
        return (
            "smoke-test only — full measurement deferred",
            "3-of-3",
        )

    probs = [r["per_run_probability"] for r in results.values()]
    min_prob = min(probs)

    if min_prob >= 0.90:
        return "single-retry", "3-of-3"
    elif min_prob >= 0.80:
        return "escalate", "escalate"
    else:
        return "escalate + tighten prompts", "escalate"


def run_fixture(fixture_name: str, fixture_path: Path, runs: int) -> dict:
    checker = FIXTURE_CHECKERS[fixture_name]
    passed = 0
    failed = 0

    print(f"\n[{fixture_name}] Running {runs} invocation(s) against {fixture_path.name}")

    for i in range(runs):
        print(f"  Run {i + 1}/{runs}: invoking claude -p /cortex-interactive:critical-review ...", flush=True)
        ok, output = invoke_critical_review(fixture_path)

        if not ok:
            print(f"  Run {i + 1} FAILED (invocation error): {output[:200]}")
            failed += 1
            # If first run fails with a hard error (not found, etc.), stop early
            if "not found on PATH" in output:
                print("  FATAL: claude CLI not available. Stopping.")
                sys.exit(1)
            continue

        check_passed, reason = checker(output)
        if check_passed:
            print(f"  Run {i + 1} PASSED")
            passed += 1
        else:
            print(f"  Run {i + 1} FAILED (check): {reason}")
            failed += 1

    total = runs
    per_run_probability = passed / total if total > 0 else 0.0

    return {
        "runs": total,
        "passed": passed,
        "per_run_probability": round(per_run_probability, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline stability measurement for /cortex-interactive:critical-review")
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of invocations per fixture (default 5; use 1 for smoke test)",
    )
    parser.add_argument(
        "--fixture",
        choices=list(FIXTURES.keys()),
        default=None,
        help="Run a single fixture only (default: all fixtures)",
    )
    args = parser.parse_args()

    runs = args.runs
    smoke_test_only = runs < 5

    selected_fixtures = (
        {args.fixture: FIXTURES[args.fixture]} if args.fixture else FIXTURES
    )

    print(f"Baseline-stability harness: runs={runs}, smoke_test_only={smoke_test_only}")
    print(f"Fixtures: {list(selected_fixtures.keys())}")

    fixture_results: dict[str, dict] = {}

    for fixture_name, fixture_path in selected_fixtures.items():
        if not fixture_path.exists():
            print(f"ERROR: fixture not found: {fixture_path}")
            sys.exit(1)

        result = run_fixture(fixture_name, fixture_path, runs)
        fixture_results[fixture_name] = result
        print(
            f"  Summary: {result['passed']}/{result['runs']} passed "
            f"(p={result['per_run_probability']:.4f})"
        )

    retry_policy, pass_criterion = determine_policy(fixture_results, runs)

    head_sha = get_head_sha()
    measured_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    output_data = {
        "measured_at": measured_at,
        "skill_version_commit": head_sha,
        "smoke_test_only": smoke_test_only,
        "fixtures": fixture_results,
        "retry_policy": retry_policy,
        "pass_criterion_recommendation": pass_criterion,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output_data, indent=2) + "\n")
    print(f"\nWrote {OUTPUT_PATH}")
    print(f"retry_policy: {retry_policy}")
    print(f"pass_criterion_recommendation: {pass_criterion}")

    if not smoke_test_only and pass_criterion == "escalate":
        print("\nWARNING: pass_criterion_recommendation == 'escalate' — halt and route to user before Task 11.")
        sys.exit(2)


if __name__ == "__main__":
    main()
