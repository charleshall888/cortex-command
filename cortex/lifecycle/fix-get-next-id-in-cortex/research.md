# Research: Update _get_next_id in cortex-create-backlog-item so allocation skips the 990-999 dashboard-seed fixture range and assigns max-real-id + 1 even when seeds are present in cortex/backlog/

## Codebase Analysis

### Files that will change

- `cortex_command/backlog/create_item.py` — function `_get_next_id` at lines 36-44. Current shape:

  ```python
  def _get_next_id(backlog_dir: Path) -> str:
      """Return the next available numeric ID (no zero-padding for IDs > 999)."""
      ids = [
          int(m.group(1))
          for p in backlog_dir.glob("[0-9]*-*.md")
          if (m := re.match(r"^(\d+)-", p.name))
      ]
      next_id = (max(ids) + 1) if ids else 1
      return f"{next_id:03d}" if next_id < 1000 else str(next_id)
  ```

  Module-private; sole caller is `create_item()` at line 98 (same file). No external importer.

- `tests/test_create_backlog_item.py` — does NOT exist. The acceptance criterion in #231 ("existing tests for `cortex-create-backlog-item` still pass") is partially vacuous: the only existing coverage is `cortex_command/backlog/tests/test_dispatch.py` (a parametrized entry-point/telemetry smoke test that does not exercise `_get_next_id`). A new test file is required to enforce the fix. Two viable locations:
  - **`tests/test_create_backlog_item.py`** (top-level, matches sibling backlog tests `tests/test_backlog_readiness.py`, `tests/test_backlog_ready_render.py`, `tests/test_resolve_backlog_item.py`).
  - `cortex_command/backlog/tests/test_create_item.py` (co-located with module, matches `test_dispatch.py`).

### Dashboard-seed fixture generator

- **Generator**: `cortex_command/dashboard/seed.py`.
  - `_BACKLOG_ITEMS` tuple at lines 596-602 hardcodes IDs 990, 991, 992, 993, 994 + slug/status/title.
  - `write_backlog_items(repo_root)` at lines 605-636 writes `cortex/backlog/{number}-{slug}.md` for each tuple.
  - `clean_all()` at lines 692-784 cleans via `range(990, 995)` + glob `f"{prefix}-seed-*.md"` (lines 770-776).
- **Entry point**: `pyproject.toml:31` — `cortex-dashboard-seed = "cortex_command.dashboard.seed:main"`.
- **Just recipes**: `justfile:116-121` — `dashboard-seed` and `dashboard-seed-clean`.
- **Range used today**: 990-994 (contiguous, exclusive of 995). The 990-999 reservation in #231 leaves headroom 995-999 for future seeds.

### Other readers of `cortex/backlog/[0-9]*-*.md` (Fix B blast radius)

| Module | Lines |
|---|---|
| `cortex_command/backlog/create_item.py` | 40 (target) |
| `cortex_command/backlog/generate_index.py` | 113, 127 |
| `cortex_command/backlog/update_item.py` | 129, 138, 143, 148, 215, 277, 301 |
| `cortex_command/backlog/ready.py` | 118, 265, 268 |
| `cortex_command/dashboard/data.py` | 987, 1047 (parse_backlog_counts, parse_backlog_titles — dashboard panel consumers) |
| `cortex_command/overnight/backlog.py` | 287 |
| `cortex_command/overnight/outcome_router.py` | 361 |
| `cortex_command/overnight/report.py` | 731, 747, 749, 777 |
| `tests/test_resolve_backlog_item.py` | 175, 286, 296, 316, 326, 344, 358, 372 |

At least 10 modules + 1 test file enumerate backlog files by ID. Fix B touches all of them; Fix A touches only `create_item.py`.

### Existing patterns for ID-range reservation

None. `grep -rn "reserved\|skip_range\|seed.*range" cortex_command/` returns only docstring "reserved for future use" comments — no actual ID-range exclusions. Fix A introduces a new (small) pattern.

### Conventions to follow

- Preserve list-comprehension + walrus-match style in `_get_next_id`; the ticket's Fix A snippet adds the predicate as an additional `if` clause and matches house style.
- Keep `_get_next_id` signature stable.
- Tests use `tmp_path` and call module functions directly (per `tests/test_backlog_readiness.py`).
- `bin/cortex-create-backlog-item` parity (cortex-check-parity) requires SKILL.md/requirements/docs/hooks/justfile/tests cross-reference; existing references should not drift.

## Web Research

The canonical pattern across IANA registries, the Linux kernel, the CVE service, and reference allocator libraries (vm-allocator, Hibernate) is **a range-exclusion predicate inside the allocator** — not separate data layouts. Key takeaways:

- **CVE ID allocator** (https://github.com/CVEProject/cve-services/issues/15) carves each thousand into a sequential band and a reserved band, enforced in the allocator. Direct analogue.
- **Linux `ip_local_reserved_ports`** (https://docs.kernel.org/networking/ip-sysctl.html) is a config-driven skip list consulted at allocation time. Justifies the predicate-in-allocator pattern, but the configurability there exists because operators need it — for one hard-coded range, a single inline predicate is proportionate.
- **RFC 6335 / RFC 8126bis**: partitioning a numeric registry into bands with different policies is the long-lived design. Validates the general choice of reserving a contiguous high band for non-production use.
- **Hibernate `@SequenceGenerator`**: gaps in a sequential ID series are explicitly considered normal by mainstream ORM allocators. The 10 burned IDs (990-999) are acceptable.
- **Django/Rails fixture-PK collision threads**: decades of pain reports converge on either natural keys or moving fixtures out of the production ID space. Hashed/high-range fixture PKs are a known **anti-pattern** ("hashes bumped PK incrementors way up, throwing away ranges of valid IDs") — exactly the failure mode #231 fixes.
- **Anti-pattern: hard-coding reserved-range bounds in multiple places.** Prior art (kernel, IANA) keeps the bounds in one place. For this fix, that means: if the predicate becomes load-bearing, define `FIXTURE_RANGE` once and let `_get_next_id` consult it — don't duplicate the literal across the allocator and any future validator.
- **Anti-pattern: treating the reserved band as a ceiling, not a hole.** If real IDs ever reach 989, `max(filtered) + 1` would still be 990 (in the reserved band). Prior art (CVE, vm-allocator) explicitly handles the hole on overflow. See Open Question #1 below — for this fix the overflow case is ~760 tickets away.

## Requirements & Constraints

### From `cortex/requirements/project.md`

- **Philosophy of Work / Complexity** (line 19): *"Must earn its place by solving a real problem now. When in doubt, simpler wins."* Decisive for Fix A vs Fix B.
- **Philosophy of Work / Solution horizon** (line 21): *"Before suggesting a fix, ask: do I already know this needs redoing (follow-up planned, patch applies in multiple known places, sidesteps a known constraint)? If yes, propose the durable version or surface both with tradeoff. Test: current knowledge, not prediction."* The ticket already surfaces Fix A + Fix B with tradeoff — Solution Horizon is honored.
- **Quality bar** (line 23): *"Tests pass; the feature works as specced. ROI matters — ship faster, not be a project."*
- **Architectural Constraints — SKILL.md-to-bin parity**: `bin/cortex-create-backlog-item` participates in parity enforcement; the canonical Python source is `cortex_command/backlog/create_item.py`.

### From `cortex/requirements/observability.md`

- Dashboard inputs explicitly listed do **not** include `cortex/backlog/`. The seed's choice to populate `cortex/backlog/` is incidental to the seed generator, not a load-bearing dashboard input contract. However, `cortex_command/dashboard/data.py:987,1047` (parse_backlog_counts, parse_backlog_titles) does read `cortex/backlog/` to produce the "Backlog by status" panel — so the seeds being *visible* in `cortex/backlog/` IS the affordance the seed exists to provide. Fix B/C/D break that affordance without compensating reader changes.

### From `cortex/adr/`

- **ADR-0001 (file-based state, accepted)**: backlog items as individual markdown files under `cortex/backlog/` is load-bearing. Any restructure (Fix B) must keep file-based, just relocated. Doesn't conflict with Fix A.
- No ADR yet records the 990-999 seed reservation; it's an implicit convention in `cortex_command/dashboard/seed.py` only.

## Tradeoffs & Alternatives

- **Fix A — Predicate filter `not (990 <= id <= 999)` inside `_get_next_id`** (ticket-proposed)
  - Complexity: trivial (1 file, ~2 lines). One callsite.
  - Maintainability: introduces an implicit invariant (990-999 reserved). Burns 10 IDs out of natural sequence — harmless headroom.
  - Performance: one extra integer comparison per file in the existing glob.
  - Alignment: matches house style for cheap defensive guards; canonical pattern per web prior art.

- **Fix B — Relocate seeds to `cortex/fixtures/dashboard-seed/`; readers merge at read time**
  - Complexity: high. ~10 reader modules + tests must be audited and updated. New "seeded-mode" flag plumbing.
  - Maintainability: WORSE near-term — adds parallel directory and merge-mode branch in every reader. Long-term only cleaner if seeds proliferate beyond dashboard scaffolding.
  - Alignment: weak — no other component uses a "fixture dir merged at read time" pattern.

- **Fix C — Symlink fixture dir into `cortex/backlog/` only in seed-mode**
  - Stateful "seed-mode active vs not" with filesystem-mutation hazards (broken symlinks if cleanup fails, git diff confusion if user `git add`s a symlink). Cross-platform fragility. Misaligned with how `seed.py:clean_all()` deliberately writes regular files.

- **Fix D — Rename seeds to non-numeric prefix (`seed-feature-alpha.md`, no `990-` prefix)**
  - Sidesteps `_get_next_id` (the `[0-9]*-*.md` glob excludes them). But the seeds would silently disappear from the dashboard's "Backlog by status" panel — breaking the seed's primary user-facing affordance — unless every reader's regex is widened. Similar surface-area cost as Fix B.

- **Fix E — Frontmatter tag-based detection (`tags: [dashboard-seed]`)**
  - Adds YAML-parse to a pure filename-scan hot path. Introduces an implicit tag invariant. Overkill for a CLI whose only job is to allocate the next number.

### Recommended approach: Fix A

Anchored rationale:

1. **Solution Horizon honored**: ticket already surfaces Fix A + Fix B with tradeoff and names Fix B as a follow-up if seeds grow. No other place this patch would be repeated, no constraint Fix A sidesteps. Simpler wins.
2. **Seeds are intentionally visible in the dashboard panel.** `parse_backlog_counts`/`parse_backlog_titles` read `cortex/backlog/` directly. Fixes B, C, D either break that affordance or require auditing ~10 reader modules to preserve it. Fix A preserves visible behavior and changes only the allocator — which is where the bug is.
3. **Surface area**: 1 file (`cortex_command/backlog/create_item.py`) + new test. Fix B touches 10+ modules.
4. **Reserved-range cost is small**: 10 IDs burned vs real-ID growth ~230. Revisit only if real IDs approach 990 (>700 tickets away).

## Open Questions

The following items are **deferred** to the Spec phase — they are scope decisions for the user, not codebase ambiguities research can resolve:

1. **Overflow handling for the reserved band — deferred.** The ticket's Fix A snippet filters input IDs before `max(...) + 1`. If real IDs ever reach 989, `max(filtered) + 1 = 990` would collide with the reserved band. Web prior art (CVE allocator, vm-allocator) handles this as a "skip past the hole" overflow. Cheap to handle (one extra clause to skip 990→1000), but ~760 tickets away from triggering. Spec to decide whether to include defensive overflow now or defer to a future ticket. *Deferred: spec interview will resolve.*

2. **Reserved-band literal style — deferred.** Inline literals `990 <= id <= 999` with a `# reserved for dashboard-seed fixtures` comment (matches ticket's Fix A snippet, simpler), or module-level named constants `SEED_FIXTURE_ID_MIN = 990` / `SEED_FIXTURE_ID_MAX = 999` (matches web prior art's "define once, consume once" principle, slightly more ceremonious). *Deferred: spec interview will resolve.*

3. **New test file location — deferred.** `tests/test_create_backlog_item.py` (top-level, matches sibling backlog tests) vs. `cortex_command/backlog/tests/test_create_item.py` (co-located with module, matches `test_dispatch.py`). Both patterns exist in the repo. *Deferred: spec interview will resolve.*
