# Research: Untrack the derived backlog index (treat index.json/index.md as a regenerated local cache)

**Clarified intent:** Stop version-controlling the derived backlog index (`cortex/backlog/index.json` + `index.md`); regenerate it as a local cache so parallel sessions stop conflicting on the shared aggregate, while every consumer keeps working when the file is absent.

**Tier:** complex · **Criticality:** high

---

## Codebase Analysis

**Generator — `cortex_command/backlog/generate_index.py`**
- Console script `cortex-generate-backlog-index = "cortex_command.backlog.generate_index:main"` (pyproject.toml).
- `main()` (≈L321) resolves the backlog dir via `_resolve_user_project_root()` (repo-anchored, **not** CWD-relative) → writes `index.json` + `index.md` via `atomic_write` (≈L327-330).
- **Reusable callables exist** for in-process regeneration: `collect_items(backlog_dir, lifecycle_dir) -> (items, active_ids, archive_ids, all_items)` (≈L85), `generate_json(items)`, `generate_md(...)`. No CLI subprocess required.
- `atomic_write` (`common.py` ≈L768) = tempfile + `os.replace` → concurrent regeneration is corruption-safe; deterministic output ⇒ last-writer-wins is benign.

**Side-effect regeneration — `cortex_command/backlog/update_item.py:410-421`**
- Every `cortex-update-item` shells `python3 -m cortex_command.backlog.generate_index` (non-fatal on failure). Keeps the on-disk cache fresh on every mutation. No change required.

**Path resolution divergence (note for implement):** `ready.py` uses `BACKLOG_DIR = Path.cwd() / "cortex" / "backlog"` (CWD-relative) whereas the generator uses `_resolve_user_project_root()`. For ready.py's regenerate-on-miss, call `collect_items(BACKLOG_DIR, ...)` so it stays consistent with ready.py's own dir resolution.

**.gitignore** currently groups by category; line 33 = `cortex/backlog/*.events.jsonl`. Add anchored index lines adjacent to it.

---

## Web Research

Dominant convention: **do not commit generated/derived files** — gitignore + regenerate. The recognized exceptions (commit-it-anyway) are: (1) the diff is human-reviewed / gates correctness; (2) it locks for reproducibility and consumers can't regenerate identically (lock files for *apps*, not libs); (3) regeneration is unavailable at point of use (vendored/distribution); (4) the build is non-deterministic.

Distinguishing test: *commit a derived file only if its diff is decision-relevant OR regeneration is unavailable/non-deterministic.* The backlog index fails all four — deterministic, cheaply regenerable, not a lock, not reviewed-as-a-diff ⇒ **gitignore + regenerate is the industry-standard answer.**

The specific anti-pattern here ("committing an aggregate that many parallel writers regenerate") is the textbook merge-conflict generator (cf. kubernetes#27088). Mitigations, in preference order: gitignore+regenerate (eliminates the class) ≫ regenerate-in-CI/release-branch ≫ `.gitattributes merge=union` (only safe for append-only line lists; silent-wrong-merge risk; not honored by all PR UIs) ≫ custom merge driver (heavy) ≫ serialize through one owner. `merge=union`/merge-driver are only the right call if the file must *stay* tracked for one of the four exception reasons — which it must not. Pair regeneration with atomic write-then-rename + last-writer-wins (already satisfied).

---

## Requirements & Constraints

- **`project.md` Solution horizon** → blesses the durable fix: committing derived aggregate data is the root anti-pattern; untracking is the root fix, not a stop-gap. **Complexity / "simpler wins"** → blesses the minimal version.
- **Quality attributes:** *Graceful partial failure* (index regeneration is already non-fatal; index is optional for correctness — overnight has a file-scan fallback) and *Destructive ops preserve uncommitted state* (`git rm --cached` keeps the on-disk file; `git rm` of the stray is safe — it's empty junk).
- **`pipeline.md`:** index is an O(1) optimization with a documented fallback; not a required/committed input. Overnight reads working-tree state.
- **ADR gate (`cortex/adr/README.md` three-criteria):** hard-to-reverse? no (git-level reversible). surprising? no (gitignoring derived data is conventional). real trade-off? weak (pragmatic, no rejected-alternative tension). **Verdict: no new ADR — routine change.**
- **Process gates:** dual-source drift (skills edits → plugin mirror via `just build-plugin` + pre-commit hook); `cortex_command/` library edits (ready.py, generate_index.py) are **not** mirrored and **not** parity-gated; `cortex-backlog-ready`/`cortex-generate-backlog-index` already have parity wiring (no new console scripts).

---

## Prior Art (Related Backlog Items)

- **#135 — shared git index race (status: `wontfix`)** → **ORTHOGONAL.** This is the `.git/index` *staging-area* race: concurrent `/commit`s consume each other's staged files so a commit's subject mis-describes its content. It is **not** the backlog-index *file* conflict. Untracking the backlog index does **not** solve #135 (the root needs commit-locking / `GIT_INDEX_FILE` isolation / worktrees, which were wontfix'd). It does remove one file from the shared-staging contention surface, a marginal help only. **This must be stated explicitly at spec approval** — the user's "commits all editing the same file" symptom is the file-conflict variant this work targets, distinct from #135.
- **#038 — index regeneration in overnight pre-flight (status: `complete`)** → **REFINES.** #038 *added* the overnight pre-flight `cortex-generate-backlog-index` step (+ the git add/commit) this work modifies. We keep #038's regenerate-and-halt; we remove its now-pointless git add/commit.
- **#272 — surface deferred/parked state in index.md (`complete`)** → COMPLEMENT (content of the generated file; orthogonal to tracking).
- **#180 — index.md body trimming (`complete`)** → COMPLEMENT (size of generated file; if untracked, frontmatter-preservation becomes moot but harmless).
- **#152 — ready treats terminal blockers as external (`complete`)** → COMPLEMENT; regenerate-on-miss makes ready's view fresher relative to current `.md` files.
- No active/in-progress item overlaps. None blocks this work.

---

## Commit Sites & Gitignore

| Site | Path:Line | Type | Action |
|------|-----------|------|--------|
| Overnight pre-flight | `skills/overnight/references/new-session-flow.md:20` | explicit by-name `git add index.json index.md` + commit | **REMOVE add+commit; KEEP regenerate+halt (L19) and the conditional-commit logic disappears with the add** |
| Overnight SKILL summary | `skills/overnight/SKILL.md:64` | prose mirror of the above | **UPDATE wording: "regenerate, do not commit"** |
| Lifecycle complete | `skills/lifecycle/references/complete.md:256-262` | directory-scoped `git add cortex/backlog/` | **KEEP — respects .gitignore once index is ignored** |
| Lifecycle complete regen | `skills/lifecycle/references/complete.md:214-216` | regenerates index (script run, not an import) | **KEEP as-is — regenerates cache, dir-add won't commit it; NOT an L201 violation; out of scope** |
| Plugin mirrors | `plugins/cortex-overnight/...`, `plugins/cortex-core/...` | regenerated by drift hook | **Do not hand-edit — `just build-plugin`** |

**Overnight regenerate/commit logic (verbatim, new-session-flow.md:19-22):** (1) run `cortex-generate-backlog-index`, halt on non-zero; (2) `git add cortex/backlog/index.json cortex/backlog/index.md`; (3) commit "Regenerate backlog index" if changed, halt on failure; (4) skip if unchanged. **Fix = delete steps 2-3; keep step 1's regenerate-and-halt.**

**Stray nested `cortex/backlog/backlog/index.json|.md`:** empty junk (`[]` + bare header), origin commit `c8110de5` (umbrella relocation, May 12); generator no longer writes there (it's repo-anchored). **`git rm -r cortex/backlog/backlog/`** (delete — it's not a real index).

**Gitignore additions (anchored, near line 33):**
```
# Backlog derived index — regenerated on demand, not version-controlled
cortex/backlog/index.json
cortex/backlog/index.md
```
Anchored (not `**/index.*`) is sufficient once the stray is deleted; the canonical pair is the only index the generator produces.

**No broad git-add risk:** grep found no `git add -A|.|-u` / `commit -a` in skills/hooks/cortex_command.

---

## Consumer Inventory & ready.py Design

| Reader | Path:Line | Missing-index behavior | Change? |
|--------|-----------|------------------------|---------|
| `overnight/backlog.py` | ~1038 | GRACEFUL FALLBACK → `parse_backlog_dir` | none |
| `backlog/ready.py` | ~429 | **HARD-FAIL** `_emit_error("…not found")` | **FIX: regenerate-on-miss** |
| `backlog/build_epic_map.py` | ~206 | exit 1 (by design) | none — `dev` Step 3a regenerates first + has exit-1 fallback (`dev/SKILL.md:161-164`) |
| `hooks/scan_lifecycle.py` | ~222 | FAIL-OPEN `({}, [])` | none — acceptable degradation |
| `dashboard/data.py` | ~987 | scans `*.md` directly | none — no index dependency |
| `skills/backlog/SKILL.md` `list` | :70-72 | soft-fail "suggest reindex" (reads index.md) | **FIX (minor): auto-regenerate then read** |
| `skills/dev/SKILL.md` | 3a | self-regenerates + fallback | none |

**ready.py fix (recommended — Option A, regenerate-in-process, in-memory):**
```python
from cortex_command.backlog.generate_index import collect_items, generate_json
...
except FileNotFoundError:
    items, *_ = collect_items(BACKLOG_DIR)          # confirm tuple unpack vs single return at implement
    records = json.loads(generate_json(items))      # in-memory; no disk write
```
Chosen over Option B (fall back to `parse_backlog_dir`) because it reuses the same generator that produces the records ready.py already consumes (no `BacklogItem→dict` projection layer) and writes nothing to disk. Confirm `collect_items` return-shape and whether to pass `lifecycle_dir` at implement (records carry `lifecycle_slug`/`lifecycle_phase`).

**Staleness machinery (`ready.py:92-123`): KEEP.** It already returns silently when the index is absent, and remains useful when the index is present-but-stale (direct `.md` edit bypassing the tool). It is not dead code under regenerate-on-**miss** (we only regenerate when absent, not when stale-present). Behavior for present-but-stale is unchanged from today (warn to stderr, exit 0).

---

## Tests, Docs & Plugin Mirror

**Tests:** Most index tests build their own `index.json` in `tmp_path` fixtures (`test_backlog_ready_render.py` explicitly constructs it; `test_hooks_scan_lifecycle.py`, `test_select_overnight_batch.py`, `test_generate_backlog_index.py`) → **unaffected** by gitignoring the repo's committed copy. No test asserts the index is git-tracked (no `git ls-files` expectation found). **Add:** a test that `cortex-backlog-ready` on an absent index exits 0 with valid JSON (regenerate-on-miss contract). Re-run `test_backlog_ready_*` to confirm green.

**Docs to update (clarify "regenerated local cache, not committed"):** `docs/backlog.md` (~L92 list-subcommand note, ~L176 regeneration note), `docs/agentic-layer.md:250` (backlog-index description).

**Plugin mirror / drift:** canonical skills → mirrors via `just build-plugin` + `.githooks/pre-commit` (auto-runs build-plugin, **blocks commit on drift**). Mapping: `skills/overnight/*` → `plugins/cortex-overnight/skills/overnight/*`; `skills/backlog/*` → `plugins/cortex-core/skills/backlog/*`. `cortex_command/` library edits (ready.py) are **not** mirrored. **Implement discipline (per project convention): run `just build-plugin` and commit canonical + regenerated mirror together** — do not defer mirror regen to a final task. No new parity wiring needed.

---

## Adversarial Review

- **Fresh checkout / `/backlog pick|ready`:** the real hard-fail window — `cortex-backlog-ready` errors before any regeneration. **Mitigated** by the ready.py regenerate-on-miss fix (the one required code change). `/backlog list` (reads index.md) is the soft-fail twin → auto-regenerate fix.
- **Scheduled overnight on fresh checkout:** SAFE — `new-session-flow.md:19` regenerates the index before `select_overnight_batch`, and `overnight/backlog.py` falls back to file scan regardless.
- **CI:** SAFE — `.github/workflows/{validate,release,auto-release,pat-auth-scheme-probe}.yml` do not read the index.
- **Removed overnight commit:** no downstream step greps for the "Regenerate backlog index" commit; pre-flight `git status --porcelain -- cortex/lifecycle/ cortex/backlog/` (new-session-flow.md:123) correctly stops seeing the now-ignored index (a benefit — the dirty index no longer trips the block).
- **tracked→untracked transition / worktrees:** SAFE — pull removes it from the index, `.gitignore` prevents re-tracking, working copy retained; no active worktrees; transition is uniform across worktrees.
- **Stale-but-present:** acceptable, unchanged from today (warn + exit 0); overnight selection is fresh because overnight regenerates first.
- **No other hard-failing reader** found across cortex_command/, bin/, hooks/, report/metrics/notifications.

---

## Open Questions

1. **Preference decision (for spec approval): untrack BOTH `index.json` and `index.md`, or keep `index.md` committed for GitHub browsability?** Recommendation: **untrack both** — `index.md` browsability on GitHub is the only reason to keep it committed and it is exactly the file causing conflicts; its value (a glanceable table) is recoverable by regenerating or by `/backlog list`. Surfaced explicitly because it is the one genuine product trade-off.
2. **Scope confirmation:** include the minor `skills/backlog/SKILL.md` `list` auto-regenerate tidy (so `list` doesn't show "run reindex" on a fresh checkout)? Recommendation: yes — small, completes the "every consumer works when absent" goal.
3. **Out of scope, recorded:** #135 (`.git/index` staging-area race) is orthogonal and remains `wontfix`; this work does not address it. `complete.md:214`'s `python3 …generate_index.py` idiom is pre-existing, not an L201 violation, and out of scope. No new ADR. No change to build_epic_map/scan_lifecycle/dashboard/overnight-backlog (all degrade acceptably). ready.py staleness machinery retained.
