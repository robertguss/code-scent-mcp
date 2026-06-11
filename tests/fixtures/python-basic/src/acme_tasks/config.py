from __future__ import annotations


DEFAULT_STATUS = "pending-review"
ESCALATION_STATUS = "pending-review"
NOTIFICATION_STATUS = "pending-review"


def load_config(environment: str) -> dict[str, str]:
    settings = {
        "environment": environment,
        "status": DEFAULT_STATUS,
        "queue": "ops",
    }

    # TODO: split staging and local credentials.
    # TODO: move queue names into deployment config.
    # FIXME: preserve migration compatibility before renaming status values.
    return settings
