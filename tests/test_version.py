"""The version number must be the same everywhere."""
from __future__ import annotations

import re
from pathlib import Path

import server.catalog as catalog
from kws.__about__ import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_is_consistent():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(rf'^version = "{re.escape(__version__)}"$', pyproject, re.M)
    assert catalog.app_meta()["version"] == __version__
    install = (ROOT / "installer" / "setup" / "Install.ps1").read_text(encoding="utf-8")
    assert f"'DisplayVersion'  -Value '{__version__}'" in install
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"v{__version__}" in readme
