# Criticality Heuristics

Consumed by `/cortex-core:dev` Step 2 (Branch 5) and the Step-4 decline path.

### Heuristic Signals

| Signal | Suggests |
|--------|----------|
| Authentication/authorization, security, encryption, secrets, tokens | high or critical |
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

- **low**: no elevated signals, easily reversed, minimal impact.
- **medium**: some signals but contained scope — default when uncertain or when none are detected.
- **high**: multiple signals or broad blast radius, hard to reverse.
- **critical**: security, financial, or data-loss signals — severe consequences.

Present conversationally: **Criticality suggestion: `<level>`** — `<one-sentence justification>`.
