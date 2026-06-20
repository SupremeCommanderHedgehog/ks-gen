from ks_gen.registry import load_rules


def test_registry_discovers_alma9_modules():
    rules = load_rules("alma9")
    ids = {r.id for r in rules}
    assert "admin_user_and_keys" in ids
    assert "banner_text" in ids
    assert "ssh_keep_open" in ids


def test_registry_skips_underscore_modules_in_alma9():
    rules = load_rules("alma9")
    ids = {r.id for r in rules}
    assert "_types" not in ids
    assert not any(rid.startswith("_") for rid in ids)


def test_registry_returns_rule_instances_for_alma9():
    rules = load_rules("alma9")
    assert len(rules) >= 15
    for r in rules:
        assert hasattr(r, "id")
        assert hasattr(r, "applies")
        assert hasattr(r, "emit_post")


def test_registry_ubuntu2404_loads_admin_user_and_keys():
    rules = load_rules("ubuntu2404")
    ids = {r.id for r in rules}
    assert "admin_user_and_keys" in ids


def test_registry_ubuntu2404_package_exists():
    """ubuntu2404 package marker exists post-phase-2 so phase 3 has a home.

    Before this file existed, `load_rules('ubuntu2404')` returned [] via the
    `ModuleNotFoundError` branch; now it returns [] via a real (empty)
    package iterated by pkgutil.
    """
    import importlib

    pkg = importlib.import_module("ks_gen.rules.ubuntu2404")
    assert pkg.__path__  # truthy => is a real package


def test_registry_alma8_returns_empty_for_phase_1():
    """alma8 package exists post-phase-1 but ships no rules yet.

    Phase 1 of #121 added the empty package marker so `load_rules("alma8")`
    returns [] via the real-but-empty-package branch (not the
    ModuleNotFoundError branch). Phase 2 starts populating per-rule
    siblings of the alma9 rules.
    """
    assert load_rules("alma8") == []


def test_registry_alma8_package_exists():
    """alma8 package marker exists so phase 2 has a home."""
    import importlib

    pkg = importlib.import_module("ks_gen.rules.alma8")
    assert pkg.__path__  # truthy => is a real package
