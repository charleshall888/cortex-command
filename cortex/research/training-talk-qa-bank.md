# Q&A defense bank: "Attention Is the Game"

> Prepared 2026-07-13 by the Q&A-gauntlet pass. Format: question → ≤30-sec spoken answer → scene callback. Pointing back at taught visuals is the strongest Q&A move.

## The bank

**1. "Contexts hit 1M and keep growing — won't this talk be obsolete in a year?"**
"Windows will keep growing — conceded. But the rule is a percentage, not a number: 30% of a million is 300k, and it scales with whatever they ship next. Two things haven't budged across model generations: you resend the whole session every turn, and effective context stays smaller than advertised context — that's consistent research, not my opinion. Bigger windows raise the ceiling on what you *can* carry. They've never changed what you *should*."
→ the scan + the zones

**2. "What did designing this deck with agents actually cost — cheaper than just making it?"**
"Here are the real numbers: [N agents, ~X tokens, ~$Y — FILL BEFORE TALK]. Was it cheaper than me typing an outline? No. It wasn't buying speed — it was buying breadth: five perspectives I can't hold simultaneously. One of them, the fact-checker, caught a pricing claim I had exactly backwards. If it had survived to this room, someone here would have caught it instead. That correction alone was worth the bill."
→ tint transfer (hold numbers as appendix slide; don't volunteer in-scene)

**3. "The METR study — doesn't it show this all makes us slower, period?"**
"It's a good study and I believe it: experienced devs, codebases they knew cold, 19% slower — while feeling faster. Now look at *how* they worked: watching every diff, line by line, in repos where their own hands are genuinely fast. That's the exact workflow I'm telling you to stop doing. The slowdown is what unmanaged context plus review-everything looks like. And where it stays true — code you know cold and can type faster than you can specify — don't use an agent. That's on my by-hand list for a reason."
→ METR plant (Act 0→I) + by-hand list

**4. "How do you MEASURE whether any of this works? Or is it vibes?"**
"Straight answer: 50/30 is calibrated experience, not a benchmark — I said so when I put it up. What I measure is one level up, where measurement is honest: how often I re-run a task, whether overnight work lands approved by morning, token cost per merged change. And where measurement matters most I make it a gate, not a chart — my skill files have size budgets enforced by lint; they physically can't bloat. If you want proof for yourself, it's a twenty-minute A/B on your own ticket."
→ turnstile + scene 3's measurement-posture line

**5. "Isn't rewinding just throwing away paid-for work?"**
"Those tokens are spent whether I rewind or not — that's sunk cost. The question is whether I keep paying: every future turn re-reads the dead exploration, at rent, forever. And the cost isn't even the bad part — the contamination is. The model keeps anchoring on the design we rejected. I keep the one-line lesson; I drop the two hundred thousand tokens of scaffolding around it."
→ filmstrip coins + the scan

**6. "Subagents and forks fan our code out to more model calls — data-surface problem?"**
"Right question, and worth routing to security properly. But fan-out multiplies *calls*, not *surfaces* — same provider, same endpoint, same account terms as the single-agent calls we already make; a subagent isn't a new vendor. The thing that actually needs governing is what agents can *touch* — which directories, which tools — and that's enforced as config, structurally, not as a promise in a prompt."
→ sign vs turnstile · **PREP: verify actual DPA/data-handling terms before saying "same account terms" live**

**7. "Don't let agents write skills — but you use them for everything else. Where's the line?"**
"Verifiability. Code has tests, compilers, diffs — the agent can be checked, so delegate freely. A skill file has no failure signal; nothing tells you it's bloated until every future session is paying for it. So: closed-ended and verifiable, delegate. Open-ended and unverifiable, the human owns authorship — the agent can draft, you hold the knife. And if you really want to automate meta-work, first build the verification that closes the loop. That's how I earned back the right to point Claude at my own harness."
→ scroll-and-drawers + turnstile

**8. "Claude Code costs a multiple of what we pay now. Justify it."**
"It's a premium — I won't pretend otherwise, and I'm not the procurement decision. Two things: first, per-seat is the wrong denominator; measure per merged change, and run that A/B on your own work. Second — everything I showed tonight works in any harness. The gauge, tickets, rewind, review: if we stayed on Cursor forever, tonight still pays. My claim was never 'buy the expensive one'; it's 'the harness is a variable — stop ignoring it.'"
→ assembly/"harness" scene

**9. "My 800-line .cursorrules works fine. Why would I gut it?"**
"Maybe it does! The question is what it costs per turn — every one of those 800 lines rides along on every request, whether tonight's task needs it or not. And the model did that to you, by the way — they ratchet; mine did it to me at five times that size. The experiment is cheap: split it into a 30-line core plus reference files loaded on demand, and watch what happens. Mine surprised me — quality went *up* when I cut, because instructions compete for attention."
→ scan line sweeping the scroll

**10. "Adversarial review is paying the model to argue with itself. ROI?"**
"That's exactly what it is — cheap insurance priced against expensive failures. A review pass costs pocket change; the rare-but-small class of bug it catches costs an afternoon and a bad deploy. But here's the honest half: the ROI is only positive if you *synthesize*. Act on every finding and you pay twice — once for the review, once for the armor-plating. The judgment step is the product. And yes, sometimes it's steered me wrong. Net of everything, strongly positive."
→ gold seam + the binned finding

**11. "Why decompose at all? One agent, whole epic, million-token window."**
"I've run that experiment. The epic-in-one-session agent is at 60% on the gauge before it writes a line of the third ticket — and it degrades exactly the way the research predicts. Decomposition was never about *fitting* — it's about giving every piece of work a fresh head that carries just its ticket and the badge of intent. Plus the operational win nobody mentions: four small sessions run in parallel, and any one of them can fail alone."
→ zones + prism/badge

**12. "What happens when the model is wrong ANYWAY, after all this process?"**
"It will be — nondeterminism is a property, not a defect. The process isn't there to make the model right; it's there to make wrongness cheap and visible. Small tickets bound the blast radius. Gates catch it before merge. Review catches what tests don't. And I still read everything that ships — that's the by-hand list. Then the important move: when it's wrong, don't patch the output — fix the input. The ticket, the badge, or the gate, so that *class* of wrong doesn't come back."
→ by-hand list + turnstile + badge

**13. "This is a lot of ceremony. I just want to code."**
"For a one-file fix? Skip all of it — open the editor, or one-shot the agent. The ceremony scales with what you're delegating: ticket-sized work needs a ticket-shaped ask and nothing more; the full extract-and-decompose pipeline is for epic-sized work. Match the ceremony to the blast radius. The gauge tells you when you've crossed the line."
→ zones/exit door + scene 5's ceremony-scoping line

**14. "These demos were staged — has any of this shipped real code?"**
"Every technique tonight runs my actual repo — including work that merged while I slept. The staging is so it's clean on screen and nobody's real code gets dunked on, not because the real thing doesn't exist. Grab me after and I'll show you a real session log and the PR trail."
→ staging disclosure · **PREP: have one real morning report / merged-PR trail ready to show**

## Hard prep dependencies (before the talk)

1. Pull real token/cost numbers for the making-of story (Q2) — hold as an appendix slide.
2. Have a real merged-PR trail / session log ready to show after (Q14).
3. Verify org data-handling/DPA terms with the vendor-relationship owner (Q6).
