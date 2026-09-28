#!/usr/bin/env python3
"""story-series verifier — computes the countable (S) criteria of the stage-7 rubric.
Usage: python3 verify.py draft.md [more.md]
Every FAIL overrides the model's self-score for the matching criterion (see stage-7 §7.3.1)."""
import re, sys, json

PUNCT = r"[«»\"'\.،,:;!\?؟…\(\)\[\]\-–—/|⚡]"

def words(t):
    t = re.sub(r"\[\d+(?:\.\d+)?-\d+(?:\.\d+)?s?\]", " ", t)       # strip timecodes
    t = re.sub(r"^[^:«]{1,12}:", " ", t)                            # speaker label at start
    t = re.sub(r"(?<=\s)[^\s:«]{1,12}:(?=\s*«)", " ", t)            # inline speaker labels
    t = re.sub(PUNCT, " ", t)
    return [w for w in t.split() if w.strip() and w not in {"—", "-"}]

def parse_rows(block):
    rows = []
    for line in block.splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    return rows

def check(path):
    s = open(path, encoding="utf-8").read()
    res = []
    def add(name, ok, detail=""):
        res.append({"check": name, "pass": bool(ok), "detail": detail})

    # sections
    for n, key in [(1,"بریف اجرایی"),(2,"لاگ لوپ"),(3,"کتاب سریال"),(9,"فرض")]:
        add(f"section:{key}", key in s)
    presence = re.search(r"PRESENCE:\s*(\w+)", s)
    presence = presence.group(1) if presence else "?"
    add("presence-declared", presence in {"animation","on_camera","hybrid"}, presence)
    L = re.search(r"EP_LENGTH:\s*(\d+)", s); L = int(L.group(1)) if L else 60
    add("length-multiple-of-10", L % 10 == 0 and 40 <= L <= 90, str(L))

    EP = re.search(r"EPISODES:\s*(\d+)", s); EPISODES = int(EP.group(1)) if EP else 3
    types = []
    # episodes
    eps = re.split(r"\n## (?:[۰-۹0-9]+\. )?قسمت ([۰-۹0-9]+)", s)
    ep_blocks = {}
    for i in range(1, len(eps), 2):
        ep_blocks[eps[i]] = eps[i+1]
    add("episodes-found", len(ep_blocks) >= 1, str(list(ep_blocks)))
    for ep, blk in ep_blocks.items():
        tbl = blk.split("###")[1] if "###" in blk else blk
        rows = parse_rows(tbl)
        if not rows: add(f"E{ep}:table", False); continue
        hdr = rows[0]; data = [r for r in rows[1:] if re.match(r"C\d", r[0])]
        def col(name):
            for i,h in enumerate(hdr):
                if name in h: return i
            return None
        ivo, idl, ilb = col("VO"), col("دیالوگ"), col("برچسب")
        add(f"E{ep}:clip-count", len(data) == L//10, f"{len(data)} vs {L//10}")
        # labels
        if ilb is not None:
            labels = [r[ilb] for r in data]
            allowed = ["قلاب","درس","اوج","پشتیبان","داستان","پایان"]
            ok = all(any(k in x for k in allowed) for x in labels) and not any("LU" in x for x in labels)
            nstory = sum("داستان" in x for x in labels); npeak = sum("اوج" in x for x in labels)
            add(f"E{ep}:labels", ok and nstory <= 2 and npeak == 1, f"story={nstory} peak={npeak}")
            add(f"E{ep}:first=قلاب,last=پایان", "قلاب" in labels[0] and "پایان" in labels[-1])
        else:
            add(f"E{ep}:labels", False, "no label column")
        # word budgets
        worst = 0
        for k, r in enumerate(data):
            txt = (r[ivo] if ivo is not None else "") + " " + (r[idl] if idl is not None and idl != ivo else "")
            n = len(words(txt)); worst = max(worst, n)
            cap = 14 if (ilb is not None and "اوج" in r[ilb]) else 20
            add(f"E{ep}:{r[0]}:words<= {cap}", n <= cap, str(n))
            iw = col("کلمات")
            if iw is not None:
                try: declared = int(re.sub(r"[^0-9]","",r[iw].translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹","0123456789"))))
                except ValueError: declared = -99
                add(f"E{ep}:{r[0]}:declared-count", abs(declared - n) <= 1, f"declared={declared} counted={n}")
            else:
                add(f"E{ep}:count-column", False, "no کلمات column")
            # three beats non-empty
            beats = [r[col("[0-3]")], r[col("[3-7]")], r[col("[7-10]")]] if col("[0-3]") is not None else []
            add(f"E{ep}:{r[0]}:3-beats", len(beats)==3 and all(b not in {"", "—", "-"} for b in beats))
        # recap for E2+
        if ep not in {"1","۱"} and len(data) > 1 and ivo is not None:
            c2 = data[1][ivo]
            m = re.search(r"\[0-4\]\s*([^\[]+)", c2)
            rec = words(m.group(1)) if m else []
            add(f"E{ep}:recap<=9", m is not None and 0 < len(rec) <= 9, str(len(rec)))
        # silence in peak
        if ilb is not None:
            peak = [r for r in data if "اوج" in r[ilb]]
            add(f"E{ep}:peak-silence", bool(peak) and "سکوت" in " ".join(peak[0]))
        imd = col("رسانه")
        if presence == "hybrid":
            add(f"E{ep}:hybrid-single-medium", imd is not None and all(r[imd] in {"انیمیشن","دوربین"} for r in data))
            if imd is not None and data: add(f"E{ep}:hybrid-hook-animated", data[0][imd] == "انیمیشن")
        # ---- P1 loop ledger
        ilp = col("لوپ"); ipi = col("شکست")
        single = EPISODES == 1
        if ilp is None:
            add(f"E{ep}:loop-column", False, "no لوپ column")
        else:
            openl=set(); maxopen=0; bad=[]; carried=set()
            peak_i = next((k for k,r in enumerate(data) if ilb is not None and "اوج" in r[ilb]), len(data)-1)
            first_opens = re.findall(r"\+(Q\d+)", data[0][ilp]) if data else []
            if not first_opens: bad.append("hook opens no loop")
            for k,r in enumerate(data):
                for tok in r[ilp].split():
                    m=re.match(r"([+-])(Q\d+)(>?)$", tok)
                    if not m: continue
                    sign,q,car=m.groups()
                    if q=="Q0": continue
                    if sign=="+":
                        openl.add(q)
                        if car: carried.add(q)
                    else:
                        if q in openl: openl.discard(q)
                        else: bad.append(f"close-unopened {q}")
                ep_open = openl - carried
                maxopen=max(maxopen,len(ep_open))
                if 0 < k < peak_i and not openl: bad.append(f"no open loop at {r[0]}")
            left = openl - carried
            if left: bad.append(f"unclosed {sorted(left)}")
            if single and carried: bad.append("carry in single")
            if maxopen>2: bad.append(f"max open {maxopen}")
            add(f"E{ep}:P1-loops", not bad, ";".join(bad))
        # ---- P3 interrupt
        if ipi is None:
            add(f"E{ep}:interrupt-column", False)
        else:
            idx=[k for k,r in enumerate(data) if r[ipi] not in {"","—","-"}]
            n=len(data)
            ok = len(idx)==1 and n/3 <= idx[0] < 2*n/3
            types.append(data[idx[0]][ipi].split(":")[0].strip() if len(idx)==1 else "?")
            add(f"E{ep}:P3-interrupt-middle", ok, str(idx))
        # ---- P2 rhythm (narrator sentences)
        if ivo is not None:
            sents=[]; peak_sents=[]
            for k,r in enumerate(data):
                for seg in re.split(r"\[\d+(?:\.\d+)?-\d+(?:\.\d+)?s?\]", r[ivo]):
                    for sp in re.split(r"[\.؟\?!…]+", seg):
                        w=len(words(sp))
                        if w: sents.append(w); (peak_sents.append(w) if ilb is not None and "اوج" in r[ilb] else None)
            bad=[]
            if sents and sents[0] > 6: bad.append(f"first sentence {sents[0]}>6")
            if peak_sents and max(sents) > max(peak_sents)+2: bad.append(f"longest {max(sents)} > peak {max(peak_sents)}+2")
            for a in range(len(sents)-2):
                t=sents[a:a+3]
                if max(t)-min(t)<=1: bad.append(f"flat run {t}"); break
            add(f"E{ep}:P2-rhythm", not bad, ";".join(bad))
        # no stage names in episode text
        add(f"E{ep}:no-stage-leak", not re.search(r"مرحله ?[۰-۹]|Stage|stage-", blk))

    if len(types) > 1:
        add("P3-interrupt-varies", all(a!=b for a,b in zip(types,types[1:])), str(types))
    ot = re.search(r"نوع شروع قسمت‌ها:(.*)", s)
    otypes = [x.strip() for x in re.findall(r"E\d+\s+([^·\n]+)", ot.group(1))] if ot else []
    add("opening-types-listed", len(otypes) == len(ep_blocks), str(otypes))
    if len(otypes) > 1:
        add("opening-types-vary", all(a!=b for a,b in zip(otypes,otypes[1:])) and len(set(otypes)) >= min(len(otypes),4), str(otypes))
    # loop log
    log = s.split("لاگ لوپ",1)[1].split("\n## ",1)[0] if "لاگ لوپ" in s else ""
    rounds = [r for r in parse_rows(log) if re.match(r"^[0-9۰-۹]+$", r[0])]
    scores = []
    for r in rounds:
        m = re.search(r"(\d+(?:\.\d+)?)", r[1]); scores.append(float(m.group(1)) if m else 0)
    add("loop:>=2 rounds", len(rounds) >= 2, str(len(rounds)))
    OK = {"A":{0,.5,1},"B":{0,.5,1,1.5},"L":{0,.5,1,1.5,2},"D":{0,.5,1},"P":{0,.3,.4,.6,.7,1},"E":{0,.5,1,1.5},"F":{0,.5,1},"G":{0,.3,.4,.6,.7,1}}
    bad = []
    for r in rounds:
        try:
            vals = [float(re.sub(r"[^\d.]","",x)) for x in r[2:10]]
            tot = float(re.search(r"(\d+(?:\.\d+)?)", r[1]).group(1))
            for k,v in zip("ABLDPEFG", vals):
                if round(v,1) not in {round(x,1) for x in OK[k]}: bad.append(f"r{r[0]}:{k}={v}")
            if abs(sum(vals)-tot) > 0.05: bad.append(f"r{r[0]}:sum {sum(vals):.1f}!={tot}")
        except Exception as e: bad.append(f"r{r[0]}:parse")
    add("loop:scores-consistent", not bad, ",".join(bad))
    add("loop:final>9", bool(scores) and scores[-1] > 9.0, str(scores))
    add("loop:round1-G<=0.4", bool(rounds) and len(rounds[0]) > 9 and float(re.sub(r"[^\d.]","",rounds[0][9]) or 9) <= 0.4 if rounds else False)
    add("loop:monotonic-with-change", all(len(r) >= 12 and r[-1] not in {"", "…"} for r in rounds[1:]))
    # handoffs
    qc = re.search(r"QC شروع قسمت‌ها:(.*)", s)
    qcs = [int(x) for x in re.findall(r"(\d)/6", qc.group(1))] if qc else []
    add("qc-listed>=5", bool(qcs) and len(qcs) == len(ep_blocks) and min(qcs) >= 5, str(qcs))
    add("header-line", bool(re.search(r"PRESENCE:.*EPISODES:.*EP_LENGTH:", s)))
    if presence in {"animation","hybrid"}:
        add("omni:block-per-episode", len(re.findall(r"OMNI HANDOFF", s)) >= len(ep_blocks) and "به همین ترتیب" not in s, str(len(re.findall(r"OMNI HANDOFF", s))))
        add("omni:text-NONE", "On-screen text: NONE" in s)
        add("omni:lockup-NONE", "Brand lockup: NONE" in s)
        add("omni:no-narration", "NO narration" in s)
        add("ref-image-brief", "REFERENCE IMAGE BRIEF" in s)
    if presence in {"on_camera","hybrid"}:
        add("shoot-kit", "SHOOT KIT" in s)
        add("teleprompter", "تله‌پرامپتر" in s)
    add("publish-plan", "برنامه‌ی انتشار" in s)
    sec9 = s.split("## ۹.",1)[1] if "## ۹." in s else ""
    add("fact-tags-listed", ("[تأیید کارفرما]" in sec9) or ("موردی نیست" in sec9), "section 9")
    return res

if __name__ == "__main__":
    total = passed = 0
    report = {}
    for p in sys.argv[1:]:
        r = check(p); report[p] = r
        f = [x for x in r if not x["pass"]]
        total += len(r); passed += len(r) - len(f)
        print(f"\n== {p}: {len(r)-len(f)}/{len(r)} pass")
        for x in f: print("  FAIL", x["check"], x["detail"])
    print(f"\nTOTAL {passed}/{total} = {passed/total:.3f}")
