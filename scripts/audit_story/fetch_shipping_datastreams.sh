#!/usr/bin/env bash
#
# Download the *currently shipping* SSG datastream for every ks-gen target and
# report the exact package version behind each one.
#
# Humans re-extracting after an SSG bump and the `ssg-drift.yml` workflow both
# run this, so the recipe cannot rot in prose (#90).
#
# Usage:
#     scripts/audit_story/fetch_shipping_datastreams.sh [OUT_DIR]
#     OUT_DIR=/tmp/ds scripts/audit_story/fetch_shipping_datastreams.sh
#
# Writes into OUT_DIR (default ./ssg-datastreams):
#     ssg-almalinux8-ds.xml   ssg-almalinux9-ds.xml
#     ssg-almalinux10-ds.xml
#     shipping-versions.txt   (the "<label> package: <file>" lines, for reuse)
#
# Exit codes: 0 success, 3 fetch/extract failure (never confuse this with
# "content drifted" — a network blip must not read as a content change).
#
# Prerequisites: curl, rpm2cpio, cpio, gzip, sort -V.
# On a Debian-family workstation/WSL: sudo apt install -y rpm2cpio cpio

set -Eeuo pipefail

OUT_DIR="${1:-${OUT_DIR:-$PWD/ssg-datastreams}}"
CONTENT_DIR=usr/share/xml/scap/ssg/content

die() {
	echo "FETCH FAILURE: $*" >&2
	exit 3
}
# -E propagates this into functions, so any unhandled failure exits 3.
trap 'die "unexpected failure at line $LINENO"' ERR

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$OUT_DIR"
VERSIONS="$OUT_DIR/shipping-versions.txt"
: >"$VERSIONS"

# Record and announce which package a datastream came from.
note_version() {
	echo "$1 package: $2" | tee -a "$VERSIONS"
}

# Pick the highest scap-security-guide RPM in an AlmaLinux release's AppStream
# repo, then pull just the one datastream member out of it — the RPM also
# carries ssg-firefox-ds.xml and friends, which the extractor must never see.
fetch_alma() {
	local rel="$1" label="$2" ds="ssg-almalinux${1}-ds.xml"
	local base="https://repo.almalinux.org/almalinux/${rel}/AppStream/x86_64/os"

	# Download before grepping: `curl | grep | head` would SIGPIPE curl and
	# pipefail would then report a network failure that did not happen.
	curl -fsSL -o "$WORK/$label-repomd.xml" "$base/repodata/repomd.xml" ||
		die "$label: could not download $base/repodata/repomd.xml"

	local pri
	pri=$(grep -o 'repodata/[a-f0-9]*-primary\.xml\.gz' "$WORK/$label-repomd.xml" |
		sort -u | tail -1) || true
	[ -n "$pri" ] || die "$label: no primary.xml.gz in $base/repodata/repomd.xml"

	curl -fsSL "$base/$pri" | gunzip >"$WORK/$label-primary.xml" ||
		die "$label: could not download or decompress $base/$pri"

	# [0-9] after the name so scap-security-guide-doc can't win the sort.
	local href
	href=$(grep -o "Packages/scap-security-guide-[0-9][^\"]*\.noarch\.rpm" \
		"$WORK/$label-primary.xml" | sort -u -V | tail -1) || true
	[ -n "$href" ] || die "$label: no scap-security-guide RPM in $base"

	curl -fsSL -o "$WORK/$label.rpm" "$base/$href" ||
		die "$label: download failed for $base/$href"

	mkdir -p "$WORK/$label-ex"
	(cd "$WORK/$label-ex" && rpm2cpio "$WORK/$label.rpm" |
		cpio -id --quiet "./$CONTENT_DIR/$ds") ||
		die "$label: could not extract $ds from $href"
	[ -s "$WORK/$label-ex/$CONTENT_DIR/$ds" ] || die "$label: $ds missing or empty in $href"

	cp "$WORK/$label-ex/$CONTENT_DIR/$ds" "$OUT_DIR/$ds"
	note_version "$label" "${href##*/}"
}

for tool in curl rpm2cpio cpio gunzip; do
	command -v "$tool" >/dev/null 2>&1 || die "missing prerequisite: $tool"
done

fetch_alma 8 alma8
fetch_alma 9 alma9
fetch_alma 10 alma10

echo "datastreams written to $OUT_DIR"
