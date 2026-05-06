#!/usr/bin/env bash
# Cross-corpus verification script for #178 (skill-creator-lens improvements).
# Runs every spec acceptance check and the U2 cross-corpus drift check.
# Pass = exit 0, final line "ALL PASS".

set -euo pipefail
fail() { echo "FAIL: $*"; exit 1; }
ok() { echo "OK: $*"; }

LIFECYCLE_DIR="lifecycle/apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry"

# R1: TOC presence on the four >300-line files
for f in skills/lifecycle/SKILL.md skills/lifecycle/references/plan.md skills/lifecycle/references/implement.md skills/critical-review/SKILL.md; do
  head -25 "$f" | grep -q '^## Contents$' || fail "R1 TOC missing in $f"
done
ok "R1 TOCs (4 files)"

# R2: when_to_use on all 4 SKILL.md files (per-file count to dodge awk's cross-file counter)
count=0
for f in skills/lifecycle/SKILL.md skills/refine/SKILL.md skills/critical-review/SKILL.md skills/discovery/SKILL.md; do
  awk '/^---$/{c++; if(c==2) exit} c==1 && /^when_to_use:/' "$f" | grep -q '^when_to_use:' && count=$((count + 1))
done
[ "$count" -eq 4 ] || fail "R2 when_to_use count=$count, expected 4"
ok "R2 when_to_use (4 files)"

# R2: sibling-disambiguator clauses
grep -q "Different from /cortex-core:refine" skills/lifecycle/SKILL.md || fail "R2 lifecycle disambiguator missing"
grep -q "Different from /cortex-core:lifecycle" skills/refine/SKILL.md || fail "R2 refine disambiguator missing"
grep -q "Different from /cortex-core:research" skills/discovery/SKILL.md || fail "R2 discovery disambiguator missing"
grep -q "Different from /devils-advocate" skills/critical-review/SKILL.md || fail "R2 critical-review disambiguator missing"
ok "R2 disambiguators (4 files)"

# R3: OQ3 soften — content-anchored (review.md)
python3 -c "
import re, sys
lines = open('skills/lifecycle/references/review.md').readlines()
bad = [i for i,l in enumerate(lines,1) if re.search(r'\b(MUST|CRITICAL|REQUIRED)\b', l) and any(k in l.lower() for k in ['verdict section','verdict-json','verdict json'])]
sys.exit(1 if bad else 0)
" || fail "R3 soften incomplete in review.md"
ok "R3 review.md soften"

# R3: OQ3 soften — content-anchored (clarify-critic.md)
python3 -c "
import re, sys
lines = open('skills/refine/references/clarify-critic.md').readlines()
bad = [(i, l.strip()[:80]) for i,l in enumerate(lines,1) if re.search(r'\b(MUST|REQUIRED)\b', l) and any(k in l.lower() for k in ['closed-allowlist','post-feature event','parent_epic_loaded'])]
if bad: print('FAIL:', bad); sys.exit(1)
" || fail "R3 soften incomplete in clarify-critic.md"
ok "R3 clarify-critic.md soften"

# R4 U1: critical-review trim
grep -q "Default ambiguous" skills/critical-review/SKILL.md || fail "R4 U1 directive missing"
! grep -q "Compliant: R10 strengthened" skills/critical-review/SKILL.md || fail "R4 U1 verbose worked-example block remains"
ok "R4 U1"

# R4 U2: cross-corpus drift check
python3 -c "
import re, sys
decisions = open('$LIFECYCLE_DIR/u2-decisions.md').read()
if '<!-- u2-decisions:complete -->' not in decisions:
    print('FAIL: u2-decisions.md missing completion sentinel'); sys.exit(1)
corpus = ['skills/discovery/references/clarify.md','skills/discovery/references/auto-scan.md','skills/discovery/references/decompose.md','skills/lifecycle/references/clarify.md','skills/lifecycle/references/clarify-critic.md','skills/lifecycle/references/specify.md','skills/lifecycle/references/plan.md','skills/lifecycle/references/implement.md','skills/lifecycle/references/review.md','skills/lifecycle/references/orchestrator-review.md','skills/lifecycle/references/complete.md','skills/refine/references/clarify-critic.md']
sections = re.split(r'^## ', decisions, flags=re.M)
for f in corpus:
    block = next((s for s in sections if s.startswith(f)), '')
    drops = re.findall(r'DROP \| reality_text=\"((?:[^\"\\\\]|\\\\.)*)\"', block)
    content = open(f).read()
    bad = [d for d in drops if d.encode().decode('unicode_escape') in content]
    if bad: print('FAIL drift in', f, ':', len(bad), 'rows'); sys.exit(1)
" || fail "R4 U2 drift check failed"
ok "R4 U2 drift (12 corpus files)"

# R4 U4: slugify trim
grep -q "cortex_command.common" skills/lifecycle/SKILL.md || fail "R4 U4 reference missing"
! grep -q "underscores become hyphens, not stripped" skills/lifecycle/SKILL.md || fail "R4 U4 verbose prose remains"
ok "R4 U4"

# R5: backlog/182 amendment
grep -q "metrics.py" backlog/182-*.md || fail "R5 metrics.py reference missing in 182"
ok "R5"

# R6: critical-review frontmatter symmetry
fm_count=$(awk '/^---$/{c++; if(c==2) exit} c==1' skills/critical-review/SKILL.md | grep -cE '^(argument-hint|inputs|outputs|preconditions):')
[ "$fm_count" -eq 4 ] || fail "R6 frontmatter fields count=$fm_count, expected 4"
! awk '/^---$/{c++; if(c==2) exit} c==1' skills/critical-review/SKILL.md | grep -q '^precondition_checks:' || fail "R6 precondition_checks should not be present"
ok "R6"

# R7: new backlog item for clarify-critic schema validator
python3 -c "
import json, sys
d = json.load(open('backlog/index.json'))
items = d if isinstance(d, list) else d.get('items', [])
matches = [i for i in items if 'clarify-critic' in i.get('title','').lower() and ('validator' in i.get('title','').lower() or 'schema' in i.get('title','').lower())]
sys.exit(0 if matches else 1)
" || fail "R7 new backlog item not in index"
ok "R7"

# Ticket-178 self-amendments
! grep -q "MUSTs retained with parser-cite" backlog/178-*.md || fail "178 line 94 not dropped"
! grep -q "documented evidence trail" backlog/178-*.md || fail "178 line 95 not dropped"
grep -q "softened to positive-routing per OQ3" backlog/178-*.md || fail "178 replacement line missing"
ok "178 self-amendments"

echo "ALL PASS"
