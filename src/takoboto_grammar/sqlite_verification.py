"""Stable fingerprints of every SQLite table and view, independent of the writer."""

import hashlib
import json


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def sqlite_signature(db):
    schema = db.execute('SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name').fetchall()
    relations = {}
    for kind, name, _, _ in schema:
        if kind not in {'table', 'view'} or name == 'metadata':
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        cursor = db.execute(f'SELECT * FROM {quoted}')
        columns = [item[0] for item in cursor.description]
        rows = [[json.loads(value) if column.endswith('_json') and value is not None else value
                 for column, value in zip(columns, row)] for row in cursor]
        rows.sort(key=canonical)
        relations[name] = {'row_count': len(rows), 'sha256': digest({'columns': columns, 'rows': rows})}
    return {'schema_sha256': digest(schema), 'relations': relations}


def verify_sqlite_signature(db, expected):
    actual = sqlite_signature(db)
    if actual['schema_sha256'] != expected['schema_sha256']:
        raise ValueError('SQLite schema differs from the verified release baseline')
    if actual['relations'].keys() != expected['relations'].keys():
        raise ValueError('SQLite tables or views differ from the verified release baseline')
    for name, signature in actual['relations'].items():
        if signature != expected['relations'][name]:
            raise ValueError(f'SQLite normalized content differs from the verified release baseline: {name}')
    return actual
