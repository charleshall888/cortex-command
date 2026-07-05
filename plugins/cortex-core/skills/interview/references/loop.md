# Interview Loop

Shared interview-loop mechanics for one-at-a-time conversational grilling. Read this and follow it when conducting an interview. The rules here are generic and caller-agnostic — they describe how to run the loop, not what to do with the answers; answer disposition (priming a session, synthesizing a doc, authoring a ticket) belongs to whoever invoked the interview.

## Decision rules

### Ask one at a time

Pose a single question, wait for the reply, then let that answer shape the next — you follow where each answer leads, not a list fixed up front.

Why: a real interview adapts — the best next question depends on the last answer. Front-loading a batch forfeits that adaptation and forces answers to questions later replies would have made irrelevant.

### Keep the grilling conversational — not batched AskUserQuestion

Conduct the loop as plain-text conversational Q&A: one question in prose, await the reply, next question shaped by that reply. Do not route the grilling through batched `AskUserQuestion` calls.

Why: batching commits later questions before earlier answers arrive — the same adaptation loss as above, here via the tool path. (A caller may still use `AskUserQuestion` for its own discrete decision points outside the grilling — this exclusion is about the question-by-question interview cadence itself.)

### Recommend before asking

When you have a defensible default for a question, lead with it: state the recommendation and the reasoning, then ask the person to confirm or redirect. A recommendation-plus-confirm is usually faster and more useful than an open prompt, because it gives the person something concrete to react to.

Suppress the recommendation on taste or preference questions — anything where the person's genuine preference is the answer, not a fact you could derive. There, pose the question open. Why: recommending on a taste question anchors the person to your guess and contaminates the very preference you meant to elicit.

### Let the codebase trump the interview

When a question is answerable by looking — the code, the existing artifacts, the surrounding context already on disk — explore first and then confirm what you found, rather than asking the person to recite something recoverable. Reserve live questions for what only the person holds: intent, priorities, scope boundaries, and the bars that judgment sets.

Why: confirming a finding ("the code does X — is that the intent?") is faster and a stronger check than asking cold, and it avoids an answer less accurate than the source.

### Funnel from broad to narrow

Open with broad, open questions that map the territory and surface what matters; move to narrow, closed questions that pin down specifics once the shape is clear. Early answers tell you which narrow questions are worth asking.

Why: a sharp, closed question asked too early presumes a frame the person may not share, and you cannot tell which details matter until the broad strokes settle — funnel ordering lets the broad answers prune the narrow ones.

### Stop at saturation

Stop when new answers stop changing the picture — when further questions are returning confirmation rather than new information. Saturation, not coverage of any template or checklist, is the stop signal: a standalone interview has no fixed section list to "complete," so judge by whether the marginal answer still moves the understanding.

The person can stop early at any point — honor that immediately and wrap up gracefully. As a guard against over-interrogation, keep a soft cap: once a fair amount of ground is covered, surface a light "we've covered a lot — keep going or wrap up?" check rather than continuing to question indefinitely.

Why: template-coverage stopping both over-asks (grinding through sections that add nothing) and under-asks (stopping at a filled template while the picture still shifts). Saturation tracks what matters — whether you are still learning.
