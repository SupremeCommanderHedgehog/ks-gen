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
#     ssg-almalinux10-ds.xml  ssg-ubuntu2404-ds.xml
#     shipping-versions.txt   (the "<label> package: <file>" lines, for reuse)
#
# Exit codes: 0 success, 3 fetch/extract failure (never confuse this with
# "content drifted" — a network blip must not read as a content change).
#
# Prerequisites: curl, rpm2cpio, cpio, dpkg-deb, gzip, sort -V.
# On Ubuntu/WSL: sudo apt install -y rpm2cpio cpio  (dpkg-deb is preinstalled).

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

# Ubuntu ships SSG as ssg-debderived in noble's universe pool; take the highest
# version the pool index lists.
fetch_ubuntu() {
	local label=ubuntu2404 ds=ssg-ubuntu2404-ds.xml
	local pool="http://archive.ubuntu.com/ubuntu/pool/universe/s/scap-security-guide"

	curl -fsSL -o "$WORK/$label-pool.html" "$pool/" ||
		die "$label: could not list $pool/"

	local deb
	deb=$(grep -o 'ssg-debderived_[0-9.]*-[0-9]*_all\.deb' "$WORK/$label-pool.html" |
		sort -u -V | tail -1) || true
	[ -n "$deb" ] || die "$label: no ssg-debderived deb listed at $pool/"

	curl -fsSL -o "$WORK/$label.deb" "$pool/$deb" ||
		die "$label: download failed for $pool/$deb"

	mkdir -p "$WORK/$label-ex"
	dpkg-deb -x "$WORK/$label.deb" "$WORK/$label-ex" ||
		die "$label: could not unpack $deb"
	[ -s "$WORK/$label-ex/$CONTENT_DIR/$ds" ] || die "$label: $ds missing or empty in $deb"

	cp "$WORK/$label-ex/$CONTENT_DIR/$ds" "$OUT_DIR/$ds"
	note_version "$label" "$deb"
}

for tool in curl rpm2cpio cpio dpkg-deb gunzip; do
	command -v "$tool" >/dev/null 2>&1 || die "missing prerequisite: $tool"
done

fetch_alma 8 alma8
fetch_alma 9 alma9
fetch_alma 10 alma10
fetch_ubuntu

echo "datastreams written to $OUT_DIR"
