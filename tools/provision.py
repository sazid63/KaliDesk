"""Provision the private runtime, for testing (NOT part of the app).

Run from the repository root:  python tools/provision.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.runtime as runtime  # noqa: E402
import server.config as config  # noqa: E402

cfg = config.load()
print("status before:", runtime.status(cfg))
print("ensure:", runtime.ensure(cfg))
print("status after:", runtime.status(cfg))
