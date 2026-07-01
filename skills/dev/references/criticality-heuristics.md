# Criticality Heuristics

Consumed by `/cortex-core:dev` Step 2 (Branch 5 route-to-lifecycle) and the Step-4 decline path. Read this before forming a criticality suggestion.

### Heuristic Signals

Scan the feature description for these indicators:

| Signal | Suggests |
|--------|----------|
| Authentication, authorization, access control | high or critical |
| Security, encryption, secrets, tokens | high or critical |
| Payments, billing, financial data | critical |
| Shared library, core module, base class | high |
| CI/CD, deployment, infrastructure | high |
| Foundational tooling other capabilities are built on | high or critical |
| Database migration, schema change | high |
| Data deletion, destructive operations | high or critical |
| User-facing API change, public interface | medium or high |
| Configuration, settings, preferences | low or medium |
| Documentation, comments, formatting | low |

### Forming the Suggestion

Based on signals found (or absence of signals), suggest a criticality level:

- **low**: No elevated signals. Failure is easily reversed and has minimal impact.
- **medium**: Some signals present but scope is contained. Default when uncertain.
- **high**: Multiple signals or broad blast radius. Failure is hard to reverse.
- **critical**: Security, financial, or data-loss signals. Failure has severe consequences.

Present the suggestion conversationally:

> **Criticality suggestion: `<level>`** — `<one-sentence justification>`.

If no heuristic signals are detected, suggest **medium** (the lifecycle default) and note that no elevated signals were found.
