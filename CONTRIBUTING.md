# Contributing

Use issues or pull requests to report parser defects, missing source fields or
improvements to the exports. Include the relevant grammar ID or archived label
and describe the source evidence. Keep displayed contributor credits intact.

For source research, start with the [public recovery backlog](docs/remaining-work.md#public-recovery-backlog).
Each issue records the evidence already checked and what would resolve the gap.

Before running any live Takoboto crawl, contact Takoboto and obtain your own
permission, as explained in [PERMISSION.md](PERMISSION.md). The project author's
permission does not cover other operators. Prefer the committed records and
offline fixtures for development.

```sh
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked --offline python scripts/verify_dataset.py
uv run --locked takoboto-grammar update-markdown --input data \
  --archive archive-data --archive-snapshot archive-2015 --output markdown
git diff -- data/records archive-data/records archive-data/earlier-records archive-2015/records archive-data/feeds
uv run --locked takoboto-grammar build --input data --archive archive-data --archive-snapshot archive-2015 \
  --sqlite exports/dev/grammar.sqlite --markdown exports/dev/markdown
```

Choose fresh export paths. Raw caches are local and excluded from Git; source
audits need those retained bytes and cannot run from a records-only checkout.
The unit tests and export command work without crawling either site.

Canonical grammar content is committed as YAML; generated reader Markdown under
`markdown/` is ignored. Its local hash manifest makes offline
updates repeatable: unchanged pages are not rewritten, and obsolete generated
pages move to `~/.Trash`. Manual edits to generated pages stop the update rather
than being overwritten. Review source YAML and provenance changes in pull
requests. SQLite remains a generated release asset.

GitHub runs the fixture tests and full offline dataset verification on Python
3.11 and 3.14 for pushes and pull requests. The verifier blocks network
connections, checks published snapshot hashes, reads historical verification
states, and builds a fresh SQLite export with integrity, foreign key, license,
count and complete record roundtrip checks. It also compares every normalized
table and search view against an independently reviewed SQLite baseline, so
intact `record_json` cannot hide a broken normalized column.
It retains the temporary export for
inspection and never writes source records. Raw-cache source audits remain a
separate check.

The current check uses the verified snapshot in `recon/dataset-baseline.yaml`
and table/view fingerprints in `recon/sqlite-baseline.yaml`.
For an intentional new capture, add a new report with audited counts and
`record_digests` for the current, newer, backup and feeds groups, plus
`canonical_yaml_files` (page files can contain several entry observations).
Review the normalized SQLite changes and update its baseline as well. Select
new reports with `--baseline` and `--sqlite-baseline` in the workflow. Preserve earlier QA
reports and include source evidence and coverage changes in the pull request.
Changing the baseline alone does not establish new source provenance.

Keep human corrections separate from scraped records so refreshes cannot erase
them. A correction overlay is not yet implemented; discuss proposed changes in
an issue rather than presenting an edited source record as a verified capture.

Contributions to code follow [MIT](LICENSE-CODE). Grammar data and adaptations
follow [CC BY-SA 2.0](LICENSE-DATA.md), with attribution and notices of changes.
