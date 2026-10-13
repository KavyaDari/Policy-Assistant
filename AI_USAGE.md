# AI usage log

## Tool
Claude (Anthropic), used in a chat session during the 60-minute window. No LLM is called at runtime; the system is fully offline.

## My work
- Read the assignment and all three policy documents, and supplied the data files.
- Proposed architecture (clause parser → as-of-date clause state → rule handlers → Decimal calculator, with BM25 keyword fallback). 
- Ran the system locally on Windows (Anaconda Python), fixed the folder-nesting issue that stopped it running, and confirmed both scripts reproduce the expected output (eval: 16/17).
- Verified the key answers by hand against the documents:
  - Q2: 0.50% x Rs.4,000 = Rs.20, below the Rs.25 cap from circular C (not the old Rs.15 in master 2.3); GST 18% on top (2.4) = Rs.3.60; total Rs.23.60.
  - Q3: Rs.1,50,000 exceeds the 4.1 limit; the 4.2/4.4 exception still doesn't lift the daily limit in 4.3 as amended by E.
  - Q4: circular D is effective 1 Sep, so 3.3 applies on 20 Aug but not on 5 Sep.
- Checked every expected answer in `eval.json` against the clause text rather than taking it on trust.
- Traced Q4 through the code (`ask` → `h_refund` → `version` → `Corpus.state`) so I can explain the date logic.
- Organised the commit history and published the repo.

## What the AI did
- Generated first drafts of the code in `policy_qa/`, `run_eval.py`
- Helped fixing bugs in the code in `policy_qa/`, `run_eval.py`
- Wrote README.md , WHERE_IT_BREAKS.md, DECISIONS.md after the owner verified and provided me the results 
- Helped write eval.json with the help of owner giving the question from the assignment given and some made manually by owner.
- Wrote `fixture_synthetic/` and eval_synthetic.json for testing
