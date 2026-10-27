from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.question import (
    QuestionImportPreviewResponse,
    QuestionImportResponse,
)
from app.services.excel_parser import (
    ExcelImportError,
    generate_import_preview,
    parse_and_validate_questions,
    validate_file_extension,
)
from app.services.question_import_service import QuestionImportService

router = APIRouter(prefix="/api/v1/imports", tags=["Imports"])


@router.post(
    "/questions/preview",
    response_model=QuestionImportPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview Part 5 questions from Excel file without database modifications",
)
async def preview_import_questions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> QuestionImportPreviewResponse:
    """Read-only preview endpoint: parses Excel workbook and computes diff against DB without writing."""
    try:
        validate_file_extension(file.filename)
        content = await file.read()
        return generate_import_preview(
            file_content=content,
            filename=file.filename or "unknown.xlsx",
            db=db,
        )
    except ExcelImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during import preview: {exc}",
        ) from exc


@router.post(
    "/questions",
    response_model=QuestionImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Import Part 5 questions from Excel file into Question Bank",
)
async def import_questions(
    file: UploadFile = File(...),
    allow_updates: bool = Query(
        default=False,
        description="If True, updates conflicting existing records in place. If False, skips existing records without modifying them.",
    ),
    db: Session = Depends(get_db),
) -> QuestionImportResponse:
    # 1. Parse & validate Excel file
    try:
        validate_file_extension(file.filename)
        content = await file.read()
        parsed_result = parse_and_validate_questions(content)
    except ExcelImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # 2. Save via QuestionImportService (atomic transaction & duplicate check)
    try:
        imported_count, skipped_count, updated_count = QuestionImportService.import_questions(
            db=db,
            questions=parsed_result.questions,
            allow_updates=allow_updates,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction error during import: {exc}",
        ) from exc

    # 3. Return response with counts
    parsed_result.imported_count = imported_count
    parsed_result.skipped_count = skipped_count
    parsed_result.updated_count = updated_count
    parsed_result.saved_count = imported_count + updated_count
    return parsed_result
