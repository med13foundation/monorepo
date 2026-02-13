"""
Application service for testing AI-managed data source configurations.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pydantic

from src.domain.entities import data_source_configs, user_data_source
from src.type_definitions import data_sources as data_source_types

logger = logging.getLogger(__name__)

# Confidence threshold below which queries are logged as warnings
LOW_CONFIDENCE_THRESHOLD = 0.5
CLINVAR_DISCOVERY_SOURCE_IDS: frozenset[str] = frozenset(
    {"clinvar", "clinvar_benchmark"},
)
DEFAULT_CLINVAR_AGENT_PROMPT = (
    "Use ClinVar-specific ontology and evidence criteria to generate targeted "
    "queries for pathogenicity-focused tasks."
)
DEFAULT_CLINVAR_QUERY = "MED13 pathogenic variant"

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ports.flujo_state_port import FlujoStatePort
    from src.domain.agents.ports.query_agent_port import (
        QueryAgentPort,
        QueryAgentRunMetadataProvider,
    )
    from src.domain.repositories import (
        ResearchSpaceRepository,
        UserDataSourceRepository,
    )
    from src.domain.services.pubmed_ingestion import PubMedGateway
    from src.type_definitions.common import RawRecord, SourceMetadata


class DataSourceAiTestSettings(pydantic.BaseModel):
    """Settings for AI data source test execution."""

    model_config = pydantic.ConfigDict(extra="forbid")

    sample_size: int = pydantic.Field(default=5, ge=1)
    ai_model_name: str | None = None


@dataclass(frozen=True)
class DataSourceAiTestDependencies:
    """Bundle dependencies required for AI test execution."""

    source_repository: UserDataSourceRepository
    pubmed_gateway: PubMedGateway
    query_agent: QueryAgentPort | None
    research_space_repository: ResearchSpaceRepository | None
    flujo_state: FlujoStatePort | None = None
    run_id_provider: QueryAgentRunMetadataProvider | None = None


class DataSourceAiTestService:
    """Coordinate AI configuration testing for supported data sources."""

    def __init__(
        self,
        dependencies: DataSourceAiTestDependencies,
        settings: DataSourceAiTestSettings | None = None,
    ) -> None:
        self._source_repository = dependencies.source_repository
        self._pubmed_gateway = dependencies.pubmed_gateway
        self._query_agent = dependencies.query_agent
        self._run_id_provider = dependencies.run_id_provider
        self._research_space_repository = dependencies.research_space_repository
        self._flujo_state = dependencies.flujo_state
        resolved_settings = settings or DataSourceAiTestSettings()
        self._sample_size = max(resolved_settings.sample_size, 1)
        self._ai_model_name = resolved_settings.ai_model_name

    async def test_ai_configuration(
        self,
        source_id: UUID,
    ) -> data_source_types.DataSourceAiTestResult:
        """Run a lightweight AI-driven test against a data source configuration."""
        source = self._require_source(source_id)
        checked_at = dt.datetime.now(dt.UTC)
        config = self._build_source_config(source)
        error_message = self._validate_preconditions(source=source, config=config)
        executed_query: str | None = None
        fetched_records = 0
        findings: list[data_source_types.DataSourceAiTestFinding] = []
        flujo_run_id: str | None = None
        flujo_tables: list[data_source_types.FlujoTableSummary] = []
        ai_executed = False
        fetch_attempted = False

        # Track the actual model used (configured or default)
        actual_model_id: str | None = None

        if error_message is None and config is not None:
            research_space_description = self._resolve_research_space_description(
                source,
                config,
            )
            agent_source_type = config.agent_config.query_agent_source_type
            ai_executed = True
            # Use configured model_id or fall back to default
            actual_model_id = config.agent_config.model_id or self._ai_model_name
            intelligent_query = await self._generate_intelligent_query(
                research_space_description,
                config.agent_config.agent_prompt,
                source_type=agent_source_type,
                model_id=config.agent_config.model_id,
            )

            if not intelligent_query:
                error_message = "AI agent did not return a query. Refine the AI instructions and try again."
            else:
                executed_query = intelligent_query
                test_config = config.model_copy(
                    update={
                        "query": intelligent_query,
                        "max_results": self._sample_size,
                        "relevance_threshold": 0,
                    },
                )
                if self._should_use_pubmed_gateway(source, config):
                    fetch_attempted = True
                    try:
                        raw_records = await self._pubmed_gateway.fetch_records(
                            test_config,
                        )
                        fetched_records = len(raw_records)
                        findings = self._build_findings(raw_records)
                        if fetched_records == 0:
                            error_message = (
                                "PubMed returned no results for the AI-generated query. "
                                "Adjust the prompt or filters and try again."
                            )
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.exception("AI test failed for source %s", source.id)
                        error_message = f"PubMed request failed: {exc!s}"
                else:
                    # Non-PubMed sources currently support query generation validation only.
                    logger.info(
                        "Skipping PubMed fetch for non-PubMed AI test source %s",
                        source.id,
                    )

        if ai_executed:
            flujo_run_id, flujo_tables = self._resolve_flujo_state(checked_at)

        success = error_message is None
        if error_message is None:
            if fetch_attempted:
                message = (
                    f"AI test succeeded with {fetched_records} record(s) returned."
                )
            else:
                message = (
                    f"AI query generated successfully; no connector fetch step for "
                    f"{agent_source_type}."
                )
        else:
            message = error_message

        search_terms = self._extract_search_terms(executed_query)
        model_name = self._resolve_model_name(
            has_query_agent=self._query_agent is not None,
            configured_model_id=actual_model_id,
        )

        return data_source_types.DataSourceAiTestResult(
            source_id=source.id,
            model=model_name,
            success=success,
            message=message,
            executed_query=executed_query,
            search_terms=search_terms,
            fetched_records=fetched_records,
            sample_size=self._sample_size,
            findings=findings,
            checked_at=checked_at,
            flujo_run_id=flujo_run_id,
            flujo_tables=flujo_tables,
        )

    def _require_source(self, source_id: UUID) -> user_data_source.UserDataSource:
        source = self._source_repository.find_by_id(source_id)
        if source is None:
            msg = f"Data source {source_id} not found"
            raise ValueError(msg)
        return source

    @staticmethod
    def _build_source_config(
        source: user_data_source.UserDataSource,
    ) -> data_source_configs.PubMedQueryConfig | None:
        metadata: SourceMetadata = dict(source.configuration.metadata or {})
        metadata_with_defaults = DataSourceAiTestService._apply_clinvar_defaults(
            metadata,
        )
        try:
            return data_source_configs.PubMedQueryConfig.model_validate(
                metadata_with_defaults,
            )
        except pydantic.ValidationError as exc:
            logger.warning("Invalid PubMed config for source %s: %s", source.id, exc)
            return None

    @staticmethod
    def _normalize_catalog_entry_id(metadata: SourceMetadata) -> str | None:
        catalog_entry_id = metadata.get("catalog_entry_id")
        if not isinstance(catalog_entry_id, str):
            return None
        normalized = catalog_entry_id.strip().lower()
        return normalized if normalized else None

    @classmethod
    def _is_clinvar_discovery_source(cls, metadata: SourceMetadata) -> bool:
        catalog_entry_id = cls._normalize_catalog_entry_id(metadata)
        return (
            catalog_entry_id in CLINVAR_DISCOVERY_SOURCE_IDS
            if catalog_entry_id is not None
            else False
        )

    @classmethod
    def _apply_clinvar_defaults(cls, metadata: SourceMetadata) -> SourceMetadata:
        """Backfill AI defaults for legacy ClinVar discovery sources."""
        if not cls._is_clinvar_discovery_source(metadata):
            return metadata

        normalized_metadata: SourceMetadata = dict(metadata)
        query = normalized_metadata.get("query")
        if not isinstance(query, str) or not query.strip():
            normalized_metadata["query"] = DEFAULT_CLINVAR_QUERY

        raw_agent_config = normalized_metadata.get("agent_config")
        if isinstance(raw_agent_config, dict):
            agent_config: SourceMetadata = dict(raw_agent_config)
        else:
            agent_config = {}

        agent_config.setdefault("is_ai_managed", True)
        agent_config.setdefault("query_agent_source_type", "clinvar")
        agent_config.setdefault("use_research_space_context", True)
        agent_config.setdefault("agent_prompt", DEFAULT_CLINVAR_AGENT_PROMPT)

        normalized_metadata["agent_config"] = agent_config
        return normalized_metadata

    def _validate_preconditions(
        self,
        *,
        source: user_data_source.UserDataSource,
        config: data_source_configs.PubMedQueryConfig | None,
    ) -> str | None:
        if source.source_type not in (
            user_data_source.SourceType.PUBMED,
            user_data_source.SourceType.API,
            user_data_source.SourceType.CLINVAR,
        ):
            return "AI testing is only supported for PubMed, ClinVar, or API sources."
        if config is None:
            return "Source configuration is invalid. Review the source settings."
        if not config.agent_config.is_ai_managed:
            return "AI-managed queries are disabled for this source."
        if self._query_agent is None:
            return "AI agent is not configured for testing."
        if self._research_space_repository is None:
            return "Research space context is unavailable for AI testing."
        return None

    def _resolve_research_space_description(
        self,
        source: user_data_source.UserDataSource,
        config: data_source_configs.PubMedQueryConfig,
    ) -> str:
        if not config.agent_config.use_research_space_context:
            return ""
        if source.research_space_id is None:
            return ""
        repository = self._research_space_repository
        if repository is None:
            return ""
        space = repository.find_by_id(source.research_space_id)
        return space.description if space else ""

    async def _generate_intelligent_query(
        self,
        research_space_description: str,
        agent_prompt: str,
        source_type: str,
        model_id: str | None = None,
    ) -> str:
        if self._query_agent is None:
            return ""
        try:
            contract = await self._query_agent.generate_query(
                research_space_description=research_space_description,
                user_instructions=agent_prompt,
                source_type=source_type,
                model_id=model_id,
            )

            # Log decision and confidence for observability
            if contract.decision == "escalate":
                logger.warning(
                    "AI query escalated: %s (confidence=%.2f)",
                    contract.rationale,
                    contract.confidence_score,
                )
                return ""
            if contract.confidence_score < LOW_CONFIDENCE_THRESHOLD:
                logger.warning(
                    "Low confidence AI query (%.2f): %s",
                    contract.confidence_score,
                    contract.rationale,
                )

            return contract.query.strip()
        except Exception:  # pragma: no cover - defensive
            logger.exception("AI query generation failed")
            return ""

    @staticmethod
    def _should_use_pubmed_gateway(
        source: user_data_source.UserDataSource,
        config: data_source_configs.PubMedQueryConfig,
    ) -> bool:
        """
        Determine if the configured source should run through PubMed fetch for AI tests.
        """
        return (
            source.source_type == user_data_source.SourceType.PUBMED
            or config.agent_config.query_agent_source_type.lower() == "pubmed"
        )

    def _resolve_model_name(
        self,
        *,
        has_query_agent: bool,
        configured_model_id: str | None = None,
    ) -> str | None:
        if not has_query_agent:
            return None
        # Use configured model if provided, otherwise fall back to default
        model = configured_model_id or self._ai_model_name
        return model.strip() if isinstance(model, str) and model.strip() else None

    @staticmethod
    def _extract_search_terms(query: str | None) -> list[str]:
        if not query:
            return []

        terms: list[str] = []
        quoted_terms = re.findall(r'"([^"]+)"', query)
        for term in quoted_terms:
            normalized = term.strip()
            if normalized and normalized not in terms:
                terms.append(normalized)

        scrubbed = re.sub(r'"[^"]+"', " ", query)
        scrubbed = re.sub(r"\[[^\]]+\]", " ", scrubbed)
        scrubbed = scrubbed.replace("(", " ").replace(")", " ")
        for token in scrubbed.split():
            normalized = token.strip()
            if not normalized:
                continue
            if normalized.upper() in {"AND", "OR", "NOT"}:
                continue
            if normalized not in terms:
                terms.append(normalized)

        return terms

    def _build_findings(
        self,
        records: list[RawRecord],
    ) -> list[data_source_types.DataSourceAiTestFinding]:
        findings: list[data_source_types.DataSourceAiTestFinding] = []
        for record in records[: self._sample_size]:
            pubmed_id = self._coerce_scalar(record.get("pubmed_id"))
            title = self._coerce_scalar(record.get("title")) or "Untitled PubMed record"
            doi = self._coerce_scalar(record.get("doi"))
            pmc_id = self._coerce_scalar(record.get("pmc_id"))
            publication_date = self._coerce_scalar(record.get("publication_date"))
            journal = self._extract_journal_title(record.get("journal"))
            links = self._build_links(pubmed_id, pmc_id, doi)

            findings.append(
                data_source_types.DataSourceAiTestFinding(
                    title=title,
                    pubmed_id=pubmed_id,
                    doi=doi,
                    pmc_id=pmc_id,
                    publication_date=publication_date,
                    journal=journal,
                    links=links,
                ),
            )
        return findings

    @staticmethod
    def _coerce_scalar(value: object | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, int | float):
            return str(value)
        return None

    @staticmethod
    def _extract_journal_title(value: object | None) -> str | None:
        if not isinstance(value, dict):
            return None
        title_value = value.get("title")
        return (
            title_value.strip()
            if isinstance(title_value, str) and title_value.strip()
            else None
        )

    @staticmethod
    def _build_links(
        pubmed_id: str | None,
        pmc_id: str | None,
        doi: str | None,
    ) -> list[data_source_types.DataSourceAiTestLink]:
        links: list[data_source_types.DataSourceAiTestLink] = []
        if pubmed_id:
            links.append(
                data_source_types.DataSourceAiTestLink(
                    label="PubMed",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
                ),
            )
        if pmc_id:
            links.append(
                data_source_types.DataSourceAiTestLink(
                    label="PubMed Central",
                    url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/",
                ),
            )
        if doi:
            links.append(
                data_source_types.DataSourceAiTestLink(
                    label="DOI",
                    url=f"https://doi.org/{doi}",
                ),
            )
        return links

    def _resolve_flujo_state(
        self,
        checked_at: dt.datetime,
    ) -> tuple[str | None, list[data_source_types.FlujoTableSummary]]:
        if self._flujo_state is None:
            return None, []

        if self._run_id_provider is None:
            return None, []

        run_id = self._run_id_provider.get_last_run_id()
        if run_id is None:
            window_start = checked_at - dt.timedelta(minutes=2)
            run_id = self._flujo_state.find_latest_run_id(since=window_start)

        if run_id is None:
            return None, []

        return run_id, self._flujo_state.get_run_table_summaries(run_id)


__all__ = [
    "DataSourceAiTestDependencies",
    "DataSourceAiTestService",
    "DataSourceAiTestSettings",
]
