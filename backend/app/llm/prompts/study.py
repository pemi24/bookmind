"""Study mode prompts: quizzes, short-answer grading, flashcards."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.llm.prompts.coerce import to_enum, to_int, to_list, to_str

QuestionType = Literal["multiple_choice", "true_false", "short_answer"]
_TYPES = ("multiple_choice", "true_false", "short_answer")
_TYPE_SYNONYMS = {"mcq": "multiple_choice", "multiple": "multiple_choice", "choice": "multiple_choice",
                  "true": "true_false", "tf": "true_false", "boolean": "true_false", "short": "short_answer",
                  "open": "short_answer", "free": "short_answer", "written": "short_answer"}


class QuestionOut(BaseModel):
    type: QuestionType
    question: str
    options: list[str] = Field(description="4 options for multiple_choice, else empty")
    answer: str = Field(description="multiple_choice: the exact correct option text; true_false: 'True' or "
                                    "'False'; short_answer: a model answer of one or two sentences")
    explanation: str = Field(description="Why this is the answer, referring to the passage")
    passage: int = Field(description="Number of the passage the question is based on")

    _type = field_validator("type", mode="before")(lambda v: to_enum(v, _TYPES, _TYPE_SYNONYMS))
    _options = field_validator("options", mode="before")(lambda v: [str(o) for o in to_list(v)])
    _answer = field_validator("answer", "explanation", mode="before")(to_str)
    _passage = field_validator("passage", mode="before")(lambda v: to_int(v, 1, 999, 1))


class QuizOut(BaseModel):
    title: str = Field(description="Short quiz title")
    questions: list[QuestionOut]

    _title = field_validator("title", mode="before")(lambda v: to_str(v) or "Quiz")


QUIZ_SYSTEM = """You write reading-comprehension quiz questions from numbered book passages. Each \
question must be answerable from one passage and give that passage's number. Test events, \
characters and ideas, not wording trivia. Multiple choice: 4 options, plausible wrong ones, and \
the answer is the exact text of the correct option."""


def _passages(passages: list[str]) -> str:
    return "\n\n".join(f"[{i}]\n{p}" for i, p in enumerate(passages, 1))


def quiz_user(book_title: str, passages: list[str], n: int, types: list[str], difficulty: str) -> str:
    return (f"Book: {book_title}\nPASSAGES:\n\n{_passages(passages)}\n\n"
            f"Write exactly {n} questions. Types allowed: {', '.join(types)} (mix them). Difficulty: {difficulty}.")


class GradeOut(BaseModel):
    index: int
    correct: bool
    feedback: str = Field(description="One sentence: what was right or missing")

    _index = field_validator("index", mode="before")(lambda v: to_int(v, 0, 999, -1))
    _feedback = field_validator("feedback", mode="before")(to_str)


class GradesOut(BaseModel):
    grades: list[GradeOut]

    _grades = field_validator("grades", mode="before")(to_list)


GRADE_SYSTEM = """You grade short answers to reading questions. Mark an answer correct if it \
captures the key idea of the model answer, even with different wording. Be fair and brief."""


def grade_user(items: list[tuple[int, str, str, str]]) -> str:
    lines = [f"[{i}] Question: {q}\nModel answer: {model}\nStudent answer: {student or '(blank)'}"
             for i, q, model, student in items]
    return "Grade each answer (use the number in brackets as index):\n\n" + "\n\n".join(lines)


class CardOut(BaseModel):
    front: str = Field(description="A question, term or prompt")
    back: str = Field(description="Concise answer (1-3 sentences)")
    passage: int

    _passage = field_validator("passage", mode="before")(lambda v: to_int(v, 1, 999, 1))


class CardsOut(BaseModel):
    cards: list[CardOut]

    _cards = field_validator("cards", mode="before")(to_list)


CARDS_SYSTEM = """You create flashcards from numbered book passages: key facts, characters, terms, \
ideas, cause and effect. One idea per card, short answers, no trick questions. Give each card's \
passage number."""


def cards_user(book_title: str, passages: list[str], n: int) -> str:
    return f"Book: {book_title}\nPASSAGES:\n\n{_passages(passages)}\n\nCreate exactly {n} flashcards."
