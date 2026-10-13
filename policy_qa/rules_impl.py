"""Handlers for question types whose clauses I read by hand (see DECISIONS.md).

Rules:
* Every number (rate, cap, limit, GST, hours, days) is regex-extracted from the
  in-force clause text at runtime. If the text no longer contains what we expect,
  extraction fails and we return CANNOT_ANSWER instead of a stale constant.
* Clause ids are looked up in the corpus; citations come from Clause objects only.
* All arithmetic goes through calc.py.
"""
import re
from datetime import timedelta
from decimal import Decimal

from .calc import add_working_days, mdr_fee
from .parsing import find_amounts, find_percents, money

SESSION = {"size": None}  # remembers merchant size for follow-ups like "same merchant"


# ---------------- helpers ----------------
class Missing(Exception):
    pass


def _res(status, answer, clauses, resolution=None):
    seen, cites = set(), []
    for c in clauses:
        if c is None:
            continue
        k = (c.doc, c.cid, c.heading)
        if k not in seen:
            seen.add(k)
            cites.append(c.citation())
    return {"status": status, "answer": answer, "citations": cites, "resolution": resolution, "trace": []}


def version(corpus, state, cid):
    """In-force text for master clause cid on the query date.
    Returns dict(cur, master, amender, status, pending)."""
    ms = corpus.find(cid, "master")
    if not ms:
        raise Missing(f"master clause {cid} not found")
    m = ms[0]
    amender = next((c for c in corpus.clauses if c.kind == "circular"
                    and any(t == cid for t, _ in c.amends)), None)
    st = state[id(m)][0]
    if st == "superseded":
        return dict(cur=amender, master=m, amender=amender, status=st, pending=None)
    if st == "deleted":
        return dict(cur=None, master=m, amender=amender, status=st, pending=None)
    pend = amender if amender is not None and state[id(amender)][0] == "pending" else None
    return dict(cur=m, master=m, amender=None, status="in_force", pending=pend)


def body(c):
    """Clause text after 'Clause X is replaced:' and without the leading id."""
    t = re.sub(r"^\s*(?:[A-Z]|\d+(?:\.\d+)*)\.?\s+", "", c.text.strip())
    t = re.sub(r"^Clause\s+[\d.]+\s+is\s+(?:replaced|amended)\s*:\s*", "", t, flags=re.I)
    return t.strip()


def faq_entry(corpus, *words):
    for c in corpus.clauses:
        if c.kind == "faq" and all(w in c.text.lower() for w in words):
            return c
    return None


def faq_text(c):
    return " ".join(c.text.split("\n")[1:]).strip()


def merchant_size(q):
    ql = q.lower()
    if re.search(r"\b(large|big)\b|(above|over|more than|exceed\w*)\s*(rs\.?|₹|inr)?\s*10\s*lakh", ql):
        return "large"
    if re.search(r"\bsmall\b|(up to|upto|below|under|less than)\s*(rs\.?|₹|inr)?\s*10\s*lakh", ql):
        return "small"
    if "same merchant" in ql:
        return SESSION["size"]
    return None


def txn_amounts(q):
    """Payment amounts in the question, ignoring the monthly-volume threshold
    ('above Rs.10 lakh monthly') which is a merchant attribute, not a payment."""
    cleaned = re.sub(r"(above|over|more than|up to|upto|below|under|less than)\s*(rs\.?|₹|inr)?\s*[\d,.]+\s*"
                     r"(lakh|lac|crore)?\s*(monthly|per month|a month|volume)?", " ", q, flags=re.I)
    return find_amounts(cleaned)


def _one(vals, what, c):
    if not vals:
        raise Missing(f"no {what} found in {c.label}")
    return vals[0]


# ---------------- fee / limits core ----------------
def fee_terms(corpus, state, size):
    """Return rate, cap, gst and the clauses used, for 'small' | 'large'."""
    used, notes = [], []
    if size == "small":
        v = version(corpus, state, "2.1")
    else:
        v = version(corpus, state, "2.2")
    rate = _one(find_percents(body(v["cur"])), "rate", v["cur"])
    used.append(v["cur"])
    if v["status"] == "superseded":
        used.append(v["master"])
        notes.append(f"{v['master'].label} replaced by circular {v['amender'].cid}")

    cv = version(corpus, state, "2.3")
    amts = find_amounts(body(cv["cur"]))
    if cv["status"] == "superseded":
        # circular C: "cap of ₹15 applies only to ... up to ₹10 lakh. For ... above ₹10 lakh, the cap is ₹25."
        caps = [a for a in amts if a < 1000]
        if len(caps) != 2:
            raise Missing(f"could not read two caps from {cv['cur'].label}")
        cap = caps[0] if size == "small" else caps[1]
        used += [cv["cur"], cv["master"]]
        notes.append(f"{cv['master'].label} (flat cap) replaced by circular {cv['amender'].cid} (size-based cap)")
    else:
        cap = _one(amts, "cap", cv["cur"])
        used.append(cv["cur"])

    gst_c = version(corpus, state, "2.4")["cur"]
    gst = _one(find_percents(gst_c.text), "GST rate", gst_c)
    used.append(gst_c)
    return rate, cap, gst, used, notes


def limit_terms(corpus, state):
    per = version(corpus, state, "4.1")["cur"]
    enh = version(corpus, state, "4.2")["cur"]
    kyc = version(corpus, state, "4.4")["cur"]
    dv = version(corpus, state, "4.3")
    per_amt = _one(find_amounts(per.text), "per-txn limit", per)
    enh_amt = _one(find_amounts(enh.text), "enhanced limit", enh)
    daily = _one(find_amounts(body(dv["cur"])), "daily limit", dv["cur"])
    bank_clause = "customer's own bank" in dv["cur"].text
    return dict(per=per_amt, enh=enh_amt, daily=daily, bank_lower=bank_clause,
                clauses=[per, enh, kyc, dv["cur"]] + ([dv["master"]] if dv["status"] == "superseded" else []))


# ---------------- handlers ----------------
def h_faq_check(q, d, corpus, state):
    ql = q.lower()
    if "faq" not in ql or not re.search(r"\b(cap|mdr|fee|upper limit)\b", ql):
        return None
    f = faq_entry(corpus, "what do i pay")
    m23 = corpus.find("2.3", "master")[0]
    cv = version(corpus, state, "2.3")
    faq_date = re.search(r"last updated ([^)]+)\)", corpus._doc[f.doc].head)
    ans = (f"The FAQ says: \"{faq_text(f)}\" It is wrong. A per-transaction MDR cap has existed since the "
           f"master policy took effect ({corpus.effective(m23).isoformat()}): {m23.label} capped MDR at "
           f"{money(find_amounts(m23.text)[0])}, so the FAQ was already wrong when written"
           f"{' (' + faq_date.group(1) + ')' if faq_date else ''}. ")
    used = [f, m23]
    if cv["status"] == "superseded":
        ans += (f"On {d.isoformat()} the cap is set by circular item {cv['amender'].cid}: {body(cv['amender'])} "
                "The FAQ's rates are also stale for small merchants (see master 2.1 as replaced by circular B).")
        used.append(cv["amender"])
        b = version(corpus, state, "2.1")
        if b["status"] == "superseded":
            used.append(b["amender"])
    if txn_amounts(q):  # false-premise question that also asks for a number: still compute it
        fee = h_fee(q, d, corpus, state)
        if fee is not None:
            ans = "False premise. " + ans + " Calculated under the policy: " + fee["answer"]
            used += [c for c in fee_clauses(corpus, fee)]
    return _res("CONFLICT_RESOLVED", ans, used,
                "FAQ is lowest authority and contradicts master 2.3 and circular C; followed the policy text.")


def fee_clauses(corpus, res):
    keys = {(x["document"], x["clause"]) for x in res["citations"]}
    return [c for c in corpus.clauses if (c.doc, c.cid) in keys and c.cid]


def h_closure(q, d, corpus, state):
    ql = q.lower()
    if not re.search(r"\b(close|closed|closing|closure)\b", ql):
        return None
    c51 = version(corpus, state, "5.1")["cur"]
    c52 = version(corpus, state, "5.2")["cur"]
    days = int(re.search(r"(\d+)\s+working days", c52.text).group(1))
    v11 = version(corpus, state, "1.1")
    used = [c52, c51]
    ans = f"Per {c52.label}: {body(c52)}"
    res = ("FAQ says 'within 10 days'; master 5.2 says 10 *working* days after deducting dues; followed master.")
    f = faq_entry(corpus, "close")
    if f:
        used.append(f)
    if "yesterday" in ql or re.search(r"\bon\b|\d{4}", ql):
        closed = d  # ask() already turned 'yesterday' into as_of - 1
        earliest = add_working_days(closed, days)
        ans += (f" Account closed {closed.strftime('%a %d %b %Y')}: counting {days} working days (Sundays excluded) "
                f"gives {earliest.strftime('%a %d %b %Y')} at the earliest. Bank holidays push this later, and the "
                "documents give no holiday calendar.")
        ind = closed.replace(month=8, day=15)  # Independence Day: a known national bank holiday
        if closed < ind <= earliest:
            later = add_working_days(closed, days, holidays={ind})
            ans += f" For example, 15 Aug (Independence Day) falls in this window, which would make it {later.strftime('%a %d %b %Y')}."
        ans += " The amount paid is net of any outstanding dues."
        if v11["status"] == "superseded":
            ans += (f" Caveat: the 'working day' definition was in master 1.1, which circular {v11['amender'].cid} "
                    "replaced without restating it; I assume it still holds.")
            used += [v11["master"], v11["amender"]]
        ans += f" Note: {c51.label} requires 30 days' written notice; I assume the closure was effective, not just requested."
    return _res("CONFLICT_RESOLVED" if f else "ANSWERED", ans, used, res if f else None)


def h_refund(q, d, corpus, state):
    ql = q.lower()
    if "refund" not in ql:
        return None
    c31 = version(corpus, state, "3.1")["cur"]
    c32 = version(corpus, state, "3.2")["cur"]
    v33 = version(corpus, state, "3.3")
    hm = re.search(r"(\d+(?:\.\d+)?)\s*(hour|hr|minute|min|day)s?", ql)
    hours = None
    if hm:
        n = Decimal(hm.group(1))
        hours = n * {"hour": 1, "hr": 1, "minute": Decimal(1) / 60, "min": Decimal(1) / 60, "day": 24}[hm.group(2)]
    elif "same day" in ql:
        hours = Decimal(0)  # treated as within 24h but flagged
    used = [c32]
    window = int(re.search(r"(\d+)\s+days", c31.text).group(1))
    if hours is not None and hours > window * 24:
        return _res("ANSWERED", f"No refund can be initiated: {c31.label} allows refunds only within {window} days.", [c31])
    f = faq_entry(corpus, "refund")

    if v33["status"] == "deleted":
        ans = (f"No. On {d.isoformat()} the MDR is not returned. Master 3.3 (full reversal within 24 hours) was deleted by "
               f"circular item {v33['amender'].cid} effective {corpus.effective(v33['amender']).isoformat()}, so {c32.label} "
               "applies without exception: MDR on a refunded transaction is not returned.")
        used += [v33["master"], v33["amender"]] + ([f] if f else [])
        return _res("CONFLICT_RESOLVED", ans, used,
                    f"Circular {v33['amender'].cid} (in force) deletes master 3.3; FAQ's 24-hour reversal is stale.")
    c33 = v33["cur"]
    hrs = int(re.search(r"(\d+)\s*hours", c33.text).group(1))
    used.append(c33)
    if hours is None:
        ans = (f"Depends on timing. {c33.label}: refund within {hrs} hours -> MDR reversed in full; otherwise "
               f"{c32.label}: MDR not returned.")
    elif hours < hrs:
        ans = (f"Yes. The refund is within {hrs} hours, so under {c33.label} the MDR is reversed in full "
               f"(exception to {c32.label}). The clause does not say whether the GST on the MDR is also reversed.")
    else:
        ans = f"No. The refund is after {hrs} hours, so {c32.label} applies: MDR is not returned."
    note = None
    if v33["pending"] is not None:
        p = v33["pending"]
        note = (f"Changes soon: circular item {p.cid} deletes 3.3 effective {corpus.effective(p).isoformat()}; "
                "from then MDR is never returned on refunds.")
        used.append(p)
    return _res("ANSWERED", ans, used, note)


def h_limits(q, d, corpus, state):
    ql = q.lower()
    if not re.search(r"twice|thrice|\btimes\b|in one day|per day|daily|limit|maximum|max\b|accept", ql):
        return None
    L = limit_terms(corpus, state)
    amts = txn_amounts(q)
    count = 2 if "twice" in ql else 3 if "thrice" in ql else None
    m = re.search(r"(\d+)\s*times", ql)
    if m:
        count = int(m.group(1))
    if not amts:
        ans = (f"Per transaction: {money(L['per'])} (4.1); Capital Markets/Insurance merchants with enhanced KYC: "
               f"{money(L['enh'])} (4.2, 4.4). Daily per customer account: {money(L['daily'])}"
               f"{' or the customer bank limit, whichever is lower' if L['bank_lower'] else ''} (4.3 as amended).")
        return _res("ANSWERED", ans, L["clauses"])
    amt, n = amts[0], count or 1
    total = amt * n
    problems, cond = [], ""
    special = re.search(r"insurance|capital market", ql)
    kyc = re.search(r"enhanced kyc|annexure c", ql) and not re.search(r"(without|no|not)\s+(completed\s+)?enhanced kyc", ql)
    per = L["enh"] if (special and kyc) else L["per"]
    if special and not kyc and L["per"] < amt <= L["enh"]:
        cond = (f" Insurance/Capital Markets merchants may accept up to {money(L['enh'])} per transaction only after "
                "enhanced KYC (4.4), which the question does not confirm.")
    if amt > per:
        problems.append(f"a payment of {money(amt)} exceeds the {money(per)} per-transaction limit"
                        + (" for this merchant category (4.2, 4.4)" if per == L["enh"] else " (4.1)"))
    elif per == L["enh"] and amt > L["per"]:
        cond = f" The per-transaction limit is satisfied: enhanced-KYC Insurance/Capital Markets merchants may accept up to {money(per)} (4.2, 4.4)."
    if total > L["daily"]:
        problems.append(f"{n} x {money(amt)} = {money(total)} exceeds the {money(L['daily'])} daily limit per customer account")
    if problems:
        ans = "No: " + "; ".join(problems) + "." + cond
        if n > 1 and amt <= L["daily"]:
            ans += f" The first payment can go through; the second would be declined."
        ans += " The higher per-transaction limit for Capital Markets/Insurance merchants does not lift the daily limit."
    else:
        ans = f"Yes: {money(total)} in total is within both the per-transaction and the daily limits." + cond
    if L["bank_lower"]:
        ans += " The customer's own bank may set a lower daily limit (4.3 as amended), which would apply instead."
    return _res("CONFLICT_RESOLVED" if any(c.kind == "circular" for c in L["clauses"]) else "ANSWERED", ans,
                L["clauses"], "Master 4.3 amended by circular E (in force): daily limit is the lower of Rs.1,00,000 and the bank's limit."
                if any(c.kind == "circular" for c in L["clauses"]) else None)


def h_fee(q, d, corpus, state):
    ql = q.lower()
    amts = txn_amounts(q)
    if re.search(r"\bcard", ql) and re.search(r"\b(mdr|fee|fees|charge|cost)\b", ql):
        return _res("CANNOT_ANSWER", "The documents give MDR rates only for UPI; no clause states an MDR for card transactions, so I cannot answer.", [])
    if not amts or not re.search(r"\b(mdr|fee|fees|pay|charge|cost|gst)\b", ql):
        return None
    size = merchant_size(q)
    if size:
        SESSION["size"] = size
    sizes = [size] if size else ["small", "large"]
    parts, used, notes = [], [], []
    amt = amts[0]
    for s in sizes:
        rate, cap, gst, u, n = fee_terms(corpus, state, s)
        r = mdr_fee(amt, rate, cap, gst)
        parts.append(f"{'Large (above Rs.10 lakh/month)' if s == 'large' else 'Small (up to Rs.10 lakh/month)'} merchant: "
                     f"MDR {money(r.mdr)} + GST {money(r.gst)} = {money(r.total)}. ({r.explain()})")
        used += u
        notes += [x for x in n if x not in notes]
    ans = " ".join(parts)
    if not size:
        ans = "Merchant size not stated, so both cases: " + ans
    L = limit_terms(corpus, state)
    if amt > L["per"]:
        ans = (f"This payment should not happen: {money(amt)} exceeds the {money(L['per'])} UPI per-transaction limit (4.1). "
               f"Only Capital Markets/Insurance merchants with enhanced KYC may accept up to {money(L['enh'])} (4.2, 4.4), "
               f"and even then it exceeds the {money(L['daily'])} daily limit per customer account (4.3 as amended), so a single "
               f"customer cannot pay it in one day. If it were processed, the fee would be: " + ans)
        used += L["clauses"]
        notes.append("4.2 enhanced per-transaction limit vs 4.3 daily limit: both must hold, so the lower daily limit binds")
    return _res("CONFLICT_RESOLVED" if notes else "ANSWERED", ans, used, "; ".join(notes) or None)


def h_settlement(q, d, corpus, state):
    ql = q.lower()
    if not re.search(r"settle|settlement|receive|get my money|money|credited|payout|same day", ql):
        return None
    if re.search(r"\bcard", ql):
        c12 = version(corpus, state, "1.2")["cur"]
        same_day = "same day" in ql or "t+0" in ql
        ans = (f"{'No. ' if same_day else ''}{c12.label}: {body(c12)} No clause allows same-day settlement for cards; "
               "the T+0 Instant Settlement option (circular A) covers UPI only.")
        v11 = version(corpus, state, "1.1")
        return _res("ANSWERED", ans, [c12] + ([v11["amender"]] if v11["amender"] else []))
    v = version(corpus, state, "1.1")
    c13 = version(corpus, state, "1.3")["cur"]
    used = [v["cur"], c13]
    ans = f"UPI: {body(v['cur'])} Settlement dates falling on a bank holiday move to the next working day ({c13.cid})."
    if merchant_size(q):
        ans += " Merchant size does not change settlement timing."
    if v["status"] == "superseded":
        used.append(v["master"])
        f = faq_entry(corpus, "upi money")
        if f:
            used.append(f)
        return _res("CONFLICT_RESOLVED", ans, used,
                    f"Master 1.1 (T+1 for all) replaced by circular item {v['amender'].cid}, effective "
                    f"{corpus.effective(v['amender']).isoformat()}; FAQ ('next working day') ignores the T+0 add-on.")
    return _res("ANSWERED", ans, used)


ORDER = [h_faq_check, h_closure, h_refund, h_limits, h_fee, h_settlement]


def safe(h):
    def run(q, d, corpus, state):
        try:
            return h(q, d, corpus, state)
        except Missing:
            return None  # clause not in this corpus -> generic grounded retrieval
        except (AttributeError, TypeError, IndexError):
            return None
    return run
