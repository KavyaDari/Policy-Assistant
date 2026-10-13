"""Deterministic parsing of dates and Indian money amounts. No LLM involved."""
import re
from datetime import date
from decimal import Decimal

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_PATTERNS = [
    # 1 September 2026 / 1st Sept, 2026
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MON + r"\.?,?\s+(\d{4})\b", re.I), "dmy"),
    # September 1, 2026
    (re.compile(r"\b" + _MON + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I), "mdy"),
    # 2026-09-01
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    # 01/09/2026 or 01-09-2026 -> Indian convention DD/MM/YYYY (see DECISIONS.md)
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"), "dmy_num"),
]


def _month(name):
    return MONTHS[name.lower().rstrip(".")[:3]]


def find_dates(text):
    """Return list of (date, start_index) found in text."""
    out = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                if kind == "dmy":
                    d = date(int(m.group(3)), _month(m.group(2)), int(m.group(1)))
                elif kind == "mdy":
                    d = date(int(m.group(3)), _month(m.group(1)), int(m.group(2)))
                elif kind == "iso":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except (ValueError, KeyError):
                continue
            out.append((d, m.start()))
    out.sort(key=lambda x: x[1])
    return out


def parse_date(s):
    if isinstance(s, date):
        return s
    found = find_dates(s)
    if not found:
        raise ValueError(f"Unparseable date: {s!r}")
    return found[0][0]


# ---------- money ----------
_AMT = re.compile(
    r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(lakh|lakhs|lac|crore|crores|cr|k)?"
    r"|([\d,]+(?:\.\d+)?)\s*(lakh|lakhs|lac|crore|crores|cr)\b",
    re.I)
_MULT = {"lakh": 100000, "lakhs": 100000, "lac": 100000,
         "crore": 10000000, "crores": 10000000, "cr": 10000000, "k": 1000}


def find_amounts(text):
    """Return list of Decimal rupee amounts in order. Handles Rs.1,50,000 / 10 lakh / ₹4,000."""
    out = []
    for m in _AMT.finditer(text):
        num = m.group(1) or m.group(3)
        unit = (m.group(2) or m.group(4) or "").lower()
        try:
            v = Decimal(num.replace(",", ""))
        except Exception:
            continue
        out.append(v * _MULT.get(unit, 1))
    return out


_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per\s*cent|percent)", re.I)


def find_percents(text):
    return [Decimal(p) for p in _PCT.findall(text)]


def money(d):
    """Format Decimal as Rs. with 2dp, Indian grouping."""
    d = Decimal(d).quantize(Decimal("0.01"))
    sign = "-" if d < 0 else ""
    whole, frac = f"{abs(d):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}Rs.{whole}.{frac}"
