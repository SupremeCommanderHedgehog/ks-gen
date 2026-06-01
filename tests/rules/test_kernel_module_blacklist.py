from ks_gen.rules.kernel_module_blacklist import RULE


def test_post_writes_modprobe_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/modprobe.d/ks-gen-blacklist.conf" in out
    assert "install usb-storage /bin/true" in out
    assert "install squashfs /bin/true" in out


def test_does_not_apply_when_disabled(minimal_cfg):
    from ks_gen.config import KernelModuleBlacklistCfg, Overrides

    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(kernel_module_blacklist=KernelModuleBlacklistCfg(enable=False))
        }
    )
    assert not RULE.applies(cfg)
