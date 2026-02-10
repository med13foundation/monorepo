# Engineering Proposal: The Universal Study Graph Platform (v3)

**Date:** Feb 9, 2026
**To:** Engineering Leadership & Architecture Review Board
**From:** Product Architecture Team
**Status:** **Ready for Review**

---

## 1. Executive Summary

We propose replatforming the MED13 Resource Library into a **Metadata-Driven Study Graph**.

The current system relies on hardcoded parsers and domain-specific logic, making it brittle and difficult to scale to new domains (e.g., Clinical Trials, CS Benchmarking).

**The Solution:**
We will build a **Kernel** that is domain-agnostic. The "Schema" is not hardcoded in Python classes but defined in a versioned **Master Dictionary** in Postgres.

- **Ingestion:** An AI Agent acts as a **Mapper** (not a generator), mapping incoming data to strict definitions in the Dictionary.
- **Storage:** A hybrid model using **Typed Tables** for high-volume facts (Observations) and **JSONB** only for sparse metadata.
- **Governance:** Strict **Resolution Policies** and **Transform Registries** ensure data integrity and safety.

---

## 2. Core Architecture: The "Kernel"

The system is divided into three distinct layers: **Definition** (The Rules), **Ingestion** (The Processing), and **Storage** (The State).

### 2.1 Layer 1: The Master Dictionary (The Rules)

These tables define _what_ is allowed in the system. No data enters unless it maps to a definition here.

**A. `variable_definitions` (The Vocabulary)**
Defines every data element (e.g., `systolic_bp`, `gene_symbol`, `algorithm_accuracy`).

| Column           | Type  | Description                                   |
| ---------------- | ----- | --------------------------------------------- |
| `id`             | PK    | `VAR_001`                                     |
| `canonical_name` | TEXT  | `systolic_bp` (Snake case, unique)            |
| `data_type`      | ENUM  | `INTEGER`, `FLOAT`, `STRING`, `DATE`, `CODED` |
| `preferred_unit` | TEXT  | `mmHg` (UCUM standard)                        |
| `constraints`    | JSONB | `{"min": 0, "max": 300}`                      |
| `domain_context` | TEXT  | `clinical`, `genomics`, `cs_benchmarking`     |
| `sensitivity`    | ENUM  | `PUBLIC`, `INTERNAL`, `PHI`                   |

**B. `transform_registry` (Safe Normalization)**
Defines _how_ to convert data. **No user-defined code allowed.**

| Transform ID | Input Unit | Output Unit | Implementation Ref               | Status |
| ------------ | ---------- | ----------- | -------------------------------- | ------ |
| `TR_LBS_KG`  | `lbs`      | `kg`        | `func:std_lib.convert.lbs_to_kg` | ACTIVE |
| `TR_F_C`     | `degF`     | `degC`      | `func:std_lib.convert.f_to_c`    | ACTIVE |

**C. `entity_resolution_policies` (The Linkage Logic)**
Defines how we detect duplicates for each type.

| Entity Type | Policy Strategy | Required Anchors    | Auto-Merge Threshold |
| ----------- | --------------- | ------------------- | -------------------- |
| `PATIENT`   | `STRICT_MATCH`  | `["mrn", "issuer"]` | 1.0 (Exact Only)     |
| `GENE`      | `LOOKUP`        | `["hgnc_id"]`       | 1.0                  |
| `PAPER`     | `FUZZY`         | `["doi", "title"]`  | 0.95                 |

---

### 2.2 Layer 2: The Data Model (Storage)

We use a **Postgres Hybrid Schema**. We do _not_ dump everything into JSONB.

**A. `entities` ( The Nodes)**
Represents the "Who" and "What" (Patient, Gene, Paper).

- **Crucial:** No PHI or high-volume clinical data lives here. Only stable metadata.

```sql
CREATE TABLE entities (
    id UUID PRIMARY KEY,
    study_id UUID NOT NULL,
    entity_type TEXT NOT NULL, -- FK to Dictionary
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB -- Sparse data only (e.g. "website_url", "founding_year")
);

```

**B. `entity_identifiers` (The Identity & Security)**
Isolates PHI and lookup keys. Heavily protected by RLS and Column-Level Encryption.

```sql
CREATE TABLE entity_identifiers (
    entity_id UUID REFERENCES entities(id),
    namespace TEXT NOT NULL, -- e.g. "MRN", "SSN", "HGNC", "DOI"
    identifier_value TEXT NOT NULL, -- Encrypted if namespace is PHI
    sensitivity TEXT DEFAULT 'INTERNAL'
);
-- Index for fast resolution
CREATE INDEX idx_identifiers_lookup ON entity_identifiers (namespace, identifier_value);

```

**C. `observations` (The Facts/Time-Series)**
This solves the "Patient Weight over Time" problem. We use an EAV-like table backed by strict typing.

```sql
CREATE TABLE observations (
    id UUID PRIMARY KEY,
    study_id UUID NOT NULL,
    subject_id UUID REFERENCES entities(id), -- The Patient
    variable_id TEXT REFERENCES variable_definitions(id), -- "VAR_001" (Weight)

    -- The Typed Values (Only one is populated)
    value_numeric NUMERIC,
    value_text TEXT,
    value_date TIMESTAMPTZ,
    value_concept TEXT, -- Ontology Code

    unit TEXT, -- The normalized unit (e.g. "kg")
    observed_at TIMESTAMPTZ, -- When it happened

    provenance_id UUID -- Link to source PDF/Row
);

```

**D. `relations` (The Graph Edges)**
Connects entities (e.g., `Gene A` -[ASSOCIATED_WITH]-> `Disease B`).

- Includes `confidence` score and `evidence_id`.

---

### 2.3 Layer 3: The Ingestion Pipeline (The "Governor")

We move from "Parsing" to a **Map -> Normalize -> Resolve -> Validate** pipeline.

**Step 1: Hybrid Schema Mapping**

- **Input:** CSV Column "Body Wt (lbs)".
- **Action:**

1. **Deterministic:** Check `variable_synonyms` table. (Fastest)
2. **Semantic:** `pgvector` search against Dictionary embeddings.
3. **LLM Judge:** If vector score is ambiguous (0.7-0.9), LLM picks best fit.

- **Output:** Maps to `VAR_WEIGHT` + `Unit: lbs`.

**Step 2: Safe Normalization**

- **Check:** Dictionary says `VAR_WEIGHT` requires `kg`. Input is `lbs`.
- **Action:** Lookup `TR_LBS_KG` in `transform_registry`.
- **Execution:** Execute the pre-compiled function. **No LLM code generation.**

**Step 3: Policy-Based Resolution**

- **Context:** Processing a "Patient".
- **Policy:** Load `PATIENT` policy. Requires `MRN`.
- **Action:** Query `entity_identifiers`.
- _Match:_ Link `observation` to existing `entity_id`.
- _No Match:_ Create new `entity` + `entity_identifier`.

**Step 4: Triple Validation**

- **Check:** `Gene` -> `CAUSES` -> `Patient`.
- **Constraint:** Query `relation_constraints`.
- **Result:** **BLOCK**. Invalid Triple. Log error.

---

## 3. Security & Governance

### 3.1 PHI Isolation strategy

- **Physical Separation:** MRNs/Names live in `entity_identifiers`, not `entities`.
- **Encryption:** The `identifier_value` column is encrypted at rest and valid only for authorized sessions.
- **Row-Level Security (RLS):**
- Users have a `session_role`.
- `observations` table policy: `SELECT * FROM observations WHERE study_id IN (user_studies)`.
- `entity_identifiers` policy: `SELECT * FROM entity_identifiers WHERE study_id IN (user_studies) AND user_has_phi_access = true`.

### 3.2 Provenance

Every `observation` and `relation` has a `provenance_id`.

- This links back to the specific **Extraction Run**, the **Source Document**, and the **Mapping Decision** (e.g., "Mapped by AI (Confidence 98%)").

---

## 4. Implementation Plan

**Phase A: The Core & Security (Weeks 1-4)**

- Implement `variable_definitions` and `transform_registry`.
- Implement `entities`, `entity_identifiers`, and `observations` tables.
- **Deliverable:** A functioning Postgres schema that rejects invalid data types.

**Phase B: The Mapping Engine (Weeks 5-8)**

- Build the "Hybrid Mapper" (Exact + Vector + Judge).
- Implement the `transform_registry` execution logic.
- **Deliverable:** Ingest a clean CSV and see it populate `observations` correctly with normalized units.

**Phase C: Logic & Resolution (Weeks 9-12)**

- Implement `entity_resolution_policies`.
- Implement Triple Constraints.
- **Deliverable:** Ingest a "dirty" dataset (duplicates, mixed units) and verify clean graph output.

---

## 5. Risk Assessment

| Risk                  | Mitigation                                                                                                                     |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **JSONB Performance** | We moved high-volume data to `observations` (typed columns). JSONB is now only for low-velocity metadata.                      |
| **AI Hallucination**  | AI is strictly a **Mapper**. It cannot create variables, write code, or define schema. It selects from the Registry.           |
| **PHI Leakage**       | PHI is isolated in `entity_identifiers`. RLS policies explicitly block access without specific claims.                         |
| **"Generic" Trap**    | The Schema is generic, but the _Dictionary_ is specific. We will seed it with distinct Bio and CS domains to prove separation. |

---

## 6. Success Criteria

1. **System can ingest MED13 Clinical Data:** Mapping "Weight" and "BP" to standard Observations.
2. **System can ingest CS Benchmark Data:** Mapping "Accuracy" and "F1 Score" to standard Observations _without code changes_.
3. **Security Audit:** A query for "Patient Names" returns `NULL` or `Access Denied` for a standard researcher account.

**Next Steps:**
Requesting approval to lock the **Schema Definitions (Layer 1 & 2)** and begin Phase A sprint.
