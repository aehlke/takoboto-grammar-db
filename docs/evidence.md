# Preserving source evidence

Canonical YAML and the released SQLite reproduce the included collection.
Original-HTML audits additionally require the exact retained responses, URL
metadata, original backup index and compressed WARC members. A fresh request to
the current website can return different bytes. Source hashes alone do not
preserve those bytes.

After stopping any crawl, create a private evidence backup in a fresh path:

```sh
uv run --locked --offline takoboto-grammar evidence-backup --input . \
  --output exports/evidence-2026-10-04.tar.gz
```

The command records every file's SHA-256 and size, validates content-addressed
response/member/index caches and refuses source symlinks or existing output
files. Bundles use mode 0600 and restored roots use mode 0700. It includes inventories, canonical records, states, response metadata,
raw caches and held review evidence from the three dataset directories. It
checks that source bytes did not change during backup. A failed bundle remains
available for inspection and must not be treated as a verified backup.

**Keep this bundle private:** it includes unreleased third-party tutorial bodies
and raw classification evidence. It is ignored by Git and is not a public data
release. Copy the verified bundle and its reported SHA-256 to your own backup
storage. Nothing in the backup command uploads data or contacts another service.

Restore into a fresh directory and repeat the source audits:

```sh
uv run --locked --offline takoboto-grammar evidence-restore \
  --bundle exports/evidence-2026-10-04.tar.gz --output exports/restored-evidence
uv run --locked --offline takoboto-grammar audit --input exports/restored-evidence/data
uv run --locked --offline takoboto-grammar archive-audit \
  --input exports/restored-evidence/archive-data --takoboto exports/restored-evidence/data
uv run --locked --offline takoboto-grammar archive-audit \
  --input exports/restored-evidence/archive-2015 --takoboto exports/restored-evidence/data
```

Restore preflights all archive paths and hashes before writing. It rejects
symlinks, traversal, duplicates and oversized input. An existing destination is
never overwritten. Both backup and restore run offline. The audit commands also
operate on cached evidence without network requests.

For historical recovery without a local bundle, the dated records retain WARC
URLs, offsets, lengths and member hashes. `archive-dump` can recover those
scoped original members with robots checks, exact bounded ranges and pacing.
Wayback records retain original/replay URLs and payload hashes. Recovered bytes
must match the preserved hashes; substitute pages or changed live responses
cannot validate an earlier observation. Online recovery retains the normal
permission, robots and backoff requirements.
