# Research: artifact-format-evaluation

Posture-check evaluation of container-format choice for cortex-command's work-product, state, and event artifacts. Scope: lifecycle-phase docs, backlog/state files, event streams (per Clarify). Excludes SKILL.md / MEMORY.md / requirements/ / hook outputs (skill-harness internals).

**Headline finding**: the current per-class mix (markdown for prose, JSON for state, JSONL for events) is consistent with Anthropic prescription, token economics on prose, and peer-system convergence. The user-stated framing was a posture-check with no observed pain. The honest output of that framing is: **document the posture inline** (one paragraph in `cortex/requirements/project.md`); **file one evidence-gated audit ticket** to determine whether any format-adjacent misalignment (backlog frontmatter parser brittleness, events.log emit-time validator gap, plan.md task regex fragility) has produced observable cost — only ticket fixes for misalignments the audit confirms.

## Research Questions

1. **What does Anthropic officially recommend for artifact/document format in agent contexts?** → **Answered.** Markdown + YAML frontmatter is the prescribed format for in-context prose artifacts (SKILL.md, CLAUDE.md, MEMORY.md, agent rules). JSON is the only Anthropic-endorsed format for tool inputs/outputs, user-facing config (settings.json, plugin manifests), and "plan files that gate machine validation" (`changes.json` pattern). XML-tag guidance is still current for Claude 4.x prompt-content delineation but the posture is softening: per *Effective context engineering* (Sep 2025), "exact formatting […] is likely becoming less important as models become more capable." Anthropic publishes **no format prescription** for event streams or inter-agent artifact handoffs — JSONL for events is a defensible extrapolation from hook payloads, not an explicit endorsement.

2. **What is the empirical token-efficiency profile across formats for the three artifact shapes?** → **Answered with caveat.**
   - Prose-heavy (~500 words): Markdown 394 tok (baseline) < YAML 448 (+14%) < JSON 532 (+35%) < XML 558 (+42%) — measured with `tiktoken cl100k_base` as substitute.
   - Cross-reference: Webmaster Ramos's benchmark against Anthropic's `client.messages.count_tokens` reports JSON 3252 → Markdown 1514 (**-53%**), i.e., markdown advantage on the production tokenizer is *larger* than the 35% shown in-artifact, not "within a few percent" as previously framed. **Honest magnitude band on the JSON→Markdown gap: 35-53% across the two measurements.** The substitution favors the recommendation directionally (cl100k_base understates markdown's advantage on the production tokenizer), but the calibration matters for any later analysis.
   - Field-heavy state (~20 keys, mixed types): Minified JSON wins on tokens (191 tok); YAML/markdown-frontmatter/TOML cluster within ~4% of each other at 212-226 tok; indented JSON is the worst at 309 tok.
   - Event streams: JSONL is the right baseline; logfmt -13% but fragile on nested payloads; CSV -17% but loses nested structure on schema heterogeneity.
   - **Tokenizer-substitution caveat:** cl100k_base's BPE merges differ from Claude's tokenizer on markdown structural punctuation (`###`, `**`, table pipes, leading dashes), which is the most likely explanation for the 35-vs-53% divergence between the two measurements. Reproducer: `pip install tiktoken; tiktoken.get_encoding("cl100k_base").encode(s)`. For Anthropic numbers, swap in `anthropic.Anthropic().messages.count_tokens(model="claude-opus-4-7", messages=[{"role":"user","content":s}]).input_tokens`.

3. **Do Claude models show measurable behavioral differences when ingesting different formats?** → **Partially answered; verification gap explicit.** Tam et al. (arXiv 2408.02442) documents reasoning degradation from format restriction (e.g., LLaMA-3-8B Last-Letter 70.07% → 28% under JSON-mode; GPT-3.5-Turbo GSM8K 76.6% → 49.25%). Webmaster Ramos reports Sonnet 4.6 / Opus 4.6 are "format-invariant on accuracy"; only Haiku-class shows large format-driven swings. **Both findings carry `[premise-unverified]` weight for Claude Opus 4.7 specifically** — no Anthropic-published format-vs-quality benchmark exists (`NOT_FOUND(query="Anthropic published benchmark markdown vs json output quality Opus 4.7", scope="anthropic.com + docs.claude.com")`). The recommendations below proceed without Opus-4.7-specific verification; this is an accepted risk, not a settled question. If model-version drift becomes a concern, a verification ticket would be: re-run Webmaster Ramos's accuracy comparison on Opus 4.7 against the same artifact-shape inputs and confirm the format-invariance claim still holds.

4. **For each functionality criterion (write-time validation, structured query, programmatic composition, ecosystem leverage), which format delivers what at what switching cost?** → **Answered (see Decision Records DR-1 through DR-3).** Headline:
   - Write-time schema validation: JSON Schema (mature ecosystem, used by Anthropic for tools and settings); YAML via PyYAML + jsonschema; markdown frontmatter has no native validation.
   - Structured field query: JSON/YAML via jq/yq; markdown frontmatter parseable if a real YAML parser is used.
   - Programmatic composition/diff: All formats diff at line level; JSON diffs cleanly with jd; markdown diffs noisily when reflowed.
   - Tooling/ecosystem leverage: JSON wins on parsers/schemas/IDE support; markdown wins on human-write ergonomics; YAML straddles both.

5. **What is the actual de-facto format mix in cortex-command, and where are the misalignments?** → **Answered.** See Codebase Analysis. The repo already uses a per-class mix consistent with the recommendation. Three structural misalignments at parser/schema seams are surfaced; **none has a cited downstream-cost case** as of this writing, so each enters the evidence-gated audit (see Architecture).
   - (a) backlog frontmatter parsed by **custom regex, not PyYAML** [`cortex_command/backlog/generate_index.py:35-77`]
   - (b) `plan.md` task structure regex-parsed with whitespace-fragile patterns [`cortex_command/overnight/parser.py:283-304`, `cortex_command/common.py:615`]
   - (c) `events.log` enforces JSONL discipline but has no schema-validator on emit — malformed events silently skipped at read [`cortex_command/overnight/events.py:272-276`]

6. **How do peer agent systems format comparable artifacts?** → **Answered.** Markdown (often with YAML frontmatter) is dominant across Cursor, Aider, Copilot, Codex CLI, Claude Code for human-authored rules. For state/checkpoints, no winner: LangGraph and AutoGen use JSON-serializable structures; Cursor stores JSON-in-SQLite; Aider's markdown transcript is an outlier. For event streams, **NDJSON is the de-facto standard** (Claude Code `stream-json`, Codex CLI `--json`, OpenTelemetry Logs Data Model). For multi-file lifecycle work-products, **no industry pattern exists**. Continue.dev's `config.json` → `config.yaml` migration is the one cited peer precedent for a format switch (rationale: readability, forward-extensibility, escape from a flat scalar that grew into an array).

## Codebase Analysis

Cortex-command's current artifact format mix:

| Artifact class | Format | Consumer | Write pattern | Read pattern |
|---|---|---|---|---|
| `cortex/lifecycle/<f>/{research,spec,clarify,review}.md` | Markdown | LLM-only | Full rewrite | Full-file LLM read |
| `cortex/lifecycle/<f>/plan.md` | Markdown w/ regex-parsed task structure | Python + LLM | Full rewrite + field updates | Section regex `[cortex_command/overnight/parser.py:283-304]`; task status regex `[cortex_command/common.py:615]` |
| `cortex/lifecycle/<f>/events.log` | JSONL | Python + dashboard | Append-only via `tempfile + os.replace` `[cortex_command/overnight/events.py:240]` | Skip-malformed read `[cortex_command/overnight/events.py:272-276]` |
| `cortex/backlog/*.md` | Markdown + YAML-like frontmatter | Python + LLM | Partial field-level edits | Custom regex parse `[cortex_command/backlog/generate_index.py:35-77]` — **NOT PyYAML**. Three additional parser copies exist: `cortex_command/overnight/backlog.py:218-241` (separate `_parse_frontmatter`), `cortex_command/backlog/update_item.py:39-94` (`_get`/`_set_frontmatter_value`, regex line-stream), `cortex_command/dashboard/data.py:998-1014` (inline loop in `_count_backlog_by_status`) |
| `cortex/backlog/index.json` | JSON | Python | Full rewrite via `atomic_write` `[cortex_command/backlog/generate_index.py:307]` | Direct JSON load `[cortex_command/overnight/backlog.py:335-341]` |
| `cortex/backlog/index.md` | Markdown table (generated) | User-only | Full rewrite | Human-read |
| `cortex/backlog/*.events.jsonl` | JSONL | Python + overnight | Append-only | Line-by-line JSON parse |
| `cortex/research/<t>/research.md` | Markdown | LLM-only | Full rewrite | Full-file LLM read |
| `cortex/requirements/*.md` | Markdown | LLM-only | Full rewrite | Full-file LLM read |
| `claude/settings.json` | JSON | Claude Code harness | Atomic merge | Selective field merge |
| Hook stdin/stdout | JSON | Bash hooks | Serialize | `jq -r` extraction |

Cross-checks performed:
- Verified `research.md` / `spec.md` are file-existence-checked only, no section parsing in Python `[cortex_command/common.py:324]`. `NOT_FOUND(query="parse research.md sections", scope="cortex_command/**/*.py")` for any complexity-heuristic-style markdown header counting.
- Verified `cortex_command/backlog/generate_index.py:35` uses `re.compile(r"\A---\n(.*?)\n---", re.DOTALL)` for frontmatter extraction and `_parse_frontmatter` does line-by-line colon-split `[cortex_command/backlog/generate_index.py:46-60]`. `yaml.safe_load` is used elsewhere (only `cortex_command/overnight/report.py:1271`) but never for backlog frontmatter.
- Identified **four** independent frontmatter parsers in the repo (see table). Any future parser-replacement work must enumerate all four call sites; the original posture of "swap one parser" understated the surface.
- Verified `events.log` discipline: `json.dumps(entry)` per line with skip-malformed read `[cortex_command/overnight/events.py:272-286]`. Schema not validated at emit; field requirements not enforced beyond `dict` + `"event"` key presence.
- Corpus inspection of `cortex/backlog/*.md` frontmatter values shows pervasive bare integer IDs with leading zeros (`id: 003`, `parent: 010`, `parent: 042`) and bare ISO-date scalars (`created: 2026-04-09`). Both would type-coerce under `yaml.safe_load` (YAML 1.1: `010` → int 8 octal; date scalars → `datetime.date`). The current regex parser uniformly stringifies these; corpus is internally heterogeneous on the `id` field already (some quoted strings, some bare ints).

## Web & Documentation Research

**Anthropic prescription summary (verbatim sources):**

- Skill authoring best practices: *"Every skill needs a SKILL.md file with two parts: YAML frontmatter (between --- markers) that tells Claude when to use the skill, and markdown content with instructions Claude follows when the skill is invoked."* For plan-validate-execute intermediates: *"add an intermediate `changes.json` file that gets validated before applying changes."* (`platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices`)
- Claude 4.x best practices: *"Structure prompts with XML tags — XML tags help Claude parse complex prompts unambiguously, especially when your prompt mixes instructions, context, examples, and variable inputs."* Covers Opus 4.7. (`platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-4-best-practices`)
- Effective context engineering (Sep 2025): *"using techniques like XML tagging or Markdown headers to delineate these sections […] although the exact formatting of prompts is likely becoming less important as models become more capable."* Endorses *"a NOTES.md file"* as the canonical persistent-memory pattern. (`anthropic.com/engineering/effective-context-engineering-for-ai-agents`)
- CLAUDE.md / memory: *"CLAUDE.md files are markdown files that give Claude persistent instructions for a project. […] Claude scans structure the same way readers do: organized sections are easier to follow than dense paragraphs."* (`code.claude.com/docs/en/memory`)
- Structured outputs: JSON Schema for tool inputs/outputs; constrained decoding is JSON-only. (`platform.claude.com/docs/en/build-with-claude/structured-outputs`)

**Empirical token-cost evidence:**

- Webmaster Ramos benchmark (Anthropic production tokenizer): JSON 3252 → YAML 2208 (-32%) → **Markdown 1514 (-53%)** → TOON 1226 (-62%). (`dev.to/webramos/yaml-vs-markdown-vs-json-vs-toon-which-format-is-most-efficient-for-the-claude-api-4l94`)
- Improving Agents: Markdown is 34% cheaper than JSON, 10% cheaper than YAML — pattern stable across GPT-5 Nano, Llama 3.2 3B, Gemini 2.5 Flash Lite. (`improvingagents.com/blog/best-nested-data-format`)
- `NOT_FOUND(query="Anthropic-published per-format quality benchmark for Opus 4.7", scope="anthropic.com + docs.claude.com")`. Cross-format quality claims rely on third-party benchmarks `[premise-unverified for Claude Opus 4.7 specifically]`.

**Behavioral evidence (format vs reasoning):**

- Tam et al. (arXiv 2408.02442): format restriction can degrade reasoning by up to 42 points on weaker models; reverses for classification tasks. `[premise-unverified for Claude]`.
- Webmaster Ramos: Sonnet 4.6 / Opus 4.6 reported "format-invariant on accuracy." `[premise-unverified — single source; Opus 4.7 not measured]`.

## Domain & Prior Art

Peer-system format choice for the three artifact classes:

| System | Rules/prompts | State/checkpoints | Output artifacts / events |
|---|---|---|---|
| Cursor | Markdown + YAML frontmatter (`.mdc`) | JSON in SQLite | none standardized |
| Aider | Plain markdown (`CONVENTIONS.md`); YAML config | Markdown transcript (outlier) | direct diffs |
| Continue.dev | YAML (migrated from JSON, published rationale) | cloud | none |
| GitHub Copilot | Markdown ± YAML frontmatter (path-scoped) | in-IDE | PRs |
| Codex CLI | Plain markdown (`AGENTS.md`) | server | NDJSON via `--json` |
| LangGraph | Code-as-config | JSON-serializable (msgpack + extended-JSON) | JSON state |
| AutoGen | Code-defined; JSON declarative component spec | JSON-serializable | JSON |
| Claude Code | Markdown ± YAML frontmatter | JSON projects state | NDJSON `stream-json` |

Key prior-art findings:

- **Markdown is dominant** for human-authored rules across every major peer system.
- **NDJSON is the de-facto event-stream standard** — no peer agent system uses markdown for event streams.
- **No industry standard exists for multi-file lifecycle work-products** — cortex-command's choice here is constrained by Anthropic guidance + token efficiency + parseability, not peer convention.
- **One published format switch with rationale: Continue.dev's `config.json` → `config.yaml`.** Cited drivers: readability, maintainability, forward-extensibility.
- **Known pain points worth flagging:**
  - Cursor `.mdc`: silent rule-load failures, IDE-edit corruption bugs, >500-line under-performance, non-portable across tools.
  - LangGraph JsonPlusSerializer: CVE-2025-64439 (RCE in any-type JSON deserialization); advisory recommends `LANGGRAPH_STRICT_MSGPACK=true`.
  - AGENTS.md effectiveness: one study found LLM-generated AGENTS.md *reduced* task success ~3%; human-written improved ~4%. `[premise-unverified — single study]`.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|---|---|---|---|
| (δ) **Status quo, no changes** | None | Known structural fragility surfaces in the parser/schema seams: regex frontmatter parser, regex plan.md task structure, no events.log emit-time validator. **No cited downstream-cost case** (no events.log row, postmortem, or failed-ingest case in the audit). Risk is conditional on a future incident materializing | None |
| (γ) **Document the posture inline + audit-gated misalignment work** — append a Format posture paragraph to `cortex/requirements/project.md` (do-it-now); file one investigation ticket that audits events.log / postmortems / failed-ingest cases for any of the three misalignments; build tickets only fire for misalignments the audit confirms | S | Low for the inline edit; the audit is read-only investigation. Build tickets are scope-bounded by audit findings | None |
| (β) **Wholesale migration to JSON for state-shaped artifacts** (plan.md → plan.json, backlog frontmatter → sidecar JSON) | L | Medium. Inflates lifecycle artifact tokens by ~30-40%; loses human-authoring ergonomics for tickets; significant downstream consumer rewrites | None blocking, but the token-cost penalty argues against doing this absent specific pain |
| (α) **Wholesale migration to markdown** (state files → markdown tables, events.log → markdown bullets) | XL | High. Loses programmatic parseability; conflicts with Anthropic guidance on structured outputs; breaks NDJSON convergence | Not feasible — events.log and settings.json have non-LLM consumers depending on structured-data semantics |

Recommendation: **δ → γ progression**. The honest baseline given user-stated framing ("no specific pain — periodic check") is δ (do nothing). γ is the proportional response if pain emerges. The inline format-posture documentation is worth shipping immediately regardless because it codifies the de-facto posture; the audit-then-build pieces only ship if the audit confirms observable cost.

## Architecture

### Pieces

- **Format-posture inline documentation** — append a "Format posture" subsection (~one paragraph) to `cortex/requirements/project.md`'s Architectural Constraints. Content: markdown for prose-heavy work-products; JSON for state and config; JSONL for event streams; YAML frontmatter only on markdown ticket bodies; XML tags reserved for prompt-content delineation (per Anthropic's still-current Claude 4.x guidance). Reference this research artifact for rationale. Executed inline alongside this discovery's landing — not a tracked backlog item.
- **Format-misalignment evidence audit** — single investigation ticket. Examines events.log content across recent feature directories, any retros under `cortex/retros/`, and any failed-ingest or orchestrator-stall postmortems for evidence that ANY of the three structural misalignments has produced a real-world failure: (a) backlog frontmatter mis-parse caused a wrong index entry or wrong overnight readiness decision; (b) plan.md task regex broke on a real plan and dropped a task; (c) events.log accepted a malformed event that downstream code mis-interpreted (rather than the read-side skip-malformed path silently absorbing it). For each confirmed-pain case, file a scoped build ticket whose recommendation incorporates the blast-radius findings from this research (see DR-2 trade-offs for backlog-frontmatter migration risk in particular). If the audit finds zero confirmed pain, close with a "no action" verdict and revisit annually or on first incident.

### Integration shape

Two pieces connect through one named contract surface:

- **Project-level format constraint** — `cortex/requirements/project.md`'s Architectural Constraints section as the single source of truth for "what format goes where." The format-posture inline doc creates this; the audit ticket cites it as the standard against which misalignments are measured. Future build tickets (if any) cite both the format-posture text and the audit findings as their motivating evidence.

### Seam-level edges

- **Format-posture inline documentation** edges land on: `cortex/requirements/project.md` content only. No consumers to coordinate; the constraint is documentary.
- **Format-misalignment evidence audit** edges land on: read-only inspection of `cortex/lifecycle/*/events.log`, `cortex/retros/` (if any), past postmortems in commit messages and PR descriptions. No code touched in this ticket; any downstream build tickets it spawns operate per their own scope.

## Decision Records

### DR-1: Container format strategy — per-class mix vs wholesale migration

- **Context**: User posed the meta-question of whether markdown is the right format for all artifacts. Evidence had to clear: Anthropic prescription, token economics, peer-system pattern, codebase fit.
- **Options considered**:
  - (α) Markdown for everything (status quo for prose, breaking change for state/events).
  - (β) JSON for everything (breaking change for prose, status quo for state/config).
  - (γ) Per-artifact-class mix: markdown for prose, JSON for state, JSONL for events — roughly the current posture.
- **Recommendation**: **(γ)**. Anthropic prescribes markdown for in-context prose and JSON for structured outputs; peer systems converge on the same split (Claude Code's own `stream-json` is NDJSON; CLAUDE.md is markdown). Token economics reinforce the split for prose artifacts (markdown 35-53% cheaper than JSON on the two cited measurements, with the production-tokenizer end favoring markdown more strongly than the cl100k_base substitute). The current cortex-command posture is roughly correct.
- **Trade-offs**: Per-class mix means multiple formats and parsers to maintain. Mitigated by stable boundaries: prose docs don't get re-typed as state files, and vice versa.

### DR-2: Backlog frontmatter — what to do if pain is observed

- **Context**: Backlog ticket frontmatter is YAML-shaped but parsed by a custom regex (`cortex_command/backlog/generate_index.py:35-77`). No cited downstream-cost case as of this writing; DR-2 fires only if the misalignment audit (Architecture piece 2) confirms observable harm.
- **Options considered (if pain is observed)**:
  - (α) Switch to `yaml.safe_load`.
  - (β) Migrate to TOML frontmatter (`+++` delimiters).
  - (γ) Factor frontmatter out to sidecar JSON.
- **Recommendation**: **If audit confirms pain, prefer (α) but only with a typed-field schema, not as a "surgical" drop-in replacement.** The naive swap fails immediately:
  - PyYAML coerces bare `created: 2026-04-09` to `datetime.date`; existing consumer code `fm.get("created", "").strip()` at `cortex_command/backlog/generate_index.py:179-180` raises `AttributeError`. Same for `updated`. Downstream `json.dumps(items, ...)` at `generate_index.py:307` raises `TypeError: Object of type date is not JSON serializable`.
  - PyYAML returns `tags` / `areas` / `blocks` / `blocked-by` as Python `list` from inline list syntax; `_parse_inline_str_list(fm.get("tags", "[]"))` at `generate_index.py:177` calls `.strip()` on the value — `AttributeError: 'list' object has no attribute 'strip'`.
  - YAML 1.1 octal coercion silently corrupts leading-zero numeric IDs: `parent: 010` → int 8, `parent: 042` → int 34. Bare integer IDs are pervasive in the corpus (`id: 003`, `parent: 010`, `parent: 042`); same field becomes a mix of `int 3`, `str "008"`, `int 8`, `int 34` across files; blocker-graph resolution silently rewrites to wrong destinations with no error raised.
  - The `_opt` sentinel that recognizes the literal string `"null"` does not survive the switch: PyYAML maps bare `null` to Python `None` before `_opt` sees it; falsy-vs-None semantics shift for every field using `_opt` (~15 fields).
  - Repo contains **four independent frontmatter parsers**, not one: `generate_index.py:_parse_frontmatter`, `overnight/backlog.py:_parse_frontmatter` (separate copy, lines 218-241), `update_item.py:_get_frontmatter_value`/`_set_frontmatter_value` (regex line-stream, lines 39-94), and `dashboard/data.py:998-1014`. Partial migration leaves consumers reading from two parsers with different type semantics; all four call sites must change together.
  - `update_item.py` writes values back as raw strings via regex substitution. Read/write asymmetry: a `created: 2026-04-09` read as date, re-written as string, then re-read as date — produces format drift each cycle unless write-side also changes.
- **Trade-offs**: The migration as understood at research time is NOT surgical. It requires (a) per-field type schema with explicit string-coercion for dates / ints / IDs; (b) atomic migration across all four parser call sites; (c) write-side parser symmetry so round-trips are stable; (d) zero-padded-ID coercion preserved either by explicit quoting in the corpus or by post-load string-coercion in the typed schema. Any audit-driven ticket that fires DR-2 must scope these in its spec.

### DR-3: events.log — JSONL retention and the validator question

- **Context**: events.log is strict JSONL with no emit-time schema validator. Malformed entries silently dropped at read. Token-cost framing does not apply (events.log is Python+dashboard-consumed, not LLM-context-consumed).
- **Options considered**:
  - (α) Keep JSONL; add emit-time JSON Schema or typed-dataclass validator wired through `bin/.events-registry.md`.
  - (β) Migrate to OpenTelemetry Logs Data Model.
  - (γ) Status quo.
- **Recommendation**: **Keep JSONL on industry-convention grounds (Claude Code `stream-json`, Codex `--json`, OpenTelemetry's log model)**. The validator question (α vs γ) is open: the existing `bin/.events-registry.md` pre-commit gate already covers event-name registration; the marginal value of an emit-time runtime validator over the static gate is unresolved and audit-gated. β is over-engineered relative to current needs.
- **Trade-offs**: Adding a runtime validator adds an emit-time hop and a maintenance surface. The audit (Architecture piece 2) should specifically test whether any malformed-event-silently-dropped case has produced observable harm; if not, γ remains the recommendation.

### DR-4: plan.md task structure — sidecar JSON vs tightened markdown schema

- **Context**: plan.md has structured task data (`### Task N:`, `**Status**: [ ]`) regex-parsed by Python. Regex is whitespace-fragile. No OCC for concurrent writes.
- **Options considered (if pain is observed)**:
  - (α) Sidecar `plan-tasks.json` (state in JSON, narrative in plan.md).
  - (β) Tighten the markdown schema with an emit-time validator that rejects ill-shaped tasks.
  - (γ) Status quo.
- **Recommendation**: **Audit-gated** (per Architecture piece 2). No current evidence of concurrent-write conflicts or regex-parse failures. If the audit surfaces a real case, the α-vs-β decision is informed by the specifics (concurrent-write evidence favors α; whitespace-only parse failure favors β).

### DR-5: Format-posture documentation

- **Context**: The current per-class mix is implicit in the existing artifacts but not documented as a project-level constraint. This research artifact is itself evidence that future contributors keep re-asking the question.
- **Options considered**:
  - (α) Append a "Format posture" subsection under Architectural Constraints in `cortex/requirements/project.md`.
  - (β) Create a separate `cortex/requirements/format-posture.md` area doc.
  - (γ) Leave it implicit.
- **Recommendation**: **(α), executed inline alongside this research's landing** — not a tracked backlog item. The deliverable is one paragraph; backlog ceremony would consume more cycles than the change itself.
- **Trade-offs**: Slight bloat in project.md. Mitigated by high value-per-line.

## Open Questions

- **Misalignment audit outcomes** — does any of the three misalignments (backlog frontmatter, plan.md task regex, events.log emit-time validator gap) have observable downstream cost? Answer determines whether DR-2/DR-3/DR-4 spawn build tickets.
- **Opus 4.7 format-quality verification** — the format-invariance claim is single-sourced and explicitly does not cover Opus 4.7. If model-version drift becomes a concern, run Webmaster Ramos's accuracy comparison against Opus 4.7 with our artifact-shape inputs. Accepted risk for the current recommendation; not blocking.
- **TOON format** — Webmaster Ramos's benchmark showed TOON at -62% tokens vs JSON. Not endorsed by Anthropic; no peer adoption surfaced. Worth a periodic re-check in 6-12 months; out of scope for this discovery.
- **Anthropic-published quality benchmark** — `NOT_FOUND` as of this writing. If/when Anthropic publishes a format-vs-output-quality benchmark for Claude 4.x, the recommendations above should be re-graded against it.
