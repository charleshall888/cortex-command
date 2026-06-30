#!/usr/bin/env bash
# PATH-injected `gh` stub for tests/test_runner_pr_gating.py.
#
# Dispatches on the first two positional arguments. Reads $GH_STUB_SCENARIO
# (default: empty) to pick a canned response for `gh pr view --head ...`.
# For `gh pr ready` (and `gh pr ready --undo`), picks behavior based on
# $GH_STUB_READY_MODE (default: ok).
#
# Scenarios for `gh pr view`:
#   open-ready-mismatch         -> {"url":"https://example.test/pr/1","isDraft":false,"state":"OPEN"}
#                                  (merged>0 intended=false matches, merged=0 intended=true MISMATCHES)
#   open-draft-mismatch         -> {"url":"https://example.test/pr/1","isDraft":true,"state":"OPEN"}
#                                  (merged=0 intended=true matches, merged>0 intended=false MISMATCHES)
#   merged                      -> {"url":"https://example.test/pr/1","isDraft":false,"state":"MERGED"}
#   closed                      -> {"url":"https://example.test/pr/1","isDraft":false,"state":"CLOSED"}
#   <empty / unset>             -> empty stdout, exit 1 (no PR found)
#
# Additive scenarios for `gh pr view <number> --json state,mergedAt` (the
# cortex-lifecycle-complete-route verb's Branch-4 query — see #331 Task 2/3).
# These carry `state` + `mergedAt` (not url/isDraft) to match the verb's
# --json field list; the verb parses only `state`, mergedAt is carried for
# golden-table fidelity:
#   open-anchored               -> {"state":"OPEN","mergedAt":null}        (drives Branch 4c)
#   merged-anchored             -> {"state":"MERGED","mergedAt":"2026-06-29T00:00:00Z"} (4d/4e/4f; git state decides)
#   closed-unmerged             -> {"state":"CLOSED","mergedAt":null}      (drives Branch 4g)
#
# Modes for `gh pr ready` / `gh pr ready --undo`:
#   ok (default) -> exit 0, empty stderr
#   transient    -> exit 1, stderr contains "HTTP 429 rate limit exceeded"
#   persistent   -> exit 1, stderr contains "HTTP 401 unauthorized"
#
# ---------------------------------------------------------------------------
# Additive surface for the cortex-lifecycle-complete-route verb (#331 Task 2).
# All gated behind NEW $GH_STUB_* env vars that default to a backward-compatible
# value, so tests/test_runner_pr_gating.py (which sets none of them) is unchanged.
#
#   $GH_STUB_VIEW_FAIL (default: "" -> fall through to $GH_STUB_SCENARIO)
#     Failure dimension for `gh pr view`, layered ABOVE the success scenarios:
#       network  -> exit 1, network/auth stderr (NOT a "could not resolve"
#                   pattern) -> verb routes to Branch 4a (pr_unknown)
#       notfound -> exit 1, stderr "Could not resolve to a PullRequest with the
#                   number of <n>" + "GraphQL: not found" -> verb routes to 4b
#
#   $GH_STUB_PR_LIST_COUNT (default: 0)
#     Controls `gh pr list --head ... --json number,state,mergedAt`:
#       0 -> []   1 -> one object   N -> N objects
#     Emits [{"number":<i>,"state":"OPEN","mergedAt":null}, ...] (i = 1..N).
#
#   $GH_STUB_REPO (default: owner/repo)
#     Value emitted by `gh repo view --json nameWithOwner [-q .nameWithOwner]`.
#     Mimics real gh: bare value when -q/--jq is present (the verb passes
#     `-q .nameWithOwner` and parses stdout.strip()); JSON object otherwise.
#
#   $GH_STUB_AUTH (default: ok)
#     Controls `gh auth status`:  ok -> exit 0;  fail -> exit 1 + auth stderr.
#
# All other gh invocations exit 0 with empty output (harmless).

set -u

cmd="${1:-}"
sub="${2:-}"

case "$cmd" in
    pr)
        case "$sub" in
            view)
                # Failure dimension (new, #331). Layered above the success
                # scenarios; empty default means existing consumers (which do
                # not set it) fall straight through to $GH_STUB_SCENARIO.
                view_fail="${GH_STUB_VIEW_FAIL:-}"
                case "$view_fail" in
                    network)
                        printf '%s\n' 'error connecting to api.github.com: dial tcp: network is unreachable' >&2
                        exit 1
                        ;;
                    notfound)
                        num="${3:-0}"
                        printf '%s\n' "Could not resolve to a PullRequest with the number of ${num}." >&2
                        printf '%s\n' 'GraphQL: not found' >&2
                        exit 1
                        ;;
                esac
                scenario="${GH_STUB_SCENARIO:-}"
                case "$scenario" in
                    open-ready-mismatch)
                        printf '%s\n' '{"url":"https://example.test/pr/1","isDraft":false,"state":"OPEN"}'
                        exit 0
                        ;;
                    open-draft-mismatch)
                        printf '%s\n' '{"url":"https://example.test/pr/1","isDraft":true,"state":"OPEN"}'
                        exit 0
                        ;;
                    merged)
                        printf '%s\n' '{"url":"https://example.test/pr/1","isDraft":false,"state":"MERGED"}'
                        exit 0
                        ;;
                    closed)
                        printf '%s\n' '{"url":"https://example.test/pr/1","isDraft":false,"state":"CLOSED"}'
                        exit 0
                        ;;
                    open-anchored)
                        printf '%s\n' '{"state":"OPEN","mergedAt":null}'
                        exit 0
                        ;;
                    merged-anchored)
                        printf '%s\n' '{"state":"MERGED","mergedAt":"2026-06-29T00:00:00Z"}'
                        exit 0
                        ;;
                    closed-unmerged)
                        printf '%s\n' '{"state":"CLOSED","mergedAt":null}'
                        exit 0
                        ;;
                    *)
                        # No scenario -> pretend no PR exists
                        exit 1
                        ;;
                esac
                ;;
            ready)
                mode="${GH_STUB_READY_MODE:-ok}"
                case "$mode" in
                    ok)
                        exit 0
                        ;;
                    transient)
                        printf '%s\n' 'HTTP 429: rate limit exceeded' >&2
                        exit 1
                        ;;
                    persistent)
                        printf '%s\n' 'HTTP 401: unauthorized' >&2
                        exit 1
                        ;;
                    *)
                        exit 0
                        ;;
                esac
                ;;
            list)
                # `gh pr list --head ... --json number,state,mergedAt` for the
                # complete-route orphan probe (#331). Count controls match arity.
                count="${GH_STUB_PR_LIST_COUNT:-0}"
                out="["
                i=1
                while [ "$i" -le "$count" ]; do
                    if [ "$i" -gt 1 ]; then
                        out="${out},"
                    fi
                    out="${out}{\"number\":${i},\"state\":\"OPEN\",\"mergedAt\":null}"
                    i=$((i + 1))
                done
                out="${out}]"
                printf '%s\n' "$out"
                exit 0
                ;;
            create)
                # Not expected to be invoked in dry-run mode (runner wraps it
                # in dry_run_echo); if it is, emit a fake URL so the success
                # branch is taken and no recovery path triggers.
                printf '%s\n' 'https://example.test/pr/created'
                exit 0
                ;;
            *)
                exit 0
                ;;
        esac
        ;;
    repo)
        case "$sub" in
            view)
                # `gh repo view --json nameWithOwner [-q .nameWithOwner]` for the
                # complete-route Branch-3 repo resolution (#331). Mimic real gh:
                # bare value when a jq filter (-q/--jq) is present, else JSON.
                repo="${GH_STUB_REPO:-owner/repo}"
                jq_mode=0
                for a in "$@"; do
                    case "$a" in
                        -q|--jq)
                            jq_mode=1
                            ;;
                    esac
                done
                if [ "$jq_mode" -eq 1 ]; then
                    printf '%s\n' "$repo"
                else
                    printf '%s\n' "{\"nameWithOwner\":\"${repo}\"}"
                fi
                exit 0
                ;;
            *)
                exit 0
                ;;
        esac
        ;;
    auth)
        case "$sub" in
            status)
                # `gh auth status` for the complete-route Branch-4 auth gate
                # (#331). Default ok keeps the prior no-op exit-0 behavior.
                auth="${GH_STUB_AUTH:-ok}"
                case "$auth" in
                    ok)
                        exit 0
                        ;;
                    fail)
                        printf '%s\n' 'You are not logged into any GitHub hosts. Run gh auth login to authenticate.' >&2
                        exit 1
                        ;;
                    *)
                        exit 0
                        ;;
                esac
                ;;
            *)
                exit 0
                ;;
        esac
        ;;
    *)
        # Any other gh command: harmless no-op.
        exit 0
        ;;
esac
