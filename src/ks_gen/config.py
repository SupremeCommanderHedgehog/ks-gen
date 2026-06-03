from __future__ import annotations

from enum import StrEnum
from typing import Literal

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


class Disk(StrictModel):
    preset: DiskPreset = DiskPreset.STIG_SERVER
    wipe: bool = True
    bootloader_password: str | None = None

    @field_validator("preset")
    @classmethod
    def _custom_not_yet_implemented(cls, v: DiskPreset) -> DiskPreset:
        if v == DiskPreset.CUSTOM:
            raise ValueError(
                "disk.preset='custom' is reserved for v0.2 (operator-supplied layout block); "
                "use 'stig_server' or 'minimal' in v0.1."
            )
        return v


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


class Packages(StrictModel):
    base_groups: list[str] = Field(default_factory=lambda: ["@^minimal-environment", "@standard"])
    required: list[str] = Field(
        default_factory=lambda: [
            "scap-security-guide",
            "openscap-scanner",
            "aide",
            "audit",
            "rsyslog",
            "chrony",
            "firewalld",
            "sudo",
            "policycoreutils-python-utils",
        ]
    )
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
        if self.reboot_window.enable and not (
            self.nightly_security.enable or self.monthly_full.enable
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


class HostConfig(StrictModel):
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
