# Policy Assistant

Answers merchant questions about fees, refunds, settlement and limits from the three documents in `ai-2-data/`, taking into account **which clauses are in force on the date asked**. It returns an answer, citations (document + clause) and a status: `ANSWERED`, `CONFLICT_RESOLVED` (with how) or `CANNOT_ANSWER`.

**Requirements:** Python 3.10+, standard library only. **No API key, no network, no LLM at runtime.**

## Run
Run all commands from the repository root.

```bash
# The 8 questions from the assignment (Q4 asked for both 20 Aug and 5 Sep)
python demo_questions.py

# Any question (date optional, default 2026-08-15); prints full JSON incl. trace
python ask_cli.py "When does a small merchant receive UPI money?" 2026-08-15

# Evaluation: runs eval.json and prints a score table
python run_eval.py

# Engine self-test on synthetic data (independent of the real documents)
python run_eval.py tests/eval_synthetic.json tests/fixtures_synthetic
```

From Python:
```python
from policy_qa import ask
ask("A merchant refunds 3 hours after the sale. Is MDR returned?", "2026-09-05")
# -> {"status", "answer", "citations": [{"document", "clause", "heading"}], "resolution", "trace"}
```
- `as_of_date` defaults to **15 Aug 2026**. A date written inside the question overrides it, and "yesterday" means as_of_date minus one day.
- FAQ entries have no numbers in the source, so their citations have `"clause": null` and the FAQ question as `heading`. No clause number is ever invented.

## Files
| Path | Purpose |
|---|---|
| `policy_qa/parsing.py` | Date parsing (Indian formats) and money parsing (Rs./₹, lakh, crore) |
| `policy_qa/corpus.py` | Splits documents into clauses; reads effective dates, amendments/deletions, cross-references; `Corpus.state(date)` |
| `policy_qa/rules_impl.py` | Hand-written handlers: settlement, fees, refunds, limits, account closure, FAQ correctness |
| `policy_qa/rules.py` | Handler registry |
| `policy_qa/calc.py` | All arithmetic: MDR/cap/GST in `Decimal`, working-day counting |
| `policy_qa/retrieve.py` | BM25 keyword retrieval (fallback) |
| `policy_qa/ask.py` | `ask()`: date resolution, scope check, handlers, fallback, statuses |
| `ask_cli.py` | Command-line wrapper around `ask()` |
| `demo_questions.py` | Runs the 8 assignment questions |
| `run_eval.py` | Scores status, citations (incl. invented-clause check) and answer content |
| `eval.json` | 17 evaluation cases, 9 adversarial |
| `ai-2-data/` | The three policy documents |
| `DECISIONS.md` / `WHERE_IT_BREAKS.md` / `AI_USAGE.md` | Ambiguities and choices / known failures / AI-use disclosure |

## How it works
1. **Parse** (`corpus.py`): each document is split into clauses using its own labels (1.1, 2.3…, circular items A–F, unnumbered FAQ questions). Effective dates are read at document level ("Effective 01 August 2026") and item level (item D: "Effective 01 September 2026").
2. **Clause state on the date** (`Corpus.state`): every clause is `in_force`, `pending`, `superseded` or `deleted`. For example, on 20 Aug master 3.3 is in force; on 5 Sep it is deleted by circular D.
3. **Handlers** (`rules_impl.py`): for the six main topics, each handler takes the in-force version of each clause and **extracts rates, caps, limits and periods from the clause text at runtime**. Nothing is hard-coded. If the expected text isn't found, the handler steps aside rather than guess.
4. **Arithmetic** (`calc.py`): `Decimal`, round-half-up to paisa. MDR = rate × amount, then cap, then GST on top (2.4: GST is not part of the cap).
5. **Fallback** (`retrieve.py`): when no handler matches, BM25 keyword search picks clauses and conflicts are resolved by authority (in-force circular > master > FAQ). A lower-authority clause that disagrees numerically is reported as `CONFLICT_RESOLVED`.
6. **CANNOT_ANSWER** when nothing relevant is found, when the question is about a topic the documents never mention, or when the specific fact is missing (e.g. card MDR: cards appear only for settlement, never for fees).

## Results
- `python run_eval.py` → **16/17 fully correct**, 17/17 citations valid, **0 invented clause numbers**. The one failure (E17, chargeback fee) is a documented weakness.
- Note: E04 ("Same merchant…") depends on running directly after E03, because merchant size is remembered between calls.

## What works
- Effective-date reasoning: circular issued 20 Jul / effective 01 Aug, and item D's own later date (01 Sep).
- Replaced, deleted and amended clauses; cross-references (2.2→2.3, 4.2↔4.4, D→3.2); the stale or wrong FAQ.
- Deterministic fee maths and limit checks (per-transaction, category + KYC exception, daily limit).
- Refusals: card MDR, unknown topics, missing information.

## What doesn't
- The fallback is shallow keyword extraction and can answer off-topic (see WHERE_IT_BREAKS.md).
- "Same merchant" relies on process-level session memory.
- No holiday calendar, so payout dates are earliest-possible only.
- Phrasings outside the regex and synonym lists (e.g. "we do Rs.12 lakh a month") may be missed.