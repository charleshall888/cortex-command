import json, glob, os
# CORRECTED pricing per Mtok (Opus 4.8 = $5/$25; Sonnet 5 = $3/$15)
# cache write: 1.25x input (5m TTL), 2x input (1h TTL). cache read: 0.1x input.
PRICE = {
  "opus":   dict(inp=5.0, out=25.0, cw5=6.25, cw1h=10.00, cr=0.50),
  "sonnet": dict(inp=3.0, out=15.0, cw5=3.75, cw1h=6.00,  cr=0.30),
  "haiku":  dict(inp=1.0, out=5.0,  cw5=1.25, cw1h=2.00,  cr=0.10),
}
def fam(m):
    m=(m or "").lower()
    for k in PRICE:
        if k in m: return k
    return "opus"
def cost(u, model):
    p=PRICE[fam(model)]
    cc=u.get("cache_creation") or {}
    w1h=cc.get("ephemeral_1h_input_tokens",0); w5=cc.get("ephemeral_5m_input_tokens",0)
    if not (w1h or w5):   # fall back if breakdown absent
        w1h=u.get("cache_creation_input_tokens",0)
    return (u.get("input_tokens",0)*p["inp"] + u.get("output_tokens",0)*p["out"]
            + w1h*p["cw1h"] + w5*p["cw5"]
            + u.get("cache_read_input_tokens",0)*p["cr"]) / 1e6
def scan(path):
    seen={}
    try: f=open(path,errors="ignore")
    except: return []
    for line in f:
        try: d=json.loads(line)
        except: continue
        if d.get("type")!="assistant": continue
        m=d.get("message",{}); u=m.get("usage")
        if not u: continue
        mid=m.get("id") or d.get("requestId") or d.get("uuid")
        if mid in seen: continue
        seen[mid]=dict(model=m.get("model"),usage=u,skill=d.get("attributionSkill"),cost=cost(u,m.get("model")))
    return list(seen.values())
