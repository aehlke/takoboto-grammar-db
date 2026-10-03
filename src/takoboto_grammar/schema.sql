PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;

CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sources (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
    upstream_name TEXT NOT NULL, upstream_url TEXT NOT NULL,
    license_id TEXT NOT NULL, license_url TEXT NOT NULL
);
CREATE TABLE entries (
    id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
    source_url TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
    romanized_label TEXT, jlpt_level INTEGER CHECK(jlpt_level BETWEEN 1 AND 5),
    meaning TEXT, meaning_example TEXT, credits_raw TEXT,
    original_created_at TEXT, original_updated_at TEXT,
    retrieved_at TEXT NOT NULL, response_sha256 TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE entry_forms (
    entry_id INTEGER NOT NULL REFERENCES entries(id), position INTEGER NOT NULL,
    text TEXT NOT NULL, PRIMARY KEY(entry_id, position)
);
CREATE TABLE meaning_notes (
    entry_id INTEGER NOT NULL REFERENCES entries(id), position INTEGER NOT NULL,
    language TEXT, body_text TEXT NOT NULL, body_html TEXT NOT NULL,
    PRIMARY KEY(entry_id, position)
);
CREATE TABLE sections (
    entry_id INTEGER NOT NULL REFERENCES entries(id), position INTEGER NOT NULL,
    kind TEXT NOT NULL, source_dom_id TEXT NOT NULL,
    body_text TEXT NOT NULL, body_html TEXT NOT NULL, credits_raw TEXT,
    PRIMARY KEY(entry_id, position)
);
CREATE TABLE formations (
    entry_id INTEGER NOT NULL REFERENCES entries(id), position INTEGER NOT NULL,
    text TEXT NOT NULL, PRIMARY KEY(entry_id, position)
);
CREATE TABLE examples (
    entry_id INTEGER NOT NULL REFERENCES entries(id), source_id INTEGER NOT NULL,
    position INTEGER NOT NULL, japanese TEXT NOT NULL, reading TEXT,
    japanese_html TEXT NOT NULL, segments_json TEXT NOT NULL,
    credits_raw TEXT, original_created_at TEXT, original_updated_at TEXT,
    PRIMARY KEY(entry_id, source_id), UNIQUE(entry_id, position)
);
CREATE TABLE translations (
    entry_id INTEGER NOT NULL, example_id INTEGER NOT NULL, position INTEGER NOT NULL,
    language TEXT, body_text TEXT NOT NULL, body_html TEXT NOT NULL,
    segments_json TEXT NOT NULL,
    PRIMARY KEY(entry_id, example_id, position),
    FOREIGN KEY(entry_id, example_id) REFERENCES examples(entry_id, source_id)
);
CREATE TABLE comments (
    entry_id INTEGER NOT NULL REFERENCES entries(id), position INTEGER NOT NULL,
    source_id TEXT, body_text TEXT NOT NULL, body_html TEXT NOT NULL,
    credits_raw TEXT, content_sha256 TEXT NOT NULL,
    original_created_at TEXT, original_updated_at TEXT,
    PRIMARY KEY(entry_id, position)
);
CREATE TABLE related_entries (
    entry_id INTEGER NOT NULL REFERENCES entries(id), position INTEGER NOT NULL,
    target_id INTEGER NOT NULL, label TEXT NOT NULL, source_url TEXT NOT NULL,
    PRIMARY KEY(entry_id, position)
);
CREATE INDEX entries_jlpt ON entries(jlpt_level);
CREATE INDEX examples_credit ON examples(credits_raw);
CREATE INDEX comments_credit ON comments(credits_raw);
CREATE TABLE archive_entries (
    key TEXT PRIMARY KEY, source_id INTEGER, label TEXT NOT NULL, title TEXT NOT NULL,
    source_url TEXT NOT NULL, archive_url TEXT NOT NULL, archive_timestamp TEXT NOT NULL,
    retrieved_at TEXT NOT NULL, category TEXT, original_jlpt_level TEXT,
    meaning TEXT, credits_raw TEXT, response_sha256 TEXT NOT NULL, record_json TEXT NOT NULL
);
CREATE TABLE archive_notes (
    entry_key TEXT NOT NULL REFERENCES archive_entries(key), position INTEGER NOT NULL,
    body_text TEXT NOT NULL, body_html TEXT NOT NULL, credits_raw TEXT,
    PRIMARY KEY(entry_key, position)
);
CREATE TABLE archive_examples (
    entry_key TEXT NOT NULL REFERENCES archive_entries(key), source_id INTEGER NOT NULL,
    position INTEGER NOT NULL, japanese TEXT, body_text TEXT NOT NULL,
    body_html TEXT NOT NULL, credits_raw TEXT, verification_class_json TEXT NOT NULL,
    PRIMARY KEY(entry_key, source_id)
);
CREATE TABLE archive_comments (
    entry_key TEXT NOT NULL REFERENCES archive_entries(key), position INTEGER NOT NULL,
    body_text TEXT NOT NULL, body_html TEXT NOT NULL, credits_raw TEXT,
    PRIMARY KEY(entry_key, position)
);
CREATE TABLE archive_relationships (
    entry_key TEXT NOT NULL REFERENCES archive_entries(key), position INTEGER NOT NULL,
    target_label TEXT, label TEXT NOT NULL, annotation_text TEXT NOT NULL,
    annotation_html TEXT NOT NULL, credits_raw TEXT,
    PRIMARY KEY(entry_key, position)
);
CREATE TABLE archive_feeds (
    path TEXT PRIMARY KEY, source_url TEXT NOT NULL, archive_url TEXT NOT NULL,
    archive_timestamp TEXT NOT NULL, retrieved_at TEXT NOT NULL,
    response_sha256 TEXT NOT NULL, record_json TEXT NOT NULL
);
CREATE TABLE archive_feed_items (
    feed_path TEXT NOT NULL REFERENCES archive_feeds(path), position INTEGER NOT NULL,
    entry_id INTEGER, label TEXT NOT NULL, title TEXT, source_url TEXT NOT NULL,
    pub_date_raw TEXT, author_raw TEXT, creator_raw TEXT,
    body_text TEXT NOT NULL, body_html TEXT NOT NULL,
    PRIMARY KEY(feed_path, position)
);
-- target_id has no FK: samples and deleted/unindexed targets must remain representable.
CREATE VIEW search_documents AS
    SELECT id AS entry_id, 'entry' AS kind, title || char(10) ||
        coalesce(meaning, '') || char(10) || coalesce(meaning_example, '') AS text FROM entries
    UNION ALL SELECT entry_id, 'section', body_text FROM sections
    UNION ALL SELECT entry_id, 'example', japanese || char(10) || coalesce(reading, '') FROM examples
    UNION ALL SELECT entry_id, 'translation', body_text FROM translations
    UNION ALL SELECT entry_id, 'comment', body_text FROM comments;
CREATE VIEW archive_search_documents AS
    SELECT key AS entry_key, 'entry' AS kind, title || char(10) ||
        coalesce(meaning, '') AS text FROM archive_entries
    UNION ALL SELECT entry_key, 'note', body_text FROM archive_notes
    UNION ALL SELECT entry_key, 'example', body_text FROM archive_examples
    UNION ALL SELECT entry_key, 'comment', body_text FROM archive_comments
    UNION ALL SELECT entry_key, 'relationship', annotation_text FROM archive_relationships;
