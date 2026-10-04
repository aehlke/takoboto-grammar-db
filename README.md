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

The original ArchiveTeam JGram backup yielded **766 page captures containing
767 historical entry observations** from February 24–March 2, 2015: 846 notes,
5,554 examples, 3,886 comments and 924 annotated references. It preserves
**141 original IDs absent from current Takoboto**. All 1,077 selected backup
labels are resolved: 766 included pages and 311 verified exclusions. The 63
previous tutorial holds are recovered as explicitly partial observations.

The latest-indexed Wayback set contains **890 verified pages / 893 entry
observations**, with 944 notes, 6,085 examples, 4,356 comments and 1,007
references. All 1,414 discovered labels were attempted: 512 are verified
exclusions, 11 replays failed and one remains held for license evidence.
A separate **March 27, 2014 revision of `sou-2`** recovers original ID 663,
with two notes, six examples, two comments and five references. It is explicitly
an earlier revision; the latest no-entry response remains preserved.
Historical observations overlap current records and each other; these are not
unique-content totals. Five original grammar RSS feeds preserve four excerpts
and publication dates. Capture dates and RSS events are separate from
contribution dates.

See **[provenance and recovery](docs/provenance.md)** for backup discovery,
source hashes, encoding repairs, scope decisions and unresolved cases. Per-record
WARC offsets and hashes support independent verification.
The [deep reevaluation](docs/reevaluation.md) recovered a second original ID
inside the `katawara` capture and explains the corrected entry boundaries.

Start with [the reconnaissance](docs/reconnaissance.md),
[the schema](docs/schema.md) or [Archive.org handling](docs/archive.md).
Generate reader Markdown locally with the offline build command below.
Download the **[SQLite database](https://github.com/aehlke/takoboto-grammar-db/releases/latest/download/grammar.sqlite)**
from [GitHub Releases](https://github.com/aehlke/takoboto-grammar-db/releases).
Release assets include attribution, the complete data license, permission
instructions, provenance, a recovery ledger, a build manifest and SHA-256 checksums. The database also embeds
these notices in its `metadata` table and retains contributor credits.

The release includes the complete captured Takoboto collection and a
**partial JGram historical supplement**. There are 12 unresolved latest labels,
including corrupted aliases. Only current IDs 1795 (`~ageru`) and 1797 (`temade`)
lack a recovered historical observation; both current records are preserved.
See [remaining recovery work](docs/remaining-work.md). Separately copyrighted
Tutorial cells are omitted from 84 latest pages and 63 backup pages, with exact
source-bound omission metadata. No gap-free final historical database is claimed.

To generate reader Markdown and SQLite locally from the committed records,
without requesting either website:

```sh
git clone https://github.com/aehlke/takoboto-grammar-db.git
cd takoboto-grammar-db
uv sync --locked
uv run --locked takoboto-grammar build --input data --archive archive-data --archive-snapshot archive-2015 \
  --sqlite exports/local/grammar.sqlite --markdown exports/local/markdown
```

## Storage choice

Use **SQLite for the queryable release artifact**. Git tracks one YAML source
record per entry, together with inventories and provenance. YAML is the canonical
content format and provides reviewable diffs. Markdown and SQLite are generated
from it and excluded from Git.
See [the YAML format and migration guide](docs/yaml-format.md) for storage rules
and converting older checkouts. Indexes, verification states and request reports
remain JSON metadata; they do not duplicate the grammar records.
Keep scraped source records separate from community corrections so subsequent
crawls cannot silently erase an edit. Correction merging is a future feature.

```text
data/
  inventory.json                 all IDs discovered through the public index
  records/725.yaml                extracted content, attribution, and provenance
  states/725.json                 new-crawl attempt status and verified record hash
  cache/responses/<sha256>.html   original response bytes, never executed
  cache/urls/<url-hash>.json      current response metadata
  cache/snapshots/...             previous retrieval metadata
  crawl-report.json              successes, failures, warnings, completeness
  coverage-report.json           independent offline source checks
archive-data/
  inventory.json                 complete paginated Wayback CDX discovery
  records/<label-hash>.yaml       separate historical source observations
  feeds/<name>.yaml               original RSS excerpts and publication dates
  earlier-records/<hash>-<timestamp>.yaml   explicitly earlier indexed revisions
  earlier-states/<hash>-<timestamp>.json    independent earlier-source verification
  states/<label-hash>.json        latest entry attempt and verified record hash
  feed-states/<path-hash>.json    latest RSS attempt and verified record hash
  cache/responses/<sha256>.bin    original archived bytes
  access-policy.json             robots check and request policy
  crawl-report.json              parsed, excluded, review-required, failed
  coverage-report.json           parsed-record checks and remaining labels
archive-2015/
  inventory.json                 original ArchiveTeam index selection and hash
  records/<label-hash>.yaml       dated backup observations with WARC provenance
  states/<label-hash>.json        extraction, exclusion and review decisions
  coverage-report.json           source checks and explicit section omissions
  cache/                         local compressed index and scoped WARC members
exports/
  grammar.sqlite
markdown/                        optional generated reader files, ignored by Git
  .generated.json                managed page paths and content hashes
  README.md
  n1/<id>.md ... n5/<id>.md
  unclassified/<id>.md
  jgram/<id>-<label-hash>.md
```

Stable numeric IDs determine filenames; titles are not unique and levels can
change. Markdown folders describe the current displayed JLPT classification.

After an authorized crawl into the existing `data` and `archive-data`
directories, review the canonical YAML diffs:

```sh
git diff -- data/records archive-data/records archive-data/earlier-records archive-2015/records archive-data/feeds
git status --short
```

The crawler writes deterministic per-entry YAML. Cached observations retain
their original retrieval timestamps. `--refresh` can change retrieval metadata
even when the grammar text is unchanged, so those provenance changes also appear
in the diff. The crawler does not regenerate Markdown automatically.

For an optional local reader view, run:

```sh
uv run --locked takoboto-grammar update-markdown --input data \
  --archive archive-data --archive-snapshot archive-2015 --output markdown
```
The ignored output is derived entirely from YAML. `update-markdown` updates
only changed generated pages, preserves unchanged
files, and moves obsolete pages to a fresh directory under `~/.Trash` when
entries are removed or change level. `.generated.json` has no run timestamps.
The command checks all existing page hashes before writing and refuses to
overwrite manual edits or unmanaged files. Keep corrections separate from
these generated reader pages. SQLite builds still require a fresh filename;
publish a new database artifact for each release.

## Run

The implementation passed an initial [two-page live smoke test](recon/uv-smoke-test.json)
and now passes **166 automated tests**.
GitHub checks both Python 3.11 and 3.14, including an offline build of all
committed YAML records, with fingerprints for every normalized table and view.
Run that preservation check locally with
`uv run --locked --offline python scripts/verify_dataset.py`; see
[the contributor guide](CONTRIBUTING.md) for its scope and baseline policy.
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

# Dated original backup, separate from the latest indexed Wayback pages.
uv run --locked takoboto-grammar archive-dump --output archive-2015
uv run --locked takoboto-grammar archive-audit --input archive-2015

# Latest indexed original JGram supplement, with grammar RSS feeds.
uv run --locked takoboto-grammar archive --output archive-data --feeds
uv run --locked takoboto-grammar archive-audit --input archive-data

# Offline full exports: choose fresh paths for each build.
uv run --locked takoboto-grammar build --input data --archive archive-data --archive-snapshot archive-2015 \
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
Both export destinations are checked before either export is created. YAML
records, cache metadata and response bodies use atomic file replacement to
preserve earlier files if replacement is interrupted. Failed temporary files
are retained for inspection; they are excluded from record reads.

The [recovery ledger](recon/archive-recovery.json) records the latest source QA:
all 643 current records, 766 backup pages (767 entry observations), 890 latest
pages (893 entry observations), one earlier revision and five RSS feeds pass
their applicable checks. Source audits require local raw caches;
a fresh clone can reproduce SQLite and Markdown offline from committed records
and verification states. Persistent states block export after unsuccessful
refreshes. Same-digest older captures can establish equivalent latest content;
older different revisions remain held unless separately recovered and verified
as explicit earlier observations. Historical scope reviews are recorded in
[grammar-membership.yaml](src/takoboto_grammar/grammar-membership.yaml).

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

Keep attribution and license notices with redistributed data. The YAML and
SQLite exports preserve displayed credits per entry, content block, example,
and comment; Markdown includes them too. Original contribution dates are
unknown in the inspected public pages. Retrieval dates are separate fields.
