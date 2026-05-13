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

resolve_latest_tag() {
	url="$1"
	git ls-remote --tags --refs "$url" 2>/dev/null \
		| awk -F/ '{print $NF}' \
		| grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
		| sort -V \
		| tail -1
}

main() {
	resolved_url=$(normalize_repo_url)
	if [ -n "${CORTEX_INSTALL_TAG:-}" ]; then
		tag="$CORTEX_INSTALL_TAG"
	else
		tag=$(resolve_latest_tag "$resolved_url" || true)
		if [ -z "$tag" ]; then
			printf '[cortex-install] error: could not resolve latest release tag from %s; set CORTEX_INSTALL_TAG=vX.Y.Z to override\n' "$resolved_url" >&2
			exit 1
		fi
	fi
	command -v uv >/dev/null 2>&1 || install_uv
	log "resolved repo URL: $resolved_url"
	log "install tag: $tag"
	run env UV_PYTHON_DOWNLOADS=automatic uv tool install git+"${resolved_url}"@"${tag}" --force
	log "cortex CLI installed."
	log "plugin auto-registration is not yet automated -- see docs/setup.md for manual steps."
	log "if 'cortex' is not on your PATH, run 'uv tool update-shell' and reload your shell."
}

main "$@"
