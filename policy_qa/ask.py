"""ask(question, as_of_date) -> {answer, citations, status, resolution, trace}

Pipeline:
 1. Resolve the effective date (a date inside the question beats as_of_date;
    'yesterday'/'today' are relative to as_of_date).
 2. Scope check: if the question is about something the corpus never mentions
    (e.g. card payments), return CANNOT_ANSWER rather than reuse a UPI rule.
 3. Specific rule handlers (rules.py) get first try - these encode clauses we have
    read by hand and contain all arithmetic paths.
 4. Generic fallback: BM25 over all clauses, annotate each hit with its state on
    the date (in_force / pending / superseded / deleted), resolve by authority
    (in-force circular > master > FAQ) and report any conflict.
"""
import re
from datetime import date, timedelta
from pathlib import Path

from .corpus import AUTHORITY, Corpus
from .parsing import find_amounts, find_dates, parse_date
from .retrieve import BM25, tokens

DEFAULT_AS_OF = date(2026, 8, 15)
DATA_DIR = Path(__file__).resolve().parent.parent / "ai-2-data"
MIN_SCORE = 2.0  # below this, retrieval is treated as "no relevant clause"

# Payment instruments / topics. If the question names one and the corpus never
# mentions it, the docs cannot answer it.
SCOPE_TERMS = {
    "card": ["card", "cards", "credit", "debit"], "credit card": ["credit"],
    "neft": ["neft"], "rtgs": ["rtgs"], "imps": ["imps"], "wallet": ["wallet"],
    "cheque": ["cheque"], "international": ["international", "forex", "foreign"],
    "emi": ["emi"], "crypto": ["crypto"], "chargeback": ["chargeback"],
}

_corpus = None
_index = None


def load(data_dir=DATA_DIR):
    global _corpus, _index
    _corpus = Corpus(data_dir)
    _index = BM25(_corpus.clauses)
    return _corpus


def _resolve_date(question, as_of):
    q = question.lower()
    if "yesterday" in q:
        return as_of - timedelta(days=1), "'yesterday' taken relative to as_of_date"
    found = find_dates(question)
    if found:
        return found[0][0], "date stated in the question overrides as_of_date"
    return as_of, None


def _out_of_scope(question, vocab):
    qt = set(tokens(question))
    for topic, words in SCOPE_TERMS.items():
        if qt & set(words) and not (set(words) & vocab):
            return topic
    return None


def _result(status, answer, clauses=(), resolution=None, trace=None):
    seen, cites = set(), []
    for c in clauses:
        key = (c.doc, c.cid, c.heading)
        if key not in seen:
            seen.add(key)
            cites.append(c.citation())
    return {"status": status, "answer": answer, "citations": cites,
            "resolution": resolution, "trace": trace or []}


def _best_sentences(clause, question, n=2):
    qt = set(tokens(question))
    body = clause.text.split("\n", 1)[1] if "\n" in clause.text else clause.text
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", body) if len(s.strip()) > 3]
    sents = [re.sub(r"^[#*\s]+", "", s) for s in sents]
    ranked = sorted(sents, key=lambda s: -len(qt & set(tokens(s))))
    return " ".join(ranked[:n])


def _facts(c):
    """Numeric facts in a clause: percentages, rupee amounts, T+n, hours/days."""
    t = c.text.lower()
    f = {f"{p}%" for p in re.findall(r"(\d+(?:\.\d+)?)\s*%", t)}
    f |= {f"t+{n}" for n in re.findall(r"t\s*\+\s*(\d+)", t)}
    f |= {f"{n}{u[0]}" for n, u in re.findall(r"(\d+)\s*(hours?|days?)", t)}
    f |= {str(a) for a in find_amounts(t)}
    return f


def _numbers_disagree(a, b):
    fa, fb = _facts(a), _facts(b)
    return bool(fa and fb and fa - fb)


def ask(question, as_of_date=None, data_dir=None):
    if _corpus is None or data_dir:
        load(data_dir or DATA_DIR)
    as_of = parse_date(as_of_date) if as_of_date else DEFAULT_AS_OF
    eff_date, date_note = _resolve_date(question, as_of)
    trace = [f"as_of={as_of.isoformat()} effective_query_date={eff_date.isoformat()}"]
    if date_note:
        trace.append(date_note)

    topic = _out_of_scope(question, _index.vocab)
    if topic:
        return _result("CANNOT_ANSWER",
                       f"The policy documents do not mention {topic} at all, so they cannot answer this. "
                       "Applying a rule written for another payment type would be a guess.", trace=trace)

    state = _corpus.state(eff_date)

    from . import rules  # handlers for clauses we have read and verified by hand
    for handler in rules.HANDLERS:
        res = handler(question, eff_date, _corpus, state)
        if res is not None:
            res["trace"] = trace + res.get("trace", [])
            return res

    hits = _index.search(question, k=6)
    if not hits or hits[0][0] < MIN_SCORE:
        return _result("CANNOT_ANSWER", "No clause in the documents addresses this question.", trace=trace)

    for s, c in hits:
        st, why = state[id(c)]
        trace.append(f"hit {c.label} score={s:.2f} state={st} ({why})")

    top = hits[0][0]
    relevant = [(s, c) for s, c in hits if s >= 0.5 * top]
    live = [(s, c) for s, c in relevant if state[id(c)][0] == "in_force"]
    dead = [(s, c) for s, c in relevant if state[id(c)][0] != "in_force"]

    # Authoritative (non-FAQ) in-force clauses get a lower bar: the FAQ often
    # phrases things the way users ask, so it can out-score the real rule.
    for s, c in hits:
        if (s, c) not in live and c.kind != "faq" and s >= MIN_SCORE and state[id(c)][0] == "in_force":
            live.append((s, c))

    if not live:
        c = dead[0][1]
        st, why = state[id(c)]
        amenders = [a for a in _corpus.clauses if a.kind == "circular" and any(t == c.cid for t, _ in a.amends)]
        if st == "deleted":
            return _result("CONFLICT_RESOLVED",
                           f"No provision in force on {eff_date.isoformat()} covers this. {c.label} used to say: "
                           f"\"{_best_sentences(c, question)}\" but it was {why}.", [c] + amenders,
                           resolution=f"{c.label} deleted; deletion followed because the circular is in force.",
                           trace=trace)
        return _result("CANNOT_ANSWER",
                       f"The only relevant provision ({c.label}) is {st} on {eff_date.isoformat()}: {why}.",
                       [c] + amenders, trace=trace)

    # authority first, then retrieval score
    live.sort(key=lambda x: (-AUTHORITY[x[1].kind], -x[0]))
    winner = live[0][1]
    answer = _best_sentences(winner, question)
    used = [winner] + [c for c in _corpus.clauses if c.cid in winner.refs and c.doc == winner.doc]

    disagree = [c for _, c in live[1:]
                if AUTHORITY[c.kind] < AUTHORITY[winner.kind] and _numbers_disagree(c, winner)]
    agree = [c for _, c in live[1:] if c not in disagree and AUTHORITY[c.kind] < AUTHORITY[winner.kind]
             and _facts(c) and _facts(c) <= _facts(winner)]
    used += agree
    pending = [c for _, c in dead if state[id(c)][0] == "pending"]
    losers = [c for _, c in dead if state[id(c)][0] != "pending"] + disagree
    note = None
    if pending:
        note = "Not yet in force on this date: " + "; ".join(
            f"{c.label} ({state[id(c)][1]})" for c in pending) + ". The answer may change after that date."
    if losers:
        notes = []
        for c in losers:
            st, why = state[id(c)]
            if st != "in_force":
                notes.append(f"{c.label} is {st} ({why})")
            else:
                notes.append(f"{c.label} ({c.kind}) is lower authority than {winner.label}")
        return _result("CONFLICT_RESOLVED", answer, used + losers,
                       resolution="; ".join(notes) + f". Followed {winner.label}.", trace=trace)
    return _result("ANSWERED", answer, used, resolution=note, trace=trace)
