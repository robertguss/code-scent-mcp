"""Deep nesting fixture (depth 5)."""

from __future__ import annotations


def nested(flag: bool) -> int:
    if flag:
        for _ in range(1):
            while flag:
                if flag:
                    if flag:
                        return 1
    return 0
