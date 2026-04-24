#!/bin/sh
set -eu

log() {
	printf '[cortex-install] %s\n' "$*" >&2
}

run() {
	if ! "$@"; then
		printf '[cortex-install] error: command failed: %s\n' "$*" >&2
		exit 1
	fi
}

install_uv() {
	tmp=$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/cortex-uv-install.$$")
	run curl -LsSf https://astral.sh/uv/install.sh -o "$tmp"
	run sh "$tmp"
	rm -f "$tmp"
	PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
	export PATH
}

normalize_repo_url() {
	url="${CORTEX_REPO_URL:-charleshall888/cortex-command}"
	case "$url" in
		git@*:*/*)
			printf '%s\n' "$url"
			;;
		ssh://*|https://*|http://*)
			printf '%s\n' "$url"
			;;
		*)
			printf 'https://github.com/%s.git\n' "$url"
			;;
	esac
}

main() {
	resolved_url=$(normalize_repo_url)
	target=${CORTEX_COMMAND_ROOT:-$HOME/.cortex}
	if ! command -v just >/dev/null 2>&1; then
		case "$(uname)" in
			Darwin)
				log "'just' is required. Install with: brew install just"
				;;
			*)
				log "'just' is required. Install with: apt install just (or: brew install just)"
				;;
		esac
		exit 1
	fi
	command -v uv >/dev/null 2>&1 || install_uv
	log "resolved repo URL: $resolved_url"
	log "target path: $target"
	if [ ! -e "$target" ]; then
		run git clone --quiet "$resolved_url" "$target"
	else
		if [ -d "$target/.git" ]; then
			existing_origin=$(git -C "$target" remote get-url origin 2>/dev/null || echo "")  # allow-direct
			if [ "$existing_origin" = "$resolved_url" ]; then
				dirty=$(git -C "$target" status --porcelain)  # allow-direct
				if [ -n "$dirty" ]; then
					log "uncommitted changes in $target; commit or stash before re-installing (or use 'cortex upgrade' after committing)"
					exit 1
				fi
				run git -C "$target" fetch --quiet origin
				run git -C "$target" pull --ff-only --quiet
			else
				log "origin URL mismatch at $target: existing origin '$existing_origin' vs resolved '$resolved_url'; run 'git -C \"$target\" remote set-url origin \"$resolved_url\"' OR 'mv \"$target\" \"$target.old\"' and re-run"
				exit 1
			fi
		else
			log "refusing to overwrite: $target exists but is not a git repo"
			exit 1
		fi
	fi
}

main "$@"
