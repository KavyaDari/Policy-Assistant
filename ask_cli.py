"""Usage: python ask_cli.py "question" [as_of_date]"""
import json
import sys

from policy_qa import ask

if __name__ == "__main__":
    q = sys.argv[1]
    d = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(ask(q, d), indent=2, ensure_ascii=False, default=str))
