# Takoboto grammar archive

A scraper and export pipeline for the public grammar collection at
[takoboto.jp/bunpo](https://takoboto.jp/bunpo/), derived from JGram.
Created by **[Alex Ehlke](https://github.com/aehlke)** with permission from
Takoboto's owner to run the scraper against the grammar section.
**Contact Takoboto and obtain your own permission before running this scraper
against the site.** The author's permission does not extend to other operators.
See [permission and operator instructions](PERMISSION.md).

Reconnaissance came first: **643 indexed entries on 13 pages** were observed
on October 2, 2026 in America/Toronto (October 3 UTC).

The complete Takoboto crawl contains **643 entries, 5,334 examples, 5,324
translations, and 4,546 comments**, plus 150 additional meaning explanations.
An independent offline audit accounts for the captured grammar content.

The supplemental JGram archive pilot contains **25 historical records**, with
40 explanatory notes, 146 examples, 115 comments, and 45 annotated references.
Fourteen of those original entry IDs are absent from Takoboto. The full Wayback
replay crawl has not been run: discovery indexed 1,414 labels, including aliases
and non-grammar pages, from 43,686 usable captures.
The five latest archived grammar RSS feeds are also preserved. Four contain
grammar excerpts and publication dates; these are feed-event dates.

Start with [the reconnaissance](docs/reconnaissance.md),
[the schema](docs/schema.md) or [Archive.org handling](docs/archive.md).
Download the **[SQLite database](https://github.com/aehlke/takoboto-grammar-db/releases/latest/download/grammar.sqlite)**
from [GitHub Releases](https://github.com/aehlke/takoboto-grammar-db/releases).
Release assets include attribution, the complete data license, permission
instructions, a build manifest and SHA-256 checksums. The database also embeds
these notices in its `metadata` table and retains contributor credits.

The release includes the complete captured Takoboto collection and a **partial
JGram archive supplement**; 1,389 indexed historical labels remain pending.

To generate reader Markdown and SQLite locally from the committed records,
without requesting either website:

```sh
git clone https://github.com/aehlke/takoboto-grammar-db.git
cd takoboto-grammar-db
uv sync --locked
uv run --locked takoboto-grammar build --input data --archive archive-data \
  --sqlite exports/local/grammar.sqlite --markdown exports/local/markdown
```

## Storage choice

Use **SQLite for the queryable dataset** and generate Markdown for readers.
Retain one JSON record per entry as the text interchange format for GitHub:
those files provide reviewable diffs and reproduce both exports offline.
Keep scraped source records separate from community corrections so subsequent
crawls cannot silently erase an edit. Correction merging is a future feature.

```text
data/
  inventory.json                 all IDs discovered through the public index
  records/725.json                extracted content, attribution, and provenance
  cache/responses/<sha256>.html   original response bytes, never executed
  cache/urls/<url-hash>.json      current response metadata
  cache/snapshots/...             previous retrieval metadata
  crawl-report.json              successes, failures, warnings, completeness
  coverage-report.json           independent offline source checks
archive-data/
  inventory.json                 complete paginated Wayback CDX discovery
  records/<label-hash>.json       separate historical source observations
  feeds/<name>.json               original RSS excerpts and publication dates
  states/<label-hash>.json        latest entry attempt and verified record hash
  feed-states/<path-hash>.json    latest RSS attempt and verified record hash
  cache/responses/<sha256>.bin    original archived bytes
  access-policy.json             robots check and request policy
  crawl-report.json              parsed, excluded, review-required, failed
  coverage-report.json           parsed-record checks and remaining labels
exports/
  grammar.sqlite
  markdown/
    README.md
    n1/<id>.md ... n5/<id>.md
    unclassified/<id>.md
    jgram/<id>-<label-hash>.md
```

Stable numeric IDs determine filenames; titles are not unique and levels can
change. Markdown folders describe the current displayed JLPT classification.

## Run

The implementation passed an initial [two-page live smoke test](recon/uv-smoke-test.json)
and now passes **87 automated tests**.
The original smoke-test exports remain local; the public release contains the
combined dataset. Raw-response caches and local QA outputs are not committed.

Use uv to manage the environment and locked dependencies. The project pins
Python 3.14; the code also supports Python 3.11+. HTTPX reuses connections and
Beautiful Soup handles the original HTML, including malformed historical pages.

**Before the live crawl commands below, contact
[Takoboto](https://takoboto.jp/) using the contact information on its website
and obtain permission for your own crawl.** The examples do not authorize site
access. Follow the agreed scope and the request limits in [PERMISSION.md](PERMISSION.md).

```sh
uv sync --locked

# Two-page smoke test: one current page and one original JGram page.
# Saved inventories avoid fetching every index page just to test the parser.
# Use fresh output directories; these requests do not reuse the old body cache.
uv run --locked takoboto-grammar crawl --inventory data/inventory.json \
  --id 725 --output smoke/current
uv run --locked takoboto-grammar archive --inventory archive-data/inventory.json \
  --label ageku --output smoke/jgram

# Export that small test offline.
uv run --locked takoboto-grammar build --input smoke/current --archive smoke/jgram \
  --sqlite smoke/export/grammar.sqlite --markdown smoke/export/markdown

uv run --locked python -m unittest discover -s tests -v

# Full current collection, when ready; discovery follows actual pagination.
uv run --locked takoboto-grammar crawl --output data
uv run --locked takoboto-grammar audit --input data

# Full original JGram supplement, with grammar RSS feeds.
uv run --locked takoboto-grammar archive --output archive-data --feeds
uv run --locked takoboto-grammar archive-audit --input archive-data

# Offline full exports: choose fresh paths for each build.
uv run --locked takoboto-grammar build --input data --archive archive-data \
  --sqlite exports/new-build/grammar.sqlite --markdown exports/new-build/markdown
```

`uv sync` creates a local `.venv`; resolve any existing environment symlinks and
use only the intended project environment. Old output directories should be
moved to `~/.Trash`, or choose a fresh path for each test/export.

Requests run sequentially in small batches, including robots checks, redirects,
and retry attempts. Cached reads consume no request slots.

| Source | Minimum interval by default | Requests per batch | Rest after batch |
| --- | --- | --- | --- |
| Takoboto | 1.5 seconds | 5 | 15 seconds |
| Archive.org | 5 seconds | 3 | 30 seconds |

Rests start after the final response in a batch completes. `--delay`,
`--burst-size`, and `--burst-pause` control the schedule. Robot crawl-delay and
request-rate rules can increase the interval. `--contact` adds an operator
contact to User-Agent. Denials, rate limits, and server Retry-After stop the run
with persisted cooldown instead of sending another batch.

`--id` and `--label` are repeatable selectors; paired with `--inventory`, they
make a small live test without another index crawl. A saved inventory can be
stale: omit `--inventory` for fresh discovery before preparing a release.
`--limit 2` limits entry bodies, but still discovers the complete index first.
`--refresh` fetches new bodies while preserving earlier raw-response snapshots;
otherwise cached runs retain their original retrieval timestamps. Raw caches
store selected response headers without cookies and remain excluded from Git.

`crawl-report.json` distinguishes a pilot from a full, warning-free crawl.
`request-report.json` records the latest invocation's individual transport
attempts; `request-reports/<run_id>.json` retains earlier reports. Statuses,
redirects, retries, timings and error types are observable without logging
headers or operator contact details. Cached reads produce no attempts.
Reports are written when the fetcher exits; abrupt process termination can
prevent the report from being saved.

Saved inventories, selectors and pacing options are checked before requests.
Both export destinations are checked before either export is created. JSON
records, cache metadata and response bodies use atomic file replacement to
preserve earlier files if replacement is interrupted. Failed temporary files
are retained for inspection; they are excluded from record reads.

The latest [review and refinement](docs/review-refinement.md) verifies all 643
stored current entries, 25 historical entries and five RSS feeds offline.
Persistent archive entry/feed states prevent an unsuccessful refresh from
silently exporting an older record. Historical records with parser, fallback
or timestamp warnings remain held for review. The archive audit checks complete
parsed fields, independent grammar membership and replay provenance; exclusions
require retained source evidence. Normal historical export requires matching
states bound to the complete record contents. The active dataset has 25 entry
states and five feed states. To migrate older captures offline, run
`uv run --locked takoboto-grammar archive-audit --input archive-data --takoboto data --record-verification`.

Individual failures and unfamiliar data blocks are reported. Review warnings
before claiming completeness. A clean limited crawl exits successfully but
has `complete: false`. A live collection can change during pagination; the
inventory is an observation, not a transactionally consistent server snapshot.

The Takoboto scraper only fetches `/robots.txt`, the unfiltered `/bunpo/` index
and its pagination, and numeric grammar detail URLs discovered through that
index or its grammar references. It never
submits contribution forms or follows dictionary, profile, or external links.

Archive requests use a separate client: one request at a time, five seconds
between starts by default, fresh robots checks, and cached raw responses.
It honors crawl delay, request rate and Retry-After; denials and rate limits
stop the run with persisted backoff. Historical observations retain their
capture dates and original classification. They do not replace current facts.
See [the archive documentation](docs/archive.md) for selection, license review,
coverage limitations, and the command for the full replay crawl.

## Attribution and license

The extracted grammar content, fixtures, and derived exports are
[CC BY-SA 2.0](LICENSE-DATA.md), following the source's published notice.
[Attribution](ATTRIBUTION.md) credits JGram, Takoboto, and displayed contributors.
The scraper code is [MIT](LICENSE-CODE).

Keep attribution and license notices with redistributed data. The JSON and
SQLite exports preserve displayed credits per entry, content block, example,
and comment; Markdown includes them too. Original contribution dates are
unknown in the inspected public pages. Retrieval dates are separate fields.
