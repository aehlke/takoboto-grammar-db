# Verification refinement, October 4, 2026

This review follows the [v0.6.0 recovery](recovery-followup.md). It changes
verification and private evidence handling. No grammar record, source selection,
license decision or preservation baseline changes, and no new crawl was run.

## Confirmed findings and fixes

- Earlier-revision audits now verify retained attribution reference responses
  for reviewed tutorial omissions, using the same source checks as the latest
  observations. A fixture with valid extraction and state hashes previously
  passed despite a missing reference response. It now fails for missing or
  corrupted reference bytes and passes with the exact reference source.
- Additional entries on a shared capture must carry identical observation
  kind, selected timestamp, selection reason and selection provenance. Previously
  removing these fields from a secondary entry still allowed SQLite export.
  Export now rejects the inconsistency before creating the database. Earlier
  records also require nonempty textual selection reasons and provenance;
  a recomputed state hash cannot replace those required fields.
- Offline verification migration now audits earlier records before writing
  any entry or RSS verification state. An invalid earlier record previously
  caused overall failure after these states had been written. A regression
  includes both a migration-ready entry and feed and confirms neither changes.
- Private evidence backup now checks the selected file inventory as well as
  retained bytes. Files added during compression previously escaped the final
  check; additions, removals, changed bytes and new symlinks now fail verification.
  Bundle files are created with mode 0600 and restored roots with mode 0700,
  before writing any source content. Failed bundles remain private inspection
  material and must not be treated as verified backups.

The contributor diff command now includes explicitly earlier YAML revisions.
YAML remains the sole canonical grammar content format in Git.

## Verification and provenance

The 171-test offline suite passes. `scripts/verify_dataset.py` verifies all
2,305 canonical YAML files, source record digests, full SQLite record roundtrips,
integrity, foreign keys and all 19 normalized tables/views against the unchanged
v0.6.0 baselines. No baseline was refreshed to accept these changes.

A fresh private backup and restoration verified 13,465 files containing
197,136,605 uncompressed bytes. The local compressed bundle SHA-256 is
`27e43273f339f118837edfed743d37ba1cc3a86f742a39cf8603b7fcf94784a9`.
Compression headers can change the bundle digest between backups; individual
file hashes and sizes establish source identity. Raw evidence remains ignored
by Git and is not a public release asset.

With HTTP and socket connections explicitly blocked, audits of the restored
sources passed for:

| Source | Entry observations | Notes | Examples | Comments | Relationships |
| --- | ---: | ---: | ---: | ---: | ---: |
| Latest-indexed JGram pages | 893 | 944 | 6,085 | 4,356 | 1,007 |
| Separate earlier indexed revision | 1 | 2 | 6 | 2 | 5 |
| Dated 2015 backup | 767 | 846 | 5,554 | 3,886 | 924 |

The historical audits also reparse all 643 current Takoboto records to establish
grammar membership. All canonical YAML bytes remained unchanged during backup,
restore and auditing. The sole retained earlier observation passes the stricter
selection checks and source audit.

The [v0.6.0 SQLite release](https://github.com/aehlke/takoboto-grammar-db/releases/tag/v0.6.0)
remains the published dataset; an identical dataset does not require replacement
release assets. The [remaining source gaps](remaining-work.md) still apply:
eleven failed latest replays, the missing-license `-oku` hold, separately
copyrighted tutorial omissions, and no recovered historical observations for
current IDs 1795 and 1797. This verification refinement supplies no new evidence
that those gaps are resolved. The Yookoso outreach draft remains unsent.
