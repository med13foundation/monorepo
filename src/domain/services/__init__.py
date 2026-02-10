"""
Domain services - pure business logic without infrastructure dependencies.

These services encapsulate domain rules, validations, and business logic
that operate purely on domain entities and value objects.
"""

from .base import DomainService

__all__ = [
    "DomainService",
]
