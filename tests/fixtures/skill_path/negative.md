# Skill-Path Lint — Negative (False-Positive) Fixtures

Each section below contains a case that should produce ZERO violations. This
file is NOT a `*-prompt.md` whole-file prompt, so D1 fires only inside an
explicit subagent-prompt fence (there are none here). The `${CLAUDE_SKILL_DIR}/`
-prefixed Read targets exercise the precise D2 exemption.

## (a) Correct SKILL.md-body resolved token

The skill directory is `${CLAUDE_SKILL_DIR}` (absolute). Every script and
reference path uses it — for example `${CLAUDE_SKILL_DIR}/references/foo.md` is
the body form that resolves at load time and must NOT flag.

## (b) ${CLAUDE_SKILL_DIR}/../ sibling form in a Read context (D2 exemption)

Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` and follow its
full protocol. This is the correct body-propagated sibling form — the bare
`../lifecycle/...` segment is carried by a resolved `${CLAUDE_SKILL_DIR}/../`
prefix, so the D2 exemption applies and it must PASS.

The own-dir resolved form is also exempt:

Read `${CLAUDE_SKILL_DIR}/references/clarify.md` and follow it.

And the execute-context resolved form is exempt:

```
cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "msg" "$(pwd)"
```

## (c) "Do not load" markdown citation

For provenance only, the prior convention lived at `claude/reference/claude-skills.md`
(do not load — this is a historical citation, not a Read target).

## (d) :-$TMPDIR cache fallback path in main-agent shell

The main agent resolves the cache path with a working fallback, which is
main-agent-resolvable and out of scope:

```
bash "${CLAUDE_SKILL_DIR:-$TMPDIR}/scripts/cache-warm.sh"
```
