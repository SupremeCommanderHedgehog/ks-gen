from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class HostConfig(StrictModel):
    meta: Meta = Field(default_factory=Meta)
    system: System
    network: Network = Field(default_factory=Network)
    disk: Disk = Field(default_factory=Disk)
