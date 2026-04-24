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
	log "resolved repo URL: $resolved_url"
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
}

main "$@"
