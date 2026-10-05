#!/bin/bash
# Hook: validate git commit messages before execution (PreToolUse).
set -euo pipefail

INPUT=$(cat)

# --- Command extraction ---
# Claude sends: {"tool_name": "Bash", "tool_input": {"command": "..."}}

TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only validate git commit commands from Bash tool
[[ "$TOOL" == "Bash" ]] || exit 0

# Cheap pre-filter; the parser below finds the real commit command (amend commits are skipped there)
[[ "$COMMAND" == *"commit"* ]] || exit 0

# --- Extract commit message ---

# Parse the shell text: only the message of the `git commit` command itself counts. A heredoc
# elsewhere in the command (a ticket note, a python script) is never read as the message. Handles
# -m/--message (quoted, heredoc, repeated), -F/--file (a file on disk, or one the same command writes
# from a heredoc, or `-F -` fed by a heredoc). Unparseable shell extracts nothing and is not validated.
extract_message() {
  command -v python3 >/dev/null 2>&1 || return 0
  CMD="$1" CWD="$2" python3 - <<'PY' || true
import os, re, shlex, sys

cmd = os.environ.get("CMD", "")
cwd = os.environ.get("CWD", "") or os.getcwd()

# 1. Lift heredoc bodies out, so their text is never read as shell and a marker token stands in.
bodies, out, lines, i = [], [], cmd.split("\n"), 0
marker = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
while i < len(lines):
    line, pending = lines[i], []
    def sub(m):
        pending.append((m.group(1) == "-", m.group(3)))
        bodies.append(None)
        return "<<__HD%d__" % (len(bodies) - 1)
    line = marker.sub(sub, line)
    out.append(line)
    i += 1
    first = len(bodies) - len(pending)
    for k, (dash, delim) in enumerate(pending):
        body = []
        while i < len(lines) and (lines[i].lstrip("\t") if dash else lines[i]).strip() != delim:
            body.append(lines[i].lstrip("\t") if dash else lines[i])
            i += 1
        i += 1
        bodies[first + k] = "\n".join(body)
skel = "\n".join(out)

try:
    lex = shlex.shlex(skel, posix=True, punctuation_chars=";&|()<>\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    toks = list(lex)
except ValueError:
    sys.exit(0)  # unparseable shell: do not guess a message

SEP = {";", "&&", "||", "|", "&", "\n", "(", ")", ";;", "|&"}

def heredoc_of(tok):
    m = re.search(r"__HD(\d+)__", tok)
    return bodies[int(m.group(1))] if m else None

# Files the same command writes from a heredoc: cat > f <<EOF / cat <<EOF > f.
written = {}
for j, t in enumerate(toks):
    if t in (">", ">>") and j + 1 < len(toks):
        seg = toks[max(0, j - 4): j + 5]
        for s in seg:
            if s.startswith("__HD"):
                written[toks[j + 1]] = heredoc_of(s)

# 2. Find the `git [global opts] commit` that starts a command, and its segment.
seg, j = None, 0
while j < len(toks):
    at_start = j == 0 or toks[j - 1] in SEP
    if at_start and toks[j] == "git":
        k = j + 1
        while k < len(toks) and toks[k].startswith("-"):
            k += 2 if toks[k] in ("-C", "-c", "--git-dir", "--work-tree") else 1
        if k < len(toks) and toks[k] == "commit":
            end = k + 1
            while end < len(toks) and toks[end] not in SEP:
                end += 1
            seg = toks[k + 1:end]
            break
    j += 1
if seg is None or "--amend" in seg:
    sys.exit(0)

def resolve(tok):
    hd = heredoc_of(tok)
    if hd is not None:
        return hd
    return tok

msgs, files, n = [], [], 0
while n < len(seg):
    t = seg[n]
    val = None
    if t in ("-m", "--message", "-F", "--file") and n + 1 < len(seg):
        val, kind = seg[n + 1], t
        n += 1
    elif t.startswith("--message="):
        val, kind = t.split("=", 1)[1], "-m"
    elif t.startswith("--file="):
        val, kind = t.split("=", 1)[1], "-F"
    elif re.fullmatch(r"-[a-zA-Z]*[mF]", t) and n + 1 < len(seg):
        val, kind = seg[n + 1], "-" + t[-1]
        n += 1
    elif re.fullmatch(r"-[a-zA-Z]*[mF].+", t):
        idx = re.match(r"-[a-zA-Z]*?[mF]", t).end()
        val, kind = t[idx:], "-" + t[idx - 1]
    n += 1
    if val is None:
        continue
    if kind in ("-m", "--message"):
        msgs.append(resolve(val))
    else:
        files.append(val)

if not msgs and files:
    f = files[0]
    if f in written:
        msgs.append(written[f])
    elif f == "-":
        msgs.extend(heredoc_of(s) for s in seg if heredoc_of(s) is not None)
    elif f != "-":
        p = f if os.path.isabs(f) else os.path.join(cwd, f)
        try:
            text = open(p).read()
            msgs.append("\n".join(l for l in text.split("\n") if not l.startswith("#")))
        except OSError:
            pass

msg = "\n\n".join(m.strip("\n") for m in msgs if m is not None)
sys.stdout.write(msg.strip("\n"))
PY
}

CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
MESSAGE=$(extract_message "$COMMAND" "$CWD")

# No message extracted — not a format we validate
[[ -n "$MESSAGE" ]] || exit 0

SUBJECT=$(echo "$MESSAGE" | head -n1)
ERRORS=()

# --- Validation rules ---

# 1. Subject must start with a capital letter
if [[ ! "$SUBJECT" =~ ^[A-Z] ]]; then
  ERRORS+=("Subject must start with a capital letter")
fi

# 2. No trailing period on subject
if [[ "$SUBJECT" =~ \.$ ]]; then
  ERRORS+=("Subject must not end with a period")
fi

# 4. Subject must be meaningful (at least 10 chars)
if (( ${#SUBJECT} < 10 )); then
  ERRORS+=("Subject too short — provide a meaningful description (≥10 chars)")
fi

# 5. Must use imperative mood (reject past tense openers)
LOWER_SUBJECT=$(echo "$SUBJECT" | tr '[:upper:]' '[:lower:]')
PAST_TENSE_RE='^(added|fixed|removed|updated|changed|modified|improved|merged|moved|renamed|deleted|refactored|cleaned|bumped) '
if [[ "$LOWER_SUBJECT" =~ $PAST_TENSE_RE ]]; then
  VERB=$(echo "$LOWER_SUBJECT" | awk '{print $1}')
  ERRORS+=("Use imperative mood ('Add' not 'Added') — found '$VERB'")
fi

# 6. Body must be separated from subject by a blank line
LINE_COUNT=$(echo "$MESSAGE" | wc -l | tr -d ' ')
if (( LINE_COUNT > 1 )); then
  SECOND_LINE=$(echo "$MESSAGE" | sed -n '2p')
  if [[ -n "$SECOND_LINE" ]]; then
    ERRORS+=("Body must be separated from subject by a blank line")
  fi
fi

# --- Output (agent-specific format) ---

if (( ${#ERRORS[@]} > 0 )); then
  REASON=$(printf "• %s\n" "${ERRORS[@]}")

  jq -n --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: ("Commit message validation failed:\n" + $reason)
    }
  }'
else
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow"
    }
  }'
fi

exit 0
