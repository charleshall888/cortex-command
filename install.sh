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

main() {
	:
}

main "$@"
