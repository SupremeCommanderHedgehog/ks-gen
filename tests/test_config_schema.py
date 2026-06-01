import pytest
from pydantic import ValidationError

from ks_gen.config import HostConfig, Meta, System


def test_meta_defaults():
    m = Meta()
    assert m.release == "9"
    assert m.profile == "stig"
    assert m.scap_content == "ssg-almalinux9-ds.xml"


def test_system_requires_hostname():
    with pytest.raises(ValidationError):
        System()


def test_system_defaults():
    s = System(hostname="web01.example.com")
    assert s.timezone == "UTC"
    assert s.locale == "en_US.UTF-8"
    assert s.keyboard == "us"


def test_host_config_partial_ok():
    # Only meta + system are required at this stage.
    cfg = HostConfig.model_validate({"meta": {}, "system": {"hostname": "web01.example.com"}})
    assert cfg.system.hostname == "web01.example.com"


def test_unknown_top_level_key_rejected():
    with pytest.raises(ValidationError):
        HostConfig.model_validate({"meta": {}, "system": {"hostname": "x"}, "garbage": True})
