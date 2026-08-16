# Update policy

Update the wiki when a change alters knowledge that a new developer, operator, product owner, or LLM needs to understand the project correctly.

## Usually requires an update

| Change | Likely destination |
|---|---|
| New or changed user-visible capability | `project-overview.md`, `scope.md`, or `main-flows.md` |
| Changed product boundary, limitation, or non-goal | `scope.md` |
| New service, datastore, queue, worker, or major dependency | `architecture.md` |
| Changed end-to-end behavior or state transition | `main-flows.md` |
| New domain term, invariant, validation, or business rule | `domain.md` or `glossary.md` |
| New external API, webhook, provider, or ownership boundary | `integrations-and-data.md` |
| Changed configuration, deployment, observability, backup, or recovery | `operations.md` |
| Durable decision with meaningful alternatives or tradeoffs | new ADR under `decisions/` |
| Breaking change or important migration | affected page plus `operations.md` or an ADR |

## Usually does not require an update

- Formatting, renaming, or internal refactoring with no behavioral or architectural effect.
- Test-only changes that do not reveal a changed contract.
- Dependency patch updates with no meaningful operational or behavioral impact.
- Generated files, lockfile-only churn, or mechanical migrations.
- Private helper functions and low-level implementation details.
- Temporary experiments that are not part of the supported system.

## Judgment rules

1. Document the resulting system, not the edit history.
2. A small code diff can represent a major product change; a large refactor can require no wiki change.
3. Prefer updating an existing canonical section over adding a new page.
4. Record “why” only when evidence exists. Otherwise document the verified current constraint without inventing rationale.
5. If a changed behavior is intentionally undocumented for security or privacy reasons, describe the boundary without exposing sensitive mechanics.
6. When uncertain, state the uncertainty in the result and leave unsupported claims out of the wiki.
