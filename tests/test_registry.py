from ks_gen.registry import load_rules


def test_registry_discovers_modules():
    rules = load_rules()
    ids = {r.id for r in rules}
    assert "admin_user_and_keys" in ids


def test_registry_skips_underscore_modules():
    rules = load_rules()
    ids = {r.id for r in rules}
    assert "_types" not in ids  # ensure private modules ignored


def test_registry_returns_rule_instances():
    rules = load_rules()
    for r in rules:
        assert hasattr(r, "id")
        assert hasattr(r, "applies")
        assert hasattr(r, "emit_post")
