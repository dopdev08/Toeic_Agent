from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Canonical Part-of-Speech and Lexical-Unit taxonomy for TOEIC Part 5 enrichment.
# Covers standard English word classes and specific multiword syntactic units.
# Note: For backward compatibility, the public field name remains 'part_of_speech'.
# It represents a word class for single words (e.g., 'noun', 'verb', 'adjective')
# or a lexical-unit category for multiword entries (e.g., 'noun phrase', 'verb phrase',
# 'prepositional phrase', or generic 'phrase' fallback).
VALID_PARTS_OF_SPEECH: frozenset[str] = frozenset({
    # Single-word standard parts of speech
    "noun",
    "verb",
    "adjective",
    "adverb",
    "preposition",
    "conjunction",
    "pronoun",
    "determiner",
    "auxiliary verb",
    "modal verb",
    "numeral",
    "proper noun",
    # Specific multiword syntactic unit categories
    "noun phrase",
    "verb phrase",
    "prepositional phrase",
    # Generic multiword expression fallback
    "phrase",
})


class VocabularyItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    word: str = Field(..., min_length=1)
    meaning: str = Field(..., min_length=1)
    part_of_speech: str = Field(..., min_length=1)

    @field_validator("part_of_speech")
    @classmethod
    def validate_part_of_speech(cls, v: str) -> str:
        canonical = v.strip().lower()
        if canonical not in VALID_PARTS_OF_SPEECH:
            raise ValueError(
                f"Invalid part of speech: '{v}'. Must be one of: {sorted(VALID_PARTS_OF_SPEECH)}"
            )
        return canonical


class DistractorAnalysis(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    A: str = Field(..., min_length=1)
    B: str = Field(..., min_length=1)
    C: str = Field(..., min_length=1)
    D: str = Field(..., min_length=1)


class QuestionEnrichment(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    grammar_topic: str = Field(..., min_length=1)
    sentence_structure: str = Field(..., min_length=1)
    pattern: str = Field(..., min_length=1)
    vocabulary: list[VocabularyItem] = Field(..., min_length=1)
    explanation: str = Field(..., min_length=1)
    distractor_analysis: DistractorAnalysis
    difficulty: Literal["easy", "medium", "hard"]


class QuestionEnrichmentResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    question_id: int
    grammar_topic: str = Field(..., min_length=1)
    sentence_structure: str = Field(..., min_length=1)
    pattern: str = Field(..., min_length=1)
    vocabulary: list[VocabularyItem] = Field(..., min_length=1)
    explanation: str = Field(..., min_length=1)
    distractor_analysis: DistractorAnalysis
    difficulty: Literal["easy", "medium", "hard"]


class BatchEnrichmentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question_ids: list[int] = Field(..., min_length=1)

    @field_validator("question_ids")
    @classmethod
    def validate_positive_and_unique_ids(cls, ids: list[int]) -> list[int]:
        for q_id in ids:
            if q_id <= 0:
                raise ValueError(f"Question ID must be a positive integer, got: {q_id}")
        if len(ids) != len(set(ids)):
            raise ValueError("question_ids must contain unique question IDs without duplicates")
        return ids


class BatchItemResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question_id: int
    status: str  # "COMPLETED" or "FAILED"
    error: str | None = None


class BatchEnrichmentResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    total: int
    success: int
    failed: int
    results: list[BatchItemResponse]
