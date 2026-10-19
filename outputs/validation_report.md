# Validation report (2026-10-19 14:38)
```

[Data]
  PASS  required columns exist   (1800 rows)
  PASS  no username/email/phone columns or values   (pii cols [], text hits 0)
  PASS  span is 8-12 weeks   (12 weeks)
  PASS  cap of 150 reviews per week respected   (max 150/week)
  PASS  ratings are all integers 1-5
  PASS  review_id unique

[Themes]
  PASS  at most 5 themes   (5 themes)
  PASS  exactly 3 top themes   (3)
  PASS  counts match a from-scratch recount   (all theme totals and 1-2 star counts match)
  PASS  every review has a theme and theme totals sum to the sample size   (1800 vs 1800)
  PASS  ranking follows the written rule (1-2 star desc, share desc, total desc, name)   (expected top ['T2', 'T1', 'T5'], got ['T2', 'T1', 'T5'])

[Quotes]
  PASS  3 stored quotes are verbatim substrings of their CSV review   (bad [])
  PASS  3 quotes in the pulse appear word for word in the CSV   (3 quotes, missing [])
  PASS  each pulse quote is 10-25 words   ([22, 16, 19])

[Fee issue]
  PASS  stance counts match a recount of data/fee_labels.csv   ({'confused': 28, 'complaint_only': 247, 'unrelated': 42, 'praise': 23})
  PASS  fee issue = most frequent fee among 'confused' (ignoring other/none), tie-break per rule   (expected brokerage, file says brokerage)
  PASS  all labels are from the allowed sets

[Pulse]
  PASS  at most 250 words   (219 words)
  PASS  required sections present (themes, quotes, key observation, actions)   (missing [], quotes 3)
  PASS  exactly 3 action ideas   (3)
  PASS  theme numbers in the pulse equal recomputed counts   (missing [])
  PASS  fee numbers in the pulse equal fee_issue.json

[Explainer]
  PASS  at most 6 bullets (and at least 3)   (6)
  PASS  exactly 2 official source links, both from the fetched list   (['https://groww.in/pricing', 'https://groww.in/help/stocks,-f&o,-ipo-&-mtf/sx-pricing/what-is-the-charge-for-buy-order-delivery'])
  PASS  'Last checked' date present
  PASS  every number in every bullet appears in its cited source   (bad [])
  PASS  no URLs written inside bullet text (links are hardcoded)
  PASS  no opinion words
  PASS  not marked NEEDS HUMAN REVIEW (>=3 bullets passed number check + judge)   (dropped 0)
  PASS  explainer topic equals the identified fee issue

[Safety]
  PASS  approval fingerprint is stable across two independent builds   (8031d3a00530a6fb)
  PASS  email subject has the required format   (Weekly Product Pulse + Customer Clarification — 2026-10-19)
  PASS  doc entry contains all 6 required fields   (missing [])
  PASS  approve.py requires the exact string APPROVE
  PASS  no 'send' tool exists on the MCP server (live) and tool set is exactly 3   (['append_to_doc', 'create_email_draft', 'read_doc'])
  FAIL  append_to_doc is configured to insert (not 'Old_Text' replace)   (params ['actionFields0_Old_Text'])
  PASS  .env, venv/, cache/ are git-ignored and .env is not tracked
  PASS  no API key or MCP token in any tracked/working source file   (hits [])
  PASS  LLM responses are cached (cache/ non-empty)   (140 cached responses)

[Bad inputs]
  PASS  validator rejects: empty file   (missing columns ['review_id', 'text', 'rating', 'date', 'week_start'])
  PASS  validator rejects: missing column   (missing columns ['rating'])
  PASS  validator rejects: only 20 rows   (only 20 rows (<100); 3 weeks of data (need 8-12))
  PASS  validator rejects: rating 0   (ratings outside 1-5 or non-numeric)
  PASS  validator rejects: rating 'good'   (ratings outside 1-5 or non-numeric)
  PASS  validator rejects: phone number in text   (phone/email found in text)
  PASS  validator rejects: 20 weeks of data   (20 weeks of data (need 8-12))
  PASS  validator rejects: username column   (PII column present)
  PASS  validator accepts a clean frame
  PASS  validator accepts the real sample
48/49 checks passed
```
