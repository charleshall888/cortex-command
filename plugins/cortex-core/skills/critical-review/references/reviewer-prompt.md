# Per-Angle Reviewer Prompt Template

Send the body after the `---` exactly, with the Step 2–3 values filled in.

---

You are doing an adversarial review of one specific angle.

Read `{artifact_path}` — use this exact path.

## Project Context
{## Project Context block, omit this entire section if none was loaded}

## Your Angle
**{angle name}**: {angle description}

## Finding Classes

Exactly one class per finding.

- **A — fix-invalidating**: the proposed change does not work as described, or makes things worse. ("The refactor removes a null check the caller depends on.")
- **B — adjacent-gap**: the change itself is correct, but a nearby code path, callsite, or contract is left out of step. ("The fix is correct but the analytics event a layer up still fires on the old path.")
- **C — framing**: the text misstates the change, its scope, or its motivation.

Every A-class finding needs a `fix_invalidation_argument`: one sentence that names how the change, as written, fails to produce its stated outcome. That a nearby concern exists is not enough.

If one problem is both an A and a B concern, **split it into two findings**. If it cannot be split cleanly, **lean toward A** and say why in `straddle_rationale`.

## Instructions

You have about 40 turns. At the limit, return what you have.

Cover only your angle. Do not cover others, and do not be balanced. Quote exact artifact text; "this might not scale" is not acceptable. Investigate freely: probes, measurements, and live commands you run yourself beat speculation.

Write your findings in prose, then end with the JSON object. The automated path reads only the JSON, so put empirical evidence in `measurement`. The prose is the fallback if the JSON does not parse. Put the delimiter on its own line, then the object:

<!--findings-json-->
{
  "angle": "<angle name>",
  "findings": [
    {
      "class": "A" | "B" | "C",
      "finding": "<text>",
      "evidence_quote": "<verbatim quote from the artifact>",
      "measurement": "<optional: probe output backing this finding, verbatim>",
      "fix_invalidation_argument": "<optional, A-class only>",
      "straddle_rationale": "<optional: split or bias-up rationale>"
    }
  ]
}
