# Reconnaissance

Observed October 2, 2026 America/Toronto / October 3 UTC. Reconnaissance used
public HTTP GETs, source HTML and inline scripts, a browser check, and one
archived JGram grammar page. No login or contribution forms were used.

## Collection boundary and discovery

The root [grammar index](https://takoboto.jp/bunpo/) returns 50 entries per
page. Following its actual pagination links reached page 13 with 43 entries,
for **643 distinct numeric IDs**. [The inventory](../recon/inventory.json)
records all observed titles, meanings, summary examples, and source URLs.
Counts are observations of this crawl, not a hardcoded expected total.

The index exposes All, N4, N3, N2, and N1 filters. Some detail pages nevertheless
say **N5** (including IDs 725 and 626). Others have no level, including 978,
1784, and 1787. Crawling filtered pages alone would miss content. Use the
unfiltered index and preserve the detail page's current label.

The initial boundary is every numeric entry discovered from that index and
its attached examples, formations, credits, grammar cross-references, and
discussion. It excludes the dictionary, dictionary example corpora, word
lists, user accounts/profiles, app assets, edit/remove endpoints, and external
sites linked from contributions. Referenced grammar IDs outside the inventory
are followed within the numeric grammar detail scope. No additional IDs were
found in the completed crawl.

## Rendering and network behavior

| Surface | Observed behavior | Extraction consequence |
| --- | --- | --- |
| `/bunpo/` and `?page=N` | Server-rendered HTML with `.GrammarSummaryDiv` and hidden `GrammarEntryIdN` inputs | Enumerate IDs without JavaScript |
| `/bunpo/725/` | Full HTML with editable display blocks, examples and comments | One GET supplies inspected entry content |
| `/bunpo/725/?ajax=1` | HTML fragment with the same editable block IDs as the full response | Desktop side panel is not a separate JSON dataset |
| Inline `loadSidePage` | XMLHttpRequest GET of `/bunpo/<id>/?ajax=1` | Confirms the side-panel request path and response handling |
| Discussion controls | Comment markup is already in `GrammarCommentsDiv`; Show comments changes display styles | No comments API or click is necessary in inspected pages |
| Inline contribution code | POSTs to `/bunpo/edit/...` and `/bunpo/remove/...` | Mutation routes; excluded |
| Embedded data | No JSON/JSON-LD script tags or external script sources in the inspected detail responses | HTML is the observed data transport |
| `/robots.txt` | `User-agent: *` and `Allow: /` at reconnaissance time | Checked afresh by online commands |

This is source inspection and an HTTP comparison, not a complete browser
network capture. No claim is made that undocumented backend data does not
exist. No JavaScript execution or browser automation is needed by the scraper.

The full response cache preserves non-rendered source markup for auditing.
It also contains the site's ordinary navigation and inline scripts; these are
transport evidence, not extracted dataset fields. Scripts are never executed
by the pipeline. Active content and event handlers are removed from extracted
HTML fragments and generated display content.

## What is retrievable

| Data | Fields and caveats |
| --- | --- |
| Entry | Numeric ID, Japanese title, alternate Japanese forms, romanized label, nullable displayed JLPT level |
| Meaning | Main explanation, summary example, additional explanations and language labels, plus separate displayed credits |
| Formation | Ordered patterns, optional parts, source HTML/text, and any displayed credits; may be absent |
| Examples | Numeric source IDs, Japanese text, displayed kana reading, translations with language flags, and displayed credits |
| Highlighting | Exact text runs and highlighted grammar spans in Japanese and translated examples |
| Discussion | Ordered comment bodies with line breaks/links and displayed author labels |
| Relationships | Numeric grammar reference targets, display labels, and source URLs |
| Provenance | Source URL, response SHA-256, retrieval time, source license notice |

Displayed credit lists such as `Amatuka, Raza` or `bamboo4, Kuval Anand` are
retained **verbatim as a credit string**. There are no stable user account IDs
in the sampled display blocks. Splitting every comma into an identity or
assigning creator/editor roles would add assumptions. Repeated display names
do not prove a shared account identity.

No original creation/update timestamps, comment IDs, revision-history links,
`time` tags, or date attributes were found across all 643 captured detail pages.
HTTP Date and file capture times are retrieval evidence, not contribution
dates. Those original date fields remain null. Comments get source positions
and content hashes, not fabricated permanent IDs. No threaded relationship
is exposed. Newly encountered date markup causes an audit warning.

Some content is imperfect: kana readings, spelling, translations, and user
corrections can disagree. Extraction preserves the source instead of silently
editing it. The origin of Takoboto's displayed kana readings was not verified.

## JGram comparison and license evidence

[Takoboto's homepage](https://takoboto.jp/) states:

> The grammar pages content is from jgram.org and is CC BY-SA 2.0.

The linked license is [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/).
The project owner reports permission from Takoboto's owner to scrape this
grammar collection. That permission is user-supplied context; no permission
correspondence is included in this repository.

A Wayback CDX lookup found captures for JGram's `tagE=ga-2`. The
[April 11, 2007 capture](https://web.archive.org/web/20070411155229/http://www.jgram.org:80/pages/viewOne.php?tagE=ga-2)
was fetched in original-byte mode and decoded as CP932/Shift_JIS rather than
UTF-8. It contains:

- The label `ga-2`, title `～が`, and an edit link with grammar ID **725**.
- Example IDs **865**, **866**, and **4790–4804**, also present in current Takoboto.
- Contributor labels such as Amatuka and Miki, and comments from Amatuka,
  Nick, and Miki whose content remains in Takoboto.
- A license link to **CC BY-SA 2.0** and a “some rights reserved” notice.
- Historical JLPT level **4**, while current Takoboto says **N5** for this entry.
- Explanatory text on See Also relationships which is not shown alongside the
  corresponding links in current Takoboto.

This directly verifies shared IDs for that entry; it does not establish that
every current entry ID, example ID, or label has an archived counterpart.
The romanized label is therefore not automatically turned into a supposedly
verified JGram URL. Archive.org now supplies separate provenance/enrichment,
but historical facts should be a separate source observation, not overwrite
current Takoboto fields. Dates/revisions absent from Takoboto cannot currently
be promised as recoverable from the archive.

## Pilot and validation

The sample IDs are 397, 509, 626, 725, 978, 1355, 1537, 1725, 1784, and 1787.
Together they contain **95 examples and 92 comments**. They exercise N1, N4,
N5, unclassified entries, alternate forms, multiple formation rows, absent
formations, zero examples, multiple credits, highlights, and lengthy comments.

The supplied SQLite and Markdown exports are built from exactly those ten
JSON records. Tests verify Japanese spacing and highlighting, English boundary
spaces, attribution, relationships, missing values, pagination, parser failure
reporting, scope restrictions, cache integrity, safe output paths, and SQLite
round trips. The live CLI smoke test discovered all 643 entries using the
previously fetched index cache and fetched/parsed one entry over the network.

The full 643-entry detail crawl is now complete. Reassessment independently
compared captured HTML with all records and found/fixed 150 additional meaning
explanations omitted from the first reader export, an empty formation control,
and a discussion contribution without a displayed author. It also preserved
red-font emphasis found in source contributions.

Verified totals: 5,334 examples, 5,324 translations, 4,546 comments, 150 additional
meaning explanations, 360 formation rows, 211 alternate forms, and 788 grammar
references. All reference targets are indexed. No unaccounted content text,
non-flag content images, additional contribution dates, or extraction warnings
remain in the captured current collection. This verifies the inspected public
responses, not inaccessible backend records.

The independent filter check found N1 144, N2 245, N3 147 and N4 33 entries;
none were absent from the unfiltered index. See [the filter evidence](../recon/filter-coverage.json)
and [current coverage report](../data/coverage-report.json).

Historical reconnaissance recovered grammar lessons and comparison pages
omitted from Takoboto, plus standalone notes and annotated cross-references.
The current archive pilot is 25 records, not a complete historical collection.
See [archive findings and limitations](archive.md) and
[the archive coverage report](../archive-data/coverage-report.json).
