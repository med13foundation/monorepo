"""Biomedical-pack extraction prompt dispatch."""

from __future__ import annotations

from src.graph.core.extraction_prompt import ExtractionPromptConfig
from src.infrastructure.llm.prompts import extraction as extraction_prompts

BIOMEDICAL_EXTRACTION_PROMPT_CONFIG = ExtractionPromptConfig(
    system_prompts_by_source_type={
        "clinvar": (
            f"{extraction_prompts.CLINVAR_EXTRACTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{extraction_prompts.CLINVAR_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
        "pubmed": (
            f"{extraction_prompts.PUBMED_EXTRACTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{extraction_prompts.PUBMED_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
    },
)
