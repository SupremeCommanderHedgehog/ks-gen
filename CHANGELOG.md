# Changelog

All notable changes to ks-gen are tracked here. Rule additions especially:
the catalog drives the audit story.

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
