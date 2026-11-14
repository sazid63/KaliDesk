"""Single source of truth for the application version.

pyproject.toml, catalog/tools.yaml, the installer and the CHANGELOG must all show
this number; tests/test_version.py fails the build if they drift apart.
"""

__version__ = "1.5.0"
