# Review and refinement — 2026-10-03

**87 tests pass**, including eight new regression tests. Each new test reproduced
a concrete defect before its fix. The review used local source records and
fixtures; no live crawl or additional archive retrieval occurred.

| Finding | Result after refinement |
| --- | --- |
| Historical fallback or parser warnings prevented a clean audit but did not prevent export. | Warning-bearing captures retain their extracted records and raw evidence with `review_required` states. Normal export also refuses legacy warning-bearing records even when their existing state says `parsed`. |
| RSS parsing checked the replay's feed path without fully checking its origin, claimed original URL or timestamp. Offline migration could consequently verify inconsistent replay metadata. | Validate requested and actual replay scope. The requested replay must match its claimed original URL and timestamp. Valid redirects preserve the actual original URL and capture time; timestamp changes remain review cases. |
| A non-grammar exclusion could claim the latest timestamp while pointing at a different replay. | Exclusions now use the same original/replay/timestamp agreement checks as included entry records. Inconsistent evidence leaves the label pending and prevents completeness. |
| RSS channel notices such as `CC-BY-NC-SA-2.0` escaped the shorthand license check. | Detect spaced and hyphenated notices, including multiple notices within one declaration. Conflicting variants and versions require review; matching CC BY-SA 2.0 declarations remain accepted. |
| Explicit RSS author/creator metadata was retained in JSON/SQLite but omitted from Markdown. | Display those values in Markdown when present, with Markdown escaping and without inferring account identities. |

## Verification

The full offline QA used fresh copies of the stored datasets and blocked
`httpx.Client.send` throughout. It confirmed:

- All **643 current entries**, including 5,334 examples, 5,324 translations,
  4,546 comments and 150 additional meaning notes, match retained source HTML.
- All **25 historical entries and five RSS feeds** pass source checks.
  Repeating verification twice writes zero states and preserves state bytes.
- Fresh SQLite passes integrity and foreign-key checks, roundtrips every complete
  record, and matches the previous verified schema and every table/view.
- All **674 Markdown files** match the previous build byte for byte. All pages
  retain the original license link; 11,523 displayed credit values were checked.
  The existing RSS observations have no explicit author/creator metadata, so
  the added display fields introduce no changes to their exports.
- Sharing extracted records and states without raw caches still reproduces
  identical exports. Source auditing correctly requires the raw evidence.
- Nine malformed-record/state cases fail before export outputs are created;
  corrupt raw caches fail verification without rewriting records or states.
  Invalid selectors fail before requests or output creation.

After the final license-check change, all 87 tests were rerun and all five
stored RSS feeds were reparsed again. Every parsed field remained identical.
Original datasets, caches and verification states remain unchanged.

```sh
uv run --locked python -m unittest discover -s tests -v
```

The [machine-readable report](../recon/review-refinement.json) records the
retained QA scripts, checks and fresh export directory:
`smoke/review-refine-j1_amqct/export/`.

## Remaining limits

Historical coverage remains incomplete: **1,389 indexed labels are pending**.
The stored-source checks verify captured observations; they do not establish
eligibility or availability for the unfetched labels. Live-page changes were
not tested in this offline pass. Where sources omit contribution dates or
account identities, those facts remain unknown.
