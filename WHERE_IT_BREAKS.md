# Where it breaks

1. **"What is the chargeback fee?"** (eval E17, fails). Clause 3.4 mentions chargebacks but states no fee. No handler covers chargebacks, so the generic BM25 fallback finds 3.4, quotes the 120-day window as if it answered the question, and labels it CONFLICT_RESOLVED because unrelated FAQ entries scored too. It should be CANNOT_ANSWER. The root cause is that keyword overlap can't tell "this clause is on the topic" apart from "this clause answers the question". **Don't trust any answer that came from the generic fallback** (no handler fired); it is extractive and does no reasoning.

2. **Follow-ups that depend on earlier turns, e.g. "Same merchant, Rs.1,50,000".** Merchant size is carried in a module-level `SESSION`. That's fine for one user in a CLI, but it is wrong across users or in a different order. Asking Q3 in a fresh process gives a "both sizes" answer, which is still correct but less specific. A merchant described in other words ("we do Rs.12 lakh a month", "big shop") won't be recognised, since size detection is a regex.

3. **Exact payout dates (Q7) and anything involving holidays.** The documents have no bank-holiday calendar, and the working-day definition was removed when A replaced 1.1. The date given (Wed 26 Aug 2026) is the earliest possible, excluding Sundays only. Regional holidays, second/fourth Saturdays and the time it takes to deduct dues are unknown. A merchant should not treat this date as a promise.

Also fragile: handlers rely on regexes over the current wording (e.g. reading two caps out of circular C). If a document is reworded, extraction raises `Missing` and falls back to generic retrieval rather than returning a wrong number. That's safe, but the answer gets worse.
