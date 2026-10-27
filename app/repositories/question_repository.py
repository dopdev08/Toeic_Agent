from collections.abc import Sequence
from sqlalchemy.orm import Session

from app.models.question import Question
from app.schemas.question import QuestionItem
from app.services.question_import_service import QuestionImportService


class QuestionRepository:
    """Repository for Question Bank queries and persistence."""

    def import_questions_transaction(
        self, db: Session, questions: list[QuestionItem], allow_updates: bool = False
    ) -> tuple[int, int, int]:
        return QuestionImportService.import_questions(db, questions, allow_updates=allow_updates)

    def get_questions(
        self,
        db: Session,
        test_id: str | None = None,
        part: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Question]:
        return QuestionImportService.get_questions(
            db, test_id=test_id, part=part, limit=limit, offset=offset
        )

    def get_question_by_id(self, db: Session, question_id: int) -> Question | None:
        return QuestionImportService.get_question_by_id(db, question_id)

    def count_questions(
        self,
        db: Session,
        test_id: str | None = None,
        part: int | None = None,
    ) -> int:
        return QuestionImportService.count_questions(db, test_id=test_id, part=part)
