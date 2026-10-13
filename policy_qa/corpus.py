"""Load policy docs into clauses and decide which clauses are in force on a date.

Clause ids are ALWAYS taken verbatim from the document text. If a block has no
number in the source, its id is None and it is cited by heading only - we never
manufacture a clause number.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .parsing import find_dates

# Authority order used to resolve conflicts (higher wins). See DECISIONS.md.
AUTHORITY = {"circular": 3, "master": 2, "faq": 1}

_HEAD = re.compile(r"^\s*(#{1,6})\s*(.*)$")
_NUM = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?P<pre>(?:Clause|Section|Para(?:graph)?)\s+)?"
    r"(?P<id>\d+(?:\.\d+)*[A-Za-z]?)(?P<punct>[.):])?(?:\*\*)?\s+(?P<rest>.+)$", re.I)
_LETTER = re.compile(r"^\s*(?P<id>[A-Z])\.\s+(?P<rest>.+)$")   # circular items "A. ..."
_BOLDQ = re.compile(r"^\s*\*\*(?P<q>.+?)\*\*\s*$")             # FAQ "**question?**" (unnumbered)
_FAQ = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?P<id>Q\s*\d+)[.):]?(?:\*\*)?\s*(?P<rest>.*)$", re.I)

_REF = r"(?:clauses?|sections?|paras?(?:graphs?)?)\s+(\d+(?:\.\d+)*[A-Za-z]?)"
_ACTION_DEL = re.compile(r"\b(delet|omit|withdraw|rescind|revok|stand[s]? removed)", re.I)
_ACTION_AMEND = re.compile(r"\b(substitut|replac|amend|supersed|modif|revis|read as)", re.I)
_EFFECT = re.compile(r"(effective|w\.?e\.?f\.?|with effect|comes? into force|applicable from|from)", re.I)


@dataclass
class Clause:
    doc: str                 # file name
    kind: str                # master | circular | faq
    cid: str | None          # verbatim clause number, or None
    heading: str
    text: str
    effective: date | None = None
    amends: list = field(default_factory=list)   # [(target_cid, 'amend'|'delete')]
    refs: list = field(default_factory=list)     # cross-referenced clause ids

    @property
    def label(self):
        return f"{self.doc} clause {self.cid}" if self.cid else f"{self.doc} [{self.heading[:50]}] (no clause number)"

    def citation(self):
        return {"document": self.doc, "clause": self.cid, "heading": self.heading}


@dataclass
class Document:
    name: str
    kind: str
    effective: date | None
    clauses: list


def _kind(name):
    n = name.lower()
    if "circular" in n or "amend" in n:
        return "circular"
    if "faq" in n:
        return "faq"
    return "master"


def _effective_in(text):
    """First date that appears after an 'effective'-style phrase in the text."""
    for m in _EFFECT.finditer(text):
        ds = find_dates(text[m.start(): m.start() + 80])
        if ds:
            return ds[0][0]
    return None


def _is_clause_start(line):
    m = _NUM.match(line)
    if not m:
        return None
    is_heading = line.lstrip().startswith("#") or line.lstrip().startswith("**")
    cid = m.group("id")
    # Need a structural signal. "Clause 5.2 of the master policy is deleted" is a
    # sentence REFERRING to a clause, not the start of one (bug found in testing).
    if is_heading:
        return cid, m.group("rest").strip("* ").strip()
    if m.group("pre") and not m.group("punct"):
        return None
    if "." in cid or m.group("punct"):
        return cid, m.group("rest").strip("* ").strip()
    return None


def parse_document(path):
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    kind = _kind(path.name)
    lines = raw.splitlines()
    clauses, cur, preamble = [], None, []
    last_heading = ""
    for line in lines:
        start = None
        if kind == "faq":
            fm = _FAQ.match(line)
            if fm:
                start = (fm.group("id").replace(" ", ""), fm.group("rest").strip("* "))
        if kind == "faq" and start is None:
            bq = _BOLDQ.match(line)
            if bq:  # unnumbered FAQ entry: cid stays None, cited by question text
                if cur:
                    clauses.append(cur)
                cur = Clause(path.name, kind, None, bq.group("q").strip(), line)
                continue
        if kind == "circular" and start is None:
            lm = _LETTER.match(line)
            if lm:
                start = (lm.group("id"), lm.group("rest"))
        if start is None:
            start = _is_clause_start(line)
        if start:
            if cur:
                clauses.append(cur)
            cur = Clause(path.name, kind, start[0], start[1] or last_heading, line)
            continue
        h = _HEAD.match(line)
        if h:
            last_heading = h.group(2).strip()
            # un-numbered heading in FAQ -> own block, cited by heading only
            if kind == "faq":
                if cur:
                    clauses.append(cur)
                cur = Clause(path.name, kind, None, last_heading, line)
                continue
        if cur:
            cur.text += "\n" + line
        else:
            preamble.append(line)
    if cur:
        clauses.append(cur)

    clauses = [c for c in clauses if not (c.kind == "faq" and "\n" not in c.text.strip())]
    clauses = [c for c in clauses if "\n" in c.text.strip() or c.kind != "master" or not c.text.lstrip().startswith("#")]
    pre = "\n".join(preamble)
    doc_eff = _effective_in(pre) or _effective_in(raw[:1500])
    for c in clauses:
        c.text = c.text.strip()
        c.effective = _effective_in(c.text)
        for sent in re.split(r"(?<=[.;])\s+", c.text):
            targets = re.findall(_REF, sent, re.I)
            # bare refs like "subject to the cap in 2.3", "see 4.4" (not the clause's own id)
            bare = [t for t in re.findall(r"\b(?:in|see|under|per)\s+(\d+\.\d+)\b", sent, re.I) if t != c.cid]
            if not targets:
                c.refs += bare
                continue
            if kind == "circular" and (_ACTION_DEL.search(sent) or _ACTION_AMEND.search(sent)):
                act = "delete" if _ACTION_DEL.search(sent) else "amend"
                c.amends += [(t, act) for t in targets]
            else:
                c.refs += [t for t in targets if t != c.cid]
    doc = Document(path.name, kind, doc_eff, clauses)
    doc.head = raw[:300]
    return doc


class Corpus:
    def __init__(self, data_dir):
        self.docs = [parse_document(p) for p in sorted(Path(data_dir).glob("*.md"))]
        if not self.docs:
            raise FileNotFoundError(f"No .md policy files in {data_dir}")
        self.clauses = [c for d in self.docs for c in d.clauses]
        self._doc = {d.name: d for d in self.docs}

    def effective(self, c):
        return c.effective or self._doc[c.doc].effective

    def find(self, cid, kind=None):
        return [c for c in self.clauses if c.cid == cid and (kind is None or c.kind == kind)]

    def state(self, as_of):
        """Return dict: clause -> (status, reason). status in
        in_force | pending | superseded | deleted."""
        out = {}
        active_amendments = []
        for c in self.clauses:
            eff = self.effective(c)
            if eff and eff > as_of:
                out[id(c)] = ("pending", f"not effective until {eff.isoformat()}")
            else:
                out[id(c)] = ("in_force", f"effective {eff.isoformat()}" if eff else "no effective date stated")
                if c.kind == "circular":
                    active_amendments.append(c)
        for amender in active_amendments:
            for target, act in amender.amends:
                for t in self.find(target, "master"):
                    out[id(t)] = ("deleted" if act == "delete" else "superseded",
                                  f"{act}d by {amender.label} (effective {self.effective(amender)})")
        return out
