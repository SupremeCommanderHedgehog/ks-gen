# Changelog

All notable changes to ks-gen are tracked here. Rule additions especially:
the catalog drives the audit story.

## [0.6.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.5.0...v0.6.0) (2026-06-08)


### Features

* **iso:** add unattended boot entry templates ([3a1dcd8](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/3a1dcd862d31f7779491aeb621c36acc5aa2517b))
* **iso:** rewrite_grub pure rewriter + golden snapshot ([925a302](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/925a30224e4636c230501ba2112973300952c7ca))
* **iso:** rewrite_isolinux pure rewriter + golden snapshot ([b90fffa](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/b90fffa978adcbd8e90d3fc5397f6ecd5b12fc14))
* **iso:** three-pass xorriso flow (extract, rewrite, author) ([d07ff2e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/d07ff2e23804b98488b1b11897a627ae6acebb48))


### Refactoring

* **iso:** promote iso.py to a package ([85994fc](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/85994fc1af72165bcaa0dcc4a926cf9ed5c91e32))


### Documentation

* **manual:** document unattended ISO boot, strike v0.1 limitation ([3b116ff](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/3b116ff792c9811bd5801e73634e3b0f85fa4871))
* **plans:** ISO unattended boot implementation plan ([425b28a](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/425b28ae1e5c09bf1019c3692ff64976cba0993b))
* **specs:** ISO unattended boot design ([3777dd1](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/3777dd1738ed16f3a620cd80f96578feec37161d))

## [0.5.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.4.0...v0.5.0) (2026-06-07)


### Features

* **config:** add DiskLuks model with internal validators ([65880c3](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/65880c32bcd0ae50ef0ea66d11788960b624b330)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **config:** add LuksPreset, TangServer, and Tang models ([b3b82b0](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/b3b82b09808730c72400b86394516b168dfc74cf)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **config:** mount DiskLuks on Disk + minimal+LUKS HostConfig validator ([24c334e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/24c334e1ddd24749aa386666ad7a52363c783759)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **disk_luks:** kickstart_passphrase_quoted helper ([e1cebe8](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/e1cebe8e8a90eb5c17dff31e4ebe14591d7bc669)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **disk_luks:** resolve_passphrase helper ([ea5b44d](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/ea5b44d52900c63b23ae59cbe65d6975fe31c157)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **skeleton:** register disk_luks helpers as Jinja globals ([08acaa5](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/08acaa5ff1f87be24592345a53e7553de88ae65f)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **templates:** _luks_flags.j2 macro ([3ee0be7](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/3ee0be7b16d3fd550e2d591f92f26f2a3b768cf1)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **templates:** luks_tang_bind.j2 partial + ks.cfg.j2 selector ([b69522c](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/b69522c1f3deeda17f1847eac4512caae6402142)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **templates:** wire luks_pv_flags into partitioning_layout.j2 ([5d4855b](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/5d4855b4134354cf8a7ef8dc10de4317fa7f1832)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **templates:** wire luks_pv_flags into partitioning_stig_server.j2 ([3664ba0](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/3664ba0ebf2c65911d527a7cfb264a6b453d3d72)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)


### Documentation

* **manual:** document disk.luks block ([d9c5039](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/d9c5039bfdeb4afb1b74f243ec280b1e3765f28c)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **manual:** replace stale 'LUKS not yet supported' note in disk.layout ([9961bf5](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/9961bf51473ca5c462dd06b3ee9fff2fbdeb98b4)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **plans:** LUKS presets implementation plan ([9fce355](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/9fce3559b8d47c9d89f8e082b00f53ab3984a3b6)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)
* **specs:** LUKS presets design ([2233c33](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/2233c33d4612396260acf1bc6993337db6146a16)), closes [#7](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/7)

## [0.4.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.3.0...v0.4.0) (2026-06-07)


### Features

* **config:** add DiskBootPart and DiskEfiPart models ([efb5ac7](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/efb5ac730ffc91818b1978979572471929a2de21)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **config:** add DiskLayout basic schema ([1422ffd](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/1422ffd2219059878788a7f63fafbe96a8b71d9e)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **config:** add DiskLvDef model ([0ab7d36](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/0ab7d36196d2892a76eb3c38fbf7016023a6ef4a)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **config:** Disk.preset becomes Optional, mutually exclusive with layout ([5ac9892](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/5ac989296d37a28c5d5aef8225d9103a2b8c6e8d)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **config:** DiskLayout rejects duplicate LV names and mounts ([87b7c07](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/87b7c07d20c0ca7eaeba435a17d1be023b98bff0)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **config:** DiskLayout validates required mountpoints + swap cardinality ([ddf4351](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/ddf435149591d08197059799d9c80b167bb71913)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **config:** DiskLayout validates swap consistency and custom-mount sizes ([17d95ee](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/17d95ee5fa94252444814e384a65ace812ee3e65)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **disk_layout:** effective_fsoptions helper + STIG defaults ([108a170](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/108a170f1480d6927c493cafb45e889f8eb3b225)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **disk_layout:** effective_size_mb helper + LV size defaults ([fd08e24](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/fd08e24c12991530cfe21bdd2ff139816bdce72a)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **disk_layout:** size_to_mb helper ([1608e9f](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/1608e9fa5e1cd8b13778b5fdc47c119a65778f49)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **skeleton:** register disk_layout helpers as Jinja globals ([f362df5](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/f362df544ed769eb475b35ff27ba96d2ffb4d9a3)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **templates:** partitioning_layout.j2 partial + selector ([19ab934](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/19ab9348126631cd57ee5f8831c592a6c7405903)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)


### Bug Fixes

* **templates:** preserve newlines between logvol lines in partitioning_layout.j2 ([0a33ec1](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/0a33ec176054570bfce9cc1b75550d1c948bf4df)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)


### Refactoring

* **disk_layout:** delegate effective_size_mb to size_to_mb, lift T unit ([6daa983](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/6daa9837e0f9bf764acf456468ded23d0cc37687)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)


### Documentation

* add SECURITY, CONTRIBUTING, CODE_OF_CONDUCT ([c015ac1](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/c015ac1a779be26a86a9b759e70ee58c8f71a61d))
* **config:** explain mode='before' rationale + breadcrumb for Task 13 ([d8bb5ba](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/d8bb5baeaa41c6a0adc3161516be33249692fe6d)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* fix going-public.md trigger-line count for CodeQL activation ([7b3cd9e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/7b3cd9e8075d5edf924d28157f4f2caa9628aecf))
* **github:** add issue forms and PR template ([2b31cd2](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/2b31cd27ef64f995d10318c03eee2946c439360a))
* going-public runbook for the visibility flip ([6a28a6e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/6a28a6e724f432eadbd14e577ec94913c8288f04))
* **going-public:** note Code Scanning prereq for codeql smoke-test ([bcbcfbf](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/bcbcfbfbef9aa347f57380566cff1e827063cb44))
* **manual:** document disk.layout block ([14f246b](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/14f246ba74993c13b07951e8912274e7a640239f)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **manual:** nest disk.layout under §4.4 as H4 ([75f49c9](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/75f49c9a273d09591e7267839e2324d48512e8e1)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* note Integration-actor bypass limit on personal-account repos ([a002171](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/a0021716b32e6250431ec294e5540f1b370c2098))
* **plan:** github-setup implementation plan (PR-A foundation + PR-B automation) ([771c8dc](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/771c8dcb3c3d20c5965d827a6a06f9ca7afeee25))
* **plans:** disk.layout block implementation plan ([e552392](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/e552392054b83132787f400f34c45bec6c3840d0)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **readme:** add CI, license, Python, release, issues badges ([f0fae1f](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/f0fae1f95be067a7c13427e07bb0e66d9e1326b6))
* **spec:** github setup — public-readiness, security, automation ([e26d3cd](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/e26d3cd56913fe3c1dcdb91e702c1d722838904a))
* **specs:** disk.layout block design ([dd69aec](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/dd69aec9869d6d294bea1d587828767167f70f32)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)
* **templates:** explain the trim_blocks workaround + drop unused snapshot arg ([613ab13](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/613ab13c59d8ff1870c1c5799c0bd71086c781c9)), closes [#8](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/8)

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
