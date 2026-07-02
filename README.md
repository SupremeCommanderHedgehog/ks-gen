# ks-gen — remote-safe DISA STIG kickstart generator for AlmaLinux 9

[![ci](https://github.com/SupremeCommanderHedgehog/ks-gen/actions/workflows/ci.yml/badge.svg)](https://github.com/SupremeCommanderHedgehog/ks-gen/actions/workflows/ci.yml)
[![License: GPL v3+](https://img.shields.io/badge/License-GPLv3+-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://pypi.org/project/ks-gen/)
[![Latest release](https://img.shields.io/github/v/release/SupremeCommanderHedgehog/ks-gen?display_name=tag&sort=semver)](https://github.com/SupremeCommanderHedgehog/ks-gen/releases/latest)
[![Open issues](https://img.shields.io/github/issues/SupremeCommanderHedgehog/ks-gen)](https://github.com/SupremeCommanderHedgehog/ks-gen/issues)

`ks-gen` turns a small YAML file into a fully baked AlmaLinux 9 kickstart that:

- Applies the upstream DISA STIG profile via `scap-security-guide` + `oscap xccdf eval --remediate` from a `%post` block.
- Stays remote-safe by default — won't lock you out of a cloud or headless box.
- Substitutes civilian text for DoD-specific banners, certificate bundles, time servers.
- Emits an `exceptions.md` audit report naming every XCCDF rule it disables and why.

See [`MANUAL.md`](MANUAL.md) for the operator's reference, or the design spec at
`docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md` for the rationale.

## Quickstart

```bash
pipx install .
ks-gen new --out ./build
# Walks you through a few prompts, writes ./build/<hostname>/{host.yaml,ks.cfg,tailoring.xml,exceptions.md}

ks-gen gen --config ./build/<hostname>/host.yaml --out ./build/<hostname>
ks-gen iso --src AlmaLinux-9-latest-x86_64-dvd.iso \
           --ks ./build/<hostname>/ks.cfg \
           --tailoring ./build/<hostname>/tailoring.xml \
           --out ./<hostname>-installer.iso
```

Delivery modes: HTTP (`inst.ks=http://…/ks.cfg`) or ISO
(`inst.ks=hd:LABEL=<volid>:/ks.cfg`, with the ISO from `ks-gen iso`).
Both run oscap remediation at install time; see `MANUAL.md` §5.4.

## Subcommands

| Command | Purpose |
|---|---|
| `ks-gen new` | Interactive wizard; produces the 4-file bundle |
| `ks-gen gen` | Non-interactive re-render from `host.yaml` |
| `ks-gen lint` | Validate a `ks.cfg` (ksvalidator + invariants) |
| `ks-gen iso` | Repackage the AlmaLinux DVD ISO with kickstart embedded |
| `ks-gen rules` | List the override rule catalog |
| `ks-gen schema` | Emit JSON Schema for `host.yaml` |
| `ks-gen verify --host <addr> --config <host.yaml>` | Re-run oscap on a deployed host, reconcile failures against `host.yaml`, report compliance + drift. Exits 0 on clean, 6 on failures, 7 on transport error. Pass `--check-tailoring` to also diff the deployed `/root/tailoring.xml` against your current `host.yaml` (exit 8 if drift is detected and compliance is otherwise clean). Use `--capture-baseline <path>` and `--baseline <path>` to reconcile against an operator-captured ARF instead of the install-time ARF. Defaults to passwordless `sudo -n`; pass `--ask-sudo-pass` to use password-based sudo (read from `KSGEN_SUDO_PASSWORD`, or prompted). |

## Exit codes

`0` success · `1` usage · `2` config invalid · `3` rule conflict · `4` lint failure · `5` external tool missing · `6` verify failures · `7` verify transport error · `8` verify tailoring drift.

## License

GPL-3.0-or-later, with an [output exception](LICENSE.exception) for the
kickstart files, tailoring XML, exception reports, and installer ISOs
that `ks-gen` produces — operators retain full discretion over how to
license and distribute their generated artifacts. See [`LICENSE`](LICENSE)
for the full GPL text. Aligned with `pykickstart` (GPL-2.0-or-later),
which `ks-gen` links against.
