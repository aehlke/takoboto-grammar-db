"""Parse observed public HTML, without executing scripts or following dictionary links."""

import copy
import hashlib
import re
from urllib.parse import urljoin, urlsplit, parse_qs

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from . import SCHEMA_VERSION

BASE = "https://takoboto.jp"
LICENSE = {"id": "CC-BY-SA-2.0", "url": "https://creativecommons.org/licenses/by-sa/2.0/"}


class ParseError(ValueError):
    pass


def cc_license_links(soup):
    links = []
    for anchor in soup.select('a[href]'):
        url = urljoin(BASE, anchor['href'])
        parts = urlsplit(url)
        if parts.hostname in {'creativecommons.org', 'www.creativecommons.org'} and parts.path.startswith('/licenses/'):
            links.append(url)
    return links


def is_data_license(url):
    parts = urlsplit(url)
    return (parts.scheme in {'http', 'https'} and parts.hostname in {'creativecommons.org', 'www.creativecommons.org'}
            and bool(re.fullmatch(r'/licenses/by-sa/2\.0/?(?:deed\.[\w-]+|legalcode)?', parts.path)))


def text(node):
    if node is None:
        return ""
    clone = copy.copy(node)
    for br in clone.select("br"):
        br.replace_with("\n")
    return clone.get_text().strip()


def fragment(node, base_url=BASE):
    """A display-safe subset; original bytes remain in the response cache."""
    clone = copy.copy(node)
    for tag in list(clone.find_all(True)):
        if tag.name is None:
            continue
        if tag.name in {"script", "style", "form", "input", "button", "iframe", "object", "img"}:
            tag.decompose()
            continue
        if tag.name == "span" and "font-weight:bold" in tag.get("style", "").replace(" ", ""):
            tag.name = "strong"
        if tag.name == 'font' and tag.get('color', '').lower() in {'red', '#ff0000'}:
            tag.name = 'strong'
        href = tag.get("href")
        tag.attrs = {}
        if tag.name == "a" and href:
            url = urljoin(base_url, href)
            if urlsplit(url).scheme in {"http", "https"}:
                tag["href"] = url
        if tag.name not in {"a", "strong", "b", "em", "i", "br", "p", "div", "span", "ul", "ol", "li", "table", "tbody", "tr", "td", "th", "ruby", "rt", "rp", "sub", "sup", "code", "pre", "blockquote"}:
            tag.unwrap()
    return clone.decode_contents().strip()


def credit(card):
    footer = card.select_one(".GrammarPartSeparateDiv:last-child, .GrammarPartSeparateMainDiv:last-child")
    if footer:
        spans = footer.find_all("span", recursive=False)
        value = text(spans[-1]) if spans and "float:right" in spans[-1].get("style", "").replace(" ", "") else ""
        return re.sub(r"^#\d+\s*", "", value) or None
    return None


def segments(node):
    """Keep exact inline text and emphasis, avoiding inserted spaces in Japanese."""
    out = []
    for leaf in node.descendants:
        if isinstance(leaf, Comment):
            continue
        is_break = isinstance(leaf, Tag) and leaf.name == 'br'
        if not is_break and not isinstance(leaf, NavigableString):
            continue
        if any(p.name in {"script", "style"} for p in leaf.parents):
            continue
        highlight = any("#00b060" in p.get("style", "").lower() for p in leaf.parents if p is not node)
        item = {"text": '\n' if is_break else str(leaf), "grammar_highlight": highlight}
        if out and out[-1]["grammar_highlight"] == highlight:
            out[-1]["text"] += item["text"]
        else:
            out.append(item)
    return out


def parse_index(body, url):
    soup = BeautifulSoup(body, "html.parser")
    if soup.select_one("#GrammarContent") is None:
        raise ParseError(f"Not a grammar index: {url}")
    entries = []
    for row in soup.select(".GrammarSummaryDiv"):
        identifier = row.select_one('input[id^="GrammarEntryId"]')
        if not identifier or not identifier.get("value", "").isdigit():
            raise ParseError("Index row has no numeric grammar ID")
        parts = row.find_all("div", recursive=False)
        if len(parts) < 3:
            raise ParseError("Unexpected grammar summary shape")
        gid = int(identifier["value"])
        entries.append({"id": gid, "source_url": f"{BASE}/bunpo/{gid}/",
                        "title": text(parts[0]), "meaning": text(parts[1]),
                        "meaning_example": text(parts[2]) if len(parts) > 3 else None})
    current = int(parse_qs(urlsplit(url).query).get("page", ["1"])[0])
    pages = set()
    for a in soup.select("a.PageLink[href]"):
        target = urljoin(url, a["href"])
        parts = urlsplit(target)
        query = parse_qs(parts.query)
        start_filter = parse_qs(urlsplit(url).query).get("filter")
        if (parts.netloc != "takoboto.jp" or parts.path != "/bunpo/" or set(query) - {"page", "filter"}
                or query.get("filter") != start_filter):
            raise ParseError(f"Out-of-scope pagination: {target}")
        page = int(query.get("page", ["1"])[0])
        if page > current:
            pages.add((page, target))
    return entries, sorted(pages)


def parse_entry(body, gid, retrieved_at, response_sha256=None):
    soup = BeautifulSoup(body, "html.parser", from_encoding="utf-8")
    main = soup.select_one(f"#editable_Main_{gid} .GrammarPartMainDiv")
    if main is None:
        raise ParseError(f"Expected Main_{gid}; response may be an error or changed layout")
    header = main.find("div", recursive=False)
    title = header.select_one("a")
    if not title or not text(title):
        raise ParseError(f"Missing entry title: {gid}")
    label = header.find_all("span", recursive=False)
    level = re.search(r"JLPT N([1-5])", main.get_text())
    record = {
        "schema_version": SCHEMA_VERSION, "id": gid, "source": "takoboto",
        "source_url": f"{BASE}/bunpo/{gid}/", "license": LICENSE,
        "title": text(title), "romanized_label": text(label[-1]) if label else None,
        "alternate_forms": [text(n) for n in soup.select(f"#editable_Main_{gid} .GrammarPartJapDiv")],
        "jlpt_level": int(level[1]) if level else None, "credits_raw": credit(main),
        "meaning": None, "meaning_example": None, "meaning_notes": [], "sections": [], "formations": [],
        "examples": [], "comments": [], "related_entries": [],
        "original_created_at": None, "original_updated_at": None,
        "retrieved_at": retrieved_at,
        "response_sha256": response_sha256 or hashlib.sha256(body).hexdigest(),
        "warnings": [],
    }
    if soup.select("time, [datetime], [data-date], [data-timestamp]"):
        record["warnings"].append("Date metadata detected; inspect cached HTML and extend date extraction")
    # Preserve all observed editable content blocks rather than silently skipping new kinds.
    for editable in soup.select('[id^="editable_"]'):
        dom_id = editable["id"]
        match = re.fullmatch(r"editable_(\w+)_(\d+)", dom_id)
        if not match:
            raise ParseError(f"Unexpected editable ID: {dom_id}")
        kind, identifier = match[1], int(match[2])
        if kind in {"Main", "Phrase"}:
            continue
        if kind in {'UserPhrase', 'Comment'} and identifier == 0:
            # Only the inspected empty contribution controls are safe to omit.
            expected = 'Add a new phrase >' if kind == 'UserPhrase' else 'Write a comment >'
            if text(editable) == expected:
                continue
        card = editable.select_one(".GrammarPartDiv, .GrammarPartMainDiv")
        if card is None:  # Empty 'Add formation' control has no data card.
            if kind != "Formation":
                raise ParseError(f"Unknown empty block: {dom_id}")
            continue
        content = card.find("div", recursive=False)
        if content is None:
            raise ParseError(f"Missing section content: {dom_id}")
        if kind == "Formation" and content.get("id") == f"note_Formation_{identifier}":
            # This is the editor's empty-state control, not a formation pattern.
            if text(content) == "Add formation":
                continue
            raise ParseError(f"Unexpected formation control: {dom_id}")
        section = {"kind": kind.lower(), "source_dom_id": dom_id,
                   "body_text": text(content), "body_html": fragment(content), "credits_raw": credit(card)}
        record["sections"].append(section)
        if kind == "Meaning":
            fields = content.find_all("span", recursive=False)
            if not fields:
                raise ParseError(f"Missing meaning fields: {gid}")
            record["meaning"] = text(fields[0])
            record["meaning_example"] = text(fields[1]) if len(fields) > 1 else None
            record["meaning_notes"] = [{"language": field.get("lang"), "text": text(field),
                                         "html": fragment(field)} for field in fields[2:]]
        elif kind == "Formation":
            rows = content.select('div[lang="ja"]')
            record["formations"] = [row.get_text(" ", strip=True) for row in rows]
            if not rows and text(content):
                record["warnings"].append("Formation layout not recognized; retained as section HTML/text")
        else:
            record["warnings"].append(f"Additional section retained: {kind}")

    for position, editable in enumerate(soup.select('[id^="editable_Phrase_"]')):
        identifier = int(editable["id"].rsplit("_", 1)[1])
        if identifier == 0:
            continue
        card = editable.select_one(".GrammarPartDiv")
        if card is None:
            raise ParseError(f"Missing phrase card: {identifier}")
        parts = card.find_all("div", recursive=False)
        if len(parts) < 3 or parts[0].get("lang") != "ja":
            raise ParseError(f"Unexpected phrase layout: {identifier}")
        example = {"source_id": identifier, "position": position, "japanese": text(parts[0]),
                   "japanese_html": fragment(parts[0]), "segments": segments(parts[0]),
                   "reading": None, "credits_raw": credit(card), "translations": [],
                   "original_created_at": None, "original_updated_at": None}
        for part in parts[1:]:
            if "GrammarPartSeparateDiv" in part.get("class", []):
                continue
            flag = part.select_one('img[src^="/flags/"]')
            if flag:
                lang = re.fullmatch(r"/flags/([\w-]+)\.png", flag.get("src", ""))
                translated = part.find("span", recursive=False) or part
                example["translations"].append({"language": lang[1] if lang else None,
                                                 "text": text(translated), "html": fragment(translated),
                                                 "segments": segments(translated)})
            elif example["reading"] is None:
                example["reading"] = text(part) or None
            else:
                raise ParseError(f"Unrecognized phrase field: {identifier}")
        record["examples"].append(example)

    for position, card in enumerate(soup.select("#GrammarCommentsDiv .GrammarPartDiv")):
        parts = card.find_all("div", recursive=False)
        if len(parts) not in {1, 2}:
            raise ParseError(f"Unexpected comment layout: {gid}:{position}")
        body_text, author = text(parts[0]), (text(parts[1]) or None) if len(parts) == 2 else None
        record["comments"].append({"position": position, "source_id": None,
                                   "text": body_text, "html": fragment(parts[0]), "credits_raw": author,
                                   "content_sha256": hashlib.sha256((str(author) + "\0" + body_text).encode()).hexdigest(),
                                   "original_created_at": None, "original_updated_at": None})

    for a in soup.select('a[href]'):
        target = urljoin(BASE, a["href"])
        parts = urlsplit(target)
        match = re.fullmatch(r"/bunpo/(\d+)/?", parts.path)
        if parts.netloc == "takoboto.jp" and match and not parts.query:
            record["related_entries"].append({"target_id": int(match[1]), "label": text(a), "source_url": target})
    # Catch new standalone cards (e.g. a future note section) outside known wrappers.
    for card in soup.select(".GrammarPartDiv, .GrammarPartMainDiv"):
        known = any((p.get("id", "").startswith("editable_") or p.get("id") == "GrammarCommentsDiv")
                    for p in card.parents if isinstance(p, Tag))
        if not known:
            record["sections"].append({"kind": "unclassified", "source_dom_id": card.get("id", ""),
                                       "body_text": text(card), "body_html": fragment(card),
                                       "credits_raw": credit(card)})
            record["warnings"].append("Standalone content card retained; review its semantic role")
    if len({e["source_id"] for e in record["examples"]}) != len(record["examples"]):
        raise ParseError(f"Duplicate example ID within entry {gid}")
    return record
