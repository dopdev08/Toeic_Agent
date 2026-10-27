from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.schemas.enrichment import QuestionEnrichment as QuestionEnrichmentSchema


class EnrichmentRepository:
    """Repository component for persisting and querying QuestionEnrichment models."""

    @classmethod
    def save_enrichment(
        cls,
        session: Session,
        question_id: int,
        enrichment: QuestionEnrichmentSchema,
        status: str = "COMPLETED",
        existing: QuestionEnrichmentModel | None = None,
    ) -> QuestionEnrichmentModel:
        """Persist or update QuestionEnrichment in database and flush.

        - If existing record is provided or found in DB: updates in-place, preserving row ID.
        - If no record exists: maps schema to new SQLAlchemy model.
        - Preserves vocabulary and distractor_analysis as native Python structures for JSON columns.
        - Adds/flushes so DB constraints are enforced and ID is populated.
        - Does NOT commit the session; caller owns transaction boundary.
        - Returns the persisted QuestionEnrichment SQLAlchemy instance.
        """
        vocab_data = [item.model_dump() for item in enrichment.vocabulary]
        distractor_data = enrichment.distractor_analysis.model_dump()

        if existing is not None:
            existing.grammar_topic = enrichment.grammar_topic
            existing.sentence_structure = enrichment.sentence_structure
            existing.pattern = enrichment.pattern
            existing.vocabulary = vocab_data
            existing.explanation = enrichment.explanation
            existing.distractor_analysis = distractor_data
            existing.difficulty = enrichment.difficulty
            existing.status = status
            session.flush()
            return existing

        record = QuestionEnrichmentModel(
            question_id=question_id,
            grammar_topic=enrichment.grammar_topic,
            sentence_structure=enrichment.sentence_structure,
            pattern=enrichment.pattern,
            vocabulary=vocab_data,
            explanation=enrichment.explanation,
            distractor_analysis=distractor_data,
            difficulty=enrichment.difficulty,
            status=status,
        )

        session.add(record)
        session.flush()
        return record

    @staticmethod
    def get_by_question_id(
        session: Session, question_id: int
    ) -> QuestionEnrichmentModel | None:
        """Query persisted QuestionEnrichment record by question_id."""
        stmt = select(QuestionEnrichmentModel).where(
            QuestionEnrichmentModel.question_id == question_id
        )
        return session.scalars(stmt).first()
