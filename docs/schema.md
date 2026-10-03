# Storage and schema

SQLite fits this collection because entries have many examples, each example
can have several translations, each entry can have several formations and
comments, and grammar links form a graph. A Markdown-only hierarchy cannot
represent those relationships reliably or answer queries without reparsing
prose.

Use per-entry JSON as the loss-preserving text interchange format in Git,
SQLite as the queryable build, and Markdown as the reader-friendly build.
The JSON record includes every extracted HTML/text field and observation;
SQLite also embeds it in `entries.record_json`, so SQL normalization does not
discard information. Raw response bytes live separately in a hash-addressed
cache. Database/Markdown exports require no network.

The executable schema is [schema.sql](../src/takoboto_grammar/schema.sql).
SQLite schema **3** is set in `user_version` and database metadata.
Current-source JSON remains schema **2**; legacy version 1 records can be read.
Historical records have their own `archive_schema_version: 1`.

SQLite schema **3** preserves repeated historical example IDs by keying
`archive_examples` on `(entry_key, position)`. `source_id` is original metadata
and may repeat. Current JSON schema remains 2; historical JSON remains 1.
Dated backup observations use a snapshot-qualified entry key and preserve the
complete `retrieval` and `source_decoding_segments` objects in `record_json`.
See [provenance](provenance.md) for the WARC verification and byte-preservation rules.

| Table | Key | Purpose |
| --- | --- | --- |
| `sources` | `id` | Takoboto, JGram attribution, and the declared license |
| `entries` | Numeric source `id` | Title, label, current JLPT level, meaning, entry credits, provenance, full JSON record |
| `entry_forms` | Entry + position | Additional displayed Japanese forms |
| `meaning_notes` | Entry + position | Additional explanations, language labels, text and HTML |
| `sections` | Entry + position | Meaning, formation, and any additional content blocks, HTML/text and credits |
| `formations` | Entry + position | Ordered, readable formation patterns |
| `examples` | Entry + numeric example source ID | Japanese, reading, emphasis runs, displayed credits, source order |
| `translations` | Entry + example + position | Language label, translated text/HTML, emphasis runs |
| `comments` | Entry + source position | Body HTML/text, author label, content hash, nullable source ID/dates |
| `related_entries` | Entry + position | Reference target ID, display label, and source URL |
| `metadata` | `key` | Build schema and included entry count |
| `search_documents` | SQL view | Union of entry, section, example, translation, and comment text |
| `archive_entries` | Label hash; snapshot-qualified for dated backups | Original ID, category/level, capture and retrieval dates, original/replay URLs, response hash, full JSON record |
| `archive_notes` | Historical entry + position | Original explanatory notes and displayed contributor credits |
| `archive_examples` | Historical entry + position | Japanese where exposed separately, complete example body including translations, credits and original verification classes |
| `archive_comments` | Historical entry + position | Original discussion text, HTML and credits |
| `archive_relationships` | Historical entry + position | See Also labels, annotation prose/HTML and credits |
| `archive_feeds` | Original RSS path | Latest grammar feed capture, source/replay URLs, retrieval time, hash and full source observation |
| `archive_feed_items` | Feed + position | Grammar label/verified current ID, original RSS publication date, author/creator where exposed, complete grammar excerpt |
| `archive_search_documents` | SQL view | Historical entry, note, example, comment and relationship text |

Examples use an entry-qualified key: shared global IDs are observed in the
JGram comparison, but universal global uniqueness has not been independently
established. Related targets deliberately have no foreign key constraint:
partial datasets and references to unindexed targets must be representable.
Other relationships have foreign keys and are verified during each build.

Historical IDs can match current IDs, but the two observations remain separate.
Original JGram four-level classifications are stored as source text, including
`0`, and never converted into current N1–N5. Label hashes distinguish historical
aliases without treating a spelling variant as a new verified numeric identity.
Full archived example bodies preserve translations together; separate language
and reading fields are not invented when the old layout does not expose them.
Header/extra sections, reading, archive CDX digests, selection attempts, license
evidence and nullable original dates remain in `archive_entries.record_json`.
RSS `pub_date_raw` identifies publication of a feed item. Preserve its original
timezone string and do not assign it to entry/example/comment creation dates.
Contributor labels inside the excerpt remain in body HTML/text; full source XML
and unsanitized description strings remain in the feed record JSON for auditing.

## Information rules

- Keep original numeric grammar and example IDs. Never identify entries by
  Japanese title or romanization alone; the same pattern can have multiple uses.
- Store displayed JLPT levels 1–5, or null. Do not reconstruct current levels
  from old JGram's four-level system or from index filter membership.
- Preserve exact inline Japanese text and its emphasis runs. Inserting spaces
  between DOM spans would corrupt sentences. English boundary spaces matter too.
- Treat `romanized_label` as source text, not necessarily a clean slug. For
  example, ID 1784 includes English explanation in that field.
- Keep `credits_raw` as displayed, without inferring separate accounts,
  roles, or verified creator versus editor identities.
- Keep original creation/update dates null until actual source evidence is
  found. `retrieved_at` and HTTP Date must never populate those fields.
- Use comment positions only within a source observation. The content hash
  supports comparing snapshots, but identical repeated comments remain separate.
  There is no claim of permanent comment identity or threading.
- Keep HTML fragments as well as text; plain text alone loses line breaks,
  links, and presentation cues. Strip scripts, event handlers, forms, and unsafe
  link schemes from display fragments. Preserve original bytes in the cache.
- Snapshot old responses instead of erasing evidence on refresh. The current
  JSON record is a refreshed extraction, not a claim to contain revision history.
- Do not silently omit unfamiliar content blocks. Retain them, report a warning,
  and review the parser before calling the full extraction complete.

## Example queries

```sql
-- Grammar points displayed as N4.
SELECT id, title, meaning FROM entries WHERE jlpt_level = 4 ORDER BY id;

-- Examples credited to a particular displayed name; this is string matching,
-- not verified account identity.
SELECT entry_id, source_id, japanese, reading, credits_raw
FROM examples WHERE credits_raw LIKE '%Miki%';

-- An example and all of its translations.
SELECT e.japanese, t.language, t.body_text
FROM examples e JOIN translations t
  ON t.entry_id = e.entry_id AND t.example_id = e.source_id
WHERE e.entry_id = 725 AND e.source_id = 865;

-- Comments discussing an example ID.
SELECT entry_id, position, credits_raw, body_text
FROM comments WHERE body_text LIKE '%531%';

-- Cross-reference targets not present in this export.
SELECT r.entry_id, r.target_id, r.label
FROM related_entries r LEFT JOIN entries e ON e.id = r.target_id
WHERE e.id IS NULL;

-- Simple text lookup, including discussion. SQLite LIKE works for substring
-- lookup here; Japanese morphology/tokenization needs a separate search design.
SELECT entry_id, kind, text FROM search_documents WHERE text LIKE '%ように%';
```

## Community workflow

Commit canonical JSON records, provenance manifests, attribution, and reviewed
corrections. Publish SQLite as a generated release artifact. Generate Markdown
locally for browsing or documentation hosting; keep it out of Git. Exports should use
fresh directories so changed classifications cannot leave old copies behind.

Human corrections should live in a separate overlay keyed by entry ID and,
where applicable, example ID. Comment corrections need a snapshot/content hash
anchor because source positions can shift. That overlay and its merge policy
are not implemented in version 0.3.0. Source refresh currently replaces
`records/<id>.json`; do not use those files as the only home of manual edits.

The raw-response cache is local by default. Historical response metadata and
hashes provide source auditability; a future release can include selected
grammar snapshots if desired. Old entries are not automatically deleted on
rediscovery: compare the current inventory against existing records and inspect
any differences before release. The build command exports all records present
in its input directory, including older records retained after a source change.
Historical export additionally requires matching verification states at
`states/<label-hash>.json` and `feed-states/<path-hash>.json`. States bind raw
response hashes and canonical full-record digests, so a changed record needs
source verification again. Commit these states alongside historical records.
Use `archive-audit --takoboto data --record-verification` to migrate legacy
observations offline; caches are required for that source verification.
