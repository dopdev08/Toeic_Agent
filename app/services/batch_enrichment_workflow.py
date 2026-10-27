from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from sqlalchemy.orm import Session

from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.services.enrichment_workflow import EnrichmentWorkflow

if TYPE_CHECKING:
    from app.repositories.question_repository import QuestionRepository


@dataclass
class BatchItemResult:
    """Individual question result within a batch enrichment execution."""

    question_id: int
    status: str  # "COMPLETED" or "FAILED"
    error: str | None = None
    exception: Exception | None = None
    enrichment: QuestionEnrichmentModel | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "question_id": self.question_id,
            "status": self.status,
        }
        if self.error is not None:
            data["error"] = self.error
        return data


@dataclass
class BatchEnrichmentResult:
    """Aggregated application-level result of batch enrichment processing."""

    total: int
    success: int
    failed: int
    results: list[BatchItemResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "results": [r.to_dict() for r in self.results],
        }


class BatchEnrichmentWorkflow:
    """Synchronous application-level workflow for enriching multiple questions.

    - Processes items sequentially (no concurrency, no background jobs).
    - Delegates single-question enrichment and persistence to EnrichmentWorkflow.
    - Preserves independent transaction boundary per question (EnrichmentWorkflow owns transactions).
    - BatchEnrichmentWorkflow does NOT own or manage session.commit() / session.rollback().
    - On individual question failure:
        * records failure with error details and original exception.
        * continues processing subsequent questions.
    """

    def __init__(
        self,
        enrichment_workflow: EnrichmentWorkflow | None = None,
        question_repository: "QuestionRepository | None" = None,
    ) -> None:
        if question_repository is None:
            from app.repositories.question_repository import QuestionRepository

            self.question_repository = QuestionRepository()
        else:
            self.question_repository = question_repository
        self.enrichment_workflow = enrichment_workflow or EnrichmentWorkflow()

    def execute(
        self,
        session: Session,
        items: Sequence[int | Question],
    ) -> BatchEnrichmentResult:
        """Execute enrichment across a collection of Question instances or question IDs."""
        total = len(items)
        results: list[BatchItemResult] = []
        success_count = 0
        failed_count = 0

        for item in items:
            # 1. Resolve question instance and ID
            if isinstance(item, Question):
                question_id = item.id
                question = item
            elif isinstance(item, int):
                question_id = item
                question = self.question_repository.get_question_by_id(session, question_id)
                if question is None:
                    results.append(
                        BatchItemResult(
                            question_id=question_id,
                            status="FAILED",
                            error=f"Question with ID {question_id} not found",
                            exception=KeyError(f"Question with ID {question_id} not found"),
                        )
                    )
                    failed_count += 1
                    continue
            else:
                # Unsupported item type fallback
                results.append(
                    BatchItemResult(
                        question_id=-1,
                        status="FAILED",
                        error=f"Unsupported item type: {type(item)}",
                        exception=TypeError(f"Unsupported item type: {type(item)}"),
                    )
                )
                failed_count += 1
                continue

            # 2. Delegate enrichment and transaction to EnrichmentWorkflow
            try:
                record = self.enrichment_workflow.execute(session=session, question=question)
                results.append(
                    BatchItemResult(
                        question_id=question_id,
                        status="COMPLETED",
                        enrichment=record,
                    )
                )
                success_count += 1
            except Exception as exc:
                results.append(
                    BatchItemResult(
                        question_id=question_id,
                        status="FAILED",
                        error=str(exc),
                        exception=exc,
                    )
                )
                failed_count += 1

        return BatchEnrichmentResult(
            total=total,
            success=success_count,
            failed=failed_count,
            results=results,
        )
