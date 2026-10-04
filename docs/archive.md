# Original JGram supplement

The scraper preserves current Takoboto, latest available original JGram
Wayback pages and a **dated original ArchiveTeam WARC backup**. The backup
was discovered through an archived export's `x-archive-src` header, then verified
against [Internet Archive item metadata](https://archive.org/metadata/archiveteam_archivebot_go_20150302130001).
It is a website capture rather than an SQL dump. Export summaries alone omit
notes and discussion. See [provenance](provenance.md) and the
[recovery ledger](../recon/archive-recovery.json) for the investigation.

The backup is stored separately in `archive-2015/`: 766 included pages / 767
entry observations, 311 verified exclusions and no active holds out of 1,077
selected labels. Its 63 formerly held tutorial pages are explicitly partial:
separately copyrighted cells are omitted with exact source proof. Snapshot
selection is latest **within February 24–March 2, 2015**, and does not establish
the final live version. Hash-checked bounded WARC ranges avoid downloading the
unrelated website container. `archive-dump` obeys fresh robots checks on every
archive origin, five-second spacing and 30-second rests after three requests.
An exact 206 byte range is mandatory.

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

For each label, sort captures newest first and retain distinct revisions plus
repeat observations of the same digest. Try up to three observations of each of
up to three distinct revisions. An older replay can establish the latest content
only when its indexed identity and raw SHA-1 agree with the newest CDX digest.
An older different body retains a hold. Redirects preserve actual timestamps;
a changed label fails validation and an unindexed redirect cannot establish
equivalence. Parser, licensing and fallback discrepancies remain blocked until
resolved against source evidence. Selection attempts are retained.

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
collection membership when an old category is absent. Nine additional unclassified grammar/usage entries were reviewed individually
and included; two dictionary-only entries were excluded. The source-bound
[scope manifest](../src/takoboto_grammar/grammar-membership.yaml) records IDs,
labels, exact titles, reasons, source URLs and response hashes. Unknown
unclassified entries remain held. Other categories are excluded. Standalone notes, complete examples/translations, comments, contributor
labels, annotated See Also links, original readings/levels and retained header
sections are part of each separate source observation.

A replay must display CC BY-SA 2.0 without an additional conflicting Creative
Commons notice. Missing/changed/mixed notices produce `review_required`, retain
cached evidence, and export no new record. Older versions are not substituted
to avoid such a notice. Two inspected Tae Kim pages, `Introduction` and
`HonorificAndHumbleForms`, contain separate **CC BY-NC-SA 2.0** notices and
now have reviewed partial observations: the separately copyrighted cells remain
outside the CC BY-SA export. See [section review](section-review.md). This check
is evidence handling; a footer
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

The latest set contains **890 pages / 893 entry observations** (789 distinct
original IDs), with **944 notes, 6,085 examples, 4,356 comments and 1,007
references**; 149 IDs are absent current Takoboto. All 1,414 labels were attempted:
512 exclusions, 11 failed replays and one license hold (`-oku`) accompany the
890 pages. The separate backup contains **766 pages / 767 entry observations**
(764 distinct IDs), with **846 notes, 5,554 examples, 3,886 comments and 924
references**; 141 IDs are absent Takoboto. Historical observations overlap and
must not be summed as unique contributions.

A separate earlier revision of `sou-2`, captured March 27, 2014, recovers original
ID 663 with two notes, six examples, two comments and five relationships. Later
revisions report no entry. `earlier-records/` and `earlier-states/` preserve the
selection without replacing the latest state. Earlier records bind to the full
inventory's latest timestamp and the exact selected capture/digest, and have
independent raw-source audits. Their SQLite keys and reader notices distinguish
them from latest observations. Ordinary offline builds include this record.

For [ageku](https://web.archive.org/web/20200215021200id_/http://jgram.org:80/pages/viewOne.php?tagE=ageku),
the supplement recovers six original explanatory notes and three annotated
relations. Takoboto does not display those standalone notes and keeps only its
sueni relationship. One recovered note, “Often used with さんざん,” is credited
to MightyAtom. Original contribution dates were not exposed in the pilot.

All source audits pass for exported records, including the separately selected
earlier revision. All dated-backup labels are resolved for the included scope.
Twelve latest labels remain unresolved, and only current IDs 1795 (`~ageru`) and
1797 (`temade`) lack historical observations. Both current records are preserved.
See [remaining work](remaining-work.md), [source leads](../recon/source-leads.yaml)
and [the recovery follow-up](recovery-followup.md). No complete final historical
database or exhaustive revision history is claimed.

## Commands

```sh
# Dated original backup; resume via cached members or original index.
uv run --locked takoboto-grammar archive-dump --output archive-2015
uv run --locked takoboto-grammar archive-dump --output archive-2015 --offline
uv run --locked takoboto-grammar archive-audit --input archive-2015 --takoboto data

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
uv run --locked takoboto-grammar build --input data --archive archive-data --archive-snapshot archive-2015 \
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
been exhausted. Builds export verified records in each supplied source directory;
inspect reports and retained older observations before preparing a release.

Warning-bearing new extractions are written to ignored `review-records/`,
with source-bound states retained in Git. They cannot become release records.
If a refresh of an existing clean record is held, its state blocks the older
record until the discrepancy is resolved; it is never silently exported.
