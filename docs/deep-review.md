# Deeper review

This review covered discovery, source scope, latest-capture selection,
contribution preservation, refresh behavior, audits and exports. All verification
used existing captures with network sending blocked.

## Findings and fixes

| Priority | Confirmed defect | Change |
| --- | --- | --- |
| High | A license-blocked or failed archived refresh left an earlier record available for export. Later selected runs could overwrite the only report of the hold. | Persistent per-label states hold older records before retrieval begins. Interrupted, failed, excluded or review-required attempts prevent normal export. Earlier records and response bytes remain available as evidence. RSS refreshes have the same protection. |
| High | The archive audit accepted changes to titles, readings, meanings, header sections and relationship annotations. RSS reader fragments were also insufficiently checked. | Reparse retained, hash-verified source bytes and compare every parsed field, alongside independent contribution counts/text/credit checks. Check original/replay URL and timestamp agreement. Report missing source warnings and captures differing from the latest inventory timestamp. |
| Medium | Non-grammar exclusions could never satisfy historical coverage; an incomplete CDX inventory could nevertheless produce a complete crawl report. | Completeness requires an explicitly complete index. An exclusion counts only when its latest retained replay reproduces the non-grammar classification. A report assertion alone cannot establish coverage. |
| Medium | Every `UserPhrase` or editable `Comment` block was silently skipped. | Omit only the inspected empty ID-zero controls. Retain other blocks as sections and issue a parser warning. No populated skipped blocks were found in the existing 643-page collection. |
| Medium | Emphasis segments dropped `<br>` line breaks and included invisible HTML comments. | Preserve line breaks and exclude HTML comments. Existing captured records remain identical. |
| Medium | RSS rights checks omitted channel-level declarations, and the audit crashed on review-required feeds. | Flag conflicting channel declarations, validate official Creative Commons hosts and license paths, and audit held feeds as structured review results. Export remains blocked. |
| Medium | RSS eligibility was restricted to current Takoboto labels, despite recovered historical grammar entries. | Include successfully reviewed historical labels too. Persistent holds exclude historical observations from that eligibility set. |
| Medium | A library caller could send a Takoboto request without checking robots policy. | Enforce policy checks at the transport callback, while retaining network-free cached reads. Archive policy retrieval is restricted to `robots.txt`. |

Regression tests reproduced these defects before fixes. They also check forged
exclusion evidence, pending holds, failed RSS refreshes, complete-record field
mutations and deleted selection warnings.

## Verification

**66 tests pass** with:

```sh
uv run --locked python -m unittest discover -s tests -v
```

Fresh copies of the existing datasets were used to:

- Audit all **643 current Takoboto records** against captured source HTML.
- Replay and audit all **25 previously captured JGram entries** and **five RSS
  feeds**, preserving their original retrieval timestamps and complete JSON.
- Exercise persistent state writes on real cached observations: 25 entry
  states and five feed states.
- Build SQLite, check integrity and foreign keys, and roundtrip every complete
  current, archived and RSS record.
- Generate **674 Markdown files**, including the collection index.

The current-source audit, stored historical-source audit and RSS audit pass.
No live requests occurred. Original datasets, caches and earlier test evidence
remain unchanged. [Machine-readable evidence](../recon/deep-review-report.json)
records the fresh verification output directory.

## Remaining limits

Historical coverage is still incomplete: **1,389 indexed labels lack extracted
records**. The stronger audit confirms stored observations, not eligibility or
availability of all remaining labels. Selection remains the latest successful
indexed capture per entry, rather than one simultaneous final database snapshot.

The follow-up resolution below closes the legacy-state and circular membership
checks identified in this review. Source counts and fields are checked, but
unfamiliar source layouts can still require parser review.
Contribution dates and account identities remain unverified where absent from
the public source. Original attribution and license exclusions are preserved.

## Findings resolution

The active `archive-data` dataset now has verified states for **25 entries and
five feeds**. Migration validates the entire stored batch against retained
source bytes before writing states, preserves existing holds and checks latest
cached URL metadata to avoid accepting an earlier observation after a newer
response. It leaves extracted records, raw caches and prior crawl reports unchanged.

Legacy records without states remain inspectable for auditing, but normal export
requires a state. Each state binds both the response hash and a canonical digest
of the complete record contents; editing a record invalidates that verification.
Both archived records and RSS excerpts require independently established grammar
membership. The archive audit ignores claimed `eligible_ids` in archive state and
instead reparses the captured Takoboto records supplied with `--takoboto`.

```sh
uv run --locked takoboto-grammar archive-audit --input archive-data \
  --takoboto data --record-verification
```

This command is offline and idempotent. Existing pending, failed, excluded and
license-review holds are not lifted. Missing or inconsistent source evidence
prevents migration. It verifies only stored observations; pending historical
labels remain pending.

**78 tests pass.** Migration was rehearsed in a fresh directory and then applied
to the active dataset with network sending blocked. A fresh combined export
roundtrips all 643 current records, 25 archived records and five feeds through
SQLite; integrity and foreign-key checks pass. See the
[resolution evidence](../recon/findings-resolution.json).
