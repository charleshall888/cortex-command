# Glossary

## Language

- **scene**: the authoring unit of training content: one mental model expressed as one visual, hand-authored into a deliverable's page using animations from the shared component library; each deliverable owns its scene wording outright (a scenes-as-data schema is deliberately deferred per cortex/requirements/training.md)
- **cockpit**: the deferred (wave-2) interactive training engine: a mock-terminal simulation of an agentic coding session that pauses at branch points, lets the learner choose a prompt, plays out the consequence, and supports rewind-and-retry; v1 ships only its seed, a reusable mock-terminal display component playing scripted session beats
- **tier**: the complexity axis (simple / moderate / complex), rubric at skills/refine/references/clarify.md §5.2, decides how deep ceremony reads
- **criticality**: the risk axis (low / medium / high / critical), rubric at skills/refine/references/clarify.md §5.3, decides whether Review runs
- **short road**: the phase-fork predicate: criticality ∈ {high, critical} OR tier == complex takes the long road, everything else the short one → ADR-0036
