# Plan: apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry

## Overview

Land seven mechanical skill-design improvements (R1–R7) across canonical `skills/` files plus parallel follow-on backlog edits. Decomposition is **file-grouped**: each canonical SKILL.md or reference file is one task that bundles all in-scope edits for that file (TOC, when_to_use, OQ3 soften, U2 trim, frontmatter symmetry, slugify trim) — Tasks 2/3/4/11 dispatch in parallel since they touch disjoint files, while Tasks 5–10 serialize behind Task 1's `u2-decisions.md` analysis (a deliberate bottleneck — the audit-trail rule must be applied consistently across the corpus). U2 (named-consumer trim across 12 Constraints tables) is gated by analysis-only Task 1 that produces `u2-decisions.md`; downstream U2 trim tasks read the decisions and apply them. Backlog edits (R5 amend 182, R7 new follow-on, ticket-178 self-amendments) are bundled into one docs-only task. A final verification task runs all spec acceptance criteria via an assertion-bearing shell script.

## Tasks

### Task 1: Produce u2-decisions.md (analysis-only) [COMPLETED]

- **Files**: `lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md`
- **What**: Read all 12 Constraints "Thought/Reality" tables in the U2 corpus and emit a per-row KEEP/DROP decision applying the spec's canonical named-consumer rule (specific identifier — function name, file path, schema key, or named test/validator/contract). No source-file edits in this task; this artifact gates Tasks 5–10.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Spec R4 U2 (lines 90–96) — canonical named-consumer rule and wholesale-removal guard.
  - Corpus (12 files, line-anchor for Constraints H2):
    - `skills/discovery/references/clarify.md:60`
    - `skills/discovery/references/auto-scan.md:81`
    - `skills/discovery/references/decompose.md` (locate by `^## Constraints$`)
    - `skills/lifecycle/references/clarify.md:119`
    - `skills/lifecycle/references/clarify-critic.md:159`
    - `skills/lifecycle/references/specify.md:181`
    - `skills/lifecycle/references/plan.md:303`
    - `skills/lifecycle/references/implement.md:294`
    - `skills/lifecycle/references/review.md:212`
    - `skills/lifecycle/references/orchestrator-review.md:178`
    - `skills/lifecycle/references/complete.md:98`
    - `skills/refine/references/clarify-critic.md:207`
  - **`u2-decisions.md` schema** (pinned — fresh-subagent contract for Tasks 5–10 and Task 12):
    - **Document YAML frontmatter** (between `---` fences at file top): `wholesale_remove: <inline list of repo-relative file paths whose tables are wholesale-removed; empty list `[]` if none>`. This is the only location for the wholesale-remove signal.
    - **Section header convention**: `## <repo-relative-path>` exactly (no line-number suffix, no basename, no slug). Example: `## skills/lifecycle/references/plan.md`.
    - **Per-row entry format** (one entry per Reality-column row in the file's Constraints table):
      - KEEP form: `- [<repo-relative-path>:<line>] | KEEP | <named identifier cited verbatim from Reality column>`
      - DROP form: `- [<repo-relative-path>:<line>] | DROP | reality_text=<verbatim Reality-column text, double-quoted, with internal `"` escaped as `\"`>`
    - The DROP form's `reality_text=` field is **required** so Task 12's grep-F drift check can substring-match the original Reality text against the post-edit corpus file.
    - **Completion sentinel**: append a final line `<!-- u2-decisions:complete -->` after the last per-file section. Task 12 and Tasks 5–10 must verify this sentinel exists before parsing; absence means Task 1 is mid-write and downstream consumers must wait.
  - **Sizing**: this task targets the upper bound (~30–40 min) because it inspects 12 tables in sequence. It is intentionally bundled rather than split per-corpus-file because a single artifact applies the named-consumer rule consistently across files (Spec R4 line 92 requires a single `u2-decisions.md` audit trail) and concurrent writes to the same artifact are unsafe. The `complex` complexity tier signals the elevated turn budget. If the implementer's executor cannot complete in one turn, write `u2-decisions.md` incrementally per-file (each file a new H2 section appended), **omit the `<!-- u2-decisions:complete -->` sentinel until the final file is processed**, and resume on next dispatch by appending remaining sections then writing the sentinel. The artifact tolerates partial writes; downstream consumers gate on the sentinel.
  - **Commit disposition**: `u2-decisions.md` is committed in the same task that produces it (per `lifecycle.config.md` `commit-artifacts: true`). Task 1's commit lands the artifact alongside Task 1's other outputs.
- **Verification**:
  - `test -f lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md` — pass if exit 0.
  - `grep -q '<!-- u2-decisions:complete -->' lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md` — pass if exit 0 (completion sentinel present).
  - `grep -cE '^- \[.+:[0-9]+\] \| (KEEP|DROP) \|' lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md` — pass if count ≥ 12.
  - `python3 -c "import re; t=open('lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md').read(); drops=[l for l in t.splitlines() if re.match(r'^- \[.+:[0-9]+\] \| DROP \|', l)]; bad=[l for l in drops if 'reality_text=' not in l]; print('FAIL: DROP rows missing reality_text:', bad) if bad else print('OK')"` — pass if output is `OK` (every DROP row carries a `reality_text=` field).
  - PR review verifies per-row exhaustiveness against the actual table contents.
- **Status**: [x] completed

### Task 2: Edit `skills/lifecycle/SKILL.md` (R1 TOC + R2 when_to_use + R4 U4 slugify trim)

- **Files**: `skills/lifecycle/SKILL.md`
- **What**: Add `## Contents` H2 TOC immediately after frontmatter. Add `when_to_use` frontmatter field with sibling-disambiguator and trigger phrases (`refine` differentiator). Trim `description` to <1024 chars after disambiguator extraction. Replace the slugify HOW prose (currently the paragraph starting with the canonical-rule explanation around `## Step 1: Identify the Feature`, locate by content `grep -n "underscores become hyphens, not stripped" skills/lifecycle/SKILL.md`) with a single-sentence reference: `Use the canonical \`slugify()\` from \`cortex_command.common\`.`
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - TOC template: `skills/discovery/references/research.md:5–15` (numbered list, `[text](#anchor)` links, anchors lowercase-hyphenated, H2 entries only).
  - when_to_use content per Spec R2 (line 32 — lifecycle's disambiguator: `Different from /cortex-core:refine — refine stops at spec.md; lifecycle continues to plan/implement/review.`); add trigger phrases: `start a feature`, `build this properly`.
  - Description char-cap: post-edit `description` ≤ 1024 chars.
  - Slugify replacement target: the example-based explanation in `## Step 1`. Canonical function lives at `cortex_command/common.py:110–117`.
  - Edge Case anchor collisions: `skills/lifecycle/SKILL.md` does not have known duplicate H2s (verify when generating TOC); use `#step-1-identify-the-feature` style anchors.
- **Verification**:
  - `head -25 skills/lifecycle/SKILL.md | grep -c '^## Contents$'` = 1.
  - `awk '/^---$/{c++; if(c==2) exit} c==1 && /^when_to_use:/' skills/lifecycle/SKILL.md | wc -l` = 1.
  - `grep -c "Different from /cortex-core:refine" skills/lifecycle/SKILL.md` ≥ 1.
  - `grep -c "cortex_command.common" skills/lifecycle/SKILL.md` ≥ 1.
  - `grep -c "underscores become hyphens, not stripped" skills/lifecycle/SKILL.md` = 0.
  - `python3 -c "import yaml; doc = open('skills/lifecycle/SKILL.md').read().split('---',2); fm = yaml.safe_load(doc[1]); d = fm.get('description', ''); print('FAIL: description >1024 chars (%d)' % len(d)) if len(d) > 1024 else print('OK')"` — pass if output is `OK`. (Uses `yaml.safe_load` so multi-line block scalars and folded styles measure correctly.)
- **Status**: [x] completed

### Task 3: Edit `skills/critical-review/SKILL.md` (R1 TOC + R2 when_to_use + R4 U1 trim + R6 frontmatter symmetry)

- **Files**: `skills/critical-review/SKILL.md`
- **What**: Add `## Contents` H2 TOC. Add `when_to_use` frontmatter (relocate `/devils-advocate` disambiguator, add trigger phrases). Add the four canonical frontmatter fields (`argument-hint`, `inputs`, `outputs`, `preconditions`) per R6. Replace the `~30-line Apply/Dismiss/Ask body` (locate by content `grep -n "^\*\*Apply\*\*" skills/critical-review/SKILL.md`) with the 5-line WHAT/WHY directive from Spec R4 U1.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - TOC template: same as Task 2.
  - when_to_use trigger phrases per Spec R2: `poke holes in the plan`, `stress test the spec`, `is this actually a good idea`, `review before I commit`. Disambiguator: existing `/devils-advocate` clause relocated to `when_to_use`.
  - R6 frontmatter values verbatim from Spec R6 (lines 159–169) — `argument-hint: "[<artifact-path>]"` (quoted to avoid Issue #22161 TUI hang); `inputs`/`outputs`/`preconditions` per spec text. Do NOT add `precondition_checks`.
  - U1 directive verbatim from Spec lines 82–86 (5-line block starting `**Apply** when the fix is unambiguous`).
  - Verbose Apply/Dismiss/Ask worked-examples block to remove: locate by content sentinel `Compliant: R10 strengthened` (per Spec acceptance criterion).
  - Description char-cap: post-edit `description` ≤ 1024 chars.
- **Verification**:
  - `head -30 skills/critical-review/SKILL.md | grep -c '^## Contents$'` = 1.
  - `awk '/^---$/{c++; if(c==2) exit} c==1' skills/critical-review/SKILL.md | grep -cE '^(argument-hint|inputs|outputs|preconditions|when_to_use):'` = 5.
  - `awk '/^---$/{c++; if(c==2) exit} c==1' skills/critical-review/SKILL.md | grep -c '^precondition_checks:'` = 0.
  - `grep -c "Default ambiguous" skills/critical-review/SKILL.md` ≥ 1.
  - `grep -c "Compliant: R10 strengthened" skills/critical-review/SKILL.md` = 0.
  - `python3 -c "import re; m = re.search(r'^description:\s*(.+?)\n(?:[a-z_]+:|---)', open('skills/critical-review/SKILL.md').read(), re.M|re.S); print(len(m.group(1).strip().strip('\"')) if m else 'no match')"` ≤ 1024.
- **Status**: [x] completed

### Task 4: Edit `skills/refine/SKILL.md` and `skills/discovery/SKILL.md` (R2 when_to_use)

- **Files**: `skills/refine/SKILL.md`, `skills/discovery/SKILL.md`
- **What**: Add `when_to_use` frontmatter to both files. Move sibling-disambiguator content from `description` to `when_to_use`. Trim `description` to <1024 chars.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - refine when_to_use per Spec R2: trigger phrases `spec this out`, `tighten the requirements`, `lock in the spec`. Disambiguator: `Different from /cortex-core:lifecycle — refine produces spec only; lifecycle wraps refine and continues to plan/implement.`
  - discovery when_to_use per Spec R2: relocate existing `Different from /cortex-core:research` clause from `description` to `when_to_use` (clause already present in description today).
  - Description char-cap: ≤ 1024 chars on both files.
- **Verification**:
  - `awk '/^---$/{c++; if(c==2) exit} c==1 && /^when_to_use:/' skills/refine/SKILL.md skills/discovery/SKILL.md | wc -l` = 2.
  - `grep -c "Different from /cortex-core:lifecycle" skills/refine/SKILL.md` ≥ 1.
  - `grep -c "Different from /cortex-core:research" skills/discovery/SKILL.md` ≥ 1.
  - `python3 -c "import yaml; bad = [(f, len(yaml.safe_load(open(f).read().split('---',2)[1]).get('description',''))) for f in ['skills/refine/SKILL.md','skills/discovery/SKILL.md'] if len(yaml.safe_load(open(f).read().split('---',2)[1]).get('description','')) > 1024]; print('FAIL', bad) if bad else print('OK')"` — pass if output is `OK`.
- **Status**: [x] completed

### Task 5: Edit `skills/lifecycle/references/plan.md` (R1 TOC + R4 U2 trim)

- **Files**: `skills/lifecycle/references/plan.md`
- **What**: Add `## Contents` H2 TOC immediately after frontmatter. Apply U2 trim to the Constraints table (locate by `## Constraints` H2). Resolve duplicate H2 headings — file has duplicate `## Overview` (lines 72 and 161-equivalent) and `## Tasks` (lines 77 and 164-equivalent); use disambiguated anchors `#overview-1`, `#overview-2`, `#tasks-1`, `#tasks-2` per Spec Edge Case (line 188).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - TOC template per Task 2.
  - U2 decisions for this file are recorded in `lifecycle/.../u2-decisions.md` under the `skills/lifecycle/references/plan.md` section. Apply DROP decisions; preserve KEEP rows.
  - Disambiguated anchor convention: GitHub-flavored markdown auto-suffixes duplicates with `-1`, `-2`. Verify rendered links resolve correctly.
- **Verification**:
  - `head -25 skills/lifecycle/references/plan.md | grep -c '^## Contents$'` = 1.
  - `python3 -c "import re; toc = open('skills/lifecycle/references/plan.md').read().split('## Contents',1)[1].split('\n## ',1)[0]; anchors = re.findall(r']\(#([^)]+)\)', toc); print('FAIL: duplicate anchors' if len(anchors) != len(set(anchors)) else 'OK')"` — output `OK` (TOC anchors are unique; duplicate H2 disambiguation applied).
  - U2 trim correctness — Interactive/session-dependent: per-row drift detection requires reading `u2-decisions.md` and asserting each DROP row's Reality-text is absent from the post-edit file; consolidated in Task 12's cross-corpus sweep.
- **Status**: [ ] pending

### Task 6: Edit `skills/lifecycle/references/implement.md` (R1 TOC + R4 U2 trim)

- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Add `## Contents` H2 TOC immediately after frontmatter. Apply U2 trim to the Constraints table per `u2-decisions.md` entries for this file.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - TOC template per Task 2.
  - Verify no duplicate H2 anchor collisions (file is 301 lines, smaller H2 surface than plan.md).
  - U2 decisions: read `u2-decisions.md` `## skills/lifecycle/references/implement.md` section.
- **Verification**:
  - `head -25 skills/lifecycle/references/implement.md | grep -c '^## Contents$'` = 1.
  - U2 trim correctness — Interactive/session-dependent: per-row drift detection consolidated in Task 12 (cross-corpus check against `u2-decisions.md`).
- **Status**: [ ] pending

### Task 7: Edit `skills/lifecycle/references/review.md` (R3 OQ3 soften + R4 U2 trim)

- **Files**: `skills/lifecycle/references/review.md`
- **What**: Soften the 4 MUST/CRITICAL imperatives at lines 64, 72, 78, 80 (locate by content; `grep -nE 'MUST|CRITICAL|REQUIRED' skills/lifecycle/references/review.md`) to declarative-behavioral phrasing per Spec R3 example (line 60). Apply U2 trim to the Constraints table at line 212 per `u2-decisions.md`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - R3 rewrite pattern: drop imperative verb, retain format-contract and schema prose. Example from Spec line 60: `"The Verdict section is a JSON object with exactly these fields: …"` (replacing `"CRITICAL: The Verdict section MUST contain a JSON object with exactly these fields"`).
  - Apply same declarative-behavioral pattern to lines 72, 78, 80.
  - File is not in R1 TOC scope (review.md < 300 lines), so line numbers for R3 targets remain stable (no TOC shift).
  - U2 decisions: read `u2-decisions.md` `## skills/lifecycle/references/review.md` section.
- **Verification**:
  - `python3 -c "import re; lines = open('skills/lifecycle/references/review.md').readlines(); soften_targets = [(64,'Verdict section'),(72,'verdict-JSON'),(78,'verdict-JSON'),(80,'verdict-JSON')]; bad = [(n, expected) for n, expected in soften_targets if any(re.search(r'\b(MUST|CRITICAL|REQUIRED)\b', l) for l in lines if expected.lower() in l.lower())]; print('FAIL imperatives near targets:', bad) if bad else print('OK')"` — pass if output is `OK`. (Content-anchored check: locates the soften targets by neighboring keyword "Verdict section"/"verdict-JSON" and asserts no `MUST|CRITICAL|REQUIRED` token appears on those lines, robust to line-number drift.)
  - U2 trim correctness — Interactive/session-dependent: per-row drift detection consolidated in Task 12.
- **Status**: [ ] pending

### Task 8: Edit `skills/refine/references/clarify-critic.md` (R3 OQ3 soften + R4 U2 trim)

- **Files**: `skills/refine/references/clarify-critic.md`
- **What**: Soften 3 MUST/REQUIRED imperatives at lines 26 (closed-allowlist warning template), 155 (REQUIRED schema invariant), 159 (cross-field invariant) to declarative-behavioral phrasing per Spec R3. Apply U2 trim to the Constraints table at line 207 per `u2-decisions.md`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - R3 rewrite pattern: same declarative-behavioral approach as Task 7. For line 159 specifically per Spec line 62: `"any post-feature event whose findings[] contains origin: alignment has parent_epic_loaded: true"` (descriptive form).
  - Line numbers stable (not in R1 TOC scope; U2 trim at line 207 is after the MUSTs at 26, 155, 159 — no upward shift).
  - U2 decisions: read `u2-decisions.md` `## skills/refine/references/clarify-critic.md` section.
- **Verification**:
  - `python3 -c "import re; lines = open('skills/refine/references/clarify-critic.md').readlines(); soften_targets = [(26,'closed-allowlist'),(155,'post-feature event'),(159,'parent_epic_loaded')]; bad = [(n, expected) for n, expected in soften_targets if any(re.search(r'\b(MUST|REQUIRED)\b', l) for l in lines if expected.lower() in l.lower())]; print('FAIL imperatives near targets:', bad) if bad else print('OK')"` — pass if output is `OK`. (Content-anchored check, robust to line-number drift from U2 trim at line 207.)
  - U2 trim correctness — Interactive/session-dependent: per-row drift detection consolidated in Task 12.
- **Status**: [ ] pending

### Task 9: Apply U2 trims to remaining lifecycle reference files

- **Files**: `skills/lifecycle/references/clarify.md`, `skills/lifecycle/references/clarify-critic.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/orchestrator-review.md`, `skills/lifecycle/references/complete.md`
- **What**: Apply U2 named-consumer trim to the Constraints table in each of these 5 files per `u2-decisions.md` entries. None of these files are in R1 TOC scope. None receive R3 edits.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - U2 decisions: read `u2-decisions.md` per-file sections. Apply DROP decisions; preserve KEEP rows. If a file is marked `wholesale-remove: true` in decisions and the spec wholesale-removal guard (Spec line 96) is satisfied (zero KEEP rows in `u2-decisions.md`), remove the entire `## Constraints` table from that file.
  - Constraints table line anchors: clarify.md:119, clarify-critic.md:159, specify.md:181, orchestrator-review.md:178, complete.md:98.
- **Verification**: Per-task DROP-row drift check — for each of the 5 files, every DROP entry under that file's section in `u2-decisions.md` must have its `reality_text=` value absent from the post-edit file. Run:
  ```bash
  python3 -c "
  import re, sys
  decisions = open('lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md').read()
  for f in ['skills/lifecycle/references/clarify.md','skills/lifecycle/references/clarify-critic.md','skills/lifecycle/references/specify.md','skills/lifecycle/references/orchestrator-review.md','skills/lifecycle/references/complete.md']:
      section = re.split(r'^## ', decisions, flags=re.M)
      block = next((s for s in section if s.startswith(f)), '')
      drops = re.findall(r'DROP \| reality_text=\"((?:[^\"\\\\]|\\\\.)*)\"', block)
      content = open(f).read()
      bad = [d for d in drops if d.encode().decode('unicode_escape') in content]
      if bad: print('FAIL drift in', f, ':', bad); sys.exit(1)
  print('OK')
  "
  ```
  Pass if output is `OK` and exit 0.
- **Status**: [ ] pending

### Task 10: Apply U2 trims to discovery reference files

- **Files**: `skills/discovery/references/clarify.md`, `skills/discovery/references/auto-scan.md`, `skills/discovery/references/decompose.md`
- **What**: Apply U2 named-consumer trim to the Constraints table in each of these 3 files per `u2-decisions.md` entries.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - U2 decisions: read `u2-decisions.md` per-file sections.
  - Constraints table line anchors: clarify.md:60, auto-scan.md:81, decompose.md (locate by `^## Constraints$`).
- **Verification**: Per-task DROP-row drift check (same pattern as Task 9, with discovery file paths substituted):
  ```bash
  python3 -c "
  import re, sys
  decisions = open('lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md').read()
  for f in ['skills/discovery/references/clarify.md','skills/discovery/references/auto-scan.md','skills/discovery/references/decompose.md']:
      section = re.split(r'^## ', decisions, flags=re.M)
      block = next((s for s in section if s.startswith(f)), '')
      drops = re.findall(r'DROP \| reality_text=\"((?:[^\"\\\\]|\\\\.)*)\"', block)
      content = open(f).read()
      bad = [d for d in drops if d.encode().decode('unicode_escape') in content]
      if bad: print('FAIL drift in', f, ':', bad); sys.exit(1)
  print('OK')
  "
  ```
  Pass if output is `OK` and exit 0.
- **Status**: [ ] pending

### Task 11: Backlog edits (R5 amend 182 + R7 new follow-on + ticket-178 self-amendments)

- **Files**: `backlog/182-vertical-planning-adoption-outline-and-phases-and-p9-s7-gates-and-parser-test.md`, `backlog/178-apply-skill-creator-lens-improvements-tocs-descriptions-oq3-frontmatter.md`, `backlog/<NEW-NNN>-clarify-critic-schema-validator-and-warning-template-runtime-validator.md` (new file), `backlog/index.md`, `backlog/index.json` (regenerated by `just backlog-index`)
- **What**:
  - **R5**: amend `backlog/182-*.md` body to add a `Parser hardening at metrics.py:221` sub-bullet to its scope and add `metrics-parser` to its `tags` frontmatter. No status change.
  - **R7**: create new backlog item describing the clarify-critic schema validator + warning-template runtime validator. Reference `clarify-critic.md` lines 26, 155, 159 in the body. Set `parent: 178` (or `parent: 172` epic) in frontmatter. Use `cortex-resolve-backlog-item` slugify → `cortex-add-item` if a CLI exists, otherwise hand-author and run `just backlog-index` to refresh `backlog/index.md` and `backlog/index.json`.
  - **Ticket-178 self-amendments** (per Spec R3 lines 64–67 and Changes to Existing Behavior):
    - Drop the Verification line containing `MUSTs retained with parser-cite at metrics.py:221 documented` (currently around line 94).
    - Drop the Verification line containing `documented evidence trail` (currently around line 95).
    - Add replacement Verification line: `All 7 MUSTs in review.md and clarify-critic.md softened to positive-routing per OQ3 default.`
    - Add a body acknowledgment that R2's `when_to_use` adoption is a structural mechanism change from §2's in-description prescription (one sentence near §2).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Backlog item add/edit CLI: `cortex-update-item <slug-or-uuid> <field>=<value>` (mirrored in `plugins/cortex-core/bin/`).
  - Backlog index regen: `just backlog-index` (regenerates `backlog/index.md` and `backlog/index.json`).
  - R7 frontmatter template — copy structure from a recent backlog item (e.g., `backlog/176-*.md`); use `type: chore`, `status: refined` (or `proposed` if not refining now), `priority: medium`, `complexity: simple`, `criticality: medium`, `tags: [oq3, schema-validator, clarify-critic, follow-on]`.
- **Verification**:
  - **Step 1 (procedural — runs first)**: `just backlog-index` exits 0 (regenerates `backlog/index.md` and `backlog/index.json` from current backlog files).
  - `grep -c "metrics.py" backlog/182-*.md` ≥ 1.
  - `grep -lE 'clarify-critic.md.*155.*159|schema validator|schema enforcement' backlog/[0-9]*-*.md | wc -l` ≥ 1 (R7 backlog item exists; broadened title heuristic to tolerate "schema enforcement" / "schema validator" phrasing).
  - `grep -c "MUSTs retained with parser-cite" backlog/178-*.md` = 0.
  - `grep -c "documented evidence trail" backlog/178-*.md` = 0.
  - `grep -c "softened to positive-routing per OQ3" backlog/178-*.md` ≥ 1.
  - `cat backlog/index.json | python3 -c "import json,sys; d=json.load(sys.stdin); assert any('clarify-critic' in i.get('title','').lower() and ('validator' in i.get('title','').lower() or 'schema' in i.get('title','').lower()) for i in d.get('items',[]))"` exits 0 (R7 indexed; broadened to match "schema" or "validator").
- **Status**: [ ] pending

### Task 12: Cross-corpus U2 verification + spec acceptance sweep

- **Files**: `lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/verify.sh` (script created and committed by this task)
- **What**: Author `verify.sh` — an assertion-bearing shell script that runs every spec acceptance check and the cross-corpus U2 drift check. Each assertion uses `[ <condition> ] || { echo "FAIL: <message>"; exit 1; }` so the script exits non-zero on any failure. Run the script after authoring; pass = exit 0.
- **Depends on**: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
- **Complexity**: simple
- **Context**: Spec acceptance criteria from `lifecycle/.../spec.md` (R1 line 21; R2 lines 41–43; R3 lines 69–75; R4 U1 line 120, U2 line 121, U4 line 122; R5 lines 133–134; R6 lines 172–173; R7 lines 147–149). The script body below is the canonical content for `verify.sh`:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  fail() { echo "FAIL: $*"; exit 1; }
  ok() { echo "OK: $*"; }

  # R1 TOC presence
  for f in skills/lifecycle/SKILL.md skills/lifecycle/references/plan.md skills/lifecycle/references/implement.md skills/critical-review/SKILL.md; do
    head -25 "$f" | grep -q '^## Contents$' || fail "R1 TOC missing in $f"
  done
  ok "R1 TOCs"

  # R2 when_to_use frontmatter on 4 SKILL.md files
  count=$(awk '/^---$/{c++; if(c==2) exit} c==1 && /^when_to_use:/' skills/lifecycle/SKILL.md skills/refine/SKILL.md skills/critical-review/SKILL.md skills/discovery/SKILL.md | wc -l)
  [ "$count" -eq 4 ] || fail "R2 when_to_use count=$count, expected 4"
  ok "R2 when_to_use"

  # R3 OQ3 soften — content-anchored (review.md)
  python3 -c "
  import re, sys
  lines = open('skills/lifecycle/references/review.md').readlines()
  bad = [i for i,l in enumerate(lines,1) if re.search(r'\b(MUST|CRITICAL|REQUIRED)\b', l) and any(k in l.lower() for k in ['verdict section','verdict-json'])]
  sys.exit(1 if bad else 0)
  " || fail "R3 soften incomplete in review.md"
  ok "R3 review.md soften"

  # R3 OQ3 soften — content-anchored (clarify-critic.md)
  python3 -c "
  import re, sys
  lines = open('skills/refine/references/clarify-critic.md').readlines()
  bad = [i for i,l in enumerate(lines,1) if re.search(r'\b(MUST|REQUIRED)\b', l) and any(k in l.lower() for k in ['closed-allowlist','post-feature event','parent_epic_loaded'])]
  sys.exit(1 if bad else 0)
  " || fail "R3 soften incomplete in clarify-critic.md"
  ok "R3 clarify-critic.md soften"

  # R4 U1 critical-review trim
  grep -q "Default ambiguous" skills/critical-review/SKILL.md || fail "R4 U1 directive missing"
  ! grep -q "Compliant: R10 strengthened" skills/critical-review/SKILL.md || fail "R4 U1 verbose block remains"
  ok "R4 U1"

  # R4 U2 cross-corpus drift check
  python3 -c "
  import re, sys
  decisions = open('lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/u2-decisions.md').read()
  if '<!-- u2-decisions:complete -->' not in decisions:
      print('FAIL: u2-decisions.md missing completion sentinel'); sys.exit(1)
  corpus = ['skills/discovery/references/clarify.md','skills/discovery/references/auto-scan.md','skills/discovery/references/decompose.md','skills/lifecycle/references/clarify.md','skills/lifecycle/references/clarify-critic.md','skills/lifecycle/references/specify.md','skills/lifecycle/references/plan.md','skills/lifecycle/references/implement.md','skills/lifecycle/references/review.md','skills/lifecycle/references/orchestrator-review.md','skills/lifecycle/references/complete.md','skills/refine/references/clarify-critic.md']
  sections = re.split(r'^## ', decisions, flags=re.M)
  for f in corpus:
      block = next((s for s in sections if s.startswith(f)), '')
      drops = re.findall(r'DROP \| reality_text=\"((?:[^\"\\\\]|\\\\.)*)\"', block)
      content = open(f).read()
      bad = [d for d in drops if d.encode().decode('unicode_escape') in content]
      if bad: print('FAIL drift in', f, ':', len(bad), 'rows'); sys.exit(1)
  " || fail "R4 U2 drift check failed"
  ok "R4 U2 drift"

  # R4 U4 slugify trim
  grep -q "cortex_command.common" skills/lifecycle/SKILL.md || fail "R4 U4 reference missing"
  ! grep -q "underscores become hyphens, not stripped" skills/lifecycle/SKILL.md || fail "R4 U4 verbose prose remains"
  ok "R4 U4"

  # R5 backlog/182 amendment
  grep -q "metrics.py" backlog/182-*.md || fail "R5 metrics.py reference missing in 182"
  ok "R5"

  # R6 critical-review frontmatter symmetry
  count=$(awk '/^---$/{c++; if(c==2) exit} c==1' skills/critical-review/SKILL.md | grep -cE '^(argument-hint|inputs|outputs|preconditions):')
  [ "$count" -eq 4 ] || fail "R6 frontmatter fields count=$count, expected 4"
  ! awk '/^---$/{c++; if(c==2) exit} c==1' skills/critical-review/SKILL.md | grep -q '^precondition_checks:' || fail "R6 precondition_checks should not be present"
  ok "R6"

  # R7 new backlog item
  python3 -c "
  import json, sys
  d = json.load(open('backlog/index.json'))
  matches = [i for i in d.get('items', []) if 'clarify-critic' in i.get('title','').lower() and ('validator' in i.get('title','').lower() or 'schema' in i.get('title','').lower())]
  sys.exit(0 if matches else 1)
  " || fail "R7 new backlog item not in index"
  ok "R7"

  # Ticket-178 self-amendments
  ! grep -q "MUSTs retained with parser-cite" backlog/178-*.md || fail "178 line 94 not dropped"
  ! grep -q "documented evidence trail" backlog/178-*.md || fail "178 line 95 not dropped"
  grep -q "softened to positive-routing per OQ3" backlog/178-*.md || fail "178 replacement line missing"
  ok "178 self-amendments"

  echo "ALL PASS"
  ```
- **Verification**: `chmod +x lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/verify.sh && lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry/verify.sh` — pass if exit 0 and final output line is `ALL PASS`.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification runs in three layers:

1. **Per-task Verification**: each task's Verification field is a deterministic grep/awk/python check tied to spec acceptance criteria. Implementer runs these after the task's edits and before commit.
2. **Pre-commit dual-source drift hook**: automatic on every commit. Validates `plugins/cortex-core/skills/` mirrors are byte-identical to canonical `skills/`. Implementer must NOT edit mirrors directly. **Precondition check**: before Task 2 begins, verify `just setup-githooks` has been run (`test -f .git/hooks/pre-commit && grep -q cortex-check-parity .git/hooks/pre-commit`); if missing, run `just setup-githooks` first. Mirror paths under `plugins/cortex-core/skills/` are NOT listed in any task's `Files` field by design — they are auto-regenerated and committed by the hook on each canonical-source commit, treated as a derived artifact rather than a hand-maintained file. Reviewers comparing `git diff --name-only` against task `Files` should expect mirror paths in the diff.
3. **Task 12 verification script**: an assertion-bearing shell script (`lifecycle/.../verify.sh`) that runs every spec acceptance check and the cross-corpus U2 drift check. Each assertion exits non-zero on failure. Pass = exit 0 and final line `ALL PASS`.

Manual PR review verifies: (a) U2 per-row decisions in `u2-decisions.md` are exhaustive (one entry per row across all 12 tables); (b) duplicate-H2 disambiguation in `plan.md`'s TOC renders correctly in GitHub markdown; (c) post-edit `description` fields fit the 1024-char cap (`yaml.safe_load`-based check is robust to multi-line YAML, but PR reviewer should still spot-check rendering); (d) softened OQ3 prose preserves format-contract semantics (declarative-behavioral, not just deletions); (e) borderline U2 rows (per Spec Edge Case 192) defaulted to DROP under conservative-default rule are visually distinguishable in `u2-decisions.md` from clear-drops by an optional `# borderline` comment on the entry line.

## Veto Surface

- **Task 1 sizing**: u2-decisions.md is a complex analysis task — reading 12 tables and writing per-row decisions may take 30+ minutes and produce a long artifact. The alternative — splitting into 12 per-file analysis sub-tasks dispatching in parallel — was offered to the operator and declined; keeping the single-task form preserves Spec R4 line 92's audit-trail-as-single-file expectation and the named-consumer rule's consistency. The completion-sentinel + partial-write tolerance handles turn-budget overflow gracefully.
- **File-grouped decomposition over requirement-grouped**: Tasks 2 and 3 each bundle 3–4 requirements into one file-touch (lifecycle/SKILL.md gets R1+R2+R4 U4; critical-review/SKILL.md gets R1+R2+R4 U1+R6). This trades per-requirement rollback granularity for one commit per file. **Acknowledged risk** (per critical-review B-class residue): partial-completion failure forces rollback of correctly-applied co-edits in the same task; e.g., Task 2's U4 grep-locate failure due to upstream sentinel drift would discard the correctly-applied TOC and when_to_use edits. Mitigations: (a) U4 sentinel content is stable in current `skills/lifecycle/SKILL.md`; (b) implementer should apply the riskiest edit (sentinel-locating U4) FIRST within each bundled task to fail fast.
- **Bundling Task 11**: R5, R7, and ticket-178 self-amendments are three logically distinct backlog edits but all are docs-only and small. Operator chose bundled (one commit). **Acknowledged risk**: failure of any one (e.g., R7 slugify collision) rolls back R5's metrics.py amendment and 178's verification-line edits. Mitigation: implementer should apply edits in this order — 178-amendments (lowest risk) → R5 (low risk) → R7 (highest risk, new-file creation), so a late-task failure preserves the safer earlier edits in the working tree even if the commit rolls back.
- **U2 numeric floor absent**: Spec R4 line 94 explicitly removes the `~50-row` count target — the canonical rule is the authority. Task 1's verification only checks `≥ 12` decisions (one per file) and `reality_text=` presence on every DROP row. PR review remains the per-row-exhaustiveness check.
- **Critical-review residue surfaces in morning report**: 9 B-class concerns from this critical-review pass landed at `lifecycle/.../critical-review-residue.json`; bundling-rollback and PR-review-as-exhaustiveness-gate concerns are tracked there for post-merge audit.
- **Cross-ticket sequencing risk** (per Spec Edge Cases line 194): R3 soften lands without a co-landing gate on R5/R7 mitigations. The 14-day morning-report flag and 90-day acceptance window are spec-level rollback conditions, not plan-level work.

## Scope Boundaries

Per Spec Non-Requirements (lines 175–184):

- **OUT**: Parser hardening implementation at `cortex_command/pipeline/metrics.py:221` (deferred to backlog/182's own implementation).
- **OUT**: Schema validator + warning-template runtime validator implementation (deferred to R7's new backlog item).
- **OUT**: 100-line TOC threshold (held at 300 per OQ-E).
- **OUT**: Restructuring into 5 separate per-class tickets (Alt B rejected).
- **OUT**: Co-landing gate between this ticket and R5/R7 follow-ons.
- **OUT**: Plain-bullet TOC variant (markdown-anchor-link variant adopted).
- **OUT**: Output-style or `--system-prompt` adoption (separate epic).
- **OUT**: Restoring `precondition_checks` on discovery/refine (only critical-review gets symmetry edits).
