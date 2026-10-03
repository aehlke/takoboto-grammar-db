# Releases

The public repository contains the scraper, tests, canonical extracted YAML,
historical verification states, inventories and provenance reports. Generated
Markdown, SQLite files, raw caches, local smoke tests and virtual environments
are excluded from Git.
SQLite is published as a GitHub release asset.

Run the locked test suite and build into fresh destinations:

```sh
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked --offline python scripts/verify_dataset.py
uv run --locked takoboto-grammar build --input data --archive archive-data --archive-snapshot archive-2015 \
  --sqlite exports/new-release/grammar.sqlite --markdown exports/new-release/markdown
```

Review and commit changed YAML and provenance before tagging the release.
Reader Markdown is an optional local export; do not commit generated pages.
The Markdown update command maintains its local `.generated.json`, rewrites only
changed pages and moves obsolete generated pages to `~/.Trash`. It refuses
manual edits to managed pages; keep corrections separate. SQLite exports require
a fresh filename rather than overwriting an existing release database.

Check SQLite integrity and foreign keys, roundtrip all full YAML records through the embedded SQLite JSON and
preserve displayed credits. Where raw caches are available, also run source
audits for current, newer historical and dated-backup observations. Builds need no network access. New live crawls require prior contact with
Takoboto and permission under [the operator instructions](../PERMISSION.md).

Release assets include `grammar.sqlite`, `LICENSE`, `LICENSE-DATA.md`,
`ATTRIBUTION.md`, `PERMISSION.md`, `provenance.md`, `archive-recovery.json`,
`release-manifest.json` and `SHA256SUMS`.
Releases after the multi-entry correction distinguish 704 backup page captures
from 705 original entry observations. Historical source schemas 1 and 2 coexist;
SQLite remains schema 3. Use the current dataset/table baselines rather than
the earlier YAML migration report when checking new releases.
The manifest records the source commit, counts, verification results and pending
historical coverage. Checksums cover the database, manifest and notices.

The released database's `metadata` table additionally embeds the complete data
license, attribution and permission notices, repository URL, release tag and
source commit, provenance text and recovery ledger. These packaging fields do not change any source records or
normalized grammar tables. An ordinary offline build reproduces the grammar
tables; release packaging adds these notices to the metadata.

Describe partial historical coverage explicitly in the release notes. Exclude
records held for warnings or conflicting license evidence. Upload the assets to
a draft release, verify the tag and asset checksums, then publish the release.
