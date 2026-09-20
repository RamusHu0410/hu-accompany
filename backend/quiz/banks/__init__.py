"""Question banks, one module per era.

Adding an era means writing a new module with a module-level QUESTIONS list
and registering it below and in topic.ERA_ALIASES. Nothing else in the
package needs to change.
"""

from typing import Dict, List

from ..models import Question
from . import baroque, classical, middle_ages, modern, renaissance, romantic

_BANKS = {
    "middle_ages": middle_ages.QUESTIONS,
    "renaissance": renaissance.QUESTIONS,
    "baroque": baroque.QUESTIONS,
    "classical": classical.QUESTIONS,
    "romantic": romantic.QUESTIONS,
    "modern": modern.QUESTIONS,
}


def bank_for(era_key: str) -> List[Question]:
    """Every question written for one era, core and ARCT alike. Returns a
    copy so callers can shuffle in place without corrupting the bank."""
    return list(_BANKS.get(era_key, ()))


def bank_sizes() -> Dict[str, int]:
    """era_key -> question count, for the API's capability response."""
    return {key: len(value) for key, value in _BANKS.items()}


__all__ = ["bank_for", "bank_sizes"]
