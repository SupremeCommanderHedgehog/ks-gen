from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Meta(StrictModel):
    release: str = "9"
    profile: str = "stig"
    scap_content: str = "ssg-almalinux9-ds.xml"


class System(StrictModel):
    hostname: str = Field(..., min_length=1)
    timezone: str = "UTC"
    locale: str = "en_US.UTF-8"
    keyboard: str = "us"


class Interface(StrictModel):
    device: str = "link"
    bootproto: Literal["dhcp", "static"] = "dhcp"
    onboot: bool = True
    ip: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    nameservers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _static_requires_fields(self) -> Interface:
        if self.bootproto == "static":
            missing = [f for f in ("ip", "netmask", "gateway") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"ip is required for static interfaces: missing {missing}")
        return self


class Network(StrictModel):
    interfaces: list[Interface] = Field(default_factory=lambda: [Interface()])
    dns_search: list[str] = Field(default_factory=list)
    hostname_from_dhcp: bool = False


class DiskPreset(StrEnum):
    STIG_SERVER = "stig_server"
    MINIMAL = "minimal"
    CUSTOM = "custom"


class DiskLvDef(StrictModel):
    name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    mount: str | None = None
    size: str | None = Field(default=None, pattern=r"^\d+(M|G|T)$|^recommended$")
    fstype: Literal["xfs", "ext4", "swap"] = "xfs"
    fsoptions: str | None = None
    encrypted: bool = False

    @field_validator("encrypted")
    @classmethod
    def _encryption_deferred(cls, v: bool) -> bool:
        if v:
            raise ValueError(
                "per-LV encryption is not supported; use disk.luks.preset for PV-level LUKS"
            )
        return v


DEFAULT_LV_SIZES: dict[str | None, str] = {
    "/": "15G",
    "/home": "5G",
    "/tmp": "3G",
    "/var": "10G",
    "/var/log": "5G",
    "/var/log/audit": "3G",
    "/var/tmp": "2G",
    None: "recommended",  # swap LV
}


DEFAULT_FSOPTIONS: dict[str, str] = {
    "/home": "nodev,nosuid",
    "/tmp": "nodev,nosuid,noexec",
    "/var": "nodev",
    "/var/log": "nodev,nosuid,noexec",
    "/var/log/audit": "nodev,nosuid,noexec",
    "/var/tmp": "nodev,nosuid,noexec",
}


_STIG_REQUIRED_LV_MOUNTPOINTS: frozenset[str] = frozenset(
    {
        "/",
        "/home",
        "/tmp",
        "/var",
        "/var/log",
        "/var/log/audit",
        "/var/tmp",
    }
)

# Accepts persistent identifiers (disk/by-id/ata-FOO, disk/by-path/...)
# and bare kernel names (sda, vda, nvme0n1). Rejects: leading "/", empty,
# leading digit, whitespace. Strict superset of the v0.10-v0.12 regex.
DISK_TARGET_REGEX = r"^[a-zA-Z][a-zA-Z0-9._/:-]*$"


class DiskBootPart(StrictModel):
    size: str = Field(default="1G", pattern=r"^\d+(M|G)$")
    fstype: Literal["xfs", "ext4"] = "xfs"
    fsoptions: str | None = "nodev,nosuid"


class DiskEfiPart(StrictModel):
    size: str = Field(default="1G", pattern=r"^\d+(M|G)$")
    # fstype is always "efi" for the EFI System Partition; not configurable.


class DiskLayout(StrictModel):
    boot: DiskBootPart = Field(default_factory=DiskBootPart)
    efi: DiskEfiPart = Field(default_factory=DiskEfiPart)
    vg_name: str = "vg_root"
    lvs: list[DiskLvDef] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_layout(self) -> DiskLayout:
        lv_mounts = {lv.mount for lv in self.lvs if lv.mount is not None}

        missing = _STIG_REQUIRED_LV_MOUNTPOINTS - lv_mounts
        if missing:
            # deterministic: report the lexicographically-first missing mount
            # so the parametrized tests can pin a stable error message.
            mount = sorted(missing)[0]
            raise ValueError(f"disk.layout missing STIG-required mountpoint: {mount}")

        # Per-LV swap consistency runs BEFORE the swap-cardinality check so
        # that a swap LV with a mount path is reported as a config error on
        # that specific LV, rather than as an opaque "found 2 swap LVs" miss.
        for lv in self.lvs:
            if lv.fstype == "swap" and lv.mount is not None:
                raise ValueError(
                    f"disk.layout.lvs[{lv.name}]: swap LV mount must be null (got {lv.mount!r})"
                )
            if lv.fstype != "swap" and lv.mount is None:
                raise ValueError(f"disk.layout.lvs[{lv.name}]: non-swap LV requires a mount path")

        swap_lvs = [lv for lv in self.lvs if lv.fstype == "swap"]
        if len(swap_lvs) != 1:
            raise ValueError(
                f"disk.layout requires exactly one swap LV "
                f"(fstype=swap, mount unset); found {len(swap_lvs)}"
            )

        names = [lv.name for lv in self.lvs]
        if len(names) != len(set(names)):
            seen: set[str] = set()
            for n in names:
                if n in seen:
                    raise ValueError(f"disk.layout duplicate LV name: {n}")
                seen.add(n)

        mounts = [lv.mount for lv in self.lvs if lv.mount is not None]
        if len(mounts) != len(set(mounts)):
            seen_m: set[str] = set()
            for m in mounts:
                if m in seen_m:
                    raise ValueError(f"disk.layout duplicate LV mount: {m}")
                seen_m.add(m)

        # Size check runs LAST so duplicate-name / duplicate-mount errors
        # surface first when a custom-mount LV is also a duplicate.
        for lv in self.lvs:
            if lv.size is None and lv.mount not in DEFAULT_LV_SIZES:
                raise ValueError(
                    f"disk.layout.lvs[{lv.name}].size: required for custom "
                    f"mountpoint {lv.mount}; no default available"
                )

        return self


class LuksPreset(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    TANG = "tang"


class TangServer(StrictModel):
    url: str = Field(..., pattern=r"^https?://[^\s/]+(/.*)?$")
    thumbprint: str = Field(..., pattern=r"^[A-Za-z0-9_-]{32,}$")


class Tang(StrictModel):
    servers: list[TangServer] = Field(..., min_length=1)
    threshold: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _threshold_within_servers(self) -> Tang:
        if self.threshold > len(self.servers):
            raise ValueError(
                f"disk.luks.tang.threshold ({self.threshold}) exceeds "
                f"servers count ({len(self.servers)}); threshold must be "
                f"<= servers count"
            )
        return self


class DiskLuks(StrictModel):
    preset: LuksPreset = LuksPreset.NONE
    passphrase: str | None = None
    passphrase_file: str | None = None
    tang: Tang | None = None

    @model_validator(mode="after")
    def _validate_luks(self) -> DiskLuks:
        other_fields_set = (
            self.passphrase is not None or self.passphrase_file is not None or self.tang is not None
        )

        if self.preset == LuksPreset.NONE:
            if other_fields_set:
                raise ValueError(
                    "disk.luks.preset='none' rejects passphrase, "
                    "passphrase_file, and tang fields; set preset to "
                    "'partial' or 'tang'"
                )
            return self

        # preset != none from here on
        if self.passphrase is not None and self.passphrase_file is not None:
            raise ValueError(
                "disk.luks: passphrase and passphrase_file are mutually exclusive; specify one"
            )
        if self.passphrase is None and self.passphrase_file is None:
            raise ValueError(
                f"disk.luks.preset='{self.preset.value}' requires passphrase or passphrase_file"
            )

        if self.preset == LuksPreset.TANG and self.tang is None:
            raise ValueError(
                "disk.luks.preset='tang' requires disk.luks.tang block with at least one server"
            )
        if self.preset != LuksPreset.TANG and self.tang is not None:
            raise ValueError(
                f"disk.luks.preset='{self.preset.value}' rejects tang "
                f"block; tang is only valid with preset='tang'"
            )

        return self


class Disk(StrictModel):
    preset: DiskPreset | None = None
    layout: DiskLayout | None = None
    luks: DiskLuks = Field(default_factory=DiskLuks)
    wipe: bool = True
    bootloader_password: str | None = None
    target: str | None = Field(default=None, pattern=DISK_TARGET_REGEX)
    data_disks: list[DataDisk] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _preset_xor_layout(cls, data: dict[str, object]) -> dict[str, object]:
        """Enforce preset/layout mutual exclusion and fill the v0.3 default.

        ``mode='before'`` is required because StrictModel is ``frozen=True``,
        so we cannot mutate ``self.preset`` after construction. Filling the
        default at the dict-input layer is the only place we can apply a
        conditional default (preset=STIG_SERVER only when layout is also
        absent).
        """
        if not isinstance(data, dict):
            return data
        preset = data.get("preset")
        layout = data.get("layout")
        if preset is not None and layout is not None:
            raise ValueError("disk.preset and disk.layout are mutually exclusive; specify one")
        # v0.3 backwards-compat: both omitted -> default to STIG_SERVER
        if preset is None and layout is None:
            data["preset"] = DiskPreset.STIG_SERVER
        return data

    @field_validator("preset")
    @classmethod
    def _custom_not_yet_implemented(cls, v: DiskPreset | None) -> DiskPreset | None:
        if v == DiskPreset.CUSTOM:
            raise ValueError(
                "disk.preset='custom' was reserved in v0.1-v0.3; use the disk.layout block instead."
            )
        return v


class DataDisk(StrictModel):
    target: str = Field(..., pattern=DISK_TARGET_REGEX)
    mount: str = Field(..., min_length=1, pattern=r"^/[a-zA-Z0-9_/-]+$")
    fstype: Literal["xfs", "ext4"] = "xfs"
    fsoptions: str | None = "nodev,nosuid"
    wipe: bool = True
    partition: int | None = Field(default=None, ge=1)
    partition_uuid: str | None = None
    partition_label: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_partition_when_preserve(cls, data: dict[str, object]) -> dict[str, object]:
        """When wipe=False and no identifier is given, default partition=1.

        Runs at the dict-input layer because StrictModel is frozen=True;
        the after-validator below relies on exactly one identifier being
        set when wipe=False.
        """
        if not isinstance(data, dict):
            return data
        if data.get("wipe", True) is False:
            ids = (
                data.get("partition"),
                data.get("partition_uuid"),
                data.get("partition_label"),
            )
            if all(x is None for x in ids):
                data["partition"] = 1
        return data

    @model_validator(mode="after")
    def _validate_identifier(self) -> DataDisk:
        ids = [self.partition, self.partition_uuid, self.partition_label]
        n_set = sum(x is not None for x in ids)
        if self.wipe:
            if n_set > 0:
                raise ValueError(
                    "data_disks: partition / partition_uuid / partition_label "
                    "are only valid when wipe=False"
                )
            return self
        if n_set > 1:
            raise ValueError(
                "data_disks: specify at most one of partition / partition_uuid / partition_label"
            )
        return self

    @model_validator(mode="after")
    def _partition_requires_stable_target(self) -> DataDisk:
        if self.partition is not None and not (
            self.target.startswith("disk/by-id/") or self.target.startswith("disk/by-path/")
        ):
            raise ValueError(
                "data_disks: partition number requires a stable target "
                "(disk/by-id/... or disk/by-path/...); use partition_uuid "
                "or partition_label for bare kernel-name targets"
            )
        return self


DEFAULT_BANNER = (
    "WARNING: This is a private computer system. Unauthorized access is\n"
    "prohibited. All activity on this system may be monitored and logged.\n"
    "Use of this system constitutes consent to such monitoring.\n"
)


class AdminUser(StrictModel):
    name: str
    gecos: str = ""
    groups: list[str] = Field(default_factory=lambda: ["wheel"])
    shell: str = "/bin/bash"
    password: str | None = None
    sudo: Literal["nopasswd_no", "nopasswd_yes"] = "nopasswd_no"
    authorized_keys: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _not_root(cls, v: str) -> str:
        if v == "root":
            raise ValueError("admin name cannot be 'root'")
        return v

    @model_validator(mode="after")
    def _keys_or_password(self) -> AdminUser:
        if self.password is None and not self.authorized_keys:
            raise ValueError(
                "user.admin.authorized_keys: at least one key required when password is null"
            )
        return self


class User(StrictModel):
    admin: AdminUser


class Ssh(StrictModel):
    port: int = Field(default=22, ge=1, le=65535)
    permit_root_login: Literal["no", "prohibit-password"] = "no"
    password_authentication: bool = False
    client_alive_interval: int = Field(default=600, ge=0)
    client_alive_count_max: int = Field(default=1, ge=0)
    max_auth_tries: int = Field(default=4, ge=1)
    use_pam: bool = True


_APPLY_TO_DEFAULT: list[Literal["issue", "issue_net", "motd", "gdm"]] = [
    "issue",
    "issue_net",
    "motd",
    "gdm",
]


class Banner(StrictModel):
    text: str = DEFAULT_BANNER
    apply_to: list[Literal["issue", "issue_net", "motd", "gdm"]] = Field(
        default_factory=lambda: list(_APPLY_TO_DEFAULT)
    )


class Time(StrictModel):
    servers: list[str] = Field(default_factory=lambda: ["pool.ntp.org"])
    chrony_makestep_threshold: float = 1.0


class CryptoPolicy(StrEnum):
    STIG = "STIG"
    MODERN = "MODERN"
    FUTURE = "FUTURE"


class Crypto(StrictModel):
    policy: CryptoPolicy = CryptoPolicy.MODERN


class ContainerVolume(StrictModel):
    size: str = Field(default="20G", pattern=r"^\d+(M|G|T)$")
    fsoptions: str = "nodev,nosuid"

    @field_validator("fsoptions")
    @classmethod
    def _reject_noexec(cls, v: str) -> str:
        tokens = [t for t in re.split(r"[,\s]+", v) if t]
        if "noexec" in tokens:
            raise ValueError(
                "containers.volume.fsoptions: noexec is incompatible with "
                "container image execution; remove it"
            )
        return v

    @property
    def size_mib(self) -> int:
        unit = self.size[-1]
        n = int(self.size[:-1])
        if unit == "M":
            return n
        if unit == "G":
            return n * 1024
        # unit == "T" — pattern guarantees one of M|G|T
        return n * 1024 * 1024


class ContainerUser(StrictModel):
    name: str = Field(..., pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    gecos: str = ""
    authorized_keys: list[str] = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def _not_root(cls, v: str) -> str:
        if v == "root":
            raise ValueError("containers.users[].name cannot be 'root'")
        return v


class Containers(StrictModel):
    enabled: bool = False
    users: list[ContainerUser] = Field(default_factory=list)
    volume: ContainerVolume = Field(default_factory=ContainerVolume)

    @model_validator(mode="after")
    def _validate_users_distinct(self) -> Containers:
        if not self.enabled:
            return self
        names = [u.name for u in self.users]
        if len(names) != len(set(names)):
            seen: set[str] = set()
            for n in names:
                if n in seen:
                    raise ValueError(f"containers.users duplicate name: {n}")
                seen.add(n)
        return self


class InstallSourceKind(StrEnum):
    MEDIA = "media"
    NETWORK = "network"


_INSTALL_DEFAULT_BASEOS_URL = "https://repo.almalinux.org/almalinux/9.8/BaseOS/x86_64/os/"
_INSTALL_DEFAULT_APPSTREAM_URL = "https://repo.almalinux.org/almalinux/9.8/AppStream/x86_64/os/"


class Install(StrictModel):
    """Where Anaconda gets packages. `media` (default) uses the boot media's
    own repo (a full DVD). `network` emits `url`/`repo` pointing at AlmaLinux
    mirrors, so a repo-less `boot.iso` can be used — the iso builder then also
    drops the hardcoded `inst.repo=hd:LABEL` boot-menu arg (see iso/_menu.py)."""

    source: InstallSourceKind = InstallSourceKind.MEDIA
    baseos_url: str = Field(default=_INSTALL_DEFAULT_BASEOS_URL, min_length=1)
    appstream_url: str = Field(default=_INSTALL_DEFAULT_APPSTREAM_URL, min_length=1)


class PackagesPreset(StrEnum):
    STANDARD = "standard"
    LEAN = "lean"


LEAN_EXTRA_PACKAGES: tuple[str, ...] = (
    "logrotate",
    "postfix",
    "cronie",
    "crontabs",
    "parted",
)

# Module-level defaults for Packages so the lean-normalization
# `model_validator(mode="before")` can reference them when the input dict
# omits the field. Pydantic doesn't apply Field default_factory at
# mode="before" time — the validator sees the raw input dict only. The
# field default_factory below reuses these constants so the source of
# truth stays single.
_PACKAGES_DEFAULT_BASE_GROUPS: list[str] = ["@^minimal-environment", "@standard"]
_PACKAGES_DEFAULT_REQUIRED: list[str] = [
    "scap-security-guide",
    "openscap-scanner",
    "aide",
    "audit",
    "rsyslog",
    "chrony",
    "firewalld",
    "sudo",
    "policycoreutils-python-utils",
    "dnf-automatic",
    "dnf-utils",
]


class Packages(StrictModel):
    preset: PackagesPreset = PackagesPreset.STANDARD
    base_groups: list[str] = Field(default_factory=lambda: list(_PACKAGES_DEFAULT_BASE_GROUPS))
    required: list[str] = Field(default_factory=lambda: list(_PACKAGES_DEFAULT_REQUIRED))
    extra: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(
        default_factory=lambda: [
            "telnet-server",
            "rsh-server",
            "tftp-server",
            "vsftpd",
            "ypserv",
        ]
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_lean_preset(cls, data: Any) -> Any:
        """When preset is LEAN, normalize base_groups + required into the
        stored fields so model_dump() (used by writer.py to produce
        host.yaml) reflects what's actually installed. Without this,
        host.yaml continues to show the raw defaults (`@standard` in
        base_groups, no LEAN_EXTRA_PACKAGES in required) while the
        kickstart's `%packages` block uses the corrected effective set
        — host.yaml ends up lying about what's on the box. Fixes #134.

        Runs in mode="before" because StrictModel is frozen — Pydantic v2
        forbids `mode="after"` validators from returning a different
        instance on a frozen model. Mutating the input dict before
        construction is the supported path.

        Idempotent: re-validating an already-normalized cfg is a no-op.
        The `effective_*` properties below keep their old contract for
        backward compat — after normalization they just echo the fields.
        """
        if not isinstance(data, dict):
            return data
        preset = data.get("preset", PackagesPreset.STANDARD)
        # Normalize StrEnum-or-str so the comparison is robust either way.
        preset_value = preset.value if isinstance(preset, PackagesPreset) else preset
        if preset_value != PackagesPreset.LEAN.value:
            return data
        base_groups = data.get("base_groups", list(_PACKAGES_DEFAULT_BASE_GROUPS))
        data = {**data, "base_groups": [g for g in base_groups if g != "@standard"]}
        required = data.get("required", list(_PACKAGES_DEFAULT_REQUIRED))
        existing = set(required)
        data["required"] = list(required) + [p for p in LEAN_EXTRA_PACKAGES if p not in existing]
        return data

    @property
    def effective_base_groups(self) -> list[str]:
        # Post-#134 normalization makes this equivalent to base_groups on
        # a lean cfg; preserved as a property so existing call sites
        # (writer.py, rules/) keep working with no behavior change.
        if self.preset == PackagesPreset.LEAN:
            return [g for g in self.base_groups if g != "@standard"]
        return list(self.base_groups)

    @property
    def effective_required(self) -> list[str]:
        # Post-#134 normalization makes this equivalent to required on a
        # lean cfg; preserved as a property for backward compat.
        if self.preset != PackagesPreset.LEAN:
            return list(self.required)
        existing = set(self.required)
        return list(self.required) + [p for p in LEAN_EXTRA_PACKAGES if p not in existing]


class FaillockCfg(StrictModel):
    enable: bool = True
    deny: int = Field(default=3, ge=1)
    unlock_time: int = Field(default=900, ge=0)
    even_deny_root: bool = False


class AuditdSystemAction(StrEnum):
    SUSPEND = "SUSPEND"
    SYSLOG = "SYSLOG"
    HALT = "HALT"
    SINGLE = "SINGLE"


class AuditdMaxFileAction(StrEnum):
    ROTATE = "ROTATE"
    KEEP_LOGS = "keep_logs"
    SYSLOG = "SYSLOG"
    IGNORE = "IGNORE"


class AuditdActionsCfg(StrictModel):
    disk_full_action: AuditdSystemAction = AuditdSystemAction.SUSPEND
    disk_error_action: AuditdSystemAction = AuditdSystemAction.SUSPEND
    max_log_file_action: AuditdMaxFileAction = AuditdMaxFileAction.ROTATE


class SshKeepOpenCfg(StrictModel):
    ensure_firewalld_port: bool = True
    ensure_selinux_port: bool = True
    ensure_ufw_port: bool = True


class UsbguardCfg(StrictModel):
    enable: bool = False


class KernelModuleBlacklistCfg(StrictModel):
    enable: bool = True
    modules: list[str] = Field(
        default_factory=lambda: [
            "usb-storage",
            "cramfs",
            "freevxfs",
            "jffs2",
            "hfs",
            "hfsplus",
            "squashfs",
            "udf",
        ]
    )


class PackagePurgeCfg(StrictModel):
    enable: bool = True


class DodRootCaCfg(StrictModel):
    install: bool = False


class NightlySecurityCfg(StrictModel):
    enable: bool = True
    on_calendar: str = Field(default="*-*-* 02:00:00", min_length=1)


class MonthlyFullCfg(StrictModel):
    enable: bool = True
    on_calendar: str = Field(default="Sun *-*-1..7 02:30:00", min_length=1)


class RebootWindowCfg(StrictModel):
    enable: bool = True
    on_calendar: str = Field(default="Sun *-*-* 03:00:00", min_length=1)


class UnattendedUpdatesCfg(StrictModel):
    enable: bool = True
    nightly_security: NightlySecurityCfg = Field(default_factory=NightlySecurityCfg)
    monthly_full: MonthlyFullCfg = Field(default_factory=MonthlyFullCfg)
    reboot_window: RebootWindowCfg = Field(default_factory=RebootWindowCfg)

    @model_validator(mode="after")
    def _reboot_window_needs_an_update_timer(self) -> UnattendedUpdatesCfg:
        if (
            self.enable
            and self.reboot_window.enable
            and not (self.nightly_security.enable or self.monthly_full.enable)
        ):
            raise ValueError(
                "overrides.unattended_updates.reboot_window requires at least one "
                "update timer enabled (nightly_security or monthly_full) — "
                "otherwise the host will reboot weekly against a never-updated system."
            )
        return self


class Overrides(StrictModel):
    fips_mode: bool = False
    faillock: FaillockCfg = Field(default_factory=FaillockCfg)
    auditd: AuditdActionsCfg = Field(default_factory=AuditdActionsCfg)
    ssh_keep_open: SshKeepOpenCfg = Field(default_factory=SshKeepOpenCfg)
    usbguard: UsbguardCfg = Field(default_factory=UsbguardCfg)
    kernel_module_blacklist: KernelModuleBlacklistCfg = Field(
        default_factory=KernelModuleBlacklistCfg
    )
    package_purge: PackagePurgeCfg = Field(default_factory=PackagePurgeCfg)
    dod_root_ca: DodRootCaCfg = Field(default_factory=DodRootCaCfg)
    unattended_updates: UnattendedUpdatesCfg = Field(default_factory=UnattendedUpdatesCfg)


class ExceptionDecl(StrictModel):
    id: str
    reason: str
    stig_rules_disabled: list[str] = Field(..., min_length=1)


_DEFAULT_SCAP_CONTENT_BY_DISTRO: dict[str, str] = {
    "alma9": "ssg-almalinux9-ds.xml",
    "alma8": "ssg-almalinux8-ds.xml",
    "ubuntu2404": "ssg-ubuntu2404-ds.xml",
}


class HostConfig(StrictModel):
    distro: Literal["alma9", "alma8", "ubuntu2404"] = "alma9"
    meta: Meta = Field(default_factory=Meta)
    system: System
    network: Network = Field(default_factory=Network)
    disk: Disk = Field(default_factory=Disk)
    user: User
    ssh: Ssh = Field(default_factory=Ssh)
    banner: Banner = Field(default_factory=Banner)
    time: Time = Field(default_factory=Time)
    crypto: Crypto = Field(default_factory=Crypto)
    packages: Packages = Field(default_factory=Packages)
    overrides: Overrides = Field(default_factory=Overrides)
    custom_post: list[str] = Field(default_factory=list)
    exceptions: list[ExceptionDecl] = Field(default_factory=list)
    containers: Containers = Field(default_factory=Containers)
    install: Install = Field(default_factory=Install)

    @model_validator(mode="after")
    def _crypto_fips_mutex(self) -> HostConfig:
        if self.crypto.policy in (CryptoPolicy.MODERN, CryptoPolicy.FUTURE):
            if self.overrides.fips_mode:
                raise ValueError(
                    "crypto.policy=MODERN/FUTURE conflicts with overrides.fips_mode=true: "
                    "FIPS kernel mode blocks Curve25519/Ed25519 at the kernel layer."
                )
        return self

    @model_validator(mode="after")
    def _network_install_source_is_supported(self) -> HostConfig:
        if self.install.source != InstallSourceKind.NETWORK:
            return self
        if self.distro == "ubuntu2404":
            raise ValueError(
                "install.source=network is not supported for distro=ubuntu2404: "
                "the Ubuntu autoinstall path does not consume install.* (the "
                "setting would be silently ignored)."
            )
        if self.distro != "alma9" and (
            self.install.baseos_url == _INSTALL_DEFAULT_BASEOS_URL
            or self.install.appstream_url == _INSTALL_DEFAULT_APPSTREAM_URL
        ):
            raise ValueError(
                "install.source=network still uses AlmaLinux 9.8 default mirror "
                f"URL(s) that do not match distro={self.distro}. Set BOTH "
                "install.baseos_url and install.appstream_url to your distro/"
                "release's BaseOS and AppStream repos."
            )
        return self

    @model_validator(mode="after")
    def _admin_credential_mutex(self) -> HostConfig:
        admin = self.user.admin
        if admin.password is None and admin.sudo != "nopasswd_yes":
            raise ValueError(
                "locked admin (user.admin.password unset) requires "
                "user.admin.sudo=nopasswd_yes: without a password, "
                "password-required sudo cannot be satisfied, leaving the "
                "admin unable to escalate privileges."
            )
        return self

    @model_validator(mode="before")
    @classmethod
    def _scap_content_matches_distro_before(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Check and adjust scap_content before model construction."""
        distro = data.get("distro", "alma9")
        meta_was_explicit = "meta" in data

        # Only process if distro is a valid value; let Literal validation catch invalid ones
        if distro not in _DEFAULT_SCAP_CONTENT_BY_DISTRO:
            return data

        expected = _DEFAULT_SCAP_CONTENT_BY_DISTRO[distro]
        alma_default = _DEFAULT_SCAP_CONTENT_BY_DISTRO["alma9"]

        # If meta was not explicitly provided and distro is not alma9, we'll auto-update it later
        # If meta was explicitly provided, validate it matches the distro
        if meta_was_explicit:
            meta_data = data.get("meta", {})
            if isinstance(meta_data, dict):
                scap_content = meta_data.get("scap_content", alma_default)
            else:
                scap_content = getattr(meta_data, "scap_content", alma_default)

            # If explicitly set meta and it mismatches, raise error
            if scap_content != expected:
                raise ValueError(
                    f"meta.scap_content={scap_content!r} does not match distro={distro!r}; "
                    f"expected {expected!r}"
                )
        else:
            # If meta not provided and distro is not alma9, inject the correct scap_content
            if distro != "alma9":
                if "meta" not in data:
                    data["meta"] = {}
                if isinstance(data["meta"], dict):
                    data["meta"]["scap_content"] = expected

        return data

    @model_validator(mode="after")
    def _minimal_preset_rejects_luks(self) -> HostConfig:
        if self.disk.preset == DiskPreset.MINIMAL and self.disk.luks.preset != LuksPreset.NONE:
            raise ValueError(
                "disk.preset='minimal' has no LVM PV; disk.luks "
                "requires disk.preset='stig_server' or disk.layout"
            )
        return self

    @model_validator(mode="after")
    def _minimal_preset_rejects_containers(self) -> HostConfig:
        if self.disk.preset == DiskPreset.MINIMAL and self.containers.enabled:
            raise ValueError(
                "disk.preset='minimal' has no LVM VG; containers.enabled "
                "auto-injects an LV at /srv/containers which requires "
                "disk.preset='stig_server' or disk.layout"
            )
        return self

    @model_validator(mode="after")
    def _validate_data_disks_require_target(self) -> HostConfig:
        if self.disk.data_disks and self.disk.target is None:
            raise ValueError(
                "disk.data_disks is non-empty but disk.target is unset; "
                "without a system target, anaconda's clearpart --all would "
                "clobber the data disks"
            )
        return self

    @model_validator(mode="after")
    def _validate_data_disks_targets_distinct(self) -> HostConfig:
        seen: set[str] = {self.disk.target} if self.disk.target else set()
        for i, d in enumerate(self.disk.data_disks):
            if d.target in seen:
                raise ValueError(
                    f"disk.data_disks[{i}].target {d.target!r} collides "
                    f"with disk.target or another data disk"
                )
            seen.add(d.target)
        return self

    @model_validator(mode="after")
    def _validate_data_disks_mounts_distinct(self) -> HostConfig:
        reserved: set[str] = {"/", "/boot", "/boot/efi"}
        if self.disk.layout is not None:
            reserved.update(lv.mount for lv in self.disk.layout.lvs if lv.mount is not None)
        elif self.disk.preset == DiskPreset.STIG_SERVER:
            reserved.update(_STIG_REQUIRED_LV_MOUNTPOINTS)
        # No branch for MINIMAL: _minimal_preset_rejects_data_disks (below)
        # raises before any minimal+data_disks combination can matter, and
        # minimal's sole `/` mount is already in `reserved`. CUSTOM never
        # reaches here — _custom_not_yet_implemented rejects at field load.
        if self.containers.enabled:
            reserved.add("/srv/containers")
        seen: set[str] = set()
        for i, d in enumerate(self.disk.data_disks):
            if d.mount in reserved or d.mount in seen:
                raise ValueError(
                    f"disk.data_disks[{i}].mount {d.mount!r} collides with "
                    f"a reserved or already-assigned mount point"
                )
            seen.add(d.mount)
        return self

    @model_validator(mode="after")
    def _minimal_preset_rejects_data_disks(self) -> HostConfig:
        if self.disk.preset == DiskPreset.MINIMAL and self.disk.data_disks:
            raise ValueError(
                "disk.preset='minimal' is incompatible with disk.data_disks; "
                "use disk.preset='stig_server' or disk.layout"
            )
        return self

    @model_validator(mode="after")
    def _validate_containers_integration(self) -> HostConfig:
        if not self.containers.enabled:
            return self

        admin_name = self.user.admin.name
        for u in self.containers.users:
            if u.name == admin_name:
                raise ValueError(
                    f"containers.users[].name {u.name!r} collides with "
                    f"user.admin.name; admin user and container users must be distinct"
                )

        if self.disk.layout is not None:
            for lv in self.disk.layout.lvs:
                if lv.mount == "/srv/containers":
                    raise ValueError(
                        "containers.enabled=True conflicts with disk.layout LV mounted at "
                        "/srv/containers; the container-host preset auto-injects this LV"
                    )

        return self
