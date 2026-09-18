"""The quiz domain objects.

Framework-free on purpose -- no Django, no serializers -- for the same
reason feedback_generator/judges is: the question banks and the generator
should not depend on how the API layer happens to hand them to a client.
`as_dict` is the one concession, and it exists so api.py stays a thin
translation layer rather than reaching into fields itself.
"""

from dataclasses import dataclass, field
from typing import Dict, List

# Question kinds. `FILL_BLANK` is graded against `accepted` rather than by
# index, since a typed answer has more than one correct spelling.
MULTIPLE_CHOICE = "multiple_choice"
FILL_BLANK = "fill_blank"

# What a question is testing. Mirrors the four areas an RCM history paper
# covers, so a generated set can be balanced across them rather than
# accidentally being all composer-name recall.
CATEGORY_COMPOSERS = "composers"
CATEGORY_FORMS = "forms"
CATEGORY_TERMS = "terminology"
CATEGORY_CONTEXT = "context"

CATEGORIES = (
    CATEGORY_COMPOSERS,
    CATEGORY_FORMS,
    CATEGORY_TERMS,
    CATEGORY_CONTEXT,
)

# Syllabus depth. `CORE` is History 10; `ARCT` questions are only drawn in
# when the requested topic line mentions ARCT.
LEVEL_CORE = "core"
LEVEL_ARCT = "arct"


@dataclass(frozen=True)
class Question:
    """One quiz question.

    `choices` is empty for a fill-in-the-blank. `accepted` holds every
    answer spelling that should be marked correct, lowercased by
    [normalized_accepted]; `answer` is the canonical one shown on the
    results screen.
    """

    id: str
    kind: str
    category: str
    prompt: str
    answer: str
    explanation: str
    choices: List[str] = field(default_factory=list)
    accepted: List[str] = field(default_factory=list)
    level: str = LEVEL_CORE

    def normalized_accepted(self) -> List[str]:
        """Every acceptable answer, lowercased and stripped. Always includes
        `answer` itself so a bank entry never has to repeat it."""
        raw = [self.answer, *self.accepted]
        return [value.strip().lower() for value in raw if value.strip()]

    def as_dict(self) -> Dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "category": self.category,
            "prompt": self.prompt,
            "choices": list(self.choices),
            "answer": self.answer,
            "accepted": self.normalized_accepted(),
            "explanation": self.explanation,
            "level": self.level,
        }


@dataclass(frozen=True)
class QuizSet:
    """A generated quiz: the parsed topic plus the questions drawn for it."""

    era_key: str
    era_name: str
    era_span: str
    level_label: str
    questions: List[Question]

    def as_dict(self) -> Dict:
        return {
            "topic": {
                "era_key": self.era_key,
                "era_name": self.era_name,
                "era_span": self.era_span,
                "level": self.level_label,
            },
            "question_count": len(self.questions),
            "questions": [q.as_dict() for q in self.questions],
        }
