from ks_gen.disk_layout import size_to_mb


def test_size_to_mb_megabytes():
    assert size_to_mb("500M") == 500


def test_size_to_mb_gigabytes():
    assert size_to_mb("15G") == 15360


def test_size_to_mb_one_gigabyte():
    assert size_to_mb("1G") == 1024
