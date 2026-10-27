from collections.abc import Sequence
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.question import Question
from app.schemas.question import QuestionItem


class QuestionImportService:
    @staticmethod
    def import_questions(
        db: Session,
        questions: list[QuestionItem],
        allow_updates: bool = False,
    ) -> tuple[int, int, int]:
        """Import questions into SQLite database via SQLAlchemy with atomic transaction.

        - Checks duplicates against (test_id, part, question_no) in database.
        - Checks duplicates within the batch.
        - When allow_updates is False: skips existing records without modifying them.
        - When allow_updates is True: updates conflicting existing records in place.
        - Saves new questions (increments imported_count).
        - Rolls back all changes atomically if any error occurs.
        """
        if not questions:
            return 0, 0, 0

        imported_count = 0
        skipped_count = 0
        updated_count = 0
        seen_in_batch: set[tuple[str, int, int]] = set()

        try:
            # Query existing (test_id, part, question_no) records in DB
            test_ids = {q.test_id for q in questions}
            existing_records = db.scalars(
                select(Question).where(Question.test_id.in_(test_ids))
            ).all()
            existing_map: dict[tuple[str, int, int], Question] = {
                (q.test_id, q.part, q.question_no): q for q in existing_records
            }

            for item in questions:
                key = (item.test_id, item.part, item.question_no)

                # Duplicate check within batch
                if key in seen_in_batch:
                    skipped_count += 1
                    continue

                seen_in_batch.add(key)

                # Check if record already exists in database
                if key in existing_map:
                    existing = existing_map[key]
                    if allow_updates:
                        existing.question_text = item.question_text
                        existing.option_a = item.option_a
                        existing.option_b = item.option_b
                        existing.option_c = item.option_c
                        existing.option_d = item.option_d
                        existing.correct_answer = item.correct_answer
                        existing.explanation = item.explanation
                        updated_count += 1
                    else:
                        skipped_count += 1
                    continue

                # Map Pydantic QuestionItem to SQLAlchemy Question model
                question_model = Question(
                    test_id=item.test_id,
                    part=item.part,
                    question_no=item.question_no,
                    question_text=item.question_text,
                    option_a=item.option_a,
                    option_b=item.option_b,
                    option_c=item.option_c,
                    option_d=item.option_d,
                    correct_answer=item.correct_answer,
                    explanation=item.explanation,
                )
                db.add(question_model)
                imported_count += 1

            db.commit()
            return imported_count, skipped_count, updated_count

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_questions(
        db: Session,
        test_id: str | None = None,
        part: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Question]:
        """Retrieve questions from database with filtering and pagination."""
        stmt = select(Question)
        if test_id:
            stmt = stmt.where(Question.test_id == test_id)
        if part is not None:
            stmt = stmt.where(Question.part == part)

        stmt = stmt.order_by(Question.test_id, Question.part, Question.question_no).limit(limit).offset(offset)
        return db.scalars(stmt).all()

    @staticmethod
    def get_question_by_id(db: Session, question_id: int) -> Question | None:
        """Retrieve a single question by ID."""
        return db.get(Question, question_id)

    @staticmethod
    def count_questions(
        db: Session,
        test_id: str | None = None,
        part: int | None = None,
    ) -> int:
        """Count total questions matching filters."""
        stmt = select(func.count(Question.id))
        if test_id:
            stmt = stmt.where(Question.test_id == test_id)
        if part is not None:
            stmt = stmt.where(Question.part == part)

        return db.scalar(stmt) or 0
