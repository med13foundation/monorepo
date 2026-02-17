"""Extraction agent prompts."""

from src.infrastructure.llm.prompts.extraction.clinvar import (
    CLINVAR_EXTRACTION_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.extraction.policy import (
    EXTRACTION_POLICY_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.extraction.pubmed import (
    PUBMED_EXTRACTION_SYSTEM_PROMPT,
)

__all__ = [
    "CLINVAR_EXTRACTION_SYSTEM_PROMPT",
    "EXTRACTION_POLICY_SYSTEM_PROMPT",
    "PUBMED_EXTRACTION_SYSTEM_PROMPT",
]
