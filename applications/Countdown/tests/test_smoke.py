"""Smoke tests: the package can be imported and started, without tkinter or a display."""

import importlib
import sys
import types


def test_package_can_be_imported():
    module = importlib.import_module("countdown")
    assert module.__doc__


def test_main_runs_the_gui_and_returns_its_exit_code(monkeypatch):
    calls = []
    fake_gui = types.ModuleType("countdown.gui")
    fake_gui.run = lambda: calls.append("run") or 0
    monkeypatch.setitem(sys.modules, "countdown.gui", fake_gui)
    monkeypatch.setattr("countdown.gui", fake_gui, raising=False)

    from countdown.__main__ import main

    assert main() == 0
    assert calls == ["run"]


def test_main_explains_a_missing_tkinter(monkeypatch, capsys):
    # A None entry in sys.modules makes "import countdown.gui" raise ImportError.
    monkeypatch.setitem(sys.modules, "countdown.gui", None)

    from countdown.__main__ import main

    assert main() == 1
    assert "tkinter" in capsys.readouterr().out
