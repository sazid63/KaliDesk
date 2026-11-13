"""First-run onboarding state.

The guide itself lives in ui/onboarding.js and reflects the real state of the runtime and
tools. The server only remembers that the user finished it and accepted the acceptable-use
statement.
"""

from __future__ import annotations

import server.db as db


def finish_onboarding(accepted: bool) -> bool:
    """Record completion. Refuses unless the acceptable-use statement was accepted."""
    if not accepted:
        return False
    db.set_setting("onboarding_complete", "1")
    return True


def is_onboarding_needed() -> bool:
    return db.get_setting("onboarding_complete", "") != "1"
