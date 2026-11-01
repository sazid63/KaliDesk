"""Kali Windows Substitute - core path and secret utilities."""

from kws.paths import (
    db_path,
    evidence_dir,
    resource,
    resource_root,
    secrets_dir,
    sub_dir,
    to_wsl_path,
    user_data_dir,
    work_dir,
)
from kws.secrets import (
    delete_secret,
    get_secret,
    has_secret,
    set_secret,
)

__all__ = [
    "resource_root",
    "resource",
    "user_data_dir",
    "sub_dir",
    "evidence_dir",
    "work_dir",
    "secrets_dir",
    "db_path",
    "to_wsl_path",
    "set_secret",
    "get_secret",
    "delete_secret",
    "has_secret",
]
