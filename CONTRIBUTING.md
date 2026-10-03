# Contributing

Use issues or pull requests to report parser defects, missing source fields or
improvements to the exports. Include the relevant grammar ID or archived label
and describe the source evidence. Keep displayed contributor credits intact.

Before running any live Takoboto crawl, contact Takoboto and obtain your own
permission, as explained in [PERMISSION.md](PERMISSION.md). The project author's
permission does not cover other operators. Prefer the committed records and
offline fixtures for development.

```sh
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked takoboto-grammar build --input data --archive archive-data \
  --sqlite exports/dev/grammar.sqlite --markdown exports/dev/markdown
```

Choose fresh export paths. Raw caches are local and excluded from Git; source
audits need those retained bytes and cannot run from a records-only checkout.
The unit tests and export command work without crawling either site.

Keep human corrections separate from scraped records so refreshes cannot erase
them. A correction overlay is not yet implemented; discuss proposed changes in
an issue rather than presenting an edited source record as a verified capture.

Contributions to code follow [MIT](LICENSE-CODE). Grammar data and adaptations
follow [CC BY-SA 2.0](LICENSE-DATA.md), with attribution and notices of changes.
