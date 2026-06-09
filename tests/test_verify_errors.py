from __future__ import annotations

import pytest

from ks_gen.loader import ExitCode
from ks_gen.verify.errors import (
    ArfMissingError,
    ArfParseError,
    OscapInvocationError,
    SshConnectError,
    SudoPromptError,
    ToolMissingError,
    VerifyError,
)


def test_new_exit_codes_added() -> None:
    assert ExitCode.VERIFY_FAIL == 6
    assert ExitCode.TRANSPORT_FAIL == 7


@pytest.mark.parametrize(
    "cls,expected_exit",
    [
        (SshConnectError, ExitCode.TRANSPORT_FAIL),
        (SudoPromptError, ExitCode.TRANSPORT_FAIL),
        (OscapInvocationError, ExitCode.TRANSPORT_FAIL),
        (ArfMissingError, ExitCode.TRANSPORT_FAIL),
        (ArfParseError, ExitCode.TRANSPORT_FAIL),
        (ToolMissingError, ExitCode.TOOL_MISSING),
    ],
)
def test_error_maps_to_exit_code(cls: type[VerifyError], expected_exit: ExitCode) -> None:
    err = cls("a message")
    assert err.exit_code == expected_exit
    assert str(err) == "a message"


def test_verify_error_is_exception() -> None:
    with pytest.raises(VerifyError):
        raise SshConnectError("x")


def test_tailoring_parse_error_has_verify_fail_exit_code() -> None:
    from ks_gen.loader import ExitCode
    from ks_gen.verify.errors import TailoringParseError, VerifyError

    err = TailoringParseError("garbage")
    assert isinstance(err, VerifyError)
    assert err.exit_code == ExitCode.VERIFY_FAIL
