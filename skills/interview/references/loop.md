# Interview Loop

Shared mechanics for one-at-a-time conversational grilling. Caller-agnostic: describes how to run the loop, not what to do with the answers — disposition (priming a session, synthesizing a doc, authoring a ticket) belongs to whoever invoked the interview.

### Ask one at a time, conversationally

Pose a single question in prose, wait for the reply, then let that answer shape the next — not a list fixed up front, and not batched `AskUserQuestion` calls. Either form commits to later questions before earlier answers arrive, forfeiting the adaptation a real interview depends on. (A caller may still use `AskUserQuestion` for its own discrete decisions outside the grilling.)

### Recommend before asking

When you have a defensible default, lead with it: state the recommendation and reasoning, then ask the person to confirm or redirect — concrete beats open-ended. Suppress the recommendation on taste or preference questions, where the person's genuine preference is the answer rather than a fact you could derive; recommending there anchors and contaminates the very preference you meant to elicit.

### Let the codebase trump the interview

When code, existing artifacts, or on-disk context already answer a question, explore and confirm what you found rather than asking cold — a confirmed finding is faster and more reliable than a recited answer. Reserve live questions for what only the person holds: intent, priorities, scope boundaries, and the bars judgment sets.

### Funnel from broad to narrow

Open broad to map the territory and surface what matters; narrow once the shape is clear. A closed question asked too early presumes a frame the person may not share — early answers tell you which narrow questions are worth asking.

### Stop at saturation

Stop when new answers stop changing the picture, not at coverage of a template — a standalone interview has no fixed section list to complete, so judge by whether the marginal answer still moves understanding. Honor an early stop request immediately. As a guard against over-interrogation, once a fair amount of ground is covered, surface a light "we've covered a lot — keep going or wrap up?" check.
