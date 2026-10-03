# Review of the two-page pilot

The existing live test captured Takoboto #725 and the latest indexed JGram
`ageku` replay. Content extraction passed: 20 examples and 7 comments from
Takoboto; 6 notes, 14 examples and 23 comments from JGram. No parser or schema
changes were needed.

## Refinements

- Saved inventories, requested IDs/labels, pacing parameters and archive
  eligibility inputs are validated before constructing a fetcher. Invalid
  local inputs cause no requests and create no output directories. Saved
  archive captures must match their label and timestamp and appear newest
  first. Initial access denials and cooldowns produce a concise stop message.
- Both export destinations are checked before creating either export. Existing
  databases, occupied Markdown directories, symlinks and overlapping
  destinations are refused. This fixes the case where rejecting Markdown
  previously left a newly created SQLite file behind.
- JSON records, metadata and reports use a temporary file in the destination
  directory followed by atomic replacement. Output paths are checked again
  before replacement. Response bodies use the same write mechanism, and an
  existing corrupt content-addressed body is refused rather than overwritten.
  Interrupted replacement preserves the previous file. Failed `.tmp` files
  remain available for inspection and are excluded from `*.json` record reads.
  This provides atomic visibility; it does not promise power-loss durability.
- Each fetcher invocation writes `request-report.json` and a retained copy at
  `request-reports/<run_id>.json`. Each transport attempt records URL, UTC start,
  duration, status, bytes read and error type. Retries and followed redirects
  each count; cache hits and blocked redirects do not. Reports omit headers,
  cookies and User-Agent contact details. Transport closure is guaranteed even
  if report writing fails. Hard process termination can prevent the report
  from being written.

## Verification

`uv run --locked python -m unittest discover -s tests -v` passes **49 tests**,
including regression checks for preflight failures, interrupted writes,
symlink replacement, corrupt caches, request reporting and resource closure.
The original live test passed 34 tests before these refinements.

The existing inventories validate: **643 Takoboto entries** and **1,414 JGram
labels**. This validates inventory structure; it does not establish historical
replay coverage.

The same two cached source pages were replayed in a fresh output directory with
HTTPX sending blocked. No requests occurred. Extracted JSON matches the original
pilot exactly, including retrieval timestamps, credits and content. Independent
checks of the captured source content passed. SQLite passes integrity and
foreign-key checks and retains both complete records. All three generated
Markdown files match the original pilot byte for byte.

Evidence: [refinement report](../recon/refinement-report.json). The
[original live-test evidence](../recon/uv-smoke-test.json) is preserved unchanged.
Its cached URL list does not establish the number of transport attempts;
attempt reporting applies to subsequent runs.

The full historical replay crawl remains incomplete. These checks cover the
same two content pages and make no broader claim of archive completeness.
Original CC BY-SA 2.0 attribution and conflicting-license exclusions remain
in place.
