from ks_gen import __version__


def test_version_is_a_string():
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 2
