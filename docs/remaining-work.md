# Remaining recovery work

This reassessment uses the committed inventories, records and per-label states
at data-release commit `989ae840c9c4391542c4ba5a366f13efa83f00a1`, plus retained
local review evidence. It made no requests to Takoboto or Archive.org.
The v0.5.0 release is public; its source data and database are unchanged by this
assessment. The current Takoboto capture contains all 643 indexed entries.

## Latest original JGram revisions: the main unfinished work

The latest inventory contains 1,414 labels. Saved newer crawl states cover 68:
63 parsed, four verified exclusions and one review hold. **1,346 labels have no
saved per-label crawl state**, so they must not be described as 1,346 proven
inaccessible pages. Research probes outside the stateful crawler may have
observed some URLs; absence of a state does not establish absence of every
prior request. The one held label is `da` (original ID 568).

The 1,347 unresolved latest labels break down against the dated backup as follows:

| Dated-backup evidence for the same label | Labels | What remains |
| --- | ---: | --- |
| Released 2015 page | 659 | Retrieve and verify the latest indexed content; older content is already preserved. |
| Verified 2015 exclusion | 307 | Check the latest response before extending that older classification. |
| Held 2015 tutorial page | 63 | Review section boundaries and license evidence; a newer revision may differ. |
| No selected 2015 label | 318 | Try indexed newer captures and check aliases or differently named entries. |
| Total | 1,347 | These are URL labels, not a count of missing unique grammar entries. |

Sources: `archive-data/inventory.json`, `archive-data/states/`, both historical
coverage reports and the released backup records. The next recovery run should
use the existing archive command and its pacing, robots checks, persisted
backoff and resumable caches. Do a bounded batch first, then continue the full
latest inventory. Discovery alone is not a completed replay crawl. An older
response can establish latest-content equivalence only with the existing raw
payload digest proof. Changed older revisions must stay identified as older.

## Held tutorials: review sections rather than guessing eligibility

All 63 active backup holds have the unfamiliar `Tutorial` section. For `da`,
the retained source contains an explicit Tae Kim copyright notice, alongside
ordinary JGram notes, examples and comments. Inspected newer Tae Kim material
has a CC BY-NC-SA 2.0 notice. The collection footer alone does not settle that
section's license. Review the 63 sources individually and record the section
boundaries, displayed credits and any conflicting license evidence.

Potential recovery includes retaining independently supported JGram material
while explicitly excluding a separately licensed section. Implementing this
needs section-level provenance, an omission manifest and source-audit support;
it must not merely clear a warning or silently drop content. Some tutorials
may remain outside this CC BY-SA 2.0 release after review.

There are 65 local backup review files, but only 63 active holds. The old
`kanenai` and `toiumonodehanai; toiumonodemonai` undecodable-byte extractions were
superseded by verified encoding repairs and now have parsed states and released
records. Their retained review files are historical evidence.

## Four current IDs lack a released historical observation

All four have their current Takoboto content preserved:

- **568 (`da`)**: a historical source is retained; tutorial review blocks release.
- **663 (`そう`)**: the latest `そう` and candidate `sou-2` responses report no
  entry. Check earlier revisions and alternative labels; these responses do not
  establish that the entry never existed.
- **1795 (`~ageru`) and 1797 (`temade`)**: no exact-label matches in the full
  inventory or matching safe numeric-ID detail URLs in the backup index.
  Investigate other exports, mirrors, title/reference matches or surviving dumps.
  Any proposed match must have evidence; similar titles alone are insufficient.

The earlier targeted cross-source investigation recovered 17 other current IDs.
See `recon/archive-recovery.json#cross_source_gap_check` for source hashes and
precise decisions. No full SQL dump was found in the targeted searches already
recorded; this does not prove that none survives elsewhere. Existing summary
TSV exports omit discussion and attribution and cannot replace detail records.

## Evidence and fields that remain limited

The clean repository reproduces YAML and normalized SQLite and checks them
against preservation baselines. Re-auditing original HTML requires retained raw
caches or recovery of the exact hashed responses. Historical WARC byte ranges,
member hashes and index hashes are recorded; raw caches are not release assets.
Keep that original evidence safely backed up, and improve retrieval/re-audit
instructions where needed. A fresh current-site request may return changed data.

Original contribution dates remain unknown where sources do not display them.
Archive timestamps, retrieval times and RSS publication dates cannot fill those
fields. This limitation should remain explicit rather than becoming guessed data.

Priority is: complete the latest replay crawl, review the tutorial boundaries,
then pursue earlier/alternate sources for the four historical-ID gaps. Additional
parser review should follow any newly encountered source structures; another
unchanged fixture run cannot resolve missing source coverage.
