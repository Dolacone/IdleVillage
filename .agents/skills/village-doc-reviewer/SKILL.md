---
name: village-doc-reviewer
description: Technical Writer for IdleVillage. Use to structure, audit, and update documentation to enforce the Single Source of Truth (SSOT) principle and ensure alignment with implementation.
---

# Document Reviewer Skill

This skill guides the process of reviewing and maintaining project documentation to ensure it aligns with the implementation and follows the Single Source of Truth (SSOT) principle.

## Core Principles

- Resource-based Coverage: Every logical module, significant directory, or critical configuration file (excluding `.md` and `./docs`) must be described or referenced in at least one documentation file.
- Single Source of Truth (SSOT):
  - Never duplicate the same content across different files.
  - Cross-reference using links instead of copying explanations.
- Hierarchical Structure:
  - `README.md` acts as the entry point and project map.
  - Every document should be reachable via a chain of links starting from `README.md`.
- Implementation Mapping: Documents must explicitly point to the implementation locations (files or directories) they describe.
- Read-only Implementation: This skill is strictly for updating documentation. DO NOT modify any source code files.

## Workflow

### 1. Automated Health Check

Run the health check script to identify obvious gaps and broken links.

```bash
python village-doc-reviewer/scripts/doc_health_check.py
```

### 2. Structural Review

- README.md: Verify it provides clear guidance and links to all top-level documentation categories.
- Navigation: Ensure every file in `./docs` is linked from either `README.md` or another documented file.

### 3. SSOT & Duplication Check

- Search for repeated explanations of the same logic.
- If duplication is found, consolidate the information into one primary file and replace other occurrences with links.

### 4. Implementation Alignment

- For each module identified as undocumented or poorly documented, create or update a Markdown file in `./docs`.
- Ensure the document mentions the specific file paths or directories in `src/` that implement the described design.

## Validation Criteria

- `scripts/doc_health_check.py` reports zero broken links.
- All core modules in `src/` are referenced in the documentation.
- No conceptual duplication across the `./docs` directory.
- The service design can be fully understood by reading only the documentation.
