# MED13 Resource Library - Project Overview, Current Status, and Recommendations

**Status date:** January 26, 2026

## Purpose and scope

The MED13 Resource Library is a biomedical data platform focused on MED13 genetic variants, phenotypes, and evidence. The platform targets researchers and administrators who need reliable, type-safe data management and discovery. The architecture follows Clean Architecture with a FastAPI backend and a Next.js admin interface.

This document summarizes the project based on repository documentation and highlights decision points, planned next steps, and recommendations to guide direction and resourcing.

## Architecture overview (documented)

- Dual service architecture: FastAPI backend (med13-api) and Next.js admin (med13-admin).
- Clean Architecture: Domain, Application, Infrastructure, Presentation layers with strict separation.
- Type safety: MyPy strict mode, no Any, Pydantic validation, shared TypeScript types.
- Data Sources module: domain entities, orchestration services, and admin workflows.
- Deployment: Cloud Run oriented, PostgreSQL ready, SQLite for local dev.
- Quality gate: make all (format, lint, type-check, tests).

## Goals alignment (explicit)

- Mechanistic reasoning is modeled as `Variant -> ProteinDomain -> Mechanism -> Phenotype`.
- Hypotheses are human-verifiable; no automatic promotion to truth.
- The graph is the system of record with provenance and curation status on edges.
- Agent assistance is bounded, auditable, and cannot directly change validated data.
- Clinical and scientific credibility is enforced via audit logging and review workflows.

## Graph service strategy (explicit)

- Build the graph service inside the existing FastAPI backend first.
- Stabilize a public graph API contract before any service extraction.
- Treat Postgres as the system of record; use NetworkX for traversal.
- Only extract to a standalone service if scale, latency, or external consumer needs demand it.

## Proposal alignment (ResoGraph JTC 2026)

**Program frame**
- **Project title:** ResoGraph: A Hybrid AI & Knowledge Graph Platform for Resolving Unsolved Rare Genetic and Non-Genetic Diseases
- **Duration:** 36 months
- **Primary objective:** 15-25% relative increase in diagnostic yield on >1,000 unsolved cases.
- **Scope:** Rare disease diagnosis only; architecture is domain-agnostic but no out-of-scope expansion.

**Hybrid intelligence model**
1. **Mechanism-centered knowledge graph**: Variant <-> Protein Domain <-> Mechanism <-> Phenotype (HPO)
2. **AI agents (hypothesis generators)**: Traverse existing graph paths and propose mechanistic explanations.
3. **Human validation**: Mandatory expert review before graph promotion; optional functional assays.

**Cohort strategy**
- **Phase 1 (Gold Standard):** MED13 pilot for calibration and mechanistic ground truth.
- **Phase 2 (Expansion):** Neurodevelopmental, Ciliopathy/Mito, Immune-mediated cohorts.
- **Evaluation:** Diagnostic yield uplift and VUS reclassification with evidence tracking.

## Current status summary

### Backend and domain

- Clean Architecture foundation is documented as complete and stable.
- Domain entities and services exist for core biomedical data and data sources.
- Data Sources module is documented as implemented across domain, application, infrastructure, and UI layers.
- ResoGraph ontology is **partially implemented**: `Drug` and `Pathway` entities exist; `ProteinDomain` exists as a value object; **`Mechanism` and `StatementOfUnderstanding` are implemented with DB persistence and space-scoped API endpoints under `/research-spaces/{space_id}/mechanisms` and `/research-spaces/{space_id}/statements`, including promotion of well-supported statements into mechanisms**.
- Variant/Phenotype **domain models** include structural + longitudinal fields, but **DB persistence/migrations** for these fields are not yet present.
- Authentication, authorization, rate limiting, and baseline audit logging are implemented.
- API endpoints cover genes, variants, phenotypes, evidence, research spaces, and data source management.
- Graph service, graph storage, and `/api/graph/*` endpoints are not implemented yet.
- Flujo-based PubMed **query generation** is implemented; publications are queued and a rule-based extraction runner processes title/abstract text immediately after ingestion, persisting extraction outputs. Text payloads are stored in RAW_SOURCE storage with a document URL endpoint for retrieval (full-text ingestion + LLM extraction still pending).

### Frontend

- Next.js admin interface foundation is documented as complete (App Router + server-side orchestration).
- The frontend follows a server-orchestrated pattern with dumb client components and server actions.
- Data discovery workflows are refactored to align with backend orchestration DTOs.
- Design system and component library are in place (shadcn/ui with documented typography and theme choices).
- Knowledge Graph UI exists as a space-scoped route; Statements of Understanding and mechanism management (with promotion flow) are available there, but graph explorer/visualization remains pending.
- Data Sources UI surfaces recent extraction activity and provides a document open/copy flow for stored extraction payloads.

### Infrastructure and operations

- Cloud Run deployment and CI/CD pipelines are documented.
- Development workflows are automated via Makefile targets.
- Postgres support is documented with local Docker-based workflows.

### Security and compliance

- HIPAA compliance is documented as partial with critical gaps.
- Critical gaps include encryption at rest verification, PHI inventory and handling procedures, audit logging enhancements, retention and deletion policies, and incident response and disaster recovery plans.

### Documentation maturity

- Documentation is centralized around the Postgres-first roadmap; the TypeDB plan is explicitly future/optional.
- There is no current PRD content in prd.md (file appears empty), which is a gap for product decision-making.

## Planned next steps (from existing plans)

### Translational AI Platform plan (docs/plan.md)

- Sprint 1 (Ontology): **Partially complete.** Drug/Pathway/ProteinDomain + Mechanism + Statements of Understanding are implemented; Variant + Phenotype domain schemas are enriched, but DB persistence is pending.
- Sprint 2 (Atlas ingestion): **Partially complete.** PubMed ingestion + rule-based title/abstract extraction pipeline is in place with stored payloads and document URLs. UniProt domain extraction, full-text ingestion, and LLM extraction are pending.
- Sprint 3 (Graph core): **Not started.** GraphService, graph storage, and graph endpoints are pending.
- Sprint 4 (UI and public): **Partially started.** Statements + mechanisms UI (with promotion flow) are integrated; graph explorer and public-facing features are pending.

### Future optional TypeDB plan (docs/world_model/TypeDb_plan.md)

- Retained as a possible migration path if Postgres + NetworkX no longer meets graph semantics or scale needs.
- Phase 1: Minimal TypeDB schema, MED13 seed data, GPT-assisted knowledge extraction, query API, and expert validation.
- Phase 2: Temporal, event-sourced knowledge model with provenance and agentic updates.

### Security plan (docs/security/HIPAA_COMPLIANCE_ASSESSMENT.md and docs/security/SECURITY_CHECKLIST.md)

- Verify encryption at rest and define key management.
- Implement PHI inventory, classification, and handling procedures.
- Enhance audit logging to include IP, user agent, success/failure, and retention policies.
- Define retention and secure deletion policies.
- Create incident response and disaster recovery plans.
- Implement access review procedures and BAA tracking.

## Decision points and gaps

1. Roadmap alignment
   - The chosen path is Postgres-first with NetworkX traversal.
   - Ensure all canonical docs and the PRD reflect this decision to avoid drift.

2. Graph strategy implementation
   - Define the Postgres graph schema (nodes, edges, evidence, review state) and indexing strategy.
   - Establish criteria for when a TypeDB migration would be justified.
   - Close the gap between domain models and database persistence for new mechanism fields.

3. Security readiness
   - HIPAA compliance gaps are critical if the system will handle PHI in production.
   - A formal security remediation plan must be scheduled and staffed.

4. Product scope and users
   - The admin UI is solid, but research workflows (curation, graph exploration) need clarity on scope and ownership.
   - Decision needed on short-term user priorities (admin operations vs researcher discovery).

5. PRD and strategic documentation
   - The main PRD is empty, which makes executive decisions harder.
   - A concise, current PRD should be created to align stakeholders.

## Recommendations

1. Execute the Postgres-first roadmap for the next 1-2 quarters.
   - Implement Sprint 1-2 from docs/plan.md to expand the ontology and ingestion first.
   - Keep TypeDB as a future migration option with clear trigger criteria.

2. Address HIPAA critical gaps before any PHI production use.
   - Prioritize encryption at rest verification, PHI inventory, audit enhancements, retention policies, and incident response/DR plans.

3. Establish data governance and curation workflows.
   - Define who approves data, how evidence confidence is scored, and how provenance is recorded.

4. Make hypothesis review explicit in the domain model.
   - Add Hypothesis and ReviewDecision entities and surface them in UI/ops workflows.

5. Define success metrics.
   - Examples: ingestion accuracy, coverage of MED13 variants, query response times, researcher validation rates.

6. Consolidate documentation.
   - Produce a short, current PRD and a decision log that ties the roadmap to measurable outcomes.

## Proposed next steps (actionable)

Short term (0-2 weeks)
- Document the Postgres-first decision in the PRD and align all stakeholder messaging.
- Draft a concise PRD with scope, goals, and success metrics.
- Identify the minimum security tasks needed for pilot or production.
- Expand PubMed ingestion to capture full-text/JSON payloads and store them in RAW_SOURCE with stable document URLs.
- Add admin-facing extraction metrics/overview endpoints once product requirements are clarified.

Near term (2-6 weeks)
- Add DB persistence for Drug/Pathway and Variant/Phenotype structural fields.
- Update TypeScript types and admin UI to surface the new entities once persistence is in place.
- Define the graph export contract and data schema for downstream tooling.
- Implement LLM-based extraction on stored full-text content and persist structured facts.

Mid term (6-10 weeks)
- Upgrade UniProt ingestion and enrich structural annotations.
- Implement GraphService and a basic export endpoint.
- Pilot a small network explorer view in the admin UI.
 - Add hypothesis scoring and review queue primitives.

Parallel security track
- Verify encryption at rest in the database layer.
- Enhance audit logging fields and retention strategy.
- Draft incident response and disaster recovery plans.

## Appendix: Key references

- README.md
- docs/README.md
- docs/plan.md
- docs/world_model/TypeDb_plan.md
- docs/EngineeringArchitecture.md
- docs/frontend/EngineeringArchitectureNext.md
- docs/security/HIPAA_COMPLIANCE_ASSESSMENT.md
- docs/security/SECURITY_CHECKLIST.md
- docs/system_map.md
