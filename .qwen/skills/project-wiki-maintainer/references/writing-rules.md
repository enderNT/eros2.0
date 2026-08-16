# Writing rules

## Optimize for retrieval and understanding

- Put the direct answer in the first paragraph of each section.
- Use descriptive headings that match likely questions.
- Keep paragraphs short and use tables only for genuine comparison or mapping.
- Expand uncommon abbreviations on first use.
- Use the exact project terminology consistently.
- Link to source files only when they are stable, useful evidence; do not turn the wiki into a file index.

## Distinguish certainty

Use clear labels when needed:

- **Current:** verified behavior in the present system.
- **Planned:** explicitly documented future behavior.
- **Historical:** behavior retained only to explain a migration or decision.
- **Unknown:** a relevant gap that could not be verified.

Never silently combine current and planned behavior.

## Keep documentation maintainable

- One concept, one canonical home.
- Link instead of duplicating.
- Prefer small targeted edits over broad rewrites.
- Remove stale statements when they are disproven; do not preserve contradictions for history unless they belong in an ADR.
- Avoid timestamps such as “currently” unless the date matters.
- Avoid marketing language, vague praise, and unsupported claims.

## Good high-level phrasing

Prefer:

> The API accepts an order, validates inventory, persists the order, and publishes a fulfillment event.

Avoid:

> `OrderController.create()` calls `InventoryService.reserve()` and then invokes `KafkaProducer.send()`.

The second form belongs in code or API documentation, not the project wiki.
