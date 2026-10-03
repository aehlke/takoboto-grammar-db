# Deep reevaluation and correction

This review found and corrected a real omission in the saved 2015 source, then
checked the extraction, state, transport and export boundaries. It used retained
raw captures and offline fixtures, with zero requests to the source websites.

## Recovered original entry 1649

The original `katawara` response displays two independent grammar headers:

| Original ID | Meaning | Original JLPT level | Displayed author |
| --- | --- | --- | --- |
| 1274 | beside | 2 | dc |
| 1649 | not only, ...also; written expression | 1 | rakki |

Both headers are marked `grammar`. They are in distinct source tables, each
with one note, seven examples and six comments. The page repeats the contribution
bodies under the two IDs. These are displayed source occurrences, not a claim
that the repeated wording represents new contributions.

The former parser selected the first header, selected only one Notes/Comments
heading, and collected examples from both tables. The source audit also used a
heading dictionary and shared that blind spot. ID 1649's distinct header,
meaning and author were omitted. This ID is absent from the captured Takoboto
collection and from the other released historical records.

The corrected parser identifies every entry header and scopes contributions to
its source table. The audit independently counts source headers and checks each
component's notes, examples, comments and references. Ambiguous boundaries,
duplicate original IDs, repeated headings within one entry and uncertain scope
require review. The correction preserves the original raw response hash, WARC
member hash, index hash, byte range and retrieval time.

Historical schema 2 retains both components in **one canonical YAML file**, with
`additional_entries` and `page_entry_position`. SQLite and optional Markdown
emit separate entries. The first entry keeps its existing key; the additional
entry gets a key qualified by source position and ID. No parallel content format
is committed.

The 2015 backup now contains **704 page captures, 705 entry observations and
702 distinct original IDs**, including **80 IDs absent current Takoboto**.
It preserves 844 notes, 5,537 examples, 3,849 comments and 912 references.
The combined historical SQLite tables contain 768 entries, 917 notes, 5,983
examples, 4,097 comments and 980 references. The extra displayed note/comment
occurrences and second header account for the changes; example occurrences
remain unchanged and are assigned to the correct entry.

## Other findings addressed

| Finding | Result |
| --- | --- |
| Failed or interrupted current refreshes left an older record exportable. | Current crawls persist pending/failed/parsed/review states. Exports refuse failed or pending attempts, record/hash disagreement, legacy report holds and newer cached responses. Cached success state bytes remain stable. |
| Warning-bearing current records or conflicting record licenses could still be exported. | Readers and both export writers refuse these inputs before creating outputs. Raw records remain available for source review. |
| Discovery of a newer historical revision did not itself block an older unchecked record. | Export checks the record and state against the current inventory. Proven identical-payload fallback still records actual and latest indexed times separately. |
| `Retry-After` on successful responses and redirects could be ignored. | Every source transport applies persistent backoff before following a redirect or reading the body, including 200/302/404 responses. |
| A full JSON roundtrip and correct counts could hide wrong normalized SQLite values. | CI checks fingerprints of every normalized table and both search views, including column names, all values and schema. JSON columns are compared semantically; packaging metadata rows are excluded. |
| Rebinding a verified record could discard WARC transport fields required for offline resume. | A successful source audit preserves matching capture/member evidence while updating the extraction digest. Offline resume is regression-tested. |
| A symlink in an output directory's ancestors could redirect crawl writes. | Output initialization rejects symlink ancestors before creating directories. |
| A latest replay or exclusion could disagree with a known indexed payload digest. | Known SHA-1 payload mismatches require review; an exclusion cannot claim coverage from a mismatching response. |

## Verification and limits

All **144 tests pass**, including reproductions of the new failure cases.
Fresh copies of the saved source evidence pass audits for all 643 current
entries, all 704 backup pages and all 63 newer pages, with five RSS feeds.
The multi-header scan also inspected retained exclusion and review responses;
`katawara` was the only multi-entry response found.

The reviewed SQLite comparison changes only `archive_entries`, `archive_examples`,
`archive_notes`, `archive_comments` and `archive_search_documents`. Every other
table/view and the SQLite schema match v0.4.0. Current, newer Wayback and RSS
record digests are unchanged. Only the corrected backup extraction digest
changes; the original source bytes remain unchanged.

[The machine-readable report](../recon/reevaluation.yaml) records exact source
hashes, offsets and counts. [The dataset baseline](../recon/dataset-baseline.yaml)
and [SQLite baseline](../recon/sqlite-baseline.yaml) support offline CI checks.
The old release fingerprint report is retained for comparison.

This correction does not establish a complete final live JGram database.
The latest Wayback supplement still has 1,347 unresolved indexed labels; 63
backup tutorial pages remain held for section/license review. Source audits
require retained raw caches; records-only checkouts can verify the committed
snapshot and reproduce its exports, but cannot independently re-audit raw HTML.
