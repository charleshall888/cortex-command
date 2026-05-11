# Requirements Context Load

Shared protocol for loading project requirements context. Read this file from any reference that needs to load `requirements/` (currently `clarify.md` §2, `research.md` §0b, and `specify.md` §1).

## Protocol

Check for a `requirements/` directory at the project root.

- If `requirements/project.md` exists, read it.
- Scan `requirements/` for area docs whose names suggest relevance to this feature. Read any that apply.
- If no requirements directory or files exist, note this and proceed.
