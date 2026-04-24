#!/bin/bash
# tests/test_install.sh -- install.sh integration tests
# Exercises R2/R3/R6/R7/R10/R11/R19 from
# lifecycle/ship-curl-sh-bootstrap-installer-for-cortex-command/spec.md.
#
# Hermetic: PATH-mocked uv/curl/git stubs, sandbox HOME, local bare-repo as
# clone source (routed via GIT_CONFIG_GLOBAL `url.<path>.insteadOf` rules).
#
# Deviations from Task 6 Context:
#
# 1. The Context's design assumes `CORTEX_REPO_URL=file://$tmpdir/...` passes
#    through normalize_repo_url verbatim. Per spec R5 (and install.sh as
#    implemented in Tasks 4-5), only `git@*:*/*`, `ssh://*`, `https://*`, and
#    `http://*` pass through; `file://` falls into the shorthand branch and is
#    prepended with `https://github.com/`. We use the default shorthand
#    `charleshall888/cortex-command` -> `https://github.com/...cortex-command.git`
#    and route it to a local bare repo via `url.<file-path>.insteadOf` in
#    GIT_CONFIG_GLOBAL. This matches spec R5 exactly and keeps the test hermetic.
#
# 2. Context says "do NOT stub git in most branches." We use a thin git shim
#    (tests/fixtures/install/bin/git) that intercepts ONLY `remote get-url`
#    to delegate to `git config --get remote.<name>.url`. Rationale: `git
#    remote get-url` unconditionally applies insteadOf substitution -- there is
#    no flag to bypass it -- so without the shim install.sh's byte-identity
#    check in R6(b) would always fail when insteadOf-based routing is active.
#    The shim is the minimal deviation compatible with hermetic testing.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
FIXTURE_BIN="$REPO_ROOT/tests/fixtures/install/bin"
JUST_STUB="$REPO_ROOT/tests/fixtures/install/just-stub.sh"

# Resolve real git once, used by the git shim via REAL_GIT env var.
REAL_GIT_PATH="$(command -v git)"
if [[ -z "$REAL_GIT_PATH" ]]; then
	echo "FATAL: real git binary not found on PATH" >&2
	exit 2
fi

PASS_COUNT=0
FAIL_COUNT=0

pass() {
	echo "PASS $1"
	PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
	echo "FAIL $1: $2"
	FAIL_COUNT=$((FAIL_COUNT + 1))
}

# SKIP: increments neither PASS_COUNT nor FAIL_COUNT. Use when a prerequisite
# tool is missing (e.g., shellcheck on a dev machine). A visible SKIP line
# preserves signal — the suite is not silently green.
skip() {
	echo "SKIP $1: $2"
}

# ---------------------------------------------------------------------------
# Test: shellcheck -s sh install.sh
# Placed FIRST so a bashism (`[[ ]]`, arrays, `local`, `pipefail`, etc.) fails
# fast rather than surfacing downstream as opaque stub errors. SKIP if
# shellcheck is not installed so a missing dev dependency is not a silent
# false-pass; CI must install shellcheck.
# ---------------------------------------------------------------------------
if ! command -v shellcheck >/dev/null 2>&1; then
	skip "install/shellcheck-posix-sh" "shellcheck not installed; install via 'brew install shellcheck'"
else
	shellcheck_output=$(shellcheck -s sh "$INSTALL_SH" 2>&1)
	shellcheck_exit=$?
	if [[ $shellcheck_exit -eq 0 ]]; then
		pass "install/shellcheck-posix-sh"
	else
		fail "install/shellcheck-posix-sh" \
			"shellcheck -s sh reported issues (exit=$shellcheck_exit): $shellcheck_output"
	fi
fi

# ---------------------------------------------------------------------------
# Per-test sandbox setup
# ---------------------------------------------------------------------------
# Each test calls new_sandbox to set up a fresh tmpdir + HOME + PATH-mocked bin
# directory. State is per-test so cross-test leakage is impossible.
#
# After new_sandbox the following globals are set:
#   TMPDIR_T        per-test scratch directory
#   HOME            sandbox HOME (overrides outer)
#   PATH            $TMPDIR_T/bin:/usr/bin:/bin
#   STUB_LOG_DIR    where stubs write their argv logs
#   STUB_UV_SOURCE  absolute path to the stub uv binary (for the curl-installer)
#   FAKE_UPSTREAM   a local bare repo with a one-commit baseline
#   TARGET          clone destination ($HOME/.cortex)
#   RESOLVED_URL    install.sh's normalized URL for the default shorthand
#                   ("https://github.com/charleshall888/cortex-command.git") --
#                   also what R6(b)/(c)/(d) assertions compare against.
#   GIT_CONFIG_GLOBAL  points at a per-sandbox gitconfig that routes
#                   RESOLVED_URL -> file://FAKE_UPSTREAM via insteadOf.
new_sandbox() {
	TMPDIR_T="$(mktemp -d "${TMPDIR:-/tmp}/test_install_XXXXXX")"
	HOME_SANDBOX="$TMPDIR_T/home"
	mkdir -p "$HOME_SANDBOX/.local/bin"
	export HOME="$HOME_SANDBOX"
	mkdir -p "$TMPDIR_T/bin"
	cp "$FIXTURE_BIN/uv" "$TMPDIR_T/bin/uv"
	cp "$FIXTURE_BIN/curl" "$TMPDIR_T/bin/curl"
	cp "$FIXTURE_BIN/git" "$TMPDIR_T/bin/git"
	chmod +x "$TMPDIR_T/bin/uv" "$TMPDIR_T/bin/curl" "$TMPDIR_T/bin/git"
	export STUB_LOG_DIR="$TMPDIR_T"
	export STUB_UV_SOURCE="$FIXTURE_BIN/uv"
	export REAL_GIT="$REAL_GIT_PATH"
	# /usr/bin and /bin stay on PATH for sh, mktemp, command, etc.
	export PATH="$TMPDIR_T/bin:/usr/bin:/bin"
	# Build the fake upstream via REAL git directly (bypasses shim; cheaper).
	FAKE_UPSTREAM="$TMPDIR_T/fake-upstream.git"
	"$REAL_GIT" init --quiet --bare "$FAKE_UPSTREAM"
	local seed="$TMPDIR_T/seed"
	"$REAL_GIT" init --quiet "$seed"
	(
		cd "$seed"
		"$REAL_GIT" -c commit.gpgsign=false -c user.email=t@t -c user.name=t \
			commit --allow-empty --quiet -m "init"
		"$REAL_GIT" remote add origin "$FAKE_UPSTREAM"
		"$REAL_GIT" push --quiet origin HEAD:refs/heads/main
	)
	# Set HEAD of bare repo to main so future clones succeed with default branch.
	"$REAL_GIT" --git-dir="$FAKE_UPSTREAM" symbolic-ref HEAD refs/heads/main
	TARGET="$HOME_SANDBOX/.cortex"
	export CORTEX_COMMAND_ROOT="$TARGET"
	# Use the default shorthand (no explicit CORTEX_REPO_URL) so that install.sh
	# normalizes to the canonical GitHub https URL. Route that URL to the local
	# bare repo via insteadOf.
	unset CORTEX_REPO_URL
	RESOLVED_URL="https://github.com/charleshall888/cortex-command.git"
	export GIT_CONFIG_GLOBAL="$TMPDIR_T/gitconfig"
	"$REAL_GIT" config --file "$GIT_CONFIG_GLOBAL" \
		"url.file://$FAKE_UPSTREAM.insteadOf" "$RESOLVED_URL"
	# Default: just is present (symlink the trivial stub). Tests for R3
	# explicitly remove this.
	ln -s "$JUST_STUB" "$TMPDIR_T/bin/just"
	# Default: stubs not in failure mode.
	unset STUB_UV_FAIL STUB_CURL_FAIL
}

cleanup_sandbox() {
	if [[ -n "${TMPDIR_T:-}" && -d "$TMPDIR_T" ]]; then
		rm -rf "$TMPDIR_T"
	fi
}

# Run install.sh capturing stdout/stderr/exit independently.
# Args: out_stdout out_stderr -- file paths to write captures.
run_install() {
	local out_stdout="$1"
	local out_stderr="$2"
	"$INSTALL_SH" >"$out_stdout" 2>"$out_stderr"
	echo $? > "$TMPDIR_T/.exit"
}

# ---------------------------------------------------------------------------
# Test: R2 -- no-uv simulation; uv installer runs hermetically
# ---------------------------------------------------------------------------
new_sandbox
rm -f "$TMPDIR_T/bin/uv"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
if [[ $exit_code -eq 0 && -x "$HOME/.local/bin/uv" ]]; then
	pass "install/R2-no-uv-bootstrap"
else
	fail "install/R2-no-uv-bootstrap" \
		"expected exit 0 and uv at \$HOME/.local/bin/uv; got exit=$exit_code, uv exists=$(test -x "$HOME/.local/bin/uv" && echo yes || echo no), stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R3 -- no `just` on PATH -> exit 1, stderr names just + brew install just
# ---------------------------------------------------------------------------
new_sandbox
rm -f "$TMPDIR_T/bin/just"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
stderr_content=$(cat "$TMPDIR_T/stderr")
if [[ $exit_code -eq 1 && "$stderr_content" == *"just"* && "$stderr_content" == *"brew install just"* ]]; then
	pass "install/R3-no-just-precondition"
else
	fail "install/R3-no-just-precondition" \
		"expected exit 1 with 'just' and 'brew install just' on stderr; got exit=$exit_code, stderr=$stderr_content"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R6(a) -- target absent -> clone succeeds
# ---------------------------------------------------------------------------
new_sandbox
rm -rf "$TARGET"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
if [[ $exit_code -eq 0 && -d "$TARGET/.git" ]]; then
	pass "install/R6a-target-absent-clones"
else
	fail "install/R6a-target-absent-clones" \
		"expected exit 0 and \$TARGET/.git to exist; got exit=$exit_code, .git exists=$(test -d "$TARGET/.git" && echo yes || echo no), stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R6(b) -- target is a git repo with byte-identical origin -> pull --ff-only
# Verify pull happens by pre-creating an upstream commit and asserting the
# target's HEAD ref advances.
# ---------------------------------------------------------------------------
new_sandbox
# Pre-init target pointing at FAKE_UPSTREAM with origin url == RESOLVED_URL
# (the shim ensures install.sh sees this raw value via `remote get-url`; real
# fetch/pull routes via insteadOf to FAKE_UPSTREAM).
"$REAL_GIT" clone --quiet "file://$FAKE_UPSTREAM" "$TARGET"
"$REAL_GIT" -C "$TARGET" remote set-url origin "$RESOLVED_URL"
head_before=$("$REAL_GIT" -C "$TARGET" rev-parse HEAD)
# Add a new commit to FAKE_UPSTREAM via a temporary work-tree.
work2="$TMPDIR_T/work2"
"$REAL_GIT" clone --quiet "$FAKE_UPSTREAM" "$work2"
(
	cd "$work2"
	"$REAL_GIT" -c commit.gpgsign=false -c user.email=t@t -c user.name=t \
		commit --allow-empty --quiet -m "advance"
	"$REAL_GIT" push --quiet origin HEAD:refs/heads/main
)
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
head_after=$("$REAL_GIT" -C "$TARGET" rev-parse HEAD)
if [[ $exit_code -eq 0 && "$head_before" != "$head_after" ]]; then
	pass "install/R6b-same-origin-pulls"
else
	fail "install/R6b-same-origin-pulls" \
		"expected exit 0 and HEAD to advance; got exit=$exit_code, before=$head_before, after=$head_after, stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R6(b-dirty) -- target is same-origin git repo with uncommitted changes
# -> exit 1, stderr names "uncommitted changes". Backs Task 4's dirty-tree
# pre-flight.
# ---------------------------------------------------------------------------
new_sandbox
"$REAL_GIT" clone --quiet "file://$FAKE_UPSTREAM" "$TARGET"
"$REAL_GIT" -C "$TARGET" remote set-url origin "$RESOLVED_URL"
# Stage a baseline tracked file in upstream so edits register as dirty.
work_dirty="$TMPDIR_T/work_dirty"
"$REAL_GIT" clone --quiet "$FAKE_UPSTREAM" "$work_dirty"
echo "baseline" > "$work_dirty/pyproject.toml"
(
	cd "$work_dirty"
	"$REAL_GIT" add pyproject.toml
	"$REAL_GIT" -c commit.gpgsign=false -c user.email=t@t -c user.name=t \
		commit --quiet -m "baseline pyproject"
	"$REAL_GIT" push --quiet origin HEAD:refs/heads/main
)
# Sync target to upstream so pyproject.toml exists, then dirty it.
"$REAL_GIT" -C "$TARGET" pull --quiet --ff-only "file://$FAKE_UPSTREAM" main
echo "local edit" >> "$TARGET/pyproject.toml"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
stderr_content=$(cat "$TMPDIR_T/stderr")
if [[ $exit_code -eq 1 && "$stderr_content" == *"uncommitted changes"* ]]; then
	pass "install/R6b-dirty-tree-aborts"
else
	fail "install/R6b-dirty-tree-aborts" \
		"expected exit 1 with 'uncommitted changes' on stderr; got exit=$exit_code, stderr=$stderr_content"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R6(c) -- target is a git repo with different origin -> exit 1, stderr
# names both URLs.
# ---------------------------------------------------------------------------
new_sandbox
mkdir -p "$TARGET"
"$REAL_GIT" -C "$TARGET" init --quiet
"$REAL_GIT" -C "$TARGET" config remote.origin.url "https://github.com/other/different.git"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
stderr_content=$(cat "$TMPDIR_T/stderr")
if [[ $exit_code -eq 1 \
	&& "$stderr_content" == *"https://github.com/other/different.git"* \
	&& "$stderr_content" == *"$RESOLVED_URL"* ]]; then
	pass "install/R6c-different-origin-aborts"
else
	fail "install/R6c-different-origin-aborts" \
		"expected exit 1 with both URLs on stderr; got exit=$exit_code, stderr=$stderr_content"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R6(d) -- cross-protocol same repo (HTTPS origin vs SSH CORTEX_REPO_URL)
# -> exit 1 (byte-identity is the contract; equivalence parsing is intentionally
# not implemented per spec R5 non-requirement).
# ---------------------------------------------------------------------------
new_sandbox
mkdir -p "$TARGET"
"$REAL_GIT" -C "$TARGET" init --quiet
"$REAL_GIT" -C "$TARGET" config remote.origin.url "https://github.com/charleshall888/cortex-command.git"
export CORTEX_REPO_URL="git@github.com:charleshall888/cortex-command.git"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
stderr_content=$(cat "$TMPDIR_T/stderr")
if [[ $exit_code -eq 1 \
	&& "$stderr_content" == *"https://github.com/charleshall888/cortex-command.git"* \
	&& "$stderr_content" == *"git@github.com:charleshall888/cortex-command.git"* ]]; then
	pass "install/R6d-cross-protocol-aborts"
else
	fail "install/R6d-cross-protocol-aborts" \
		"expected exit 1 with both protocol URLs on stderr; got exit=$exit_code, stderr=$stderr_content"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R6(e) -- target exists but is NOT a git repo -> exit 1, "refusing to
# overwrite".
# ---------------------------------------------------------------------------
new_sandbox
mkdir -p "$TARGET"
echo "unrelated" > "$TARGET/marker"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
stderr_content=$(cat "$TMPDIR_T/stderr")
if [[ $exit_code -eq 1 && "$stderr_content" == *"refusing to overwrite"* ]]; then
	pass "install/R6e-not-git-repo-aborts"
else
	fail "install/R6e-not-git-repo-aborts" \
		"expected exit 1 with 'refusing to overwrite' on stderr; got exit=$exit_code, stderr=$stderr_content"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R7 -- pre-clone stderr ordering.
# Both [cortex-install] log lines (URL + target) must appear before any clone/pull
# line. Verified by line-number comparison within stderr.
# ---------------------------------------------------------------------------
new_sandbox
rm -rf "$TARGET"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
url_line=$(grep -n '\[cortex-install\] resolved repo URL' "$TMPDIR_T/stderr" | head -1 | cut -d: -f1)
target_line=$(grep -n '\[cortex-install\] target path' "$TMPDIR_T/stderr" | head -1 | cut -d: -f1)
# Subsequent error lines (if any) reference clone/pull commands. A healthy run
# produces no such line, so the ordering check collapses to "both log lines
# exist before any potential clone/pull reference."
clone_line=$(grep -n 'command failed.*git clone\|command failed.*git .*pull\|fatal:.*clone' "$TMPDIR_T/stderr" | head -1 | cut -d: -f1)
ok=1
if [[ -z "$url_line" || -z "$target_line" ]]; then
	ok=0
fi
if [[ $ok -eq 1 && -n "$clone_line" ]]; then
	if [[ $url_line -ge $clone_line || $target_line -ge $clone_line ]]; then
		ok=0
	fi
fi
if [[ $exit_code -eq 0 && $ok -eq 1 ]]; then
	pass "install/R7-pre-clone-stderr-ordering"
else
	fail "install/R7-pre-clone-stderr-ordering" \
		"expected URL+target log lines before any clone reference; got exit=$exit_code, url_line=$url_line, target_line=$target_line, clone_line=$clone_line, stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R10 -- idempotent re-run.
# (a) two consecutive runs both exit 0; .git/HEAD unchanged between runs 1 and 2.
# (b) after adding a synthetic [project.scripts] entry to the upstream and
#     running a third time, the target picks up the new pyproject AND uv is
#     re-invoked (verifies --force-driven entry-point regeneration contract).
# ---------------------------------------------------------------------------
new_sandbox
rm -rf "$TARGET"
# First run -- clones fresh.
run_install "$TMPDIR_T/stdout1" "$TMPDIR_T/stderr1"
exit1=$(cat "$TMPDIR_T/.exit")
head1=$(cat "$TARGET/.git/HEAD" 2>/dev/null || echo missing)
uv_calls_after_1=$(wc -l < "$TMPDIR_T/uv.argv" 2>/dev/null | tr -d ' ')
: "${uv_calls_after_1:=0}"
# First run saved the stored remote URL as the post-substitution file path;
# to exercise the re-run branch, reset the raw remote.origin.url so byte-identity
# against RESOLVED_URL matches on run 2+.
"$REAL_GIT" -C "$TARGET" remote set-url origin "$RESOLVED_URL"
# Second run (no upstream change) -- should pull (no-op) and re-invoke uv.
run_install "$TMPDIR_T/stdout2" "$TMPDIR_T/stderr2"
exit2=$(cat "$TMPDIR_T/.exit")
head2=$(cat "$TARGET/.git/HEAD" 2>/dev/null || echo missing)
uv_calls_after_2=$(wc -l < "$TMPDIR_T/uv.argv" 2>/dev/null | tr -d ' ')
: "${uv_calls_after_2:=0}"
# Add a synthetic new [project.scripts] entry to upstream so run 3 pulls it.
work3="$TMPDIR_T/work3"
"$REAL_GIT" clone --quiet "$FAKE_UPSTREAM" "$work3"
# Write pyproject.toml via printf to avoid heredoc temp-file creation (which
# requires CWD to be writable and fails when tests run from a locked-down CWD).
printf '%s\n' \
	'[project]' \
	'name = "cortex-command"' \
	'version = "0.1.0"' \
	'[project.scripts]' \
	'cortex = "cortex_command.cli:main"' \
	'cortex-new-script = "cortex_command.cli:main"' \
	> "$work3/pyproject.toml"
(
	cd "$work3"
	"$REAL_GIT" add pyproject.toml
	"$REAL_GIT" -c commit.gpgsign=false -c user.email=t@t -c user.name=t \
		commit --quiet -m "add new script entry"
	"$REAL_GIT" push --quiet origin HEAD:refs/heads/main
)
# Third run -- pulls new pyproject AND re-invokes `uv tool install ... --force`.
run_install "$TMPDIR_T/stdout3" "$TMPDIR_T/stderr3"
exit3=$(cat "$TMPDIR_T/.exit")
uv_calls_after_3=$(wc -l < "$TMPDIR_T/uv.argv" 2>/dev/null | tr -d ' ')
: "${uv_calls_after_3:=0}"
new_entry_present=0
if grep -q 'cortex-new-script' "$TARGET/pyproject.toml" 2>/dev/null; then
	new_entry_present=1
fi
ok=1
[[ $exit1 -eq 0 ]] || ok=0
[[ $exit2 -eq 0 ]] || ok=0
[[ $exit3 -eq 0 ]] || ok=0
[[ "$head1" = "$head2" ]] || ok=0
[[ $uv_calls_after_3 -gt $uv_calls_after_2 ]] || ok=0
[[ $new_entry_present -eq 1 ]] || ok=0
if [[ $ok -eq 1 ]]; then
	pass "install/R10-idempotent-rerun"
else
	fail "install/R10-idempotent-rerun" \
		"expected three exit-0 runs with stable .git/HEAD across (1)+(2) and uv re-invocation + new pyproject after (3); got exit1=$exit1, exit2=$exit2, exit3=$exit3, head1=$head1, head2=$head2, uv_calls=($uv_calls_after_1,$uv_calls_after_2,$uv_calls_after_3), new_entry=$new_entry_present, stderr3=$(cat "$TMPDIR_T/stderr3")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R11(a) -- failing CORTEX_REPO_URL -> exit 1 (not git's native 128).
# Point at a bogus file:// URL. normalize_repo_url treats this as shorthand and
# prepends https://github.com/, producing https://github.com/file:/.../bogus.git.git
# -- not a valid path, not routed by insteadOf, so git clone fails. run() catches
# the non-zero exit and re-exits 1.
# ---------------------------------------------------------------------------
new_sandbox
rm -rf "$TARGET"
# Override insteadOf so nothing resolves the failing URL; ensure clone fails.
: > "$GIT_CONFIG_GLOBAL"
export CORTEX_REPO_URL="file:///nonexistent/bogus.git"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
if [[ $exit_code -eq 1 ]]; then
	pass "install/R11-repo-failure-exit1"
else
	fail "install/R11-repo-failure-exit1" \
		"expected exit 1 for failing repo URL; got exit=$exit_code, stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R11(b) -- stubbed failing uv -> exit 1 (not uv's native code).
# ---------------------------------------------------------------------------
new_sandbox
rm -rf "$TARGET"
export STUB_UV_FAIL=1
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
if [[ $exit_code -eq 1 ]]; then
	pass "install/R11-uv-failure-exit1"
else
	fail "install/R11-uv-failure-exit1" \
		"expected exit 1 for failing uv; got exit=$exit_code, stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R19 -- no unwrapped git/curl/uv calls outside the run() wrapper body.
# Lint regex (POSIX-portable): grep lines starting with one of the three names,
# strip lines marked `# allow-direct`, strip lines that themselves begin with
# `run ` (i.e., the wrapper body containing the literal name).
# ---------------------------------------------------------------------------
unwrapped=$(grep -nE '^[[:space:]]*(git|curl|uv)[[:space:]]' "$INSTALL_SH" \
	| grep -v '# allow-direct' \
	| grep -v '^[[:space:]]*[0-9]*:[[:space:]]*run[[:space:]]' || true)
if [[ -z "$unwrapped" ]]; then
	pass "install/R19-no-unwrapped-subprocess-calls"
else
	fail "install/R19-no-unwrapped-subprocess-calls" \
		"found unwrapped git/curl/uv calls without # allow-direct: $unwrapped"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "$PASS_COUNT passed, $FAIL_COUNT failed (out of $TOTAL)"

if [[ $FAIL_COUNT -gt 0 ]]; then
	exit 1
fi
exit 0
