"""Biomedical-pack entity-recognition prompt dispatch."""

from __future__ import annotations

from src.graph.core.entity_recognition_prompt import EntityRecognitionPromptConfig
from src.infrastructure.llm.prompts.entity_recognition import (
    CLINVAR_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
    CLINVAR_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
    PUBMED_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
    PUBMED_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
)

BIOMEDICAL_ENTITY_RECOGNITION_PROMPT_CONFIG = EntityRecognitionPromptConfig(
    system_prompts_by_source_type={
        "clinvar": (
            f"{CLINVAR_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{CLINVAR_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT}"
        ),
        "pubmed": (
            f"{PUBMED_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{PUBMED_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT}"
        ),
    },
)
