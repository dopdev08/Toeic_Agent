from sqlalchemy.orm import Session

from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.repositories.enrichment_repository import EnrichmentRepository
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_validator import EnrichmentValidator


class EnrichmentWorkflow:
    """Synchronous use case workflow combining EnrichmentService, EnrichmentValidator, and EnrichmentRepository.

    - Accepts a Question instance and an active SQLAlchemy Session.
    - Orchestrates AI enrichment generation via EnrichmentService.
    - Validates enrichment quality deterministically via EnrichmentValidator.
    - Persists validated enrichment via EnrichmentRepository.
    - Exclusively owns the transaction boundary (commit on success, rollback on failure).
    - Propagates all enrichment, quality, or database errors without silencing them.
    """

    def __init__(
        self,
        enrichment_service: EnrichmentService | None = None,
        enrichment_repository: EnrichmentRepository | None = None,
        enrichment_validator: EnrichmentValidator | None = None,
    ) -> None:
        self.enrichment_service = enrichment_service or EnrichmentService()
        self.enrichment_repository = enrichment_repository or EnrichmentRepository()
        self.enrichment_validator = enrichment_validator or EnrichmentValidator()

    def execute(
        self,
        session: Session,
        question: Question,
        force: bool = False,
    ) -> QuestionEnrichmentModel:
        """Execute enrichment, quality validation, and persistence within a transactional boundary.

        - Idempotent: If enrichment exists with status COMPLETED and force is False, returns
          the existing record immediately without calling the LLM or mutating the DB.
        - Forced update: If force is True, runs generation and validation pipeline, updates
          the existing record in place upon validation success, and commits.
        - Safe rollback: If generation or validation fails, rolls back so previously committed
          enrichments remain unharmed.
        """
        # 1. Default idempotent check: if already COMPLETED and not forcing re-enrichment
        existing = getattr(question, "enrichment", None)
        if existing is None and hasattr(question, "id") and question.id is not None:
            existing = self.enrichment_repository.get_by_question_id(session, question.id)

        if existing is not None and getattr(existing, "status", None) == "COMPLETED" and not force:
            return existing

        try:
            # 2. Generate and validate AI enrichment schema (no DB operations)
            enrichment_schema = self.enrichment_service.enrich_question(question)

            # 3. Perform deterministic quality validation before persistence
            self.enrichment_validator.validate_and_raise(
                question=question,
                enrichment=enrichment_schema,
            )

            # 4. Persist or update in DB (flush only, no commit inside repository)
            record = self.enrichment_repository.save_enrichment(
                session=session,
                question_id=question.id,
                enrichment=enrichment_schema,
                existing=existing,
            )

            # 5. Workflow explicitly commits the transaction
            session.commit()
            return record

        except Exception:
            # 6. Rollback transaction on any failure (enrichment, quality, or database error)
            session.rollback()
            raise
