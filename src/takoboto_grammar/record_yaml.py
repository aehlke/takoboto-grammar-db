"""Deterministic, lossless YAML for canonical grammar records."""

import math
import re
import json

import yaml


class RecordLoader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise ValueError('Record mapping keys must be strings')
            if key in result:
                raise ValueError(f'Duplicate YAML record key: {key}')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def validate_value(value, active=None):
    """Keep the same scalar types and acyclic structure as the source records."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if type(value) is float and math.isfinite(value):
        return
    if not isinstance(value, (list, dict)):
        raise ValueError('Record values must be strings, finite numbers, booleans, null, lists or mappings; quote dates')
    active = set() if active is None else active
    if id(value) in active:
        raise ValueError('Recursive YAML aliases are not record data')
    active.add(id(value))
    if isinstance(value, dict) and any(type(key) is not str for key in value):
        raise ValueError('Record mapping keys must be strings')
    for child in value.values() if isinstance(value, dict) else value:
        validate_value(child, active)
    active.remove(id(value))


class RecordDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def analyze_scalar(self, scalar):
        analysis = super().analyze_scalar(scalar)
        # YAML literal blocks preserve trailing spaces. The stock emitter
        # unnecessarily falls back to escaped strings for those source lines.
        if '\n' in scalar and all(c == '\n' or c == '\t' or (c.isprintable() and c not in '\x85\u2028\u2029') for c in scalar):
            analysis.allow_block = True
        return analysis


def represent_string(dumper, value):
    style = None
    if any(c in value for c in '\r\x85\u2028\u2029'):
        style = '"'
    elif '\n' in value or ('<' in value and '>' in value) or (len(value) >= 120 and ' ' in value):
        style = '|'
    elif re.fullmatch(r'[+-]?(?:0o[0-7_]+|[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][+-]?[0-9_]+)?|\.[0-9_]+(?:[eE][+-]?[0-9_]+)?)', value):
        # Also quote strings that YAML 1.2 readers would treat as numbers.
        style = "'"
    return dumper.represent_scalar('tag:yaml.org,2002:str', value, style=style)


RecordDumper.add_representer(str, represent_string)


def load_yaml(body):
    try:
        value = yaml.load(body, Loader=RecordLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f'Invalid YAML record: {exc}') from exc
    validate_value(value)
    return value


def dump_yaml(value):
    validate_value(value)
    # Source parsers can return Beautiful Soup list/string subclasses. JSON
    # serialization previously normalized them; preserve that record model.
    value = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    body = yaml.dump(value, Dumper=RecordDumper, allow_unicode=True,
                     sort_keys=False, default_flow_style=False, width=1_000_000)
    if json.dumps(load_yaml(body), ensure_ascii=False, sort_keys=True) != json.dumps(value, ensure_ascii=False, sort_keys=True):
        raise ValueError('YAML serialization changed record values')
    return body.encode('utf-8')
