from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class HostConfig(StrictModel):
    meta: Meta = Field(default_factory=Meta)
    system: System
