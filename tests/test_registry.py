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


def test_registry_ubuntu2404_returns_empty_list():
    rules = load_rules("ubuntu2404")
    assert rules == []
