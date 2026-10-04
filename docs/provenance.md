# Provenance and recovery

This repository preserves separate observations of the JGram-derived grammar
collection. It does not combine differently dated pages into an invented final
version. Contributor labels and source order are retained; archive dates are
capture dates, not contribution dates.

## Sources

| Source | Observation dates | Evidence in the repository |
| --- | --- | --- |
| [Takoboto grammar](https://takoboto.jp/bunpo/) | Retrieved October 3, 2026 UTC | `data/inventory.json`, `data/records/`, `data/coverage-report.json` |
| [Original JGram via Wayback](https://web.archive.org/web/2020/http://jgram.org/) | Per-page indexed captures, 2005–2020 | `archive-data/inventory.json`, `archive-data/records/`, states and coverage report |
| [ArchiveTeam JGram backup](https://archive.org/details/archiveteam_archivebot_go_20150302130001) | February 24–March 2, 2015 | `archive-2015/inventory.json`, `archive-2015/records/`, states and coverage report |
| Original grammar RSS | Latest retained captures, July 2020 | `archive-data/feeds/` and feed verification states |

[recon/archive-recovery.json](../recon/archive-recovery.json) records discovery,
checksums, recovery counts and unresolved cases. The original source HTML and
compressed WARC members are cached locally, outside Git. The public records
include enough source identity, offsets and hashes to retrieve their evidence.

## Original backup discovery

The JGram export navigation linked `/pages/export.php?limit=0&level=&x=Build`.
Its [December 2, 2020 capture](https://web.archive.org/web/20201202121641id_/http://jgram.org/pages/export.php?limit=0&level=&x=Build)
survives and displays a dictionary-style summary export. It does not contain
the complete notes, discussion, contributor credits or revision history.
Some archived downloadable TSV files are empty; a nonempty 2015 TSV is only a
partial summary. These files are research evidence, not a replacement for the
detail-page collection.

The nonempty TSV replay exposed the original ArchiveTeam WARC filename in
`x-archive-src`. The [Internet Archive item metadata](https://archive.org/metadata/archiveteam_archivebot_go_20150302130001)
then identified a full website backup and its companion CDX index:

| File | Bytes | Published SHA-1 |
| --- | ---: | --- |
| `jgram.org-inf-20150224-175105-5bi1u-00000.warc.gz` | 5,281,178,690 | `758a7dc751afe9a531dedd9f747de7d78edd46a0` |
| `jgram.org-inf-20150224-175105-5bi1u-00000.warc.os.cdx.gz` | 67,021,044 | `83a1a76f708c5b41dcc9975b9928aba4b94b1f9a` |

The downloaded index's SHA-256 is
`4fb4709e7d691ca2b3605e56bfefd7dde3fb7876154240e66311a8da267b9aed`.
Its 1,069,710 rows yielded 1,312 scoped successful HTML captures for 1,077
entry labels. The large row count reflects the website crawl, not a million
grammar entries. The scraper selects the latest indexed capture of each label
**within this backup**. It does not call that the last online JGram revision.

Only `/pages/viewOne.php` with one nonempty `tagE` and an optional valid date
parameter is eligible for retrieval. The backup scraper coalesces nearby
indexed members into ranges of at most 20 MiB. It fetches roughly 42 MiB in
71 ranges instead of downloading the 5.3 GB website container. It extracts and
retains only the scoped member bytes; unrelated intervening bytes are discarded.
Neither other site sections nor linked external material are imported.

## Per-observation proof

Every original backup record contains:

- `snapshot`: `archivebot-2015-02`, identifying the crawl that started in February.
- Original `source_url`, accessible Wayback `archive_url`, original entry ID,
  capture timestamp, retrieval timestamp and body SHA-256.
- `retrieval.method`: `archive-item-warc-range`, with the actual archive download
  URL, member byte offset and compressed length, index SHA-256 and member SHA-256.
- The original CDX/WARC SHA-1 payload digest in `archive_digest`.
- Original displayed contributor credits for notes, examples, comments and links.

`archive-dump` validates the exact HTTP 206 range and response length, gzip
integrity, WARC target URI and timestamp, WARC block length/hash, original HTTP
status/length, and payload hash against both WARC and CDX. `archive-audit`
recreates inventory membership from the original index and rechecks cached
members independently before checking the extracted contributions.

The historical `source` namespace is `jgram-wayback`; the `snapshot` and
`retrieval` fields distinguish acquisition from the original ArchiveTeam backup.
SQLite retains the complete record JSON in `archive_entries.record_json`.
Snapshot and newer observations have distinct deterministic keys and Markdown
paths, even when the original numeric ID and label agree.

## Decoding and original defects

Most pages declare Shift-JIS. Windows CP932 extensions are accepted when strict
Shift-JIS fails and CP932 succeeds. A text node is interpreted as UTF-8 only when
strict CP932 fails and strict UTF-8 succeeds. Invalid URL bytes are preserved by
percent-encoding the original bytes. Remaining invalid text bytes display as
U+FFFD without guessing their intended character.

For each UTF-8 text-node, URL-byte or invalid-text transformation,
`source_decoding_segments` stores the original
byte offset, length, exact bytes in hexadecimal and the decoding rule. This
preserves malformed source text as well as its readable representation. Records
with invalid original text explicitly say so in the reader Markdown. Source
response hashes always cover the original bytes, before display transformations.

Repeated original example IDs are preserved as separate occurrences in source
order. SQLite schema 3 keys historical examples by `(entry_key, position)`;
`source_id` remains the original ID and can repeat. Current records remain schema
2. Single-entry historical pages use schema 1; multi-entry pages use schema 2.

The `katawara` backup response displays two original IDs, 1274 and 1649, with
different meanings, JLPT levels and authors. Historical schema 2 keeps the first
entry plus `additional_entries` in one canonical YAML capture file, with
`page_entry_position` identifying each source table. Both entries carry the
same original response/WARC evidence. SQLite and reader Markdown expand the
components into separate entry observations. Notes, examples and comments are
scoped to their respective source table; repeated displayed contributions are
preserved as source occurrences. See [the reevaluation](reevaluation.md).

## Selection, scope and unresolved evidence

Wayback discovery retains 5,154 repeat captures formerly discarded during
digest deduplication. Recovery tries up to three observations of each of up to
three distinct revisions. An older capture counts as equivalent latest content
only when its indexed identity matches and its raw payload SHA-1 equals the
latest CDX digest. Older *different* content still requires review. Failed
attempts, actual replay timestamps and source observations are retained.

The old labels `-oku`, `juu` and `teshouganai` were investigated using original
IDs and licensed successor pages: `oku` (1350), `juu/chuu` (739), and
`teshouganai; tetamaranai` (540). All 11 old `-oku` example IDs and the old
`juu` example ID occur in the licensed successor observations. Matching an ID
does not assert that every old wording or comment is unchanged.

An explicit, source-bound “No entry exists” response is distinguished from a
transport error. Non-grammar categories are excluded. An unclassified entry
whose ID lacks independently verified grammar membership is held for scope
review rather than silently counted as outside the collection.

Eleven unclassified records absent Takoboto were inspected in newer replays.
Nine contain grammar/usage explanations and were included in both observations:
`Gerrund form of Verb + nakade`, `ano`, `ittai`, `nidoto`, `gosinpainaku`,
`teshimaimashita`, `gokensonwo`, `gomottomo` and `ha-3`. Two dictionary-only
entries, `ryuu` and `manten`, were excluded; `ryuu` also has an explicit moderator
note identifying it as dictionary material scheduled for deletion.
[The scope manifest](../src/takoboto_grammar/grammar-membership.yaml) records
each reason, original ID/label, exact reviewed title, source URL, timestamp
and raw response hash. Automated reuse requires matching ID, label and title
and still applies the source license check.

Exact capture-specific section review now excludes separately copyrighted
Tae Kim Tutorial cells while preserving independently bounded JGram material.
There are 84 partial latest-indexed pages and 63 partial backup pages. The
[section manifest](../src/takoboto_grammar/section-reviews.yaml) records response,
cell and raw-byte hashes, entry identity, credit evidence and omission reasons.
Unknown or changed cells remain held. Original complete responses remain private
and are not relabeled as CC BY-SA 2.0. See [section review](section-review.md).

The dated backup has 766 included pages / 767 entry observations (764 distinct
IDs), 311 verified exclusions and no active holds or failed retrievals. Its
846 notes, 5,554 examples, 3,886 comments and 924 references are source-audited;
141 IDs are absent from current Takoboto. The exact `newSiteFB` administration
thread is excluded from both source sets after semantic review, correcting its
misleading grammar category. The previous public release remains immutable.

All 1,414 latest-indexed labels have saved attempt states: 890 parsed pages / 893
entry observations (789 distinct IDs), 512 verified exclusions, 11 failed replays
and one missing-license hold (`-oku`). The included latest pages contain 944
notes, 6,085 examples, 4,356 comments and 1,007 references. Of their original IDs,
149 are absent current Takoboto. Labels and overlapping captures are not unique
grammar-entry or contribution counts. See [the recovery follow-up](recovery-followup.md).

**Original ID 663 (そう) is recovered from the March 27, 2014 `sou-2` revision.**
The 2017 and 2019 revisions inspected after the latest response also report no
entry. The earlier record has two notes, six examples, two comments and five
relationships. Its selected SHA-1 matches the indexed payload and its original
source bytes reproduce the extraction. It is stored in `earlier-records/`, with
an independent `earlier-states/` verification record. The full latest inventory,
latest timestamp and latest exclusion state remain unchanged. The database key
and reader notice distinguish an earlier revision from a latest observation.
See [earlier-revision evidence](../recon/earlier-revisions.yaml).

Current IDs 1795 (`~ageru`) and 1797 (`temade`) still lack historical observations.
Their current Takoboto records are preserved. Full label/index checks, source
example-ID comparisons and investigated mirrors/dumps did not establish matches.
The old Takoboto mirror redirects to the current index. Yookoso's 2021 statement
about a retained database is a concrete surviving-copy lead; its public article
provides no download. An [unsent request](source-outreach.md) is available.
No contact has been sent. See [source leads](../recon/source-leads.yaml).

The held 2005 `-oku` page links `/pages/copyright.php`, but the bounded exact
CDX query through 2005 returned no successful notice capture. It remains held;
all eleven original example IDs also occur in licensed successor `oku` records,
which does not prove every historical wording/comment unchanged. Failed replays
remain distinct from explicit no-entry responses. An encoding correction matches
such responses against exact original URL parameter bytes, without reconstructing
characters lost in a decoded label. Unknown contribution dates remain null.

## Reproduction and access policy

```sh
# Recover the fixed original backup, with a fresh robots check per origin.
uv run --locked takoboto-grammar archive-dump --output archive-2015 \
  --contact https://github.com/aehlke/takoboto-grammar-db

# Cached member extraction is resumable and can run entirely offline.
uv run --locked takoboto-grammar archive-dump --output archive-2015 --offline
uv run --locked takoboto-grammar archive-audit --input archive-2015 --takoboto data
```

Backup requests are sequential: five seconds between starts, then a 30-second
rest after every three requests. Redirects and policy requests count. Robots
rules, advertised delay/rate and Retry-After are respected. Access/rate-limit
responses and server failures stop with persistent backoff. Exact ranges are
mandatory; a server that ignores Range is stopped before its body is read.
No Save Page Now, proxy rotation, authentication or restriction bypass is used.
ArchiveTeam and Internet Archive are credited as preservation providers, not
as licensors of the original grammar. The original CC BY-SA 2.0 attribution and
[Takoboto permission requirements](../PERMISSION.md) continue to apply.

## YAML storage migration

Version 0.4.0 stores canonical entry and RSS records as YAML, with literal
blocks for multiline text/HTML, stable field order and quoted ambiguous strings.
The conversion preserves every parsed value, source URL, original byte segment
and provenance hash. Legacy JSON content files were moved to Trash and removed
from the repository tree; no parallel JSON copies are tracked. Inventories,
verification states and request reports remain machine JSON metadata.
That migration report describes the conversion snapshot. The subsequent
`katawara` correction intentionally changes one extraction digest while
preserving its original source-byte evidence; it is documented separately.

Record verification hashes still use the canonical JSON representation of the
parsed values, independent of the on-disk YAML formatting. SQLite still embeds
complete JSON records. Both representations are checked against pre-migration
values; changing file format does not create a new source observation.
See [YAML format](yaml-format.md) and [migration QA](../recon/yaml-migration.yaml).

Section-level tutorial decisions are documented in [section review](section-review.md).
Private original-source backup and restoration are documented in [evidence preservation](evidence.md).
