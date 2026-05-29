# Interview Loop

Shared interview-loop mechanics for one-at-a-time conversational grilling. Read this and follow it when conducting an interview. The rules here are generic and caller-agnostic — they describe how to run the loop, not what to do with the answers; answer disposition (priming a session, synthesizing a doc, authoring a ticket) belongs to whoever invoked the interview.

This file is the canonical source for the one-at-a-time cadence rule. Other surfaces that conduct interviews point here for that rule rather than restating it.

## Decision rules

### Ask one at a time

Pose a single question, wait for the reply, then let that answer shape the next question. The previous answer gates the next one — you are not working from a fixed list of questions decided up front, you are following where each answer leads.

Why: a real interview adapts. The most useful next question usually depends on what was just said — it sharpens a vague answer, follows a thread the person opened, or drops a branch they closed. Front-loading a batch of questions forfeits that adaptation and forces the person to answer questions that later answers would have made irrelevant.

### Keep the grilling conversational — not batched AskUserQuestion

Conduct the loop as plain-text conversational Q&A: one question in prose, await the reply, next question shaped by that reply. Do not route the grilling through batched `AskUserQuestion` calls.

Why: batching several questions into one structured call breaks the previous-answer-gates-the-next-question cadence — the whole batch is composed before any answer arrives, so later questions cannot react to earlier ones. The grilling is conversational priming, not a structured pick-menu; a plain-text exchange keeps each question contingent on the last answer. (A caller may still use `AskUserQuestion` for its own discrete decision points outside the grilling — this exclusion is about the question-by-question interview cadence itself.)

### Recommend before asking

When you have a defensible default for a question, lead with it: state the recommendation and the reasoning, then ask the person to confirm or redirect. A recommendation-plus-confirm is usually faster and more useful than an open prompt, because it gives the person something concrete to react to.

Suppress the recommendation on taste or preference questions — anything where the person's genuine preference is the answer, not a fact you could derive. There, pose the question open. Why: leading with a recommendation on a taste question anchors the person to your guess and contaminates the very preference you were trying to elicit.

### Let the codebase trump the interview

When a question is answerable by looking — the code, the existing artifacts, the surrounding context already on disk — explore first and then confirm what you found, rather than asking the person to recite something recoverable. Reserve live questions for what only the person holds: intent, priorities, scope boundaries, and the bars that judgment sets.

Why: people's time is the scarce resource in an interview. Spending a question on something the codebase already answers wastes it and risks an answer less accurate than the source. Confirming a finding ("the code does X — is that the intent?") is both faster and a better check than asking cold.

### Funnel from broad to narrow

Open with broad, open questions that map the territory and surface what matters; move to narrow, closed questions that pin down specifics once the shape is clear. Early answers tell you which narrow questions are worth asking.

Why: asking a sharp, closed question too early presumes a frame the person may not share, and you cannot tell which details matter until the broad strokes are settled. Funnel ordering lets the broad answers prune the narrow ones.

### Stop at saturation

Stop when new answers stop changing the picture — when further questions are returning confirmation rather than new information. Saturation, not coverage of any template or checklist, is the stop signal: a standalone interview has no fixed section list to "complete," so judge by whether the marginal answer still moves the understanding.

The person can stop early at any point — honor that immediately and wrap up gracefully. As a guard against over-interrogation, keep a soft cap: once a fair amount of ground is covered, surface a light "we've covered a lot — keep going or wrap up?" check rather than continuing to question indefinitely.

Why: template-coverage stopping over-asks (it grinds through sections that add nothing) and under-asks (it stops at a filled template even when the real picture is still shifting). Saturation tracks the thing that actually matters — whether you are still learning — and the early-exit and soft cap keep the loop respectful of the person's time and patience.
