"""
Factory mixin for building application services used by the dependency container.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.agents.models import ModelCapability
from src.infrastructure.dependency_injection.analysis_service_factories import (
    AnalysisServiceFactoryMixin,
)
from src.infrastructure.dependency_injection.curation_service_factories import (
    CurationServiceFactoryMixin,
)
from src.infrastructure.dependency_injection.discovery_service_factories import (
    DiscoveryServiceFactoryMixin,
)
from src.infrastructure.dependency_injection.kernel_service_factories import (
    KernelServiceFactoryMixin,
)
from src.infrastructure.llm.adapters.query_agent_adapter import FlujoQueryAgentAdapter
from src.infrastructure.llm.config.model_registry import get_model_registry

if TYPE_CHECKING:
    from src.application.services import SystemStatusService
    from src.domain.agents.ports.query_agent_port import QueryAgentPort
    from src.domain.services import storage_metrics, storage_providers


class ApplicationServiceFactoryMixin(
    AnalysisServiceFactoryMixin,
    CurationServiceFactoryMixin,
    DiscoveryServiceFactoryMixin,
    KernelServiceFactoryMixin,
):
    """Provides helper factory methods shared by the dependency container."""

    if TYPE_CHECKING:
        _storage_plugin_registry: storage_providers.StoragePluginRegistry
        _storage_metrics_recorder: storage_metrics.StorageMetricsRecorder
        _query_agent: QueryAgentPort | None

    if TYPE_CHECKING:

        def get_system_status_service(self) -> SystemStatusService: ...

    def get_query_agent(self) -> QueryAgentPort:
        if self._query_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
            self._query_agent = FlujoQueryAgentAdapter(model=model_spec.model_id)
        return self._query_agent
