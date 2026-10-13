# Decisions and ambiguities

| # | Ambiguity | Choice | Why |
|---|-----------|--------|-----|
| 1 | Which document wins when they disagree? | In-force circular > master policy > FAQ | The circular is the latest formal instrument. The FAQ is explanatory, not policy, and is dated March 2026, before the circular. |
| 2 | Circular published in August but effective later | Use the **effective** date, not the publication date | The spec says answers depend on as_of_date. A rule announced but not yet effective does not apply, though I surface it as a note. |
| 3 | Date in the question vs as_of_date | Date in the question wins | The user is explicitly asking about that date. |
| 4 | "Yesterday" | as_of_date minus 1 day | The only reference point available. |
| 5 | Numeric dates like 05/09/2026 | DD/MM/YYYY | Indian documents and an Indian business. |
| 6 | Deleted clause with no replacement | CONFLICT_RESOLVED: "no provision in force", citing both the deleted clause and the deleting circular clause | The deletion is itself the answer, and silently answering from the old text is the trap. |
| 7 | Pending amendment | ANSWERED from the current rule, plus a note about the upcoming change | It's not a conflict on that date, but hiding it would be unhelpful. |
| 8 | Question about something never mentioned (card payments) | CANNOT_ANSWER | Applying the UPI rule to cards would be a guess. |
| 9 | GST rate not stated in a clause | Do not default to 18% | The spec says never guess. calc.py only uses rates found in the text. |
| 10 | Rounding | Decimal, ROUND_HALF_UP to paisa; cap applied to MDR before GST | Deterministic, and the standard billing convention. |
| 11 | Parser read "Clause 5.2 of the master is deleted" as a new clause 5.2 | "Clause N" with no punctuation in running text is treated as a reference, not a clause start | Caught by my own test. Otherwise the circular would have been cited with a wrong clause number. |
| 12 | FAQ phrasing outscores the real rule in retrieval | Any in-force non-FAQ clause above the minimum score is considered before the FAQ | The FAQ is written in user language and would otherwise win on keywords. |

## Data-specific decisions (from reading ai-2-data/)

| # | Finding in the documents | Choice | Why |
|---|---|---|---|
| D1 | Circular is *issued* 20 Jul 2026 and *effective* 01 Aug 2026 "unless stated otherwise". The filename says "2026_08". | A, B, C, E in force from 01 Aug. Before that, master text applies (eval E02, E06). | The effective date governs, not the issue date or the filename. |
| D2 | Item D carries its own "(Effective 01 September 2026.)" on the next line | 3.3 is deleted from 01 Sep only. On 20 Aug, 3.3 still applies, with a note that it changes soon (Q4). | "Unless stated otherwise" makes the item-level date override the circular's date. |
| D3 | Circular items are lettered A–F, not numbered | Cited as clause "A" etc., exactly as written | Never invent numbering. |
| D4 | FAQ entries have no numbers | Cited with `clause: null` plus the question text as heading | Inventing "Q2" would be an invented clause number. The eval checks for this. |
| D5 | 2.2 (0.50% for large merchants) is not amended. B only changes 2.1 (small → 0.25%). | Large rate stays 0.50% | F: "All other clauses remain unchanged." |
| D6 | C makes the cap depend on size: ₹15 up to ₹10L, ₹25 above. The old 2.3 flat ₹15 is replaced. | Q2: 0.5% × 4,000 = ₹20 < ₹25, so MDR ₹20 and GST ₹3.60 | 2.4: GST 18% on MDR and "not part of the MDR cap", so cap first, then GST on top. |
| D7 | "Above Rs.10 lakh monthly" in Q2 is a merchant attribute | Stripped before extracting the payment amount | Otherwise ₹10L would be read as the transaction. |
| D8 | Q3 says "same merchant" | ask() keeps the last merchant size in a small session memory. With no size, it computes both sizes. | The signature is `ask(question, as_of_date)` with no context argument. This is the least-bad option and is noted as a limitation. |
| D9 | Q3: ₹1,50,000 > ₹1,00,000 per-transaction limit (4.1). 4.2 allows ₹2L for Insurance/Capital Markets only with enhanced KYC (4.4). The daily limit per customer is ₹1L (4.3 as amended by E). | Answer: the payment is not allowed. The fee (₹25 cap + ₹4.50 GST) is shown only as "if it were processed". | 4.2 is a per-transaction exception and does not lift the daily limit, so both limits must hold. |
| D10 | E: daily limit is ₹1L "or the customer's own bank limit, whichever is lower". The bank limit is unknown. | Use ₹1L as the ceiling and say the bank may set a lower one | We can't know the bank's limit, so it's surfaced rather than guessed. |
| D11 | 3.3 reverses "the MDR". GST on that MDR is not mentioned. | Say MDR is reversed and that the GST treatment is unstated | Not guessing. |
| D12 | Q7: 5.2 says 10 *working* days. The FAQ says "10 days". The working-day definition lived in 1.1, which A replaced without restating it. There is no holiday calendar. | Count working days excluding Sundays (earliest date: Wed 26 Aug 2026) and state the caveats. 15 Aug, a national holiday, is mentioned as an example only. | A deterministic answer with honest limits. Assuming the definition survives is the most reasonable reading. |
| D13 | 5.1 requires 30 days' notice. "Closed yesterday" may mean the closure was only requested. | Assume the closure took effect and say so | False-premise awareness. |
| D14 | The FAQ's "no upper limit on the fee" was dated 12 Mar 2026, when the ₹15 cap (effective 01 Jan) already existed | FAQ was wrong when written, not just stale | Q5 asks "is the FAQ right?", and the honest answer is that it never was. |
| D15 | Card questions: 1.2 gives T+2. There is no card MDR anywhere. The T+0 add-on in A is UPI-only. | Q8 → No (T+2). Card MDR → CANNOT_ANSWER. | Don't carry UPI rules over to cards. |
| D16 | Status labels | CONFLICT_RESOLVED whenever the answer depends on a superseded or deleted clause or on overruling the FAQ. Otherwise ANSWERED, with a forward-looking note for pending amendments. | It tells support staff when the "obvious" document is wrong. |
