import pytest

from boatev.cli import COMMANDS, main

NAMES = [
    "download",
    "parse",
    "odds",
    "beforeinfo",
    "features",
    "train",
    "backtest",
    "today",
    "precheck",
]


def test_command_list():
    assert list(COMMANDS) == NAMES


def test_help_lists_all(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for name in NAMES:
        assert name in out


@pytest.mark.parametrize("name", [n for n in NAMES if n != "precheck"])
def test_stub_exit_code(name, capsys):
    assert main([name]) == 2
    captured = capsys.readouterr()
    assert "未実装" in captured.err
    assert captured.out == ""
