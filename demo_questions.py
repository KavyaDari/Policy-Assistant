from policy_qa import ask
Q=[("Q1","When does a small merchant receive UPI money?","2026-08-15"),
("Q2","A large merchant (above Rs.10 lakh monthly) receives a Rs.4,000 UPI payment. What MDR and GST do they pay?","2026-08-15"),
("Q3","Same merchant, a Rs.1,50,000 payment. What do they pay?","2026-08-15"),
("Q4a","A merchant refunds a customer 3 hours after the sale. Do they get the MDR back?","2026-08-20"),
("Q4b","A merchant refunds a customer 3 hours after the sale. Do they get the MDR back?","2026-09-05"),
("Q5","What does the FAQ say about the MDR cap, and is the FAQ right?","2026-08-15"),
("Q6","Can a customer pay Rs.1,00,000 twice in one day to a merchant?","2026-08-15"),
("Q7","I closed my account yesterday. When will I get my money?","2026-08-15"),
("Q8","Does the policy allow me to settle card payments same day?","2026-08-15")]
for i,q,d in Q:
    r=ask(q,d); print(f"[{i}] {r['status']}\n  {r['answer']}\n  cites={[(c['document'][:8],c['clause'] or c['heading'][:25]) for c in r['citations']]}\n  res={r['resolution']}\n")
