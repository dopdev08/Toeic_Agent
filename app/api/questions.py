from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories.question_repository import QuestionRepository
from app.schemas.enrichment import (
    DistractorAnalysis,
    QuestionEnrichment,
    QuestionEnrichmentResponse,
    VocabularyItem,
)
from app.schemas.question import QuestionDetail, QuestionWithEnrichmentResponse
from app.services.enrichment_response_parser import (
    EnrichmentJSONDecodeError,
    EnrichmentValidationError,
)
from app.services.enrichment_validator import EnrichmentQualityError
from app.services.enrichment_workflow import EnrichmentWorkflow
from app.services.llm_client import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderError,
    LLMTimeoutError,
)
from app.services.question_import_service import QuestionImportService

router = APIRouter(prefix="/api/v1/questions", tags=["Questions"])


def get_enrichment_workflow() -> EnrichmentWorkflow:
    """Dependency provider for EnrichmentWorkflow."""
    return EnrichmentWorkflow()


@router.get("", status_code=status.HTTP_200_OK, summary="List questions from Question Bank")
def list_questions(
    test_id: str | None = Query(None, description="Filter by test ID"),
    part: int | None = Query(5, description="Filter by TOEIC part (default is 5 for Part 5)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    questions = QuestionImportService.get_questions(
        db=db, test_id=test_id, part=part, limit=limit, offset=offset
    )
    total = QuestionImportService.count_questions(db=db, test_id=test_id, part=part)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [QuestionDetail.model_validate(q) for q in questions],
    }


@router.get(
    "/{question_id}",
    response_model=QuestionWithEnrichmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single question details with optional enrichment",
)
def get_question(
    question_id: int,
    db: Session = Depends(get_db),
) -> QuestionWithEnrichmentResponse:
    question = QuestionRepository().get_question_by_id(db=db, question_id=question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question with ID {question_id} not found",
        )

    enrichment_payload = None
    if question.enrichment is not None:
        enrichment_payload = QuestionEnrichment(
            grammar_topic=question.enrichment.grammar_topic,
            sentence_structure=question.enrichment.sentence_structure,
            pattern=question.enrichment.pattern,
            vocabulary=[VocabularyItem(**item) for item in question.enrichment.vocabulary],
            explanation=question.enrichment.explanation,
            distractor_analysis=DistractorAnalysis(**question.enrichment.distractor_analysis),
            difficulty=question.enrichment.difficulty,
        )

    return QuestionWithEnrichmentResponse(
        id=question.id,
        test_id=question.test_id,
        part=question.part,
        question_no=question.question_no,
        question_text=question.question_text,
        option_a=question.option_a,
        option_b=question.option_b,
        option_c=question.option_c,
        option_d=question.option_d,
        correct_answer=question.correct_answer,
        explanation=question.explanation,
        created_at=question.created_at,
        enrichment=enrichment_payload,
    )


@router.post(
    "/{question_id}/enrich",
    response_model=QuestionEnrichmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Enrich a single question with pedagogical AI analysis and persist result",
)
def enrich_single_question(
    question_id: int,
    force: bool = Query(False, description="Force re-enrichment if already completed"),
    db: Session = Depends(get_db),
    workflow: EnrichmentWorkflow = Depends(get_enrichment_workflow),
) -> QuestionEnrichmentResponse:
    # 1. Load Question from Question Bank
    question = QuestionImportService.get_question_by_id(db=db, question_id=question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question with ID {question_id} not found",
        )

    # 2. Execute workflow within its owned transaction boundary
    try:
        record = workflow.execute(session=db, question=question, force=force)
    except LLMAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM service authentication failed: {exc}",
        ) from exc
    except LLMConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM service connection failed: {exc}",
        ) from exc
    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"LLM service timed out: {exc}",
        ) from exc
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {exc}",
        ) from exc
    except EnrichmentJSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to parse LLM response as JSON: {exc}",
        ) from exc
    except EnrichmentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM response failed schema validation: {exc}",
        ) from exc
    except EnrichmentQualityError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Enrichment quality validation failed [{exc.code}]: {exc}",
        ) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Enrichment database integrity conflict: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected enrichment error: {exc}",
        ) from exc

    # 3. Map to dedicated API response schema (excluding internal database IDs/status)
    return QuestionEnrichmentResponse(
        question_id=record.question_id,
        grammar_topic=record.grammar_topic,
        sentence_structure=record.sentence_structure,
        pattern=record.pattern,
        vocabulary=[VocabularyItem(**item) for item in record.vocabulary],
        explanation=record.explanation,
        distractor_analysis=DistractorAnalysis(**record.distractor_analysis),
        difficulty=record.difficulty,
    )
