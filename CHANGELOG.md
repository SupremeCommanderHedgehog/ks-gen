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

### Fixed
- `ks.cfg` now emits a `%pre` block that stages `tailoring.xml` at
  `/tailoring.xml` before `%addon` runs. Previously `oscap-anaconda-addon`
  found nothing at that path under both HTTP-served and `ks-gen iso`
  delivery, silently falling back to the unmodified base STIG profile.
  See `docs/superpowers/specs/2026-06-01-tailoring-pre-fetcher-design.md`.
