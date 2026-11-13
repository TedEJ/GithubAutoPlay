"""Fixture for the build tests: a copy of the project files with an invented source list."""
import json
import shutil

import pytest

from tests.fakes import APP, browser_source, source


@pytest.fixture
def project(tmp_path):
    """A copy of the project files with an invented source list. Returns a helper object."""

    class Project:
        root = tmp_path / "app"
        out = tmp_path / "out"

        def write_sources(self, *sources):
            (self.root / "sources.json").write_text(
                json.dumps({"version": 1, "sources": list(sources)}), encoding="utf-8")

    p = Project()
    p.root.mkdir()
    shutil.copytree(APP / "site", p.root / "site", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(APP / "politics-keywords.json", p.root / "politics-keywords.json")
    p.write_sources(source(), browser_source())
    return p
