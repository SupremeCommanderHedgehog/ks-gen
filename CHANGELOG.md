# Changelog

All notable changes to ks-gen are tracked here. Rule additions especially:
the catalog drives the audit story.

## [0.29.3](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.29.2...v0.29.3) (2026-06-27)


### Documentation

* add container-host preset design + implementation plan ([#66](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/66)) ([#142](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/142)) ([62b599f](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/62b599fa750aba9d7865812d900f84d861c72830))

## [0.29.2](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.29.1...v0.29.2) (2026-06-27)


### Bug Fixes

* **writer:** satisfy CodeQL mixed-returns on build_bundle ([#137](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/137)) ([343abbd](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/343abbd29388bf7555581959feb360b1526d44b2))

## [0.29.1](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.29.0...v0.29.1) (2026-06-20)


### Bug Fixes

* **config:** normalize Packages fields when preset=lean ([#134](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/134)) ([#135](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/135)) ([84a460b](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/84a460b0b6651c03e85712b108dd4dcde9cffc79))

## [0.29.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.28.0...v0.29.0) (2026-06-20)


### Features

* **rules:** alma8 crypto_policy divergence + alma9 SSG-drift sweep ([#127](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/127) PR B) ([#132](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/132)) ([ce88b84](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/ce88b84747e18b8ac6ebd03061672f1a0ef3ffd6))

## [0.28.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.27.0...v0.28.0) (2026-06-20)


### Features

* **rules/ubuntu2404:** wire emit_tailoring + exception_entry ([#127](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/127) PR A) ([#130](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/130)) ([2f7dbfe](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/2f7dbfe3b5235023f1a054339660bb7d6758670d))

## [0.27.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.26.0...v0.27.0) (2026-06-20)


### Features

* **audit-story:** phase 1 — SSG datastream rule-ID introspection ([#127](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/127)) ([#128](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/128)) ([92c7c48](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/92c7c483335fb273190fd511cc21b4b4f7ca128f))

## [0.26.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.25.0...v0.26.0) (2026-06-20)


### Features

* **rules/alma8:** phase 2 — re-export all 15 alma9 rules ([#121](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/121) phase 2) ([#124](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/124)) ([5a436eb](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/5a436ebc9f844c470b805a8c437cf9ec4a5283e0))

## [0.25.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.24.0...v0.25.0) (2026-06-20)


### Features

* **distro:** add alma8 — schema + dispatch ([#121](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/121) phase 1) ([#122](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/122)) ([f83399c](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/f83399c857e09bb0585d381edf72801a7e3aad44))

## [0.24.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.23.0...v0.24.0) (2026-06-20)


### Features

* **rules/ubuntu2404:** data_disks_preserve + container_host minimal ports ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.12, [#88](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/88)) ([#119](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/119)) ([10aa2da](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/10aa2dab763850545a05168848c0041a9fc4b02b))

## [0.23.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.22.0...v0.23.0) (2026-06-20)


### Features

* **rules/ubuntu2404:** usbguard + package_purge + dod_root_ca ports ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phases 3.9-3.11) ([#116](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/116)) ([58e95fd](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/58e95fdcc3dafb08cf9b058f05075b504fcfe413))

## [0.22.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.21.0...v0.22.0) (2026-06-20)


### Features

* **rules/ubuntu2404:** kernel_module_blacklist port ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.8) ([#114](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/114)) ([8134c0b](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/8134c0bded818d15d691ee0b35bccbfebb36bae5))

## [0.21.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.20.0...v0.21.0) (2026-06-20)


### Features

* **rules/ubuntu2404:** auditd_actions port ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.7) ([#112](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/112)) ([e22a591](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/e22a591cbbcd601e7cda659e46708f0540aa2a5c))

## [0.20.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.19.0...v0.20.0) (2026-06-20)


### Features

* **rules/ubuntu2404:** unattended_updates port ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.6) ([#110](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/110)) ([8f645bb](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/8f645bb37cdd27db468e6e264fdb36773860a337))

## [0.19.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.18.0...v0.19.0) (2026-06-20)


### Features

* **rules/ubuntu2404:** faillock_safety port ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.5) ([#108](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/108)) ([5a1c876](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/5a1c8761d58f0b6b4f067956107535f0ca45cb44))

## [0.18.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.17.0...v0.18.0) (2026-06-19)


### Features

* **rules/ubuntu2404:** crypto_policy port ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.4) ([#106](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/106)) ([2ba0cc5](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/2ba0cc5346f5fed3c37c1b892c56ea288a54cb87))

## [0.17.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.16.0...v0.17.0) (2026-06-19)


### Features

* **rules/ubuntu2404:** time_servers port ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.3) ([#104](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/104)) ([ab3041c](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/ab3041cc16d61f2b4cc83d3f7ad99a28776b8112))

## [0.16.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.15.0...v0.16.0) (2026-06-19)


### Features

* **rules/ubuntu2404:** banner_text port ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.1) ([#101](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/101)) ([1df3798](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/1df3798ba57c288c95609727a17ea346f34ffeff))
* **rules/ubuntu2404:** ssh_config_apply port ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.2) ([#102](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/102)) ([1e4cd9e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/1e4cd9ee440d030724ef7a4c920386993dc310f1))


### Bug Fixes

* **tailoring:** derive benchmark href from cfg.meta.scap_content ([#97](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/97)) ([#98](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/98)) ([2def33e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/2def33e9c7d22529e2dd9f24707d07661d77c1e3))
* **templates:** carry cfg.user.admin.password into autoinstall users[].passwd ([#96](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/96)) ([#100](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/100)) ([0a31081](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/0a3108112b808a680b265a256a78973cd88fda72))
* **writer/ubuntu2404:** wire rule emit_packages into autoinstall packages ([#95](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/95)) ([#99](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/99)) ([a9fbddc](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/a9fbddc26cf49a8761b30e823148e82d8d27f5ab))

## [0.15.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.14.0...v0.15.0) (2026-06-19)


### Features

* **rules/ubuntu2404:** late-commands + admin_user_and_keys + ssh_keep_open ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 3.0) ([#94](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/94)) ([53140b4](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/53140b45b914b2e0492204361f70d4a94d23a0a1))
* **writer,cli:** bundle reshape + distro dispatch ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 2) ([#92](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/92)) ([4304799](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/4304799c0d7440e6b5f3528edc4332bce421eea0))

## [0.14.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.13.0...v0.14.0) (2026-06-19)


### Features

* **config,rules:** distro discriminator + per-distro registry ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81) phase 1) ([#90](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/90)) ([60d83a1](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/60d83a12fcce9d2028a03e1687ac91d37010857e))


### Documentation

* ubuntu 24.04 STIG autoinstall design spec ([#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81)) ([#89](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/89)) ([8d194fb](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/8d194fb941601883c51216ed9e2b9249e8be26ca))
* unifi host kickstart rebuild — spec, plan, post-impl correction ([#80](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/80)) ([655f1a7](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/655f1a7d4362bb76c8a518aafc760b0a3c4107f4))
* update stale alma-linux-security paths after folder rename ([#82](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/82)) ([732c7e6](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/732c7e612694bd590df0f7535af56cb4d7702c2f))

## [0.13.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.12.2...v0.13.0) (2026-06-17)


### Features

* **disk:** accept by-id in disk.target; add disk.data_disks ([#79](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/79)) ([410cd03](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/410cd03ce9698119bae8933a693a7276eefd0cd3))


### Documentation

* unifi host config (spec + plan) ([#77](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/77)) ([b3caa08](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/b3caa088f91ace4672b62fbc6e0ec19d03fbe61d))

## [0.12.2](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.12.1...v0.12.2) (2026-06-14)


### Bug Fixes

* **iso:** make USB installs find install source and create user ([#73](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/73)) ([ff037c7](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/ff037c7fdcf9637ceae91e5f24aa6156fa65e558))


### Documentation

* **manual:** correct version pin to v0.12.2 ([#76](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/76)) ([73fe765](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/73fe76522acb90ba4a0f1a18b94c1cee50d807de))

## [0.12.1](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.12.0...v0.12.1) (2026-06-13)


### Documentation

* **examples:** add host-container.yaml worked example ([#71](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/71)) ([e789afa](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/e789afaf1f12c0b160e9f4213361ed1a6edd8b81))

## [0.12.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.11.0...v0.12.0) (2026-06-13)


### Features

* **containers:** add container-host preset with /srv/containers and rootless user provisioning ([#70](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/70)) ([03afcb9](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/03afcb9342fe068e72ce0022e12c8a813fdc5b8c))
* **packages:** add packages.preset (standard | lean) ([#68](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/68)) ([7f3694f](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/7f3694fdc82428408092fcfff126bbf1ab4dcdf3))

## [0.11.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.10.0...v0.11.0) (2026-06-13)


### ⚠ BREAKING CHANGES

* **disk:** add disk.target to confine install to a single disk ([#60](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/60))

### Features

* **disk:** add disk.target to confine install to a single disk ([#60](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/60)) ([8e250f9](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/8e250f9ddb2314204788e952746ecd633541bc65))

## [0.10.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.9.0...v0.10.0) (2026-06-12)


### Features

* **rules:** add emit_packages so rules contribute their own %packages deps ([#53](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/53)) ([#56](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/56)) ([630f455](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/630f455c22e7e0bc0367d0c370b075ac6241dd20))


### Bug Fixes

* **iso:** unbreak ks-gen iso end-to-end (pyproject + builder) ([#51](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/51)) ([da363ef](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/da363ef9de0a1907dd7bb6ecb306b386aaddbb8a))
* **iso:** unlink existing --out before xorriso so `ks-gen iso` is idempotent ([#52](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/52)) ([#55](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/55)) ([9d4e903](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/9d4e9039136cdc8f4c344a2151b164eac644519a))


### Refactoring

* **config:** unprefix DEFAULT_LV_SIZES and DEFAULT_FSOPTIONS ([#43](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/43)) ([732b318](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/732b31871637bc1e23f84c4e70f9956c06a58b5d))


### Documentation

* **claude-md:** add "Debugging a generated install" section ([#54](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/54)) ([6a26564](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/6a2656448855210383d761561c3d0afe4897a411))
* **claude-md:** note when to recommend the install-regression harness ([#58](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/58)) ([f0fb2e0](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/f0fb2e023bd0c2d4df74224a4f84224edc743bae))
* **going-public:** fix runbook bugs found while walking it live ([#48](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/48)) ([0b06894](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/0b068946584f3d83ca4fc0e95d1d100644a3df5f))

## [0.9.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.8.0...v0.9.0) (2026-06-10)


### Features

* **cli:** verify --capture-baseline + --baseline flags with mutual-exclusion check ([1387736](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/138773624a46183d1f3794cc543fa18ead6f799f))
* **cli:** verify --check-tailoring flag + TAILORING_DRIFT exit code priority ([25afbdc](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/25afbdc4bc16256a5e96b74e9223aca81c7e0674))
* **license:** relicense from Apache-2.0 to GPL-3.0-or-later ([dd73b19](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/dd73b19895254a919e60bcd237cf9a9988de422a))
* **loader:** add ExitCode.TAILORING_DRIFT=8 ([960380f](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/960380f52008701a9219ad02bfb819922633a610))
* **verify:** add TailoringParseError(VerifyError) with VERIFY_FAIL exit code ([7a5497d](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/7a5497d3b4b3a10b0c024d38334c4e0cec8f903b))
* **verify:** BaselineReport + ReadBaseline dataclasses, baseline field on VerifyReport ([9a4f5b7](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/9a4f5b7d4c3140cff33d3666fdc9ca48f74c44bd))
* **verify:** collect_deployed_tailoring — scp-pull /root/tailoring.xml ([f0a98d5](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/f0a98d5d4de5c28c4bd9dc27a5caed9458cbc03c))
* **verify:** compare_tailorings — pure (added/removed/changed) diff ([2cfb258](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/2cfb2589f1e9b085cc93f424f5c1157b23a22058))
* **verify:** orphan_rule_ids — set-difference for stale-baseline detection ([9209d53](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/9209d535e102b1bbd5e6acbcd912853940fe76ee))
* **verify:** parse_tailoring_xml — round-trips build_tailoring_xml output ([66f56e9](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/66f56e9c8818f4f2cc672e4b6d6fd33762266a95))
* **verify:** read_baseline — load captured ARF with start-time extraction ([267e405](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/267e405818b8978c3096a53a8aad2df8e90419ad))
* **verify:** render_drift_section — text drift section for verify report ([52ab716](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/52ab716bae473b9c4391364da4966f32f1536065))
* **verify:** render_table/render_json surface captured baseline + orphan note ([ac879d9](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/ac879d9a5e38be24849be8bdee8f48770bdd9058))
* **verify:** render_table/render_json surface tailoring drift section ([fbaddc8](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/fbaddc8f6658e8d9ba53ffe77c65d9b69cd00036))
* **verify:** run_verify gains baseline_path + capture_to params ([074145e](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/074145edbcaf6126d94c7c73bb6f857f278070c8))
* **verify:** run_verify gains check_tailoring=True path ([9a4d2fa](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/9a4d2fa0b361908c7e9cb5e041e43ce794fea5cf))
* **verify:** tailoring_drift module scaffold (ParsedTailoring, OpChange, TailoringDriftReport) ([d363efb](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/d363efb96bcaa1e33160817e12603b1fee13225f))
* **verify:** VerifyReport gains tailoring_drift field + has_tailoring_drift ([45b7a3d](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/45b7a3dde5c39185c03634847782e717cc91ff8b))


### Refactoring

* **writer:** extract render_tailoring helper for verify reuse ([d9139e3](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/d9139e34eaf5c2ead6b2b282810101e2785f2bd0))


### Documentation

* drop v0.1 staleness from README + add exit code 8 to MANUAL ([70cea2a](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/70cea2ae716be27e61160286bea67a2158d2b603))
* **license:** add output exception for ks-gen-generated artifacts ([cae154f](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/cae154ff402f66fde2e955d479fe6d36ad98b5c5))
* **plans:** verify capture-baseline implementation plan ([#11](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/11)) ([05e0bfd](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/05e0bfd6ee33887f7464a6ae9a0d4f1cade96a43))
* **plans:** verify tailoring drift implementation plan ([#12](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/12)) ([e40c537](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/e40c53739be808e9e291e8b918f058e46f0d45ad))
* **readme:** update license badge from Apache-2.0 to GPLv3+ ([2ac725d](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/2ac725d83d00fdc1989476304f50d90dccf30e11))
* **specs:** verify tailoring drift detection design ([#12](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/12)) ([748c4ad](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/748c4adc0dd1913cb4e418ee3d244e7b4325dd14))
* **specs:** verify workstation-captured baseline design ([#11](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/11)) ([5dae8e4](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/5dae8e47660c8351b533feb7d4e0e15a7a40eb40))
* verify --capture-baseline / --baseline — MANUAL §8.6 + README sentence ([48c2298](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/48c22981d26fe498c2a20472348d6015ede942f0))
* verify --check-tailoring — MANUAL §8.5 + README sentence ([d3a8925](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/d3a8925611fab687d6db8ba41769e21b6cbc5f67))

## [0.8.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.7.0...v0.8.0) (2026-06-09)


### Features

* **verify:** add --allow-regression flag for regression-category apply ([4de1814](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/4de1814a3fa44a5d155bc3ce877f177064ed481f))
* **verify:** add --apply flag (writes new_fail suggestions to host.yaml) ([93e3ead](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/93e3eadc17c2cacbede89209e24c105911784424))
* **verify:** add --suggest-exceptions flag to verify CLI ([991dc62](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/991dc629807e4e8f5cceb34fa43a1876ec5139e4))
* **verify:** add SuggestApplyError(VerifyError) with CONFIG_INVALID exit code ([0b91c01](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/0b91c0180fc41daf3305cece45b0773fbc22bf85))
* **verify:** apply_to_host_yaml() — validate-then-backup-then-write ([5a1508c](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/5a1508ca101b97da3c122791c6ab2a9679bb8369))
* **verify:** build_suggestions() — pure ExceptionDecl builder for failing rows ([1abf000](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/1abf00029a8cd9da801b85811e20c00391ca2397))
* **verify:** render_table/render_json accept optional suggestions= param ([4c7d7be](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/4c7d7be164c123ea2e75ae3bd69757e6a8707ff7))
* **verify:** render_yaml() — paste-friendly suggestion output ([1725fe3](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/1725fe3269f1df5e487da4b3d88d362359b81ad3))


### Bug Fixes

* **verify:** apply on clean report + clean up orphan .tmp on replace failure ([c92f978](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/c92f9786d4e8c122f32c5a7f8c930b787ae2f5c9))


### Documentation

* **manual:** verify --suggest-exceptions / --apply / --allow-regression ([a58b077](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/a58b077f240895d8c4a1ed46aab377fa59627f1e))
* **plans:** verify auto-suggest exceptions implementation plan ([dbabe0c](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/dbabe0c479cad815bf80bb127b95437c3c2bf68a))
* **specs:** verify auto-suggest exceptions design ([#14](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/14)) ([4542850](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/4542850c3489e58b01fc251546b96da3ab44387b))

## [0.7.0](https://github.com/SupremeCommanderHedgehog/ks-gen/compare/v0.6.0...v0.7.0) (2026-06-09)


### Features

* **wizard:** _OVERRIDE_TOGGLES mapping + schema consistency tests ([a10f687](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/a10f6874113c2cead007ebd7ad03dc006323c9f7))
* **wizard:** disk group LUKS partial inline passphrase + retry ([62996d1](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/62996d14090af3ca4b310360726fa56587f5a5a3))
* **wizard:** disk group LUKS partial sidecar file ([3466998](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/3466998290931bc5a19f5b8d2a42d4e4df36b208))
* **wizard:** disk group prompts (preset, wipe, LUKS none) ([bf65135](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/bf65135a7fb605a276901c0844acd77f3b3b715b))
* **wizard:** map KeyboardInterrupt to WizardError("aborted by user") ([ae0da12](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/ae0da12efaedc31458afceeab499580349fdffd8))
* **wizard:** network group single DHCP interface ([25af626](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/25af6264d55356f3cb9cbad23653b969de3d56f4))
* **wizard:** network group static interface + dotted-quad validator ([65e82d5](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/65e82d54b068e24f91cf2fe2bfa6f02e9102e472))
* **wizard:** override matrix checkbox prompts + payload build ([08e1e60](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/08e1e60420021b3bfb074a9582ac895ab32db256))
* **wizard:** typed questionary adapter in wizard/_prompts.py ([bd935ea](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/bd935ea6b5567200f939a9592085a8896cc4f204))
* **wizard:** wire disk/network/overrides groups into run_wizard ([dd915fd](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/dd915fd307c8bea98aece7af4c3f50ff36431b06))


### Bug Fixes

* **wizard:** move tang hint into partial branch + test None return ([9453bc5](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/9453bc5ca43b33b6b6d9489736b6c29de44c10f8))


### Refactoring

* **wizard:** _core.prompts() + group selector orchestration ([3e61abf](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/3e61abf5e0df0cc33b345552d4fd5bb165ea7cbc))
* **wizard:** promote wizard.py to package (no behavior change) ([3e3add8](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/3e3add8984eeb03e52400bef0c7f5d9a4936d693))


### Documentation

* **manual:** wizard prompts disk/network/overrides — update §5.1 ([1a03a51](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/1a03a51cbb5f0d346d4541aeed014097b00af33c))
* **plans:** ks-gen new wizard disk/network/overrides implementation ([dccd362](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/dccd3627126cd80af711d47e3dd769fbe0e2b216))
* **readme:** drop v0.1 wizard-limitation bullet (closes [#9](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/9)) ([f1ad316](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/f1ad31607a41ab9673ac67687f64aa3d96459260))
* **specs:** fix MANUAL.md section ref in wizard design (3.3 -&gt; 5.1) ([ef32602](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/ef32602891a60fd7f30277822e814fbc0b11d379))
* **specs:** ks-gen new wizard disk/network/overrides design ([4f212b0](https://github.com/SupremeCommanderHedgehog/ks-gen/commit/4f212b0e0778dc9ce597939f88ed3fd62f73f6e2))

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
