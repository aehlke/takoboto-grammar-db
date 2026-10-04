# Recovery follow-up

This follows the [remaining-work reassessment](remaining-work.md) and preserves
its distinction between unfinished crawling and proven missing source content.
The current Takoboto collection and original RSS records retain their previous
record digests. The v0.5.0 baselines are preserved separately for comparison.

## Completed implementation and recovery

- Review exact source cells and independently reconstruct their original byte
  ranges before excluding separately licensed material. Recover JGram notes,
  examples, comments and relationships outside those cells. Unknown responses
  remain held. See [section review](section-review.md).
- Recover all 63 previously held tutorial pages in the dated backup as explicitly
  partial observations. Its full retained-source audit now passes with 766 page
  files, 767 entry observations, 846 notes, 5,554 examples, 3,886 comments,
  924 relationships and 311 verified exclusions. All 1,077 selected backup labels
  are resolved for the included collection; separately licensed cells remain
  omitted.
- Recover original `da` (568), resolving its missing historical observation.
- Provide hash-verified private source-evidence backup and safe restoration,
  retaining raw HTML, WARC/index caches and held evidence for offline re-audits.
  [Evidence instructions](evidence.md) explain recovery and privacy.
- Exclude the exact reviewed `newSiteFB` (1480) captures in both historical
  sets. Their misleading grammar category contains website administration and
  feature feedback rather than language material. Each observation had one
  note, zero examples and 42 comments. Source hashes, IDs, titles and review
  reasons remain in the membership manifest and states. Changed sources require
  a fresh review; this is a semantic scope correction to the v0.5.0 release.
- Document researched dumps/mirrors in [the source-lead ledger](../recon/source-leads.yaml).
  The tested old Takoboto detail mirror redirects to the current index.
  Yookoso’s April 2021 retained-database statement is a specific surviving-copy
  lead, but the public article exposes no download. An [unsent request](source-outreach.md)
  is ready for Alex; no message has been sent.

The retained-record comparison with v0.5.0 confirms all 63 previously released
newer pages and all 703 retained backup pages are byte-value identical as parsed
records. The one removed backup page is the reviewed administration thread.
The YAML loader uses the safe C implementation when available, retaining the
custom duplicate-key/type/recursive-alias checks and Python fallback. Local
validation of the same 643 current records fell from 9.343 to 1.748 seconds;
this is a local measurement, not a portable speed guarantee.

## Completed source coverage and verification

All 1,414 latest labels were attempted. The latest set exports 890 pages / 893
entry observations: 944 notes, 6,085 examples, 4,356 comments and 1,007
relationships. There are 512 verified exclusions, eleven failed replays and one
license hold (`-oku`). The audit verifies every exported record and exclusion.
Nine failed labels return HTTP 404; two return error pages without entry headers.
They remain unresolved rather than being counted as empty grammar records.

The three-stage crawl retained request/continuation reports. It stopped on HTTP
503, honored the persisted cooldown and successfully probed the failing label
before continuing. A later cluster of HTTP 404 replays was inspected before
resuming the remaining labels. Fresh robots checks, five-second request spacing,
three-request bursts and 30-second pauses remained in place throughout.

Original ID 663 (そう) is recovered from the newest earlier clean `sou-2`
revision, March 27, 2014, after two later revisions also reported no entry. The
record preserves two notes, six examples, two comments and five relationships.
Its exact selected payload digest and raw bytes are verified. It has a distinct
revision identity, selected/latest timestamps and independent state. The latest
no-entry state remains unchanged. [The evidence ledger](../recon/earlier-revisions.yaml)
records all three probes. Only current IDs 1795 and 1797 still lack historical
observations, and their current Takoboto records are preserved.

An additional unclassified original URL-byte alias of てしまいました (1724)
was inspected by ID, title and fourteen attributed grammatical examples. Its
source-bound membership decision is committed. The no-entry parser now also
compares exact percent-decoded original URL bytes, resolving a lossy-label
encoding case without reconstructing missing characters. A regression test
rejects a different source byte sequence.

All 84 latest tutorial cells and 63 backup cells have exact omission reviews.
All prior exported records retain their parsed-value hashes except for the one
intentional `newSiteFB` backup removal. The current and RSS digests and thirteen
unaffected normalized SQLite relations remain identical to v0.5.0. The updated
baseline verifies all nineteen normalized tables/views and all full record
roundtrips from 2,305 canonical YAML files. SQLite schema remains version 3.

The private evidence bundle contains 13,465 files and 197,136,605 uncompressed
bytes. Its SHA-256 is
`226693f00e93168d946ce1d381823c6ab5608d62bec78ea9a93be3b8ca5de798`.
All file hashes survived restoration into a fresh private directory. Current,
latest (including the earlier revision and cross-capture tutorial attribution)
and backup raw-source audits all pass from the restoration, with zero source
requests. The bundle stays local and is not a public asset.

The full fixture suite passes **166 tests**. Release packaging builds SQLite
from the exact committed, cache-free Git snapshot, repeats fixture/dataset QA,
requires successful CI for that commit, embeds licenses/credits/permission and
provenance, and verifies downloaded GitHub assets against local checksums before
publication. Historical states now use the eligible-ID set hash/count rather than repeating
643 IDs per label; full grammar record hashes and source checks are unchanged.
Canonical grammar content remains YAML only in Git; reader Markdown
and SQLite are generated artifacts.

Unspecified contribution dates remain null. Retrieval times, archive capture
times and feed publication events do not establish those dates. Missing original
metadata cannot be repaired by inventing timestamps. Twelve unresolved latest
labels and the two remaining original-ID gaps are documented in
[remaining work](remaining-work.md); no gap-free final live database is claimed.
