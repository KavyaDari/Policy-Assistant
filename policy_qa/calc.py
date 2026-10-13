"""All arithmetic lives here. Decimal only, never float, never an LLM.

Rates, caps and GST percentages are passed in from parsed clause text; this module
never assumes a rate (e.g. it will not default GST to 18% if the docs don't say so).
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

PAISA = Decimal("0.01")


def r2(x):
    return Decimal(x).quantize(PAISA, rounding=ROUND_HALF_UP)


@dataclass
class FeeResult:
    amount: Decimal
    rate_pct: Decimal
    raw_mdr: Decimal
    cap: Decimal | None
    capped: bool
    mdr: Decimal
    gst_pct: Decimal | None
    gst: Decimal | None
    total: Decimal

    def explain(self):
        from .parsing import money
        s = f"MDR = {self.rate_pct}% x {money(self.amount)} = {money(self.raw_mdr)}"
        if self.cap is not None:
            s += (f"; cap {money(self.cap)} applies -> MDR {money(self.mdr)}" if self.capped
                  else f"; below cap {money(self.cap)}")
        if self.gst is not None:
            s += f". GST = {self.gst_pct}% x {money(self.mdr)} = {money(self.gst)}. Total = {money(self.total)}"
        else:
            s += ". GST rate not stated in the documents, so GST is not computed"
        return s + "."


def mdr_fee(amount, rate_pct, cap=None, gst_pct=None):
    amount, rate_pct = Decimal(amount), Decimal(rate_pct)
    raw = amount * rate_pct / 100
    capped = cap is not None and raw > Decimal(cap)
    mdr = r2(Decimal(cap) if capped else raw)
    gst = r2(mdr * Decimal(gst_pct) / 100) if gst_pct is not None else None
    return FeeResult(amount, rate_pct, r2(raw), Decimal(cap) if cap is not None else None,
                     capped, mdr, Decimal(gst_pct) if gst_pct is not None else None,
                     gst, r2(mdr + (gst or 0)))


def add_working_days(start, n, holidays=()):
    """Date that is n working days after start. Working days exclude Sundays and the
    given holidays (master 1.1 wording). The documents publish no holiday calendar,
    so callers pass holidays=() and must say the date is the earliest possible."""
    from datetime import timedelta
    d, count = start, 0
    while count < n:
        d += timedelta(days=1)
        if d.weekday() != 6 and d not in holidays:
            count += 1
    return d
