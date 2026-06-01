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
            "oscap-anaconda-addon",
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
