"""Extraction processor adapters."""

from src.infrastructure.extraction.ai_required_pubmed_extraction_processor import (
    AiRequiredPubMedExtractionProcessor,
)
from src.infrastructure.extraction.clinvar_extraction_processor import (
    ClinVarExtractionProcessor,
)
from src.infrastructure.extraction.placeholder_extraction_processor import (
    PlaceholderExtractionProcessor,
)

__all__ = [
    "AiRequiredPubMedExtractionProcessor",
    "ClinVarExtractionProcessor",
    "PlaceholderExtractionProcessor",
]
