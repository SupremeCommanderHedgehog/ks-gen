from ks_gen.config import DiskLvDef
from ks_gen.disk_layout import effective_fsoptions, effective_size_mb, size_to_mb


def test_size_to_mb_megabytes():
    assert size_to_mb("500M") == 500


def test_size_to_mb_gigabytes():
    assert size_to_mb("15G") == 15360


def test_size_to_mb_one_gigabyte():
    assert size_to_mb("1G") == 1024


def test_size_to_mb_terabytes():
    assert size_to_mb("1T") == 1024 * 1024


def test_effective_size_mb_explicit():
    lv = DiskLvDef(name="data", mount="/data", size="20G")
    assert effective_size_mb(lv) == 20480


def test_effective_size_mb_default_for_var():
    lv = DiskLvDef(name="var", mount="/var")
    assert effective_size_mb(lv) == 10240


def test_effective_size_mb_default_for_root():
    lv = DiskLvDef(name="root", mount="/")
    assert effective_size_mb(lv) == 15360


def test_effective_size_mb_recommended_for_swap():
    lv = DiskLvDef(name="swap", fstype="swap")
    assert effective_size_mb(lv) == "recommended"


def test_effective_size_mb_explicit_recommended():
    lv = DiskLvDef(name="swap", size="recommended", fstype="swap")
    assert effective_size_mb(lv) == "recommended"


def test_effective_fsoptions_explicit_passthrough():
    lv = DiskLvDef(name="var", mount="/var", fsoptions="nodev,custom")
    assert effective_fsoptions(lv) == "nodev,custom"


def test_effective_fsoptions_default_for_var_log_audit():
    lv = DiskLvDef(name="varlogaudit", mount="/var/log/audit")
    assert effective_fsoptions(lv) == "nodev,nosuid,noexec"


def test_effective_fsoptions_default_for_home_is_baseline_only():
    # STIG baseline: /home gets nodev,nosuid but NOT noexec.
    lv = DiskLvDef(name="home", mount="/home")
    assert effective_fsoptions(lv) == "nodev,nosuid"
    assert "noexec" not in effective_fsoptions(lv)


def test_effective_fsoptions_none_for_root():
    lv = DiskLvDef(name="root", mount="/")
    assert effective_fsoptions(lv) is None


def test_effective_fsoptions_none_for_swap():
    lv = DiskLvDef(name="swap", fstype="swap")
    assert effective_fsoptions(lv) is None
