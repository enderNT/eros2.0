---
name: project-wiki-maintainer
description: Maintains a local, Git-versioned Markdown wiki under docs/wiki for humans and LLMs. Use after changes to product behavior, scope, architecture, flows, domain rules, configuration, integrations, data handling, deployment, or operations; also use when asked to initialize, update, audit, repair, or explain the project wiki. Review the current Git diff, update only affected high-level pages, and record that the diff was reviewed even when no documentation change is needed.
argument-hint: "[init|update|audit] [optional focus]"
context: fork
agent: general-purpose
---

# Project Wiki Maintainer

Maintain a concise, high-level project wiki that explains what the software is, why it exists, how it works, what it does and does not do, and the decisions that shape it.

The wiki is a knowledge layer, not a code reference. Do not inventory every file, class, function, endpoint, or implementation detail.

## Inputs

Requested mode and optional focus:

`$ARGUMENTS`

If no mode is provided, use `update`. If `docs/wiki/` does not exist, treat `update` as `init`.

Before acting, read:

- [Update policy](references/update-policy.md)
- [Wiki blueprint](references/wiki-blueprint.md)
- [Writing rules](references/writing-rules.md)

Then run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/wiki_guard.py" status
```

Use the result to identify changed files and whether the current non-wiki diff has already been reviewed.

## Mode: init

1. Inspect existing sources of truth first: README files, manifests, configuration, routes or interfaces, schemas, deployment files, tests that reveal intended behavior, and existing design documents.
2. Explore selectively. Start broad, then read only files needed to verify high-level claims.
3. Create `docs/wiki/` using the blueprint. Omit a page when the project has no verified content for it; do not create empty ceremonial documentation.
4. Make `docs/wiki/index.md` the primary entry point for both humans and LLMs.
5. Explain current behavior only. Put planned or speculative behavior in a clearly marked “Planned” section, or omit it.
6. Create an ADR only when an important decision and its rationale can be verified.

## Mode: update

1. Inspect the changed-file list and relevant diffs before reading unrelated code.
2. Classify the change using the update policy.
3. Locate the smallest set of wiki pages affected.
4. Verify every new claim against code, configuration, tests, or an existing authoritative document.
5. Update only affected sections. Preserve accurate manual explanations and project-specific terminology.
6. If the wiki already reflects the behavior, make no content change.
7. If no high-level knowledge changed, report that no wiki update was needed.
8. Add or supersede an ADR only for durable architectural or product decisions, not routine implementation choices.

## Mode: audit

1. Read `docs/wiki/index.md` and the pages it links to.
2. Compare high-risk claims against current sources of truth: scope, public behavior, main flows, external integrations, data ownership, deployment, security boundaries, and operational constraints.
3. Fix contradictions, stale claims, broken links, duplication, and missing high-level context.
4. Do not rewrite accurate pages merely for style.
5. An audit may run with a clean Git tree; in that case, do not invent a change narrative.

## Required wiki qualities

The finished wiki must make these answers easy to find:

- What is this project and who is it for?
- What problem does it solve?
- What are its major capabilities?
- What is explicitly outside its scope?
- How does it work at a system level?
- What are the main user and system flows?
- Which domain terms or rules matter?
- What data does it own, receive, transform, and send?
- Which external systems does it depend on?
- How is it configured, deployed, observed, and recovered?
- Which important decisions constrain future work?

## Boundaries

- Do not modify application code while running this skill.
- Do not expose secrets, credentials, private keys, tokens, or sensitive example data.
- Do not infer product intent solely from names when behavior cannot be verified.
- Do not present generated diagrams as authoritative unless their relationships are verified.
- Prefer stable concepts over transient implementation details.
- Keep each fact in one canonical page and link to it elsewhere.
- Preserve the wiki's existing language. For a new wiki, follow the repository's primary documentation language unless the invocation requests another language.

## Finish

1. Validate relative Markdown links:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/wiki_guard.py" validate-links
```

2. Review the documentation diff:

```bash
git diff -- docs/wiki
```

3. Record that the current non-wiki diff was reviewed, even when no documentation content changed:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/wiki_guard.py" mark-reviewed
```

4. Return a compact result containing:
   - mode used;
   - pages created or updated;
   - high-level change captured;
   - validation result;
   - or an explicit statement that the wiki was reviewed and no update was necessary.
