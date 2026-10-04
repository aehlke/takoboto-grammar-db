# Section-level historical recovery

The dated backup's 63 held pages each contain a dedicated `Tutorial` cell
credited to Tae Kim. These cells are distinct from the JGram entry header,
notes, example rows, comments and annotated relationships. Newer captures, including earlier capitalized aliases, also contain these
separately credited tutorials. The separately copyrighted tutorial
bodies are excluded from the CC BY-SA 2.0 data export; the licensed JGram
material outside those cells is retained.

This is a partial source observation, not an assertion that the entire original
page has one license. Each recovered YAML record has `source_sections_complete:
false` and `omitted_sections`, with the exact source URL, response hash, original
ID and title, omitted cell HTML/text hashes, original byte offset/length/hash,
displayed or independently established credit and omission reason. The byte range includes the source cell
and trailing closing markup up to the next element outside that cell. Rebuilding
that range independently reproduces the reviewed cell's parsed HTML hash.

The source-bound decisions live in
[`section-reviews.yaml`](../src/takoboto_grammar/section-reviews.yaml), packaged
with the scraper. An exact source response, entry identity, section hash and
independently reconstructed raw byte range and isolated cell boundary are mandatory. Unknown or changed sources remain held
until reviewed. The parser refuses a cell containing a JGram example anchor or
additional entry/section headers. Source audits separately check the remaining
notes, examples, comments and references against the original source.

Tutorial text/HTML is absent from released records and reader Markdown.
Encoding-repair byte strings inside an omitted range are also excluded; their
count is retained as `omitted_source_decoding_segment_count`. A repair crossing
the section boundary requires review. This avoids retaining excluded text in
an auxiliary byte-evidence field.

SQLite retains the structured omission metadata in each archive entry's full
`record_json`. For example:

```sql
SELECT source_id, label, json_extract(record_json, '$.source_sections_complete')
FROM archive_entries
WHERE json_type(record_json, '$.omitted_sections') = 'array';
```

The ordinary build includes these resolved partial observations. Export guards
require the matching reviewed omission metadata and explicit partial marker.
Reader Markdown shows the omission notice prominently. The original complete
responses remain private local evidence, with recovery hashes and ranges; they
are not relabeled as CC BY-SA 2.0 or uploaded as public release assets.

The original JGram collection notice still applies to the included material.
For tutorial provenance, the source cell displays a Tae Kim copyright notice;
newer inspected Tae Kim pages carry CC BY-NC-SA 2.0. The project does not assert
that a collection footer supersedes those separate notices.

## Older cells without a displayed notice

The older `Hiragana` and `Katakana` cells lack a displayed Tae Kim copyright
notice. They contain long exact passages from the separately copyrighted
lowercase tutorial captures in the 2015 backup. After normalizing consecutive
whitespace to one space, source comparison proves 14 matching passages totaling
6,765 characters for `Hiragana` and eight totaling 4,810 for `Katakana`.

Their manifest entries explicitly distinguish established attribution from a
notice displayed on that response. `credit_evidence` records the reference
source URL and response/cell hashes, source and reference text offsets, passage
lengths and hashes. It contains no tutorial prose. The omission guard verifies
that the reference is another reviewed, directly copyrighted source and that
nonoverlapping source passages of at least 200 characters each match the
recorded hashes, totaling at least 1,000 characters. The retained private
source responses reproduce both sides of the comparison. Raw-source audits
load the reference responses from the sibling `archive-2015` evidence directory
and independently check the credited cell and every reference passage offset/hash. This evidence
supports excluding the tutorial cell while preserving independently bounded
JGram contributions; it does not license the tutorial for redistribution.
