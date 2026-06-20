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


def test_registry_alma8_returns_same_rule_ids_as_alma9():
    """alma8 phase 2 re-exports all alma9 rules.

    Until any rule's alma8 file becomes a real implementation
    (e.g., when the audit-story PR requires per-distro divergence),
    the two registries return the same set of rule IDs.
    """
    alma9_ids = {r.id for r in load_rules("alma9")}
    alma8_ids = {r.id for r in load_rules("alma8")}
    assert alma8_ids == alma9_ids


def test_registry_alma8_re_exports_same_rule_instances_as_alma9():
    """Pins re-export semantics: same Python object per rule.

    When an alma8 rule file says `from ks_gen.rules.alma9.foo import RULE`,
    the registry walks both packages and finds the SAME singleton RULE.
    This is the load-bearing invariant that lets a future audit-story PR
    branch behavior on `cfg.distro` inside a single shared RULE
    implementation. When a rule's alma8 file eventually becomes a real
    implementation (creating a distinct RULE instance), update or split
    this test.
    """
    alma9_rules = {r.id: r for r in load_rules("alma9")}
    alma8_rules = {r.id: r for r in load_rules("alma8")}
    for rid, alma8_rule in alma8_rules.items():
        assert alma8_rule is alma9_rules[rid], (
            f"alma8 rule {rid!r} should re-export the alma9 instance "
            f"(same Python object). If this rule diverged intentionally, "
            f"update the test."
        )


def test_registry_alma8_package_exists():
    """alma8 package marker exists; phase 2 populated it with re-exports."""
    import importlib

    pkg = importlib.import_module("ks_gen.rules.alma8")
    assert pkg.__path__  # truthy => is a real package
