from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.enrichment import QuestionEnrichment


class QuestionItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    test_id: str = Field(..., min_length=1)
    part: int = Field(default=5, ge=1, le=7)
    question_no: int = Field(..., gt=0)
    question_text: str = Field(..., min_length=1)
    option_a: str = Field(..., min_length=1)
    option_b: str = Field(..., min_length=1)
    option_c: str = Field(..., min_length=1)
    option_d: str = Field(..., min_length=1)
    correct_answer: Literal["A", "B", "C", "D"]
    explanation: str | None = None

    @field_validator("correct_answer", mode="before")
    @classmethod
    def normalize_answer(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class QuestionDetail(QuestionItem):
    id: int
    created_at: datetime | str | None = None

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class QuestionWithEnrichmentResponse(QuestionDetail):
    enrichment: "QuestionEnrichment | None" = None


class ImportRowError(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    row_no: int
    question_no: int | None = None
    field: str
    error: str
    raw_value: str | None = None


class QuestionFieldDiff(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    field: str
    old_value: str | None = None
    new_value: str | None = None


class QuestionChangeComparison(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    test_id: str
    part: int
    question_no: int
    existing_id: int | None = None
    diffs: list[QuestionFieldDiff]
    old_correct_answer: str
    new_correct_answer: str
    is_answer_change: bool = False


class AnswerKeyConfirmationItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question_no: int
    test_id: str
    part: int
    old_answer: str
    new_answer: str
    question_text: str
    reason: str


class QuestionPreviewItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    row_no: int
    question_no: int
    test_id: str
    part: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str
    explanation: str | None = None
    action: Literal["INSERT", "UNCHANGED", "UPDATE", "INVALID"]
    diffs: list[QuestionFieldDiff] = Field(default_factory=list)


class PreviewSummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    total_rows: int
    valid_questions: int
    invalid_rows: int
    to_insert: int
    unchanged: int
    to_update: int
    conflicts: int
    duplicates_in_file: int


class QuestionImportPreviewResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    filename: str
    test_id: str | None = None
    part: int | None = None
    min_question_no: int | None = None
    max_question_no: int | None = None
    missing_question_numbers: list[int] = Field(default_factory=list)
    summary: PreviewSummary
    validation_errors: list[ImportRowError] = Field(default_factory=list)
    duplicates_in_file: list[dict[str, Any]] = Field(default_factory=list)
    changes: list[QuestionChangeComparison] = Field(default_factory=list)
    requires_confirmation: list[AnswerKeyConfirmationItem] = Field(default_factory=list)
    questions: list[QuestionPreviewItem] = Field(default_factory=list)


class QuestionImportResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    test_id: str
    total_questions: int
    imported_count: int
    skipped_count: int
    updated_count: int = 0
    saved_count: int = 0
    questions: list[QuestionItem]
    conflicts: list[QuestionChangeComparison] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_saved_count(self) -> "QuestionImportResponse":
        if self.saved_count == 0 and (self.imported_count > 0 or self.updated_count > 0):
            self.saved_count = self.imported_count + self.updated_count
        return self
