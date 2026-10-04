# Remaining source recovery

The v0.6.0 recovery follow-up completes the previously unfinished latest-label
crawl and section review. Current Takoboto has all 643 indexed entries. All
1,414 latest JGram labels have attempt states: 890 parsed pages, 512 verified
exclusions, 11 failed replays and one license hold. The dated backup resolves
all 1,077 selected labels: 766 included pages and 311 exclusions. It contains
767 entry observations. Full source audits pass for exported material.

## Public recovery backlog

Each remaining recovery gap has a GitHub issue with pinned evidence links,
previous attempts, suggested next steps and resolution criteria. Issues carry
the `source-recovery` and `help wanted` labels. Claims of completeness still
require source evidence; an issue's existence does not prove missing unique
grammar content.

| Gap | Issue |
| --- | --- |
| Final original JGram database, including the Yookoso lead | [#1](https://github.com/aehlke/takoboto-grammar-db/issues/1) |
| Historical observation for 1795, `~ageru` | [#2](https://github.com/aehlke/takoboto-grammar-db/issues/2) |
| Historical observation for 1797, `temade` | [#3](https://github.com/aehlke/takoboto-grammar-db/issues/3) |
| Source-specific license evidence for 2005 `-oku` | [#4](https://github.com/aehlke/takoboto-grammar-db/issues/4) |
| Failed corrupted alias, state key `2ca1ac89…` | [#5](https://github.com/aehlke/takoboto-grammar-db/issues/5) |
| Failed corrupted alias, state key `498d75a4…` | [#6](https://github.com/aehlke/takoboto-grammar-db/issues/6) |
| Failed mashite/hazuganai alias, state key `4e7b420d…` | [#7](https://github.com/aehlke/takoboto-grammar-db/issues/7) |
| Failed `over` replay | [#8](https://github.com/aehlke/takoboto-grammar-db/issues/8) |
| Failed “Try to” alias, state key `6f569082…` | [#9](https://github.com/aehlke/takoboto-grammar-db/issues/9) |
| Failed greetings alias, state key `71aaa8c0…` | [#10](https://github.com/aehlke/takoboto-grammar-db/issues/10) |
| Failed corrupted alias, state key `97ef91af…` | [#11](https://github.com/aehlke/takoboto-grammar-db/issues/11) |
| Failed corrupted alias, state key `b037fb94…` | [#12](https://github.com/aehlke/takoboto-grammar-db/issues/12) |
| Error-page alias, state key `c22917d1…` | [#13](https://github.com/aehlke/takoboto-grammar-db/issues/13) |
| Error-page “How to write a Japanese letter” alias, state key `d7dd4c17…` | [#14](https://github.com/aehlke/takoboto-grammar-db/issues/14) |
| Failed corrupted alias, state key `d9de0dac…` | [#15](https://github.com/aehlke/takoboto-grammar-db/issues/15) |

Readable alias wording is only a locator. The issues preserve the exact escaped
labels and original percent-encoded replay URLs; do not reconstruct source URLs
from replacement characters. Separately licensed tutorial omissions are
intentional scope limits, not filed as parser bugs. The Yookoso draft remains
unsent; the source-recovery issue records that lead for later follow-up.

## Original sources still unavailable or uncertain

- **1795 (`~ageru`) and 1797 (`temade`)** have no recovered historical detail
  observation. Their current records are fully preserved. No exact-label or safe
  numeric-ID matches were found in the inspected full indexes; no matching
  example IDs were found in recovered historical records. Yookoso's retained
  database is a specific external lead, with an unsent request in
  [source outreach](source-outreach.md). No public complete dump was verified.
- **`-oku`** remains held because its 2005 response lacks the required license
  notice. Its linked copyright page yielded no successful capture in the exact
  CDX lookup through 2005. Licensed successor `oku` includes all eleven original
  example IDs; that does not license or establish identity of every old field.
- **Eleven latest labels** have failed replays: nine returned HTTP 404 across
  bounded indexed candidates; two returned JGram error pages without an entry
  header. These include corrupted aliases and `over`. They are unresolved URL
  observations, not eleven proven missing unique grammar entries. Exact labels,
  attempted URLs and errors are committed in `archive-data/states/`; the source
  audit lists all twelve unresolved labels, including `-oku`.

ID 568 (`da`) is recovered with an explicit tutorial omission. ID 663 (そう)
is recovered from the March 27, 2014 `sou-2` revision. Its later no-entry state
is preserved independently. See [earlier revision evidence](../recon/earlier-revisions.yaml).
No older changed body is presented as the latest indexed content.

## Explicit limits of the included collection

The 84 latest and 63 backup tutorial observations retain JGram contributions
outside separately copyrighted Tae Kim cells. Exact section identity, source
byte ranges/hashes, credits and omission reasons are recorded. Tutorial bodies
are omitted from the public YAML, Markdown and SQLite; complete raw responses
remain private evidence. No collection footer is used to override another notice.

Dates absent from original contributions remain unknown. Archive timestamps,
retrieval times and RSS publication events cannot substitute for them. The
current collection is complete, and the selected dated backup is fully classified;
no complete final live JGram database or full revision history is claimed.

## Verification and next recovery step

The recovery follows robots rules, sequential five-second pacing, three-request
bursts, 30-second pauses and persistent backoff. It stopped on HTTP 503, waited
for the recorded cooldown and probed the failing label before resuming. Later
HTTP 404 clusters were inspected rather than classified as empty entries.

Current/RSS values and thirteen unaffected normalized SQLite relations retain
the v0.5.0 fingerprints. Prior historical records are unchanged except for the
explicit administration-thread scope correction. Canonical YAML is the sole
content format in Git. Raw-source backup/restore and all restored-source audits
are documented in [the recovery follow-up](recovery-followup.md).

Further source progress needs a surviving original database or verifiable
additional capture. The [source-lead ledger](../recon/source-leads.yaml) records
positive and negative leads; the Yookoso request remains unsent without Alex's
explicit authorization. Additional source copies must be checked for original
IDs, provenance, license, attribution and collection scope before import.
