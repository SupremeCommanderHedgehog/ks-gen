# ks-gen — remote-safe DISA STIG kickstart generator for AlmaLinux 9

`ks-gen` turns a small YAML file into a fully baked AlmaLinux 9 kickstart that:

- Applies the upstream DISA STIG profile via `scap-security-guide` + `oscap-anaconda-addon`.
- Stays remote-safe by default — won't lock you out of a cloud or headless box.
- Substitutes civilian text for DoD-specific banners, certificate bundles, time servers.
- Emits an `exceptions.md` audit report naming every XCCDF rule it disables and why.

See the design spec at `docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md`.

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

## Subcommands

| Command | Purpose |
|---|---|
| `ks-gen new` | Interactive wizard; produces the 4-file bundle |
| `ks-gen gen` | Non-interactive re-render from `host.yaml` |
| `ks-gen lint` | Validate a `ks.cfg` (ksvalidator + invariants) |
| `ks-gen iso` | Repackage the AlmaLinux DVD ISO with kickstart embedded |
| `ks-gen rules` | List the override rule catalog |
| `ks-gen schema` | Emit JSON Schema for `host.yaml` |

## Exit codes

`0` success · `1` usage · `2` config invalid · `3` rule conflict · `4` lint failure · `5` external tool missing.

## v0.1 known limitations

- **`ks-gen iso` does not rewrite the ISO's bootloader.** It places `ks.cfg`
  and `tailoring.xml` at the ISO root, but the operator must type
  `inst.ks=hd:LABEL=<volid>:/ks.cfg` at the Anaconda boot prompt. Fully
  unattended installs from the generated ISO land in v0.2.
- **`disk.preset: custom`** is reserved for v0.2. Only `stig_server` and
  `minimal` are honored; selecting `custom` raises a config error.
- **Wizard (`ks-gen new`) covers system / user / SSH / crypto only.**
  Disk, network, and override-matrix tuning go through hand-edited
  `host.yaml` + `ks-gen gen` for now.

## License

Apache-2.0.
