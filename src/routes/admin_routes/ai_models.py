"""
API routes for AI model configuration.

Provides endpoints for listing available AI models and their capabilities.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.domain.agents.models import ModelCapability
from src.infrastructure.llm.config.model_registry import get_model_registry

router = APIRouter(prefix="/ai-models", tags=["AI Models"])


class ModelSpecResponse(BaseModel):
    """Response model for a single AI model specification."""

    model_id: str = Field(..., description="Model identifier")
    display_name: str = Field(..., description="Human-readable name")
    provider: str = Field(..., description="Model provider (openai, anthropic)")
    capabilities: list[str] = Field(..., description="Supported capabilities")
    cost_tier: Literal["low", "medium", "high"] = Field(
        ...,
        description="Relative cost tier",
    )
    is_reasoning_model: bool = Field(
        ...,
        description="Whether this is a reasoning model",
    )
    is_default: bool = Field(..., description="Whether this is a system default")


class AvailableModelsResponse(BaseModel):
    """Response model for listing available AI models."""

    models: list[ModelSpecResponse] = Field(..., description="Available models")
    default_query_model: str = Field(
        ...,
        description="Default model ID for query generation",
    )


@router.get(
    "",
    response_model=AvailableModelsResponse,
    summary="List available AI models",
    description="Get all available AI models that can be used for data source configuration.",
)
def list_available_models() -> AvailableModelsResponse:
    """
    List all available AI models.

    Returns models that can be selected for per-data-source configuration,
    along with their capabilities and cost tiers.
    """
    registry = get_model_registry()
    available = registry.get_available_models()

    models = [
        ModelSpecResponse(
            model_id=m.model_id,
            display_name=m.display_name,
            provider=m.provider,
            capabilities=[c.value for c in m.capabilities],
            cost_tier=m.cost_tier.value,
            is_reasoning_model=m.is_reasoning_model,
            is_default=m.is_default,
        )
        for m in available
    ]

    # Get default query model
    default_model = registry.get_default_model(ModelCapability.QUERY_GENERATION)

    return AvailableModelsResponse(
        models=models,
        default_query_model=default_model.model_id,
    )


@router.get(
    "/for-capability/{capability}",
    response_model=list[ModelSpecResponse],
    summary="List models for a capability",
    description="Get AI models that support a specific capability.",
)
def list_models_for_capability(capability: str) -> list[ModelSpecResponse]:
    """
    List models that support a specific capability.

    Args:
        capability: The capability to filter by (query_generation, evidence_extraction, etc.)

    Returns:
        List of models supporting the capability
    """
    registry = get_model_registry()

    # Validate capability
    try:
        cap = ModelCapability(capability)
    except ValueError:
        return []

    models = registry.get_models_for_capability(cap)

    return [
        ModelSpecResponse(
            model_id=m.model_id,
            display_name=m.display_name,
            provider=m.provider,
            capabilities=[c.value for c in m.capabilities],
            cost_tier=m.cost_tier.value,
            is_reasoning_model=m.is_reasoning_model,
            is_default=m.is_default,
        )
        for m in models
    ]
