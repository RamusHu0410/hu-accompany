"""Builds a quiz set from a typed topic heading.

Selection is deliberately category-balanced rather than a plain random
sample: drawing 20 questions at random from a bank that happens to hold
more terminology entries than context ones produces a quiz that feels
lopsided, and the four categories map to what an RCM paper actually
examines. Questions are dealt round-robin across categories, so a short
quiz still touches composers, forms, terminology and context.
"""

import random
from typing import List, Optional

from .banks import bank_for
from .errors import UnknownTopic
from .models import CATEGORIES, LEVEL_ARCT, QuizSet
from .topic import known_eras, parse_topic

# What the app gets when it does not ask for a specific length.
DEFAULT_LENGTH = 15

# Guard rails: a one-question quiz is not a quiz, and an enormous one just
# returns the whole bank anyway.
MIN_LENGTH = 5
MAX_LENGTH = 60


def generate_quiz(
    topic_text: str,
    length: Optional[int] = None,
    seed: Optional[int] = None,
) -> QuizSet:
    """Parse `topic_text` and draw a balanced quiz from the matching bank.

    `length` is clamped to [MIN_LENGTH, MAX_LENGTH] and then to however many
    questions the bank actually holds. `seed` makes the draw reproducible,
    which is what the tests use; leaving it None gives a fresh quiz per call.

    Raises InvalidQuizRequest (via parse_topic) if the topic is missing, or
    UnknownTopic if it names no era this package covers.
    """
    topic = parse_topic(topic_text)
    if not topic.era_key:
        raise UnknownTopic(
            f"no question bank for that topic; covered eras: "
            f"{', '.join(sorted(known_eras().values()))}"
        )

    pool = bank_for(topic.era_key)
    if not topic.include_arct:
        pool = [q for q in pool if q.level != LEVEL_ARCT]

    wanted = DEFAULT_LENGTH if length is None else int(length)
    wanted = max(MIN_LENGTH, min(MAX_LENGTH, wanted))
    wanted = min(wanted, len(pool))

    rng = random.Random(seed)
    questions = _balanced_draw(pool, wanted, rng)

    return QuizSet(
        era_key=topic.era_key,
        era_name=topic.era_name,
        era_span=topic.era_span,
        level_label=topic.level_label,
        questions=questions,
    )


def _balanced_draw(pool, wanted: int, rng: random.Random) -> List:
    """Deal `wanted` questions round-robin across the four categories.

    Categories that run dry are skipped rather than padded, so a bank with
    only two context questions contributes exactly two and the remainder is
    made up from the categories that still have stock.
    """
    buckets = {category: [] for category in CATEGORIES}
    # Anything with an unrecognized category still gets drawn, via a bucket
    # of its own, rather than being silently dropped.
    for question in pool:
        buckets.setdefault(question.category, []).append(question)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    drawn = []
    order = [c for c in buckets if buckets[c]]
    while len(drawn) < wanted and order:
        for category in list(order):
            if len(drawn) >= wanted:
                break
            if buckets[category]:
                drawn.append(buckets[category].pop())
            if not buckets[category]:
                order.remove(category)

    # Shuffle the final order so the quiz does not present itself as four
    # visibly separate category blocks.
    rng.shuffle(drawn)
    return drawn
