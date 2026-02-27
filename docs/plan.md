Here is the detailed **Engineering Implementation Plan** to evolve the MED13 Resource Library into a **Translational AI Platform**.

This plan follows **Clean Architecture principles** and assumes a **Postgres-backed graph model with NetworkX traversal** for Phases 1-4. The storage choice is intentionally swappable; a TypeDB migration remains a **future option** if graph semantics or scale demand it.

## Goals alignment (explicit)

- Mechanistic reasoning (Variant -> ProteinDomain -> Mechanism -> Phenotype) is the primary graph path.
- Hypotheses are human-verifiable and never auto-promoted to truth.
- The graph is the system of record with provenance and curation status on every edge.
- Agent assistance is bounded, auditable, and cannot write to validated data directly.
- Clinical and scientific credibility is enforced via audit logging, evidence transparency, and review workflows.

## Graph service strategy

- Initial implementation lives inside the existing FastAPI backend as an application service.
- Expose a stable graph API contract (`/api/graph/export`, `/api/graph/neighborhood`, `/api/hypotheses`) so clients are insulated from storage changes.
- Postgres remains the system of record; NetworkX is used for traversal and export.
- Extraction to an independent service is optional and only justified by scale, latency, or external consumer needs.
- Any future TypeDB migration must preserve the API contract.

## Proposal alignment (ResoGraph JTC 2026)

**Program frame**
- **Project title:** ResoGraph: A Hybrid AI & Knowledge Graph Platform for Resolving Unsolved Rare Genetic and Non-Genetic Diseases
- **Duration:** 36 months
- **Primary objective:** 15-25% relative increase in diagnostic yield on >1,000 unsolved cases.
- **Scope:** Rare disease diagnosis only; design is domain-agnostic but no out-of-scope expansion.

**Core safety constraints**
- AI agents are **hypothesis generators only** (no autonomous diagnosis, no write access to validated knowledge).
- Human experts must review and approve hypotheses before graph promotion.
- All mechanistic links are evidence-backed with provenance and confidence scores.

**Hybrid Intelligence layers**
1. **Mechanism-centered knowledge graph (Map)**:
   - Variant <-> Protein Domain <-> Mechanism <-> Phenotype (HPO)
2. **AI agents (Scouts)**:
   - Traverse existing graph paths and propose mechanistic hypotheses
   - Produce human-readable evidence reports
3. **Human review (Judges)**:
   - Mandatory expert validation + optional functional assays

**Cohort strategy**
- **Phase 1 (Gold Standard):** MED13 pilot for calibration and ground-truth mechanistic reasoning.
- **Phase 2 (Expansion):** Neurodevelopmental, Ciliopathy/Mito, and Immune-mediated cohorts.
- **Evaluation:** Diagnostic yield uplift and VUS reclassification with evidence tracking.

## Implementation status (as of January 26, 2026)

**Legend:** DONE | PARTIAL | PLANNED

### Phase 1: Ontology
- **Drug entity** DONE (`src/domain/entities/drug.py`)
- **Pathway entity** DONE (`src/domain/entities/pathway.py`)
- **ProteinDomain value object** DONE (`src/domain/value_objects/protein_structure.py`)
- **Mechanism entity** DONE (domain + DB + API; space-scoped endpoints under `/research-spaces/{space_id}/mechanisms` with UI surfaced in the per-space Knowledge Graph page)
- **Statement of Understanding entity** DONE (domain + DB + API + UI; space-scoped endpoints under `/research-spaces/{space_id}/statements` with promotion to mechanisms)
- **Variant schema enhancements** DONE (structural annotation + in-silico scores in `src/domain/entities/variant.py`)
- **Phenotype longitudinal observations** DONE (`src/domain/entities/phenotype.py`)

### Phase 2: Atlas ingestion
- **UniProt domain extraction** PLANNED (parser exists, but domains are not mapped into `ProteinDomain` or persisted)
- **PubMed research corpus + extraction** PARTIAL (rule-based title/abstract extraction runs after ingestion, persists outputs, stores text payloads in RAW_SOURCE with a document URL endpoint; full-text ingestion + LLM extraction are pending)
- **Drug/Pathway seeding** PLANNED (no seed files or seeding service yet)
- **Repository/DB JSON fields** PLANNED (DB models/migrations do not yet store structural annotation or longitudinal observations)
 - **Non-genetic inputs** PLANNED (immune/biochemical evidence ingestion and mapping to mechanism/pathway nodes)

### Phase 3: Knowledge graph core
- **GraphService + Postgres node/edge storage** PLANNED (not implemented)
- **Graph API endpoints** PLANNED (no `/api/graph/*` routes yet)

### Phase 4: AI engine + UI
- **Hypothesis scoring / inference services** PLANNED (not implemented)
- **Knowledge graph UI** PARTIAL (Statements of Understanding + mechanism management with promotion flow are integrated; graph explorer still pending)

---

# MED13 Translational AI Platform: Engineering Implementation Plan

## **Phase 1: The Ontology (Domain Layer Expansion)**
**Goal:** Formally define the biological entities required for mechanism modeling and therapeutic discovery. We move beyond "Variant Registry" to "System Biology Model."

### **1.1 New Domain Entities**
We must introduce three new core entities to the `src/domain/entities/` module.

*   **`Drug` (Therapeutic Agent)**
    *   **Purpose:** Represents small molecules, ASOs, or gene therapies.
    *   **Attributes:** `id` (DrugBank/PubChem), `name`, `mechanism_of_action` (e.g., "CDK8 inhibitor"), `brain_penetrance` (Boolean), `approval_status` (FDA/EMA).
    *   **File:** `src/domain/entities/drug.py`

*   **`Pathway` (Biological Context)**
    *   **Purpose:** Represents the functional networks MED13 regulates (e.g., "Wnt signaling", "Mitochondrial metabolism").
    *   **Attributes:** `id` (Reactome/GO), `name`, `gene_set` (List of Gene IDs).
    *   **File:** `src/domain/entities/pathway.py`

*   **`ProteinDomain` (Structural Context)**
    *   **Purpose:** Defines the physical regions of the MED13 protein.
    *   **Attributes:** `name` (e.g., "Cyclin C binding interface"), `start_residue`, `end_residue`, `3d_coordinates` (AlphaFold JSON), `function`.
    *   **Usage:** Value Object embedded within `Gene` or linked to `Variant`.

*   **`Mechanism` (Causal Link)**
    *   **Purpose:** Represents a biological mechanism that bridges variants/domains to phenotypes.
    *   **Attributes:** `id`, `name`, `description`, `evidence_tier`, `confidence_score`.
    *   **Usage:** Node type in the graph, backed by evidence with provenance.

*   **`StatementOfUnderstanding` (Hypothesis Layer)**
    *   **Purpose:** Captures evolving mechanistic hypotheses prior to canonical promotion.
    *   **Attributes:** `id`, `title`, `summary`, `evidence_tier`, `confidence_score`, `status`.
    *   **Usage:** Primary reasoning workspace; promotes into `Mechanism` when well supported.

### **1.2 Expanded Mechanism & Outcome Entities (Sprint 3)**
To fully capture the disease mechanism, we will add these entities in the next phase:

*   **`ProteinInteraction` (PPI)**
    *   **Purpose:** Explicitly models binding events (e.g., MED13-Cyclin C).
    *   **Attributes:** `protein_a`, `protein_b`, `binding_affinity` (Kd), `evidence_type` (Co-IP, Yeast 2-Hybrid).

*   **`TranscriptionalTarget`**
    *   **Purpose:** Genes whose expression is regulated by MED13.
    *   **Attributes:** `target_gene`, `regulation_direction` (Up/Down), `fold_change`, `context` (Cell Type).

*   **`CellularContext`**
    *   **Purpose:** Defines the biological environment where a phenotype occurs.
    *   **Attributes:** `cell_type` (e.g., GABAergic Neuron), `developmental_stage` (e.g., E14.5), `tissue`.

### **1.3 Hypothesis and Curation Entities (Sprint 3)**
To enable human-verifiable hypotheses, we will add explicit structures for review and provenance:

*   **`Hypothesis`**
    *   **Purpose:** Stores proposed mechanistic paths with evidence and contradictions.
    *   **Attributes:** `id`, `summary`, `support_score`, `contradiction_score`, `net_score`, `status`.

*   **`ReviewDecision`**
    *   **Purpose:** Captures human validation events.
    *   **Attributes:** `reviewer_id`, `decision`, `notes`, `reviewed_at`.

### **1.4 Enhance Existing Entities**
*   **Refactor `Variant` (`src/domain/entities/variant.py`)**
    *   **Add `StructuralAnnotation`:** Links a variant to specific `ProteinDomains` (e.g., "Variant R123X is in the IDR region").
    *   **Add `InSilicoScores`:** Fields for `cadd_phred`, `revel`, `alpha_missense` (critical for AI classification).
    *   **Add `FunctionalPrediction`:** Field for `predicted_consequence` (e.g., "Haploinsufficiency" vs "Dominant Negative").

*   **Refactor `Phenotype` (`src/domain/entities/phenotype.py`)**
    *   **Add `LongitudinalData`:** Support for time-series observations (Age of onset, severity progression) to enable Natural History modeling.

---

## **Phase 2: The "Atlas" (Ingestion & Enrichment) - Sprint 2**
**Goal:** Build the "Smart Scout" infrastructure to ingest, analyze, and persist high-fidelity scientific data (Structural, Clinical, Therapeutic).

### **2.1 Structural Biology Ingestion (UniProt)**
*   **Task:** Upgrade `UniProtIngestor` to extract `ProteinDomain` data.
*   **Implementation:**
    *   Parse `features` list in UniProt XML/JSON.
    *   Extract types: `domain`, `region`, `binding site`, `active site`.
    *   Map to `ProteinDomain` Value Object with coordinates.
*   **Success Criteria:** `Gene` entities in the DB have populated `structural_annotation` fields.

### **2.2 AI-Driven Literature Extraction (PubMed "Scout")**
*   **Task:** Transform PubMed ingestion into a "Research Corpus" builder.
*   **Implementation:**
    *   **Raw Storage (MVP):** Save title/abstract text payloads to RAW_SOURCE storage with a document URL for retrieval.
    *   **Full-Text Storage (Next):** Persist full JSON/XML or full-text content to RAW_SOURCE for downstream LLM extraction.
    *   **Analysis Queue:** Queue publications for extraction and run immediately after ingestion (scheduler-driven ingestion remains the trigger).
    *   **Entity Extraction (MVP):** Implement basic regex/rule-based extraction for:
        *   **Variants:** `c.\d+[A-Z]>[A-Z]`, `p.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}`
        *   **Phenotypes:** HPO IDs in text (`HP:#######`).
        *   **Genes:** Known gene symbols (MED13 MVP).
    *   **Entity Extraction (Next):** Add HPO term list matching and drug/compound matching.
*   **Success Criteria:** MVP can identify "Paper X contains Variant Y and Phenotype Z" from title/abstract; full-text + LLM extraction extends coverage.

### **2.3 Non-Genetic Evidence Ingestion (Immune-Mediated)**
*   **Task:** Add ingestion for non-genetic inputs relevant to immune-mediated rare disease cases.
*   **Implementation:**
    *   Define a minimal schema for immune/biochemical evidence (e.g., cytokines, auto-antibodies, pathway activity).
    *   Map non-genetic evidence into Mechanism/Pathway nodes with provenance.
    *   Support ingestion of cohort-provided structured datasets.
*   **Success Criteria:** Immune-mediated cases can be represented without a starting variant, and hypotheses can traverse from phenotype -> mechanism -> pathway.

### **2.3 Therapeutic Atlas Seeding**
*   **Task:** Populate the `Drug` and `Pathway` tables.
*   **Implementation:**
    *   Create `DrugSeedingService` to load a curated JSON list (`data/seeds/drugs.json`).
    *   **Seed Scope:**
        *   CDK8 Inhibitors (e.g., Cortistatin A, Senexin B).
        *   Broad-spectrum Neuro-drugs (e.g., Valproic Acid, Levetiracetam).
        *   Gene Therapy Vectors (AAV serotypes relevant to CNS).
*   **Success Criteria:** `DrugRepository` contains >20 validated therapeutic candidates.

### **2.4 Repository Layer Upgrades**
*   **Task:** Update SQLAlchemy models to support complex JSON fields.
*   **Implementation:**
    *   Update `VariantModel` to store `structural_annotation` and `in_silico_scores` as JSONB.
    *   Update `PhenotypeModel` to store `longitudinal_observations` as JSONB.
    *   Ensure full round-trip type safety (Pydantic <-> SQLAlchemy).

---

## **Phase 3: The Knowledge Graph (Application & Infrastructure)**
**Goal:** Connect the isolated entities into a traversable network to enable hypothesis generation.

### **3.1 Graph Service (`src/application/services/graph_service.py`)**
This is the core engine. It orchestrates the retrieval of data from Repositories and constructs the Graph.

*   **Responsibility:**
    1.  Fetch all `Variants`, `Phenotypes`, `Domains`, `Mechanisms`, `Drugs`.
    2.  Construct Nodes for each.
    3.  Construct Edges based on business rules with provenance and curation status:
        *   `Variant` --(*causes*)--> `Phenotype`
        *   `Variant` --(*located_in*)--> `ProteinDomain`
        *   `ProteinDomain` --(*impacts*)--> `Mechanism`
        *   `Mechanism` --(*explains*)--> `Phenotype`
        *   `Drug` --(*targets*)--> `Pathway`/`Gene`
        *   `Gene` --(*interacts_with*)--> `Gene` (PPI)

### **3.2 Graph Implementation (Infrastructure)**
*   **MVP (Postgres + NetworkX):**
    *   Store nodes and edges in Postgres tables as the system of record.
    *   Include provenance, evidence references, and curation status on edges.
    *   Build the graph in-memory using Python's `networkx` library for traversal and export.
    *   Fast, easy to debug, perfect for exporting to JSON for the frontend/public.
    *   **Output:** `med13_knowledge_graph.json` (Node-Link format).

*   **Future option (TypeDB/Neo4j):**
    *   Optional migration if Postgres + NetworkX hits scale or semantic constraints.
    *   See `docs/world_model/TypeDb_plan.md` for a future migration concept (not current execution).

### **3.3 Public API (`src/routes/graph.py`)**
*   **Endpoint:** `GET /api/graph/export`
    *   Returns the full JSON graph. This enables "Open Science" - researchers can download our model and run their own algorithms.

## **Phase 4: Human Validation & Evaluation (Clinical Impact)**
**Goal:** Prove clinical utility and enforce strict human governance.

### **4.1 Hypothesis Review Workflow**
*   **Task:** Add `Hypothesis` + `ReviewDecision` domain entities and a review queue in the admin UI.
*   **Implementation:**
    *   Persist hypotheses with evidence references and confidence scores.
    *   Create reviewer actions: approve, reject, request more evidence.
    *   Log every review decision with provenance and timestamps.

### **4.2 Cohort Evaluation**
*   **Task:** Evaluate ResoGraph on >1,000 unsolved cases across genetic and non-genetic cohorts.
*   **Success Criteria:** 15-25% relative increase in diagnostic yield; 100-200 VUS reclassifications backed by evidence.

### **4.3 Functional Validation (Optional in MVP)**
*   **Task:** Capture wet-lab validation outcomes for a subset of hypotheses.
*   **Implementation:** Store assay results as evidence records linked to hypotheses and mechanisms.

---

## **Phase 4: The AI Engine (Inference Layer)**
**Goal:** Use the Graph to answer questions.

### **4.1 Variant Classifier (`VariantClassificationService`)**
*   **Input:** A `Variant` with its `StructuralAnnotation` and `InSilicoScores`.
*   **Logic:**
    *   *Level 1 (Rules):* If `impact` is "High" and `clinvar` is "Pathogenic", label as "Loss of Function".
    *   *Level 2 (ML):* Train a classifier (Random Forest/Gradient Boost) on the Graph features to predict pathogenicity for VUS (Variants of Uncertain Significance).

### **4.2 Therapeutic Hypothesis Generator (`DrugRepurposingService`)**
*   **Logic:** Graph Traversal.
    *   Identify `Pathways` disrupted by pathogenic variants.
    *   Find `Drugs` that target these pathways (or inverse-target them).
    *   Rank candidates based on `safety` and `brain_penetrance`.

### **4.3 Hypothesis Evaluation (`HypothesisScoringService`)**
*   **Logic:** Evidence aggregation with explicit contradictions.
    *   Compute support, contradiction, and net scores.
    *   Emit human-readable mechanism reports with citations.
    *   Require human review before promotion to validated knowledge.

---

## **Risk Assessment & Mitigation**

### **Risk 1: Circular Dependencies in Domain Model**
*   **Description:** Tightly coupling `Variant`, `Gene`, and `ProteinDomain` can lead to Python circular import errors, especially when defining relationships (e.g., Variant -> Domain -> Variant).
*   **Mitigation:**
    *   Use `src/domain/value_objects/` for shared structures like `ProteinDomain` that don't require their own identity.
    *   Utilize `TYPE_CHECKING` blocks and string forward references (`"Variant"`) in Pydantic models.
    *   Strictly enforce unidirectional dependencies in the core domain where possible.

### **Risk 2: Graph Service Scalability**
*   **Description:** Loading the entire knowledge graph into memory (NetworkX) could become a bottleneck if the dataset grows significantly (e.g., including all genome-wide interactions).
*   **Mitigation:**
    *   **MVP Scope:** Limit the initial graph to MED13-specific interactions (~100k nodes), which easily fits in memory.
    *   **Future Scaling:** The architecture allows an optional migration of `GraphService` from NetworkX to a dedicated graph database (TypeDB/Neo4j) without changing the API contract.
    *   **Pagination:** Implement subgraph querying (e.g., `get_neighborhood(node_id, depth=1)`) instead of full-graph dumps for UI endpoints.

### **Risk 3: Data Quality Propagation**
*   **Description:** "Garbage in, garbage out." Integrating noisy data from automated extraction (NLP) or uncurated public sources could pollute the graph.
*   **Mitigation:**
    *   **Confidence Scoring:** Every edge in the graph must have a `confidence_score` (0.0-1.0) and `provenance` trace.
    *   **Source Tiering:** Prioritize "Gold Standard" sources (Curated ClinVar, Manually Verified Papers) over "Silver/Bronze" sources (Automated Mining) in the inference engine.

---

## **Execution Roadmap (36-Month, Proposal-Aligned)**

| Phase | Timeframe | Focus | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Months 1-9 | **MED13 Gold Standard** | Mechanism entity + persistence, MED13 mechanistic subgraph, curated evidence ingestion, baseline extraction MVP. |
| **Phase 2** | Months 10-18 | **Atlas Expansion** | UniProt domain ingestion, full-text PubMed ingestion + LLM extraction, non-genetic evidence ingestion. |
| **Phase 3** | Months 19-27 | **Graph Core + Agents** | GraphService + APIs, agentic hypothesis generation, review queue UX, provenance-based scoring. |
| **Phase 4** | Months 28-36 | **Cohort Evaluation** | Multi-cohort validation (>1,000 cases), diagnostic yield tracking, VUS reclassification reports. |

## **Immediate priorities (proposal-aligned)**
- Wire mechanisms into graph traversal/export and curation workflows.
- Upgrade PubMed ingestion to full-text storage + LLM extraction.
- Introduce **Hypothesis** + **ReviewDecision** with a minimal review workflow in the admin UI.
