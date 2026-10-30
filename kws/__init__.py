"""Kali Windows Substitute - core path and secret utilities."""

from kws.paths import (
    resource_root,
    resource,
    user_data_dir,
    sub_dir,
    evidence_dir,
    work_dir,
    secrets_dir,
    db_path,
    to_wsl_path,
)

from kws.secrets import (
    set_secret,
    get_secret,
    delete_secret,
    has_secret,
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