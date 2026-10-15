"""run_shell must EXECUTE commands in the shell the model expects.

Forensic 2026-07-13 18:15: on Windows, ``shlex.split(posix=False)`` kept the
surrounding quotes inside tokens, so ``powershell -Command "X"`` received a
string literal and echoed it with exit 0 — a false success that sent the
delegated brain into a retry loop until its iteration budget was exhausted.

Redesign 2026-08-08: Windows now runs Windows PowerShell (via
``-EncodedCommand``), POSIX runs ``/bin/sh -c``. The tests below pin the
contract that matters to the brain: commands execute (not echo), native exit
codes propagate (no false success), and pipes work on both platforms.
"""

from __future__ import annotations

import sys

import pytest

from jarvis.plugins.tool.run_shell import (
    RunShellTool,
    _normalize_nested_shell_executable,
    _windows_subprocess_env,
)

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows PowerShell semantics"
)
posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX sh semantics"
)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # A bare first-word PowerShell gains the suffix.
        ('powershell -Command "hi"', 'powershell.exe -Command "hi"'),
        ('  powershell -Command "hi"', '  powershell.exe -Command "hi"'),
        ('& powershell -Command "hi"', '& powershell.exe -Command "hi"'),
        ('PowerShell -Command "hi"', 'PowerShell.exe -Command "hi"'),
        ("pwsh -File x.ps1", "pwsh.exe -File x.ps1"),
        # Already suffixed, or not a bare PowerShell name: untouched.
        ('powershell.exe -Command "hi"', 'powershell.exe -Command "hi"'),
        ("pwsh.exe -File x.ps1", "pwsh.exe -File x.ps1"),
        ('powershell.extra -Command "hi"', 'powershell.extra -Command "hi"'),
        ("powershellscript cmd", "powershellscript cmd"),
        ('"C:\\x\\powershell.exe" -Command "hi"', '"C:\\x\\powershell.exe" -Command "hi"'),
        ('Get-Process | powershell -Command "hi"', 'Get-Process | powershell -Command "hi"'),
        ('echo powershell -Command "hi"', 'echo powershell -Command "hi"'),
        # Non-PowerShell commands are never rewritten.
        ("echo hi", "echo hi"),
        ("cmd /c echo hi", "cmd /c echo hi"),
    ],
)
def test_bare_powershell_first_word_gains_the_exe_suffix(
    command: str, expected: str
) -> None:
    """A bare ``powershell`` must become ``powershell.exe`` before launch.

    Forensic 2026-10-15 (Windows 11, deterministic): a zero-byte,
    extension-less ``powershell`` in ``System32`` wins the bare-name lookup, so
    a nested ``powershell -Command "..."`` was launched from a file that is not
    a program and ``run_shell`` hung to its timeout ("Timeout after 30.0s").
    ``where powershell`` -> ``System32\\powershell`` (0 bytes);
    ``where powershell.exe`` -> ``WindowsPowerShell\\v1.0\\powershell.exe``.
    With the suffix the same command answers in under a second (measured 3/3).
    """
    assert _normalize_nested_shell_executable(command) == expected


def test_non_powershell_commands_are_byte_identical() -> None:
    """No rewrite may touch a command that is not a bare nested PowerShell."""
    for command in (
        "Get-ChildItem -Recurse | Select-Object Name",
        "python -c \"print('x')\"",
        "git status --short",
    ):
        assert _normalize_nested_shell_executable(command) == command


@pytest.mark.asyncio
async def test_empty_command_is_rejected() -> None:
    result = await RunShellTool().execute({"command": "  "}, None)
    assert result.success is False


def test_description_names_the_shell() -> None:
    """The brain writes commands for the shell the description declares."""
    description = RunShellTool().description
    if sys.platform == "win32":
        assert "PowerShell" in description
    else:
        assert "/bin/sh" in description


@windows_only
@pytest.mark.asyncio
async def test_quoted_powershell_command_is_executed_not_echoed() -> None:
    result = await RunShellTool().execute(
        {"command": 'powershell -Command "Write-Output hello-from-ps"'},
        None,
    )
    assert result.success is True
    stdout = result.output["stdout"]
    assert "hello-from-ps" in stdout
    assert "Write-Output" not in stdout


@windows_only
@pytest.mark.asyncio
async def test_powershell_cmdlet_works(tmp_path) -> None:
    (tmp_path / "probe-file.md").write_text("x", encoding="utf-8")
    result = await RunShellTool().execute(
        {"command": "Get-ChildItem -Name", "cwd": str(tmp_path)},
        None,
    )
    assert result.success is True
    assert "probe-file.md" in result.output["stdout"]


@windows_only
@pytest.mark.asyncio
async def test_pipes_work_on_windows() -> None:
    result = await RunShellTool().execute(
        {"command": 'Write-Output alpha beta | Select-Object -First 1'},
        None,
    )
    assert result.success is True
    stdout = result.output["stdout"]
    assert "alpha" in stdout
    assert "beta" not in stdout


@windows_only
@pytest.mark.asyncio
async def test_native_exit_code_propagates() -> None:
    """PowerShell itself exits 0 after a failed native command — the wrapper
    must surface the REAL exit code, or the brain sees a false success."""
    result = await RunShellTool().execute({"command": "cmd.exe /c exit 7"}, None)
    assert result.success is False
    assert result.output["exit_code"] == 7


@windows_only
@pytest.mark.asyncio
async def test_failing_cmdlet_is_not_a_false_success() -> None:
    result = await RunShellTool().execute(
        {"command": "Get-Item C:\\definitely-missing-probe-xyz"},
        None,
    )
    assert result.success is False
    stderr = result.output["stderr"]
    assert "definitely-missing-probe-xyz" in stderr
    assert "CLIXML" not in stderr  # error must be plain text the brain can read


@windows_only
def test_windows_subprocess_env_compacts_semantic_path_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setenv(
        "PATH",
        (
            r'"C:\Tools";c:\tools\;%SystemRoot%\System32;'
            r"C:\Windows\System32;C:\Other"
        ),
    )
    monkeypatch.setenv("JARVIS_TEST_SENTINEL", "preserved")

    env = _windows_subprocess_env()

    assert env["PATH"].split(";") == [
        r'"C:\Tools"',
        r"%SystemRoot%\System32",
        r"C:\Other",
    ]
    assert env["JARVIS_TEST_SENTINEL"] == "preserved"


@posix_only
@pytest.mark.asyncio
async def test_posix_simple_command_works() -> None:
    result = await RunShellTool().execute({"command": "echo hello"}, None)
    assert result.success is True
    assert "hello" in result.output["stdout"]


@posix_only
@pytest.mark.asyncio
async def test_pipes_work_on_posix() -> None:
    result = await RunShellTool().execute(
        {"command": "echo hello | tr a-z A-Z"}, None
    )
    assert result.success is True
    assert "HELLO" in result.output["stdout"]


@posix_only
@pytest.mark.asyncio
async def test_posix_exit_code_propagates() -> None:
    result = await RunShellTool().execute({"command": "exit 7"}, None)
    assert result.success is False
    assert result.output["exit_code"] == 7


@posix_only
@pytest.mark.asyncio
async def test_posix_missing_command_is_readable_failure() -> None:
    """sh reports 127 with the command name on stderr — the brain needs that
    text to reformulate instead of retrying blindly."""
    result = await RunShellTool().execute(
        {"command": "definitely-missing-cmd-xyz"}, None
    )
    assert result.success is False
    assert result.output["exit_code"] == 127
    assert "definitely-missing-cmd-xyz" in result.output["stderr"]
