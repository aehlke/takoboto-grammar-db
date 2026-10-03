# Original JGram supplement

The scraper supplements current Takoboto records with original JGram pages
held by the Internet Archive Wayback Machine. Targeted searches of GitHub
repositories and Archive.org item metadata did not locate a complete grammar
dump. This was a limited search, not proof that no dump exists.

## Discovery and latest-version selection

The official [Wayback CDX API documentation](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server)
describes the index used here. Five paginated responses, following opaque
resume keys, yielded **43,686 usable captures and 1,414 canonical labels**.
The canonical domain query covers JGram and its www/http/https variants.
Only successful HTML or revisit captures of `/pages/viewOne.php` are selected.

Replay URLs must contain one nonempty `tagE`, optionally a date-only query
parameter. Reassessment found 50 date-query captures; their labels were already
indexed and none was newer than its corresponding ordinary URL. Mutation
queries, including four archived deletion URLs, are excluded. Empty labels and
malformed query names are not treated as entries.

For each label, sort captures newest first and retain the newest capture per
distinct body digest. Do not use CDX collapse options to select the latest:
they can retain the earliest capture. A missing/error replay can fall back
through up to three distinct bodies, with explicit attempts and an audit
warning. Redirects retain the actual capture timestamp and are flagged if it
differs; redirects to a different label fail validation.
Records with fallback, timestamp or parser warnings are retained as evidence
with `review_required` states and cannot be exported. Legacy warning-bearing
records are also rejected even if an older state says `parsed`. Resolve the
source/parser discrepancy and obtain a clean extraction before exporting;
offline verification does not remove these holds.

This selects each entry's latest indexed successful replay, not a synchronized
snapshot of the final live database. Latest indexed times range from April
2005 through December 2020. 641 current Takoboto labels have an exact index
match; `~ageru` and `temade` do not. Aliases, malformed labels, non-grammar pages,
and inaccessible captures remain in discovery until replay/classification.
Do not interpret 1,414 labels as 1,414 verified grammar entries.

## Dataset boundary and license checks

Original categories `grammar` and `lesson` are included: the latter contains
conjugation tables and comparisons such as `simultaneous-actions-group` and
`evaluation-group`. A verified current Takoboto numeric ID also establishes
collection membership when an old category is absent. Other categories are
excluded. Standalone notes, complete examples/translations, comments, contributor
labels, annotated See Also links, original readings/levels and retained header
sections are part of each separate source observation.

A replay must display CC BY-SA 2.0 without an additional conflicting Creative
Commons notice. Missing/changed/mixed notices produce `review_required`, retain
cached evidence, and export no new record. Older versions are not substituted
to avoid such a notice. Two inspected Tae Kim pages, `Introduction` and
`HonorificAndHumbleForms`, contain separate **CC BY-NC-SA 2.0** notices and
remain outside the CC BY-SA export. This check is evidence handling; a footer
notice alone does not establish the origin of every linked external work.

No dictionary, user profile, edit endpoint, external lesson site, or linked
third-party asset is fetched. Grammar-content assets or date metadata found
by the audit require review; raw responses preserve the evidence.

## Grammar RSS metadata

The five original grammar feed URLs (`updates.xml` and `jlpt1.xml` through
`jlpt4.xml` under `/rss/`) were discovered in source markup and checked
separately. Their latest successful captures are from July 13, 2020. The
updates feed is empty, while each JLPT feed has one full grammar excerpt:
**madashimo, gatai, wake, and he**. The excerpts include explanations, examples
and discussion with contributor labels. XML, original description HTML and
sanitized reader HTML are preserved alongside the ordinary detail records.

These four items carry original `pubDate` strings on **November 20, 2019 PST**.
They supply publication metadata absent from the detail pages, but do not
establish when any individual example/comment was written or edited. The
source dates therefore remain separate `pub_date_raw` feed-event fields.
Original per-contribution creation/update fields remain null.
Explicit RSS `author` and Dublin Core `creator` values, when present, also
appear in Markdown. They remain displayed labels rather than inferred accounts.

Feed bodies are exported only for labels verified against current grammar
records or successfully reviewed historical grammar observations. Historical
records with a persistent hold do not establish feed eligibility. Unknown
labels or conflicting item/channel licenses require review, including notices
such as `CC-BY-NC-SA-2.0` written with hyphens rather than spaces. RSS
captures have the same cache, pacing, redirect, robots and backoff rules. Exact
replay URLs must agree with the claimed original URL and capture timestamp and
remain within the five grammar feed paths. Valid feed redirects preserve the
actual original URL and timestamp; timestamp changes require review. Exact
feed CDX queries fail rather than claim latest selection if their 10,000-row
bound is reached; all five observed histories were smaller than that bound.
This covers each latest feed, not its entire historical sequence of items.

## Archive.org request behavior

- GET requests only, one at a time, with five seconds between request starts,
  including redirects; CLI delay cannot be lower than three seconds. After every
  three network requests, rest for 30 seconds from response completion.
  `--burst-size` and `--burst-pause` configure the batch and rest.
- Check `web.archive.org/robots.txt` on each online invocation and obey advertised
  exclusions, crawl delay and request rate. At inspection it returned 404;
  that response is recorded. Missing robots with 404/410 is distinguished from
  server failure. `archive.org/robots.txt` was also inspected during research.
- Identify the scraper in User-Agent; `--contact` can add an operator contact.
- Stop immediately on 401/403/429 and persist at least five minutes of backoff,
  respecting longer Retry-After values. Server Retry-After also stops and persists
  backoff. Timeouts/server errors have bounded retries with 10/20-second waits;
  exhausted server retries stop. Do not restart while cooldown is active.
- Reuse hash-checked cached bodies. Preserve original bytes, retrieval/capture
  times, response hashes and selected provenance headers; do not retain cookies.
- No Save Page Now, origin fallback, authentication, proxy rotation, or attempts
  to bypass restrictions. Offline mode never makes network requests.

## Verified output and remaining coverage

The live pilot parsed **25 records**: 11 original IDs overlap current Takoboto,
and **14 original IDs are absent there**. Thirteen are category `lesson`.
The records contain **40 notes, 146 examples, 115 comments and 45 annotated
relationships**. These counts are historical observations; many examples and
comments also exist in current records and must not be summed as unique content.

For [ageku](https://web.archive.org/web/20200215021200id_/http://jgram.org:80/pages/viewOne.php?tagE=ageku),
the supplement recovers six original explanatory notes and three annotated
relations. Takoboto does not display those standalone notes and keeps only its
sueni relationship. One recovered note, “Often used with さんざん,” is credited
to MightyAtom. Original contribution dates were not exposed in the pilot.

Both source audits pass for stored records. **The full replay crawl is pending**:
1,389 indexed labels lack extracted records, including the two license-review
pages. Additional probes of `-oku`, `juu` and `teshouganai` encountered missing
license evidence or unavailable/non-entry replays; their cached responses
remain available for investigation. Eligibility and historical completeness
cannot be asserted for unparsed labels.

## Commands

```sh
# Full discovery and replay crawl; cached work resumes without refetching.
# Allow roughly five hours at default pacing with batch rests, plus latency/retries.
uv run --locked takoboto-grammar archive --output archive-data --takoboto data
uv run --locked takoboto-grammar archive-feeds --output archive-data --takoboto data

# Or add --feeds to archive to run both supplements in one invocation.

# Select only known indexed labels for a bounded probe.
uv run --locked takoboto-grammar archive --output archive-data \
  --label ageku --label simultaneous-actions-group

# Reparse a known cached selection with no network activity.
uv run --locked takoboto-grammar archive --output archive-data --offline --label ageku
uv run --locked takoboto-grammar archive-feeds --output archive-data --offline

# Source audit and offline migration of older records without verification states.
uv run --locked takoboto-grammar archive-audit --input archive-data \
  --takoboto data --record-verification
uv run --locked takoboto-grammar build --input data --archive archive-data \
  --sqlite exports/new-build/grammar.sqlite --markdown exports/new-build/markdown
```

Reports distinguish parsed, excluded, license-review, failed and warning states.
Persistent `states/<label-hash>.json` and `feed-states/<path-hash>.json` retain
the latest attempt status across selected runs. A pending hold is written before
retrieval; unsuccessful refreshes keep earlier evidence but block normal export
of that older observation. Normal export requires a state bound to the complete
record contents. Legacy records remain readable for auditing and require the
offline `archive-audit --record-verification` migration before export. Migration
checks retained source bytes, current membership evidence and the latest cached
URL observation; it does not lift existing holds. `--takoboto` supplies captured
current pages for independent ID and RSS-label eligibility checks.
Exclusions count toward audit completeness only when the latest retained response
reproduces their classification and the replay URL, original URL and timestamp
agree. See the [latest review](review-refinement.md).
A selected or limited run never claims completeness for the full inventory.
An audit passing for stored records does not mean historical discovery has
been exhausted. Builds export all records currently stored in both directories;
inspect reports and retained older observations before preparing a release.
