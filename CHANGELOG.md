# Changelog

All notable changes to ks-gen are tracked here. Rule additions especially:
the catalog drives the audit story.

## [0.3.1](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.3.0...v0.3.1) (2026-06-07)


### Documentation

* add SECURITY, CONTRIBUTING, CODE_OF_CONDUCT ([c015ac1](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/c015ac1a779be26a86a9b759e70ee58c8f71a61d))
* fix going-public.md trigger-line count for CodeQL activation ([7b3cd9e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/7b3cd9e8075d5edf924d28157f4f2caa9628aecf))
* **github:** add issue forms and PR template ([2b31cd2](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/2b31cd27ef64f995d10318c03eee2946c439360a))
* going-public runbook for the visibility flip ([6a28a6e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/6a28a6e724f432eadbd14e577ec94913c8288f04))
* note Integration-actor bypass limit on personal-account repos ([a002171](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/a0021716b32e6250431ec294e5540f1b370c2098))
* **plan:** github-setup implementation plan (PR-A foundation + PR-B automation) ([771c8dc](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/771c8dcb3c3d20c5965d827a6a06f9ca7afeee25))
* **readme:** add CI, license, Python, release, issues badges ([f0fae1f](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/f0fae1f95be067a7c13427e07bb0e66d9e1326b6))
* **spec:** github setup — public-readiness, security, automation ([e26d3cd](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/e26d3cd56913fe3c1dcdb91e702c1d722838904a))

## [Unreleased]

### Added
- **`--fetch-remote-resources` on install-time oscap eval.** The
  chrooted `oscap xccdf eval --remediate` invocation now passes
  `--fetch-remote-resources`, so STIG rules whose OVAL definitions
  reference the AlmaLinux CVE feed
  (`https://security.almalinux.org/oval/org.almalinux.alsa-9.xml.bz2`) run
  at install time instead of silently skipping. Air-gapped
  (`hd:LABEL=`) installs will log a failed fetch but complete
  normally; OVAL-dependent rules skip cleanly. See MANUAL.md §10.
  Closes the last v0.1-era gap. Lint guards the flag's presence.
- **`hd:LABEL=` transport for oscap tailoring fetch.** The oscap `%post`
  block is now split into a `--nochroot` fetch stage and a chrooted
  eval stage. ISO-delivered bundles (`ks-gen iso`) now reach oscap
  remediation at install time; previously, install failed with
  `unsupported inst.ks transport`. HTTP delivery is unchanged
  operator-visibly. Closes the second of the two v0.1.x gaps queued
  before v0.2.0.
- `unattended_updates` rule + `overrides.unattended_updates` config block.
  Configures `dnf-automatic` for nightly security updates and monthly full
  updates, plus a `needs-restarting`-driven reboot timer scoped to an
  operator-defined maintenance window. Defaults: nightly 02:00, monthly
  full first Sunday 02:30, reboot Sundays 03:00 — all host-local time and
  overridable per host. `dnf-automatic` and `dnf-utils` added to required
  package defaults.

## [0.1.0] — 2026-06-01

### Added
- Initial implementation per design spec.
- 12 override rules: admin_user_and_keys, ssh_keep_open, ssh_config_apply,
  faillock_safety, crypto_policy, banner_text, time_servers, dod_root_ca,
  auditd_actions, usbguard, kernel_module_blacklist, package_purge.
- CLI subcommands: new, gen, iso, lint, rules, schema.
- Four golden snapshots: minimal-dhcp, stig-strict, modern-crypto, bare-metal-usbguard.

### Changed
- Drop `%addon org_fedora_oscap` and the `oscap-anaconda-addon` package.
  The addon's "supplied content" model didn't accommodate ks-gen's per-host
  tailoring — files written to its staging directory weren't registered
  unless they came through the addon's own content-handling pipeline. The
  kickstart now emits a leading `%post` block that curls `tailoring.xml`
  from the same URL `inst.ks=` used and runs `oscap xccdf eval --remediate
  --tailoring-file /root/tailoring.xml ...` directly. `tailoring.xml`,
  the oscap remediation report, and the ARF results all persist on the
  installed FS under `/root/` for later audit. HTTP delivery only in v0.1;
  `hd:LABEL=` / `ks-gen iso` punted to v0.2.
