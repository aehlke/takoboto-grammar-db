# Canonical YAML records

Entry records live in `data/records/*.yaml`, `archive-data/records/*.yaml`
and `archive-2015/records/*.yaml`. Original RSS records use
`archive-data/feeds/*.yaml`. The packaged manual scope decisions live in
`src/takoboto_grammar/grammar-membership.yaml`.

Each observation has one canonical content file. Markdown is an optional local
rendering; SQLite is the queryable release artifact. Neither generated format
is committed to Git. Indexes, verification states, request reports and earlier
QA reports remain JSON metadata, separate from the content records.

## Formatting and preservation

The writer preserves field and list order, emits Japanese directly, and uses
literal `|`, `|-` or `|+` blocks for multiline text and HTML. Those block markers
retain the original trailing-newline count. Source trailing spaces are retained,
not trimmed. `.gitattributes` disables Git whitespace warnings for these data
paths, whose literal blocks preserve source whitespace. Carriage returns, control characters and special Unicode line
separators use quoted escapes where necessary to preserve their exact values.
Long strings are not arbitrarily rewrapped between runs.

Date-like and numeric-looking strings are quoted; IDs, positions, booleans and
null retain their original types. Quote such strings when editing YAML by hand.
The reader rejects duplicate keys and non-record types, including implicitly
constructed date objects. It uses a safe loader and validates the value tree.
Generated files avoid anchors and aliases. Every write validates a lossless
roundtrip before replacing the target. Identical serialized content leaves the
existing file and its modification time untouched.

For example:

```yaml
id: 725
romanized_label: ga-2
meaning: but, however, still
original_created_at: null
archive_timestamp: '20200215021200'
body_html: |-
  <span>Meaning with <strong>emphasis</strong>.</span>
```

Record schemas are current schema 2, historical schema 1 (single-entry pages)
or 2 (multi-entry pages), RSS schema 1 and SQLite schema 3. A multi-entry capture
keeps its additional original IDs in an `additional_entries` list inside the
same canonical file; exports expand these source components into separate rows
or reader pages. SQLite `record_json` fields remain JSON
interchange representations of the complete parsed YAML records. Verification
hashes also remain canonical JSON hashes of parsed values. YAML layout and
quoting do not invalidate source evidence or silently lift review holds.

## Older checkouts

The readers still accept legacy `.json` records. Having both `.yaml` and
`.json` for the same record is an error; one cannot silently shadow the other.
New scrape writes always use YAML and move a superseded legacy JSON file to a
fresh directory under `~/.Trash` after the YAML replacement succeeds.

Convert an existing dataset offline, without scraping:

```sh
uv sync --locked
uv run --locked takoboto-grammar migrate-yaml \
  --input data --input archive-data --input archive-2015
```

All input content is parsed and serialized before conversion begins. Source
files and existing YAML destinations are checked before replacement. Superseded
JSON files are retained together in a fresh Trash directory. If conversion is
interrupted, rerun the command; mixed directories of distinct YAML and legacy
JSON records remain readable. Already converted files are not rewritten. If interruption leaves both formats
for a record, migration retires JSON only after proving their parsed values match;
conflicting copies require review and are never resolved by choosing one silently.

After migration, review the Git diff and build fresh exports with the normal
`build` command. Source audits still require the local ignored raw caches;
offline exports need only the committed records and verification metadata.

## Earlier recovered revisions

`archive-data/earlier-records/<label-hash>-<timestamp>.yaml` stores distinct
earlier indexed observations; these do not duplicate a latest source record.
`observation_kind: earlier-indexed-revision`, `selected_indexed_timestamp`,
`latest_indexed_timestamp`, `selection_reason` and `selection_provenance` make
the distinction explicit. Independent JSON metadata in `earlier-states/` binds
the full record hash to the exact indexed capture. A latest exclusion or failed
state is preserved rather than overwritten. Ordinary builds include verified
earlier records, with distinct SQLite keys and prominent reader notices.

Historical verification states record `eligible_ids_sha256` and
`eligible_ids_count` rather than duplicating the complete current ID list per
label. The hash uses the canonical JSON digest of sorted distinct IDs; the
current canonical records reproduce that list. `current_membership_sha256`,
where present, additionally binds IDs to their exact current response hashes.
These are provenance metadata, not duplicate grammar content.
