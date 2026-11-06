"""Smoke tests: the skeleton can be imported and started."""

import importlib


def test_package_can_be_imported():
    module = importlib.import_module("countdown")
    assert module.__doc__


def test_main_returns_zero(capsys):
    from countdown.__main__ import main

    assert main() == 0
    assert "not playable yet" in capsys.readouterr().out
