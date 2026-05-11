# Common Rationalizations

Patterns Claude (or any debugger) uses to skip systematic process. Read this when you catch yourself looking for shortcuts.

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Phase 1 is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is faster than guess-and-check. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = run team investigation (Phase 4 §5) if Agent Teams available, then architecture discussion. Do not add a 4th fix without completing §5. |
