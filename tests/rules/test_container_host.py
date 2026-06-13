from ks_gen.config import Containers
from ks_gen.rules.container_host import RULE


def test_container_host_rule_id_and_summary():
    assert RULE.id == "container_host"
    assert "rootless" in RULE.summary.lower() or "container" in RULE.summary.lower()


def test_container_host_rule_does_not_apply_by_default(minimal_cfg):
    assert RULE.applies(minimal_cfg) is False


def test_container_host_rule_applies_when_enabled(minimal_cfg):
    enabled_cfg = minimal_cfg.model_copy(update={"containers": Containers(enabled=True)})
    assert RULE.applies(enabled_cfg) is True


def test_container_host_emit_packages_returns_podman_stack(minimal_cfg):
    pkgs = RULE.emit_packages(minimal_cfg)
    assert "podman" in pkgs
    assert "crun" in pkgs
    assert "slirp4netns" in pkgs
    assert "fuse-overlayfs" in pkgs
    assert "containers-common" in pkgs
    assert "podman-plugins" in pkgs


def test_container_host_emit_tailoring_is_empty(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_container_host_exception_entry_is_none(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is None


def test_container_host_rule_is_discoverable():
    from ks_gen.registry import load_rules

    rule_ids = {r.id for r in load_rules()}
    assert "container_host" in rule_ids
