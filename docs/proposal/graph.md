Your current graph is already **very strong**. It has the right foundations: entities, relations, filters, and focus mode. What you need now is **evidence awareness and claim awareness** so it becomes a **scientific reasoning interface**, not just a relation map.

Below is a **practical checklist of improvements**, ordered from **highest impact → lowest effort**.

---

# 1. Add Claim Layer (highest value)

Right now the graph shows **entity → entity relations only**.

Add support to **expand a relation into its claims**.

### Behavior

When user clicks an edge:

```
MED13 ── associated_with ── intellectual disability
```

Expand to:

```
MED13 → [Claim] → intellectual disability
```

Where `[Claim]` node contains:

* claim text snippet
* polarity
* evidence count
* confidence

### Visual style

Claim node:

```
shape: diamond or rounded rectangle
color: polarity
```

Example:

```
green = SUPPORT
red = REFUTE
yellow = HYPOTHESIS
gray = UNCERTAIN
```

---

# 2. Edge evidence indicator

Currently edges look the same.

Add **small visual signals** for evidence strength.

### Options

Edge thickness = number of supporting claims
Edge color intensity = confidence score

Example:

```
thin line = weak evidence
thick line = many supporting claims
```

This gives instant visual meaning.

---

# 3. Claim evidence panel (most important UI improvement)

When clicking a **claim node**, show a side panel:

```
Claim text
Participants
Evidence sentences
Paper links
Figures
Confidence
Polarity
```

This is where your **existing claim_evidence model shines**.

---

# 4. Expand entity → claims

When clicking a node:

```
MED13
```

Add an option:

```
Show claims involving MED13
```

Graph expands:

```
MED13 → Claim A → FBW7
MED13 → Claim B → transcription
MED13 → Claim C → metabolic syndrome
```

This turns the graph into **scientific statements**, not just relations.

---

# 5. Add participant role visualization

When you introduce `claim_participants`, show roles on edges:

```
MED13 → (SUBJECT) → Claim
FBW7 → (OBJECT) → Claim
human cells → (CONTEXT) → Claim
```

Small edge labels or icons are enough.

---

# 6. Add contradiction highlighting

Your system already stores polarity.

Add automatic contradiction detection in the UI:

If a relation has both:

```
SUPPORT claims
REFUTE claims
```

Render the edge as:

```
striped or warning icon
```

Or show a **conflict badge**.

Scientists will love this.

---

# 7. Add mechanism chain view

This is a separate graph mode.

Instead of showing the whole network:

Show a **path**:

```
Variant
 ↓
Claim
 ↓
Protein stability
 ↓
Claim
 ↓
Transcription
 ↓
Claim
 ↓
Phenotype
```

Layout:

```
left → right
```

This makes mechanisms readable.

---

# 8. Improve node types visually

Right now nodes are all similar blue circles.

Differentiate strongly:

Example style:

```
Gene = teal circle
Protein = dark blue circle
Variant = purple diamond
Phenotype = blue circle
Disease = red circle
Claim = white rounded rectangle
```

This dramatically improves readability.

---

# 9. Add graph search bar

Allow queries like:

```
MED13 FBW7
MED13 variants
MED13 metabolism
```

Then:

* highlight matching nodes
* center graph on them

---

# 10. Add node badges

Small badges on nodes:

```
MED13
[42 claims]
[15 papers]
```

This helps users identify important nodes.

---

# 11. Improve layout behavior

When expanding nodes:

Use rules:

```
1-hop expansion
top 20 neighbors
sorted by confidence
```

Avoid graph explosions.

---

# 12. Add “focus path” tool

User selects two entities:

```
MED13 → metabolic syndrome
```

Graph shows **best path between them**.

This is extremely useful.

---

# 13. Add graph explanation banner

Small banner explaining the view:

Example:

```
Summary view: canonical relations
Claim view: statements with evidence
Mechanism view: causal chains
```

This prevents confusion.

---

# 14. Improve legend

Add legend entries for:

```
Claim node
Polarity colors
Evidence strength
Conflict edges
```

Right now the legend mostly covers entity types.

---

# 15. Performance improvement

Add lazy loading:

```
expand node → fetch neighbors via API
```

Never load full graph.

---

# 16. Add evidence count to relation tooltip

Hovering an edge shows:

```
Relation: ASSOCIATED_WITH
Supporting claims: 12
Refuting claims: 1
Top paper: PMID 12345
Confidence: 0.82
```

This is quick insight.

---

# The biggest impact improvements

If you only implement **four things**, do these:

1️⃣ Expand relation → claim nodes
2️⃣ Claim evidence side panel
3️⃣ Polarity coloring (support/refute)
4️⃣ Node type styling

These alone will transform the graph.

---

# The end goal

Your graph becomes something like:

```
Entity
  ↓
Claim
  ↓
Entity
  ↓
Claim
  ↓
Phenotype
```

A **scientific reasoning graph**, not just a relation network.
