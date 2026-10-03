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

Tutorial pages, especially material credited or copyrighted to Tae Kim, remain
held for section and license review. A collection footer does not authorize
relabeling separately licensed content. Inspected newer Tae Kim pages carry
CC BY-NC-SA 2.0 notices. The scraper does not choose an older page to evade them.
Held extraction bodies are local evidence and are excluded from Git, Markdown
and the release database. The repository retains their source identities and
review states.

The backup extraction has visited every one of its 1,077 selected labels:
704 included pages containing 705 entry observations (702 distinct IDs),
310 verified exclusions and 63
held tutorial pages, with zero failed retrievals. The included observations
contain 844 notes, 5,537 examples, 3,849 comments and 912 references. They add
80 IDs absent current Takoboto. Source audits pass for all included records.
The newer supplement contains 63 verified observations; 1,347 latest indexed
labels remain unresolved.
That is different from claiming every label is eligible, every historical
revision survives, or every 2020 detail page has been extracted. The complete
Takoboto collection is captured; the latest Wayback detail supplement remains
partial. Coverage reports and the recovery ledger state the remaining work
explicitly. No gap-free final historical database is claimed.

A final cross-source check found 21 current IDs without released backup
observations. Targeted newer probes recovered 17. The remaining four current
records are fully preserved in Takoboto, with these historical limitations:

- ID 568 (`da`): a newer original page exists, but its Tutorial section is held
  for source/license review, as is the backup observation.
- ID 663 (`そう`): latest indexed responses for `そう` and the candidate alias
  `sou-2` explicitly report no entry. This establishes those label responses,
  not the absence of every earlier revision or differently named entry.
- IDs 1795 (`~ageru`) and 1797 (`temade`): no exact-label matches in the full
  Wayback inventory. A scan of all original backup URL variants also found no
  matching label or safe numeric-ID detail URL. They remain historically unresolved.

The newer `da` extraction is retained only in ignored `review-records/`;
its committed state and recovery ledger retain its source URL and hash.
Seventeen useful records were recovered by this check, without changing current
records or substituting older content as the latest version.

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
