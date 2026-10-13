"""Plain BM25 keyword retrieval. Deterministic, offline, explainable."""
import math
import re
from collections import Counter

STOP = set("""a an the is are was were be been do does did of to in on for and or
what when how much many can could i my me we our they their it its this that with
by at from as will would should about any get gets pay paid say says""".split())

# Domain synonyms: question words -> policy vocabulary
SYN = {
    "receive": ["settlement", "settle", "credit"], "money": ["settlement", "funds"],
    "settle": ["settlement"], "settled": ["settlement"], "paid": ["settlement"],
    "refund": ["refund", "reversal"], "refunds": ["refund"], "back": ["reversal", "refund"],
    "fee": ["mdr", "charge"], "fees": ["mdr", "charge"], "charge": ["mdr"],
    "limit": ["limit", "cap", "maximum"], "twice": ["limit", "daily"], "day": ["daily"],
    "closed": ["closure", "close", "termination"], "close": ["closure"],
    "small": ["small"], "large": ["large"], "tax": ["gst"],
}


def stem(t):
    """Tiny suffix stripper: capped->cap, refunds->refund, settled->settl."""
    if len(t) <= 4 or t.isdigit():
        return t
    for suf in ("ing", "ed", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            t = t[: -len(suf)]
            break
    if len(t) > 3 and t[-1] == t[-2] and t[-1] not in "ls":
        t = t[:-1]  # capp -> cap
    return t


def tokens(text):
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


SYN = {stem(k): [stem(x) for x in v] for k, v in SYN.items()}


def expand(q_tokens):
    out = list(q_tokens)
    for t in q_tokens:
        out += SYN.get(t, [])
    return out


class BM25:
    def __init__(self, clauses, k1=1.4, b=0.75):
        self.clauses = clauses
        self.docs = [tokens(c.heading + " " + c.text) for c in clauses]
        self.avg = sum(map(len, self.docs)) / max(1, len(self.docs))
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]
        self.k1, self.b = k1, b
        self.vocab = set(df)

    def search(self, query, k=5):
        q = expand(tokens(query))
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
            if s > 0:
                scores.append((s, self.clauses[i]))
        scores.sort(key=lambda x: -x[0])
        return scores[:k]
