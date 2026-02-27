"""Data source configuration value objects."""

from .clinvar import ClinVarQueryConfig
from .pubmed import PubMedQueryConfig

__all__ = ["ClinVarQueryConfig", "PubMedQueryConfig"]
