# review-pulse

Groww (Play Store `com.nextbillion.groww`) reviews -> weekly product pulse + a fact-checked fee explainer -> human approval -> Google Doc entry and Gmail **draft** through an n8n MCP server. Nothing is ever sent.

Rule that runs through everything: **the AI sorts, code counts.** The LLM never produces a count, percentage or ranking; Python computes every number and inserts it. Quotes are copied from the CSV by code and verified character for character. Source links are hardcoded.

## How to run

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # then fill in the values (never commit .env)
```

`.env` needs `GROQ_API_KEY`, `N8N_MCP_URL`, `N8N_MCP_TOKEN` (`GROQ_MODEL` defaults to `openai/gpt-oss-20b`).

| Step | Command | Output |
|---|---|---|
| 1 scrape + clean + sample | `python scrape.py` | `data/reviews_sample.csv` (cap 150/week) |
| 2 themes, ranking, quotes | `python themes.py` | `outputs/themes.json` |
| 3 fee detection | `python fees.py --full` | `outputs/fee_issue.json` |
| 4 weekly pulse | `python pulse.py` | `outputs/weekly_pulse.md` |
| 5a fetch official pages | `python fetch_sources.py` | `data/sources/*.txt` |
| 5b RAG fee explainer + judge | `python explainer.py` | `outputs/fee_explainer.md` |
| 6 MCP connection test | `python mcp_client.py` | must list exactly 3 tools |
| 7 approve and publish | `python approve.py` | Doc entry + Gmail draft, `logs/` |
| 8 validation (no AI) | `python validate.py` | `outputs/validation_report.md` |

Also written by `approve.py`: `outputs/email_draft.txt`, `outputs/sources.md`. n8n setup: [docs/n8n_setup.md](docs/n8n_setup.md). Every LLM response is cached in `cache/`, so re-runs are free; Groq 429s are retried with backoff.

## Where MCP approval happens

`approve.py` is the only place anything is written. It builds the exact Doc entry and email, prints both in full, shows a SHA-256 fingerprint, and requires you to type `APPROVE` (exact, capitals). Anything else is a rejection: it asks why, logs it, and writes nothing. After approval, in order: `read_doc` (stop if this week's entry exists; resume if only the draft is missing) -> re-check hash -> `append_to_doc` -> `read_doc` again to verify the entry landed -> re-check hash -> `create_email_draft`. Each step is logged to `logs/approve_*.jsonl`. The n8n server has exactly three tools (`append_to_doc` with a fixed doc ID, `read_doc`, `create_email_draft`); there is no send tool, and `approve.py` and `validate.py` both refuse to proceed if one appears. `approve.py --dry-run` prints everything without prompting or calling MCP.

## Results (data through 2026-10-18)

Reviews: 12,800 fetched -> 3,831 clean (>= 4 words, deduplicated, phone/email redacted, no usernames) -> 1,800 sampled (150 per week, 12 weeks from 2026-07-27).

**Ranking rule** (written in `themes.py` before the first run): rank themes by the number of 1-2 star reviews in the theme, descending. Ties: higher share of 1-2 star reviews, then larger total, then theme name alphabetically.

| Rank | Theme | Reviews | 1-2 star | Share |
|---|---|---|---|---|
| 1 | Customer Support & Service | 234 | 198 | 85% |
| 2 | App Performance & Stability | 278 | 190 | 68% |
| 3 | Feature Requests & Improvements | 244 | 70 | 29% |
| 4 | Fees & Charges | 125 | 68 | 54% |
| 5 | Positive Experience & Ease of Use | 919 | 23 | 3% |

**Fee issue identified: brokerage.** Of 3,831 clean reviews, 340 matched the fee keywords. The LLM labelled them; code counted: **confused 28, complaint_only 247, praise 23, unrelated 42**. Among the 28 "confused" reviews, brokerage has **5**, DP charges 2, GST/taxes 1, withdrawal charges 1, AMC 1, and "other" 18 (mostly generic "hidden charges" with no specific fee, ignored by the selection rule). Brokerage is also the most mentioned fee overall (178 non-unrelated mentions). Selection rule: most "confused" reviews per specific fee, ignoring `other`/`none`; ties by total mentions, then name.

**Sources** (fetched 2026-10-18; the first two are the explainer's cited links, the rest were cross-checks):

1. https://groww.in/pricing
2. https://groww.in/help/stocks,-f&o,-ipo-&-mtf/sx-pricing/what-is-the-charge-for-buy-order-delivery
3. https://groww.in/help/stocks,-f&o,-ipo-&-mtf/sx-pricing/what-are-intraday-charges
4. https://groww.in/help/payments-&-withdrawals/payments-charges/why-is-my-brokerage-more-than-20-rupees--71
5. https://groww.in/help/stocks,-f&o,-ipo-&-mtf/sx-demat-account/how-much-does-groww-charge-for-stocks-1

## How the limits are enforced (in code)

- Pulse <= 250 words: counted strictly (every whitespace token), regenerated up to 3 times, no digits allowed in LLM text.
- Fee explainer <= 6 bullets: capped in code. Each bullet must cite an allowed source, carry verbatim evidence snippets that exist in that source, and use only numbers that appear in its evidence and source. A second LLM call (judge, `openai/gpt-oss-120b`) checks that every claim is directly stated; rejected bullets are regenerated once, then dropped; fewer than 3 survivors prints NEEDS HUMAN REVIEW and `approve.py` blocks.
- `validate.py` re-checks all of this with no AI: 49 checks, including recounting themes from scratch and eight bad-input cases.

## Known limitations

- **The fee signal is small.** 5 of 28 confused reviews point at brokerage; 18 more confused reviews name no specific fee. Treat "brokerage" as the best-supported guess, not a measured majority. Fee detection ran on the full clean set (3,831), while themes ran on the 1,800 sample.
- **Sampling and filtering.** About 70% of raw reviews were dropped for being under 4 words; the 150/week cap is a random sample (seed 42). Reviewers are a self-selected, mostly unhappy minority, so counts are not incidence.
- **Theme quality is unverified.** Themes and assignments come from one LLM pass with no hand-labelled check. "Feature Requests" mixes unrelated requests, and the pulse's one-line theme descriptions are LLM wording that has not been audited beyond the digit ban.
- **Model change.** `llama-3.1-8b-instant` was no longer available on the key, so classification and writing use `openai/gpt-oss-20b`, the judge `openai/gpt-oss-120b`.
- **Explainer scope.** It covers Groww equity brokerage, DP charges, GST and exchange/regulatory charges only, from two pages. The pages disagree in places (an older help article and NRI pricing give other minimums), and the pricing table loses its column headers when converted to text. An early judge pass accepted a misattributed and an over-general bullet; the verbatim-evidence check was added after a manual audit. Judge verdicts are not stored, so `validate.py` can only confirm the survivors and the `needs_human_review` flag.
- **Trend numbers** compare the last 4 sampled weeks with the prior 4 inside the 150/week sample.
- **End-to-end publish.** The MCP connection and tool list are tested live. The `append_to_doc` n8n node must be set to Insert (not Replace Text); `approve.py` and `validate.py` flag the Replace configuration. A full APPROVE run is done by the user.
- Quotes: if the LLM's substring is not an exact match, code falls back to the full review text; the pulse then shortens it to a verbatim stretch of at most 25 words.
