"""The baseline install must not download apt's Contents indexes (tens of megabytes each)."""
from __future__ import annotations

import app.runtime as runtime
import server.config as config


def test_apt_update_disables_contents_indexes(monkeypatch):
    calls = []

    def fake_in_distro(cfg, argv, timeout=60, stdin_text=None):
        calls.append(argv)
        return 1, "", "stop after the update"  # stop right after the update step

    monkeypatch.setattr(runtime, "_in_distro", fake_in_distro)
    monkeypatch.setattr(runtime, "_ensure_apt_components", lambda cfg: None)
    runtime._install_baseline(config.load())
    update = next(argv for argv in calls if "update" in argv)
    joined = " ".join(update)
    assert "Contents-deb::DefaultEnabled=false" in joined
    assert "Contents-dsc::DefaultEnabled=false" in joined
