# Wiki blueprint

Default root: `docs/wiki/`.

Create only pages that contain useful, verified information. `index.md`, `project-overview.md`, and `scope.md` are the minimum useful set.

```text
docs/wiki/
├── index.md
├── project-overview.md
├── scope.md
├── architecture.md
├── main-flows.md
├── domain.md
├── integrations-and-data.md
├── operations.md
├── glossary.md
└── decisions/
    ├── README.md
    └── NNN-short-title.md
```

## Page responsibilities

### `index.md`

The LLM and human entry point. Include:

- one-paragraph project summary;
- current status or maturity when verifiable;
- a “Start here” reading order;
- links to every canonical page;
- a short “Where to look” table mapping common questions to pages.

Do not duplicate entire sections from other pages.

### `project-overview.md`

- problem and audience;
- value provided;
- major capabilities;
- high-level operating model;
- important context needed to interpret the project.

### `scope.md`

- supported use cases;
- explicit non-goals;
- limitations and assumptions;
- boundaries between this project and adjacent systems;
- supported environments or modes when important.

### `architecture.md`

- system context;
- major runtime components and responsibilities;
- high-level communication paths;
- trust or ownership boundaries;
- optional verified Mermaid diagrams.

Avoid package maps and class diagrams unless the project genuinely needs them to explain a stable architecture.

### `main-flows.md`

Describe the few flows that define the system, such as:

- primary user journey;
- request or event lifecycle;
- asynchronous processing;
- failure and recovery flow;
- administrative or operator flow.

Use numbered steps, state tables, or sequence diagrams when they improve clarity.

### `domain.md`

- core entities and their relationships;
- business rules and invariants;
- lifecycle or state models;
- terminology whose meaning is project-specific.

### `integrations-and-data.md`

- external systems and why they are used;
- inbound and outbound interfaces at a conceptual level;
- data ownership and source of truth;
- important retention, privacy, or consistency constraints;
- failure behavior at integration boundaries.

Do not copy full API references or schemas.

### `operations.md`

- required configuration categories, never secret values;
- environments and deployment shape;
- health checks, logs, metrics, and alerts;
- migrations, backups, recovery, and rollback;
- known operational constraints.

### `glossary.md`

Only terms that are ambiguous, domain-specific, overloaded, or frequently misunderstood.

### `decisions/`

Use short Architecture Decision Records. Suggested sections:

```markdown
# ADR NNN: Title

- Status: Accepted | Superseded | Deprecated
- Date: YYYY-MM-DD

## Context
## Decision
## Consequences
## Alternatives considered
## Evidence
```

Link superseded ADRs in both directions.
