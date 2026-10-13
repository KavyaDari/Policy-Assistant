"""Run ask() over eval.json and print a score table.

Each case scores 3 checks:
  status    - exact match with expected_status
  citations - every expected (document, clause) appears in the output, AND no cited
              clause number is absent from the source docs (hallucination check)
  answer    - every string in expected_answer_contains appears (case-insensitive)
              and nothing in must_not_contain appears
Usage: python run_eval.py [eval.json] [data_dir]
"""
import json
import sys

from policy_qa import ask, load
from policy_qa.ask import DATA_DIR


def check(case, out, corpus):
    st = out["status"] == case["expected_status"]
    got = {(c["document"], c["clause"]) for c in out["citations"]}
    want = {(c["document"], c["clause"]) for c in case.get("expected_citations", [])}
    real = {(c.doc, c.cid) for c in corpus.clauses}
    invented = got - real
    cit = want <= got and not invented
    text = (out["answer"] + " " + (out.get("resolution") or "")).lower()
    ans = all(s.lower() in text for s in case.get("expected_answer_contains", [])) and \
        not any(s.lower() in text for s in case.get("must_not_contain", []))
    return st, cit, ans, invented


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "eval.json"
    data = sys.argv[2] if len(sys.argv) > 2 else DATA_DIR
    corpus = load(data)
    cases = json.load(open(path, encoding="utf-8"))
    rows, tot = [], [0, 0, 0, 0]
    for case in cases:
        out = ask(case["question"], case.get("as_of_date"))
        st, cit, ans, invented = check(case, out, corpus)
        full = st and cit and ans
        for i, v in enumerate((st, cit, ans, full)):
            tot[i] += v
        rows.append((case["id"], "Y" if case.get("adversarial") else "", st, cit, ans, full,
                     out["status"], invented))
    mark = lambda b: "PASS" if b else "fail"
    print(f"{'id':<6}{'adv':<4}{'status':<8}{'cites':<8}{'answer':<8}{'ALL':<6}got")
    print("-" * 60)
    for r in rows:
        extra = f"  INVENTED CITATION {r[7]}" if r[7] else ""
        print(f"{r[0]:<6}{r[1]:<4}{mark(r[2]):<8}{mark(r[3]):<8}{mark(r[4]):<8}{mark(r[5]):<6}{r[6]}{extra}")
    n = len(rows)
    print("-" * 60)
    print(f"status {tot[0]}/{n}   citations {tot[1]}/{n}   answer {tot[2]}/{n}   fully correct {tot[3]}/{n}")


if __name__ == "__main__":
    main()
