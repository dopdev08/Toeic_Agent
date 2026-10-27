from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.enrichment import (
    BatchEnrichmentRequest,
    BatchEnrichmentResponse,
    BatchItemResponse,
)
from app.services.batch_enrichment_workflow import BatchEnrichmentWorkflow

router = APIRouter(prefix="/api/v1/enrichments", tags=["Enrichments"])


def get_batch_enrichment_workflow() -> BatchEnrichmentWorkflow:
    """Dependency provider for BatchEnrichmentWorkflow."""
    return BatchEnrichmentWorkflow()


@router.post(
    "/batch",
    response_model=BatchEnrichmentResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Batch enrich multiple questions sequentially",
)
def enrich_batch_questions(
    request: BatchEnrichmentRequest,
    db: Session = Depends(get_db),
    workflow: BatchEnrichmentWorkflow = Depends(get_batch_enrichment_workflow),
) -> BatchEnrichmentResponse:
    """Synchronous HTTP endpoint for enriching a batch of questions.

    - Validates request (non-empty list of positive, unique integers).
    - Delegates execution, question lookup, transactions, and error isolation to BatchEnrichmentWorkflow.
    - Does NOT call commit or rollback directly.
    - Exposes only serializable application data.
    """
    batch_result = workflow.execute(session=db, items=request.question_ids)

    return BatchEnrichmentResponse(
        total=batch_result.total,
        success=batch_result.success,
        failed=batch_result.failed,
        results=[
            BatchItemResponse(
                question_id=item.question_id,
                status=item.status,
                error=item.error,
            )
            for item in batch_result.results
        ],
    )
