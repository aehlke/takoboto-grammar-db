# Final offline QA — 2026-10-03

**79 tests pass.** The full stored-data QA also passes, with HTTPX sending blocked
and zero network sends observed. The original datasets, records, caches and
verification states were preserved; audits ran on fresh copies.

One defect was reproduced and fixed: historical RSS eligibility checked the
response and record hashes but omitted the verification state's replay URL.
It now checks that URL too, matching historical export acceptance. A regression
test confirms that a mismatched replay cannot establish RSS eligibility and
that the check does not rewrite the state.

Validation covered:

- All 643 current entries compared with captured source HTML, including 5,334
  examples, 5,324 translations, 4,546 comments and 150 additional meaning notes.
- All 25 historical records and five RSS feeds compared with cached source.
  Verification ran twice with zero state writes and identical state bytes.
- Fresh combined SQLite: integrity and foreign keys pass; all complete records
  roundtrip; the schema and every table/view match the previous verified build.
- All 674 Markdown files match the previous build byte for byte. All pages
  contain the original CC BY-SA 2.0 license link; 11,523 displayed credit values
  were checked across current and historical pages.
- Extracted records plus states export identically without raw caches; source
  auditing correctly refuses missing raw evidence.
- Nine real-data cases reject edits, missing states, held states, mismatched
  hashes and mismatched replay URLs before creating export outputs. Corrupt raw
  source bytes fail verification without changing records or states. Invalid
  saved selectors fail before requests or output creation.
- Help works for the main CLI and all seven subcommands. Existing unit tests
  cover pacing, robots checks, redirects, retries, cooldown persistence,
  license holds and safe output paths using offline fixtures/mocks.

Run the suite with:

```sh
uv run --locked python -m unittest discover -s tests -v
```

[Machine-readable report](../recon/final-qa.json) records the fresh output and
retained QA script paths. The tested exports are under
`smoke/final-qa-9rh504o7/export/`.

Historical coverage remains incomplete: **1,389 indexed labels are pending**.
This pass verifies stored observations and scraper behavior against retained
fixtures; it does not retest today's live pages or recover additional labels.
