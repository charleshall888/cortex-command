#!/bin/bash
# tests/test_install.sh -- install.sh integration tests
#
# The non-editable-wheel-install migration (lifecycle 141) replaced
# install.sh's clone-and-editable-install flow with a thin bootstrap that
# (1) ensures `uv` is on PATH, (2) calls `uv tool install
# git+<url>@<tag> --force`, and (3) prints next-step guidance. These tests
# exercise the simplified surface; the obsolete clone-management,
# dirty-tree, and just-precondition tests from the old surface have been
# retired with the underlying behavior.
#
# Hermetic: PATH-mocked uv/curl stubs so no real network or system tool is
# touched. The stubs append every argv they see to per-test log files
# under $STUB_LOG_DIR.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
FIXTURE_BIN="$REPO_ROOT/tests/fixtures/install/bin"

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

# SKIP: increments neither counter. Use when a prerequisite tool is
# missing (e.g., shellcheck on a dev machine).
skip() {
	echo "SKIP $1: $2"
}

# ---------------------------------------------------------------------------
# Test: shellcheck -s sh install.sh
# Placed FIRST so a bashism fails fast rather than surfacing downstream as
# opaque stub errors. SKIP if shellcheck is not installed.
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
# Each test calls new_sandbox to set up a fresh tmpdir + HOME + PATH-mocked
# bin directory. State is per-test so cross-test leakage is impossible.
new_sandbox() {
	TMPDIR_T="$(mktemp -d "${TMPDIR:-/tmp}/test_install_XXXXXX")"
	HOME_SANDBOX="$TMPDIR_T/home"
	mkdir -p "$HOME_SANDBOX/.local/bin"
	export HOME="$HOME_SANDBOX"
	mkdir -p "$TMPDIR_T/bin"
	cp "$FIXTURE_BIN/uv" "$TMPDIR_T/bin/uv"
	cp "$FIXTURE_BIN/curl" "$TMPDIR_T/bin/curl"
	chmod +x "$TMPDIR_T/bin/uv" "$TMPDIR_T/bin/curl"
	export STUB_LOG_DIR="$TMPDIR_T"
	export STUB_UV_SOURCE="$FIXTURE_BIN/uv"
	# /usr/bin and /bin stay on PATH for sh, mktemp, command, etc.
	export PATH="$TMPDIR_T/bin:/usr/bin:/bin"
	# Default: stubs not in failure mode.
	unset STUB_UV_FAIL STUB_CURL_FAIL
	# Default: no install-tag override (install.sh defaults to v0.1.0).
	unset CORTEX_INSTALL_TAG
	unset CORTEX_REPO_URL
}

cleanup_sandbox() {
	if [[ -n "${TMPDIR_T:-}" && -d "$TMPDIR_T" ]]; then
		rm -rf "$TMPDIR_T"
	fi
}

# Run install.sh capturing stdout/stderr/exit independently.
run_install() {
	local out_stdout="$1"
	local out_stderr="$2"
	"$INSTALL_SH" >"$out_stdout" 2>"$out_stderr"
	echo $? > "$TMPDIR_T/.exit"
}

# ---------------------------------------------------------------------------
# Test: R2 — when `uv` is absent, the curl-installer bootstrap runs and
# leaves a usable uv at $HOME/.local/bin/uv before the tool-install step.
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
# Test: happy-path — invokes `uv tool install git+<url>@<tag> --force`
# with the default repo + tag.
# ---------------------------------------------------------------------------
new_sandbox
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
uv_argv=$(cat "$TMPDIR_T/uv.argv" 2>/dev/null || echo "")
ok=1
[[ $exit_code -eq 0 ]] || ok=0
[[ "$uv_argv" == *"tool install"* ]] || ok=0
[[ "$uv_argv" == *"git+https://github.com/charleshall888/cortex-command.git@v0.1.0"* ]] || ok=0
[[ "$uv_argv" == *"--force"* ]] || ok=0
if [[ $ok -eq 1 ]]; then
	pass "install/happy-path-default-tag"
else
	fail "install/happy-path-default-tag" \
		"expected exit 0 with `uv tool install git+...@v0.1.0 --force`; got exit=$exit_code, uv.argv=$uv_argv, stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: CORTEX_INSTALL_TAG override — tag flows into the uv argv.
# ---------------------------------------------------------------------------
new_sandbox
export CORTEX_INSTALL_TAG="v9.9.9-rc.42"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
uv_argv=$(cat "$TMPDIR_T/uv.argv" 2>/dev/null || echo "")
if [[ $exit_code -eq 0 && "$uv_argv" == *"@v9.9.9-rc.42"* ]]; then
	pass "install/cortex-install-tag-override"
else
	fail "install/cortex-install-tag-override" \
		"expected exit 0 with `@v9.9.9-rc.42` in uv argv; got exit=$exit_code, uv.argv=$uv_argv, stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: CORTEX_REPO_URL shorthand normalization — `<owner>/<repo>` becomes
# `https://github.com/<owner>/<repo>.git` in the resolved URL log line.
# ---------------------------------------------------------------------------
new_sandbox
export CORTEX_REPO_URL="someone/different-fork"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
stderr_content=$(cat "$TMPDIR_T/stderr")
if [[ $exit_code -eq 0 \
	&& "$stderr_content" == *"https://github.com/someone/different-fork.git"* ]]; then
	pass "install/cortex-repo-url-shorthand-expansion"
else
	fail "install/cortex-repo-url-shorthand-expansion" \
		"expected normalized URL in stderr; got exit=$exit_code, stderr=$stderr_content"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: CORTEX_REPO_URL passthrough — full URLs (https/ssh/git@) flow
# through verbatim.
# ---------------------------------------------------------------------------
new_sandbox
export CORTEX_REPO_URL="git@github.com:fork-owner/cortex-command.git"
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
stderr_content=$(cat "$TMPDIR_T/stderr")
if [[ $exit_code -eq 0 \
	&& "$stderr_content" == *"git@github.com:fork-owner/cortex-command.git"* ]]; then
	pass "install/cortex-repo-url-ssh-passthrough"
else
	fail "install/cortex-repo-url-ssh-passthrough" \
		"expected verbatim ssh URL in stderr; got exit=$exit_code, stderr=$stderr_content"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R7 — pre-tool-install stderr ordering. The resolved-URL log line
# must appear BEFORE any uv invocation. Verified by line-number comparison
# within stderr (uv runs silently when stubbed, so we instead verify the
# log line precedes the install-completion log line).
# ---------------------------------------------------------------------------
new_sandbox
run_install "$TMPDIR_T/stdout" "$TMPDIR_T/stderr"
exit_code=$(cat "$TMPDIR_T/.exit")
url_line=$(grep -n '\[cortex-install\] resolved repo URL' "$TMPDIR_T/stderr" | head -1 | cut -d: -f1)
tag_line=$(grep -n '\[cortex-install\] install tag' "$TMPDIR_T/stderr" | head -1 | cut -d: -f1)
done_line=$(grep -n '\[cortex-install\] cortex CLI installed' "$TMPDIR_T/stderr" | head -1 | cut -d: -f1)
ok=1
if [[ $exit_code -ne 0 || -z "$url_line" || -z "$tag_line" || -z "$done_line" ]]; then
	ok=0
elif (( url_line >= done_line )) || (( tag_line >= done_line )); then
	ok=0
fi
if [[ $ok -eq 1 ]]; then
	pass "install/R7-pre-tool-install-stderr-ordering"
else
	fail "install/R7-pre-tool-install-stderr-ordering" \
		"expected URL+tag log lines before completion line; got exit=$exit_code, url_line=$url_line, tag_line=$tag_line, done_line=$done_line, stderr=$(cat "$TMPDIR_T/stderr")"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R10 — idempotent re-run. Two consecutive invocations both exit 0
# and each calls `uv tool install ... --force`, so the second run picks
# up any upstream changes via the --force-driven entry-point regeneration.
# ---------------------------------------------------------------------------
new_sandbox
run_install "$TMPDIR_T/stdout1" "$TMPDIR_T/stderr1"
exit1=$(cat "$TMPDIR_T/.exit")
calls_after_1=$(wc -l < "$TMPDIR_T/uv.argv" 2>/dev/null | tr -d ' ')
: "${calls_after_1:=0}"
run_install "$TMPDIR_T/stdout2" "$TMPDIR_T/stderr2"
exit2=$(cat "$TMPDIR_T/.exit")
calls_after_2=$(wc -l < "$TMPDIR_T/uv.argv" 2>/dev/null | tr -d ' ')
: "${calls_after_2:=0}"
ok=1
[[ $exit1 -eq 0 && $exit2 -eq 0 ]] || ok=0
[[ $calls_after_2 -gt $calls_after_1 ]] || ok=0
if [[ $ok -eq 1 ]]; then
	pass "install/R10-idempotent-rerun"
else
	fail "install/R10-idempotent-rerun" \
		"expected two exit-0 runs with uv re-invoked; got exit1=$exit1, exit2=$exit2, calls=($calls_after_1,$calls_after_2)"
fi
cleanup_sandbox

# ---------------------------------------------------------------------------
# Test: R11 — failing uv -> exit 1 (not uv's native code). The run() wrapper
# catches non-zero exits and re-exits with the canonical 1.
# ---------------------------------------------------------------------------
new_sandbox
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
# Test: R19 — no unwrapped git/curl/uv calls outside the run() wrapper body.
# Lint regex: grep lines starting with one of the three names, strip lines
# marked `# allow-direct`, strip lines that themselves begin with `run `
# (the wrapper body containing the literal name).
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
