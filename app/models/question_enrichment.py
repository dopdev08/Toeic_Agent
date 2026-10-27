from datetime import datetime
from typing import TYPE_CHECKING, Any
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.question import Question

ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}
ALLOWED_STATUSES = {"PENDING", "PROCESSING", "COMPLETED", "FAILED"}


class QuestionEnrichment(Base):
    __tablename__ = "question_enrichments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("questions.id"),
        nullable=False,
        unique=True,
    )
    grammar_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    sentence_structure: Mapped[str] = mapped_column(String(255), nullable=False)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    vocabulary: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON(none_as_null=True), nullable=False
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    distractor_analysis: Mapped[dict[str, Any]] = mapped_column(
        JSON(none_as_null=True), nullable=False
    )
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')",
            name="ck_question_enrichments_difficulty",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_question_enrichments_status",
        ),
    )

    question: Mapped["Question"] = relationship(
        "Question",
        back_populates="enrichment",
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("status", "PENDING")
        super().__init__(**kwargs)

    @validates("grammar_topic")
    def validate_grammar_topic(self, key: str, value: Any) -> Any:
        if value is None:
            raise ValueError("grammar_topic cannot be None")
        return value

    @validates("sentence_structure")
    def validate_sentence_structure(self, key: str, value: Any) -> Any:
        if value is None:
            raise ValueError("sentence_structure cannot be None")
        return value

    @validates("pattern")
    def validate_pattern(self, key: str, value: Any) -> Any:
        if value is None:
            raise ValueError("pattern cannot be None")
        return value

    @validates("vocabulary")
    def validate_vocabulary(self, key: str, value: Any) -> Any:
        if value is None:
            raise ValueError("vocabulary cannot be None")
        return value

    @validates("explanation")
    def validate_explanation(self, key: str, value: Any) -> Any:
        if value is None:
            raise ValueError("explanation cannot be None")
        return value

    @validates("distractor_analysis")
    def validate_distractor_analysis(self, key: str, value: Any) -> Any:
        if value is None:
            raise ValueError("distractor_analysis cannot be None")
        return value

    @validates("difficulty")
    def validate_difficulty(self, key: str, value: str) -> str:
        if value not in ALLOWED_DIFFICULTIES:
            raise ValueError(
                f"Invalid difficulty: '{value}'. Must be one of {ALLOWED_DIFFICULTIES}"
            )
        return value

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        if value not in ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status: '{value}'. Must be one of {ALLOWED_STATUSES}"
            )
        return value
