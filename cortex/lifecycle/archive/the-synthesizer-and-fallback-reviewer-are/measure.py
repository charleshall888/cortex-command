"""Turn-count measurement for #399 (critical-review dispatched agents).

Answers: do the synthesizer and total-failure fallback reviewer actually run
long enough for a ~40-turn cap to bind?

Method. Subagent transcripts are NOT in ~/.claude/projects any more (zero
`isSidechain: true` records repo-wide -- the layout changed since the corpus
that produced the `turns^1.55` law). What survives is the orchestrator's
Task/Agent dispatch record, whose toolUseResult carries an `outputFile` path
pointing at the subagent's own JSONL under /private/tmp. Those files are
session-scoped and get cleaned, so only a recent subset survives.

So: classify dispatches by prompt signature, follow `outputFile`, and count
distinct assistant `message.id` values (dedup by message.id per the standing
rule -- raw JSONL line counts overcount by 2.7-30x).

Caveat: the surviving-file sample skews recent and is small (n=11 for the
synthesizer). Reported alongside the result rather than smoothed over.
"""

import collections
import glob
import json
import os

SIGS = {
    "synthesizer": "You are synthesizing findings from multiple independent",
    "fallback": "Derive 3-4 distinct challenge angles",
    "reviewer": "You are conducting an adversarial review",
    "clarify_critic": "You are challenging a confidence assessment",
}


def dispatches_by_role():
    """Map role -> set of subagent outputFile paths, from orchestrator records."""
    found = collections.defaultdict(set)
    for path in glob.glob("/Users/charliehall/.claude/projects/*/*.jsonl"):
        for line in open(path, errors="ignore"):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            result = rec.get("toolUseResult")
            if not isinstance(result, dict) or not result.get("outputFile"):
                continue
            prompt = result.get("prompt") or ""
            for role, sig in SIGS.items():
                if sig in prompt:
                    found[role].add(result["outputFile"])
    return found


def turns(output_file):
    """Distinct assistant message ids == billed turns for one subagent run."""
    ids = set()
    for line in open(output_file, errors="ignore"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") == "assistant":
            mid = (rec.get("message") or {}).get("id")
            if mid:
                ids.add(mid)
    return len(ids)


def main():
    found = dispatches_by_role()
    for role in ("synthesizer", "fallback", "reviewer", "clarify_critic"):
        files = found.get(role, set())
        counts = sorted(t for f in files if os.path.exists(f) and (t := turns(f)))
        if not counts:
            print(f"{role:16s} dispatches={len(files):4d}  no surviving transcripts")
            continue
        n = len(counts)
        print(
            f"{role:16s} dispatches={len(files):4d}  n={n:3d}  "
            f"median={counts[n // 2]:3d}  p90={counts[int(n * 0.9)]:3d}  "
            f"max={counts[-1]:3d}  >40={sum(1 for t in counts if t > 40)}"
        )
        print(f"{'':16s} all={counts}")


if __name__ == "__main__":
    main()
