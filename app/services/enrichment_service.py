from typing import Any

from app.models.question import Question
from app.schemas.enrichment import QuestionEnrichment
from app.services.enrichment_response_parser import parse_and_validate_enrichment
from app.services.gemini_client import GeminiClient
from app.services.llm_client import LLMService


SYSTEM_PROMPT = """You are an expert TOEIC instructor and linguistic analyst for a high-performance TOEIC learning system.
Your task is to analyze a TOEIC Reading test question and produce an in-depth, accurate educational enrichment profile.

You must output strictly valid, raw JSON conforming to the following schema without any markdown formatting, code fences, or surrounding dialogue:

{
  "grammar_topic": "string",
  "sentence_structure": "string",
  "pattern": "string",
  "vocabulary": [
    {
      "word": "string",
      "meaning": "string",
      "part_of_speech": "string"
    }
  ],
  "explanation": "string (in Vietnamese)",
  "distractor_analysis": {
    "A": "string (in Vietnamese)",
    "B": "string (in Vietnamese)",
    "C": "string (in Vietnamese)",
    "D": "string (in Vietnamese)"
  },
  "difficulty": "easy | medium | hard"
}

Pedagogical & Instructional Rules:
1. Authoritative Reference: The supplied correct answer letter and option text are authoritative reference data from the Question Bank. You must NEVER silently change, dispute, or substitute the authoritative answer.
2. Question Analysis:
   - Analyze the exact sentence and the position of the blank before assigning a grammar topic.
   - Use the four answer choices to identify the actual distinction being tested (e.g., distinguishing word forms, grammatical structures, or vocabulary/collocations).
   - Never force a question into a relative-clause, preposition, or any complex pattern if that structure does not actually exist in the sentence.
   - Never introduce words, prepositions, clauses, or relationships that are not present in the supplied sentence.
3. Accurate Structure & Pattern:
   - 'grammar_topic': Concise, standard English grammatical domain directly tested by the blank (e.g., word form, subject-verb agreement, conjunction, verb tense). Do not use vague labels like "Grammar" or "Part 5".
   - 'sentence_structure': Reusable syntactical formula showing the sentence elements and the blank position (using standard symbols such as S, V, O, Prep, Conj). Must faithfully represent the current sentence, not an invented clause.
   - 'pattern': Portable grammatical formula or collocation directly applicable to solving this specific question.
4. Grounded Explanation: In 'explanation' (in Vietnamese), explain why the authoritative option grammatically and contextually fits the actual sentence. Cite specific syntactic roles and sentence clues. Never invent false grammatical rules to justify an answer.
5. Rigorous Distractor Analysis (Mandatory 4 Keys: "A", "B", "C", "D"):
   - The 'distractor_analysis' object MUST contain EXACTLY four keys: "A", "B", "C", and "D".
   - CRITICAL CONTRACT CONSTRAINTS:
     * NEVER omit any option letter. Even if an option is the authoritative correct answer, it MUST be included as one of the four keys (A, B, C, or D). Omitting any option (such as missing "D") is a fatal schema violation.
     * NEVER add extra keys. Strictly FORBIDDEN keys include "E", "Explanation", "explanation", "summary", "notes", or any other key. The object must contain exclusively keys "A", "B", "C", "D".
     * STRICT IDENTIFIER INVARIANT: Keys MUST ALWAYS be the literal uppercase option letters "A", "B", "C", "D". NEVER use the option's text or word choice as a key (e.g. if option D is a word or phrase, the JSON key must still strictly be "D", not the word itself).
   - Analyze each option (A, B, C, D) individually with specific, question-tailored Vietnamese explanations:
     * For the authoritative correct option: Explicitly affirm why it fits the sentence structure and context.
     * For each distractor: Explain specifically why it is eliminated (e.g., incorrect part of speech, incompatible preposition, structural mismatch, or semantic clash).
     * Keep every distractor explanation specific to that option; avoid generic fillers (such as "Đáp án này sai" or "Sai ngữ pháp").
6. Grounded Vocabulary (Strict Verbatim Presence in Question or Options):
   - Select 1 to 4 useful vocabulary items or collocations that ACTUALLY APPEAR VERBATIM in the question text or options. Provide accurate Vietnamese meanings in this context and standard English parts of speech or approved lexical-unit categories.
   - CRITICAL SCHEMA CONTRACT: Each object in 'vocabulary' MUST have EXACTLY three keys: "word", "meaning", "part_of_speech".
     * FIXED KEY INVARIANT: The property representing the part of speech MUST ALWAYS be literally named "part_of_speech". NEVER replace the key name with the grammatical category itself (e.g. do NOT name the key "noun", "verb", "adjective", etc.; the key is always "part_of_speech" and the category is its value).
     * NO EXTRA METADATA KEYS: Do NOT add extra metadata keys such as "name", "tag", "type", or "category".
   - CRITICAL GROUNDING & MORPHOLOGY RULES:
     * VERBATIM PRESENCE ONLY: Every selected word or phrase MUST exist directly in the supplied question text, answer options, or authoritative completed sentence (or be a regular grammatical inflection of a word in the text, such as plural -s/-es or past -ed).
     * NO DERIVED WORDS OR WORD-FAMILY EXPANSIONS: NEVER convert a word found in the sentence into a different part of speech, derived noun, adjective, or word family member that is NOT present in the text!
       - FORBIDDEN RULE: NEVER add "-ly" to an adjective in the text to invent an adverb, and NEVER strip "-ly" from an adverb in the options to invent an adjective. Extract ONLY the exact word as it is spelled in the text or options.
       - FORBIDDEN EXAMPLE: If the question text contains the verb "expand", you must NOT extract the derived noun "expansion"! You must extract the exact word "expand" as "verb".
       - FORBIDDEN EXAMPLE: If the options contain "financially", do NOT invent "financial" or "finance" unless that exact string appears in the question or options.
     * NO EXTERNAL SYNONYMS: Do NOT introduce background vocabulary, external synonyms, or ungrounded words that do not appear anywhere in the question text or options. Any ungrounded vocabulary item causes immediate quality rejection.
   - CANONICAL PART OF SPEECH TAGS ONLY:
     * Single-word tags (12 canonical tags): noun, proper noun, adjective, adverb, verb, auxiliary verb, modal verb, preposition, conjunction, pronoun, determiner, numeral.
     * Multiword tags (4 canonical tags): noun phrase, verb phrase, prepositional phrase, phrase.
     * FORBIDDEN TAGS: Do NOT use "phrasal verb" (use "verb phrase" or "phrase"). Do NOT use "idiom", "collocation", "particle", or non-canonical labels.
   - Do not infer a category from translation alone; classify the exact word string returned in the vocabulary item.
   - Emit one exact canonical label only. Do not add explanations, pluralize tags, invent categories, or use non-Latin script as a POS tag. Do NOT invent words.
7. Linguistic Truthfulness: Never invent grammatical rules, and never claim a word has a grammatical function it does not possess. Adhere strictly to factual linguistic evidence from the supplied sentence.
8. Difficulty: Strictly one of: "easy", "medium", "hard".
9. Strict Output Constraint:
   - Return ONLY the raw JSON object conforming to the schema.
   - Do NOT include markdown code fences (```json), hidden chain-of-thought, commentary, or conversational text.
   - Ensure strictly valid JSON syntax: NEVER leave trailing commas after the last element in arrays or objects."""


USER_PROMPT_TEMPLATE = """Analyze the following TOEIC Reading question and generate the complete enrichment JSON:

Question Text: {question_text}
Option A: {option_a}
Option B: {option_b}
Option C: {option_c}
Option D: {option_d}
Authoritative correct answer: {correct_answer} — {correct_option_text}

Generate the enrichment JSON now:"""


class EnrichmentService:
    """Orchestration service for analyzing questions and generating QuestionEnrichment.

    - Builds bounded AI input payload from Question (excluding database metadata).
    - Formats prompt according to AI enrichment prompt specification.
    - Dispatches prompt to LLM Service via generate(prompt: str) -> str.
    - Delegates raw response validation to parse_and_validate_enrichment().
    - Does NOT persist anything to the database.
    """

    def __init__(self, llm_service: LLMService | Any = None) -> None:
        self.llm_service = llm_service or GeminiClient()

    @staticmethod
    def build_ai_input(question: Question | Any) -> dict[str, Any]:
        """Extract bounded input contract dictionary from a Question instance."""
        return {
            "question_text": question.question_text,
            "option_a": question.option_a,
            "option_b": question.option_b,
            "option_c": question.option_c,
            "option_d": question.option_d,
            "correct_answer": question.correct_answer,
        }

    @staticmethod
    def get_correct_option_text(ai_input: dict[str, Any]) -> str:
        """Derive the text of the authoritative correct option based on correct_answer."""
        key = (ai_input.get("correct_answer") or "").strip().upper()
        mapping = {
            "A": ai_input.get("option_a"),
            "B": ai_input.get("option_b"),
            "C": ai_input.get("option_c"),
            "D": ai_input.get("option_d"),
        }
        val = mapping.get(key)
        return str(val) if val is not None else ""

    @classmethod
    def build_prompt(cls, ai_input: dict[str, Any]) -> str:
        """Render production prompt incorporating system rules and user question data."""
        correct_option_text = cls.get_correct_option_text(ai_input)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            question_text=ai_input["question_text"],
            option_a=ai_input["option_a"],
            option_b=ai_input["option_b"],
            option_c=ai_input["option_c"],
            option_d=ai_input["option_d"] if ai_input.get("option_d") is not None else "None",
            correct_answer=ai_input["correct_answer"],
            correct_option_text=correct_option_text,
        )
        return f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    def enrich_question(self, question: Question | Any) -> QuestionEnrichment:
        """Orchestrate end-to-end question enrichment pipeline without persistence."""
        ai_input = self.build_ai_input(question)
        prompt = self.build_prompt(ai_input)
        raw_response = self.llm_service.generate(prompt)
        return parse_and_validate_enrichment(raw_response)
