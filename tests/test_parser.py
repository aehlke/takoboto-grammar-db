import unittest
from pathlib import Path

from takoboto_grammar.parser import ParseError, parse_entry, parse_index

FIXTURES = Path(__file__).parent / "fixtures"
TIME = "2026-10-03T00:47:30+00:00"


class ParserTests(unittest.TestCase):
    def load(self, gid):
        return parse_entry((FIXTURES / f"entry{gid}.html").read_bytes(), gid, TIME)

    def test_japanese_spacing_highlights_and_attribution(self):
        record = self.load(725)
        self.assertEqual(record["title"], "〜が")
        self.assertEqual(record["jlpt_level"], 5)
        self.assertEqual(record["romanized_label"], "ga-2")
        self.assertEqual(record["credits_raw"], "Amatuka, Raza")
        self.assertEqual(len(record["examples"]), 20)
        example = record["examples"][0]
        self.assertEqual(example["source_id"], 865)
        self.assertEqual(example["japanese"], "突然ですがボードゲーム告知をてっきり忘れてました。")
        self.assertEqual(example["credits_raw"], "Amatuka")
        self.assertEqual("".join(x["text"] for x in example["segments"]), example["japanese"])
        self.assertEqual([s["text"] for s in example["segments"] if s["grammar_highlight"]], ["が"])
        self.assertIn("but I completely", example["translations"][0]["text"])
        self.assertIn("<strong>が</strong>", example["japanese_html"])

    def test_alternates_formation_rows_and_comments(self):
        record = self.load(509)
        self.assertEqual(record["alternate_forms"], ["〜とき"])
        self.assertEqual(len(record["formations"]), 4)
        self.assertEqual(record["formations"][2], "な-adjective + な + 時 + (に) + (は)")
        self.assertEqual(len(record["comments"]), 12)
        self.assertEqual(record["comments"][0]["credits_raw"], "andyc")
        self.assertIsNone(record["comments"][0]["source_id"])
        self.assertTrue(all(c["original_created_at"] is None for c in record["comments"]))
        self.assertEqual(record["related_entries"][0]["target_id"], 506)

    def test_missing_level_formation_and_examples(self):
        record = self.load(1784)
        self.assertIsNone(record["jlpt_level"])
        self.assertEqual(record["formations"], [])
        self.assertEqual(record["examples"], [])
        self.assertEqual(len(record["comments"]), 2)
        self.assertIn("<br", record["comments"][0]["html"])

    def test_index_pagination_50_and_final_43(self):
        rows, pages = parse_index((FIXTURES / "index.html").read_bytes(), "https://takoboto.jp/bunpo/")
        self.assertEqual(len(rows), 50)
        self.assertEqual(rows[0]["id"], 725)
        self.assertEqual(pages[0], (2, "https://takoboto.jp/bunpo/?page=2"))
        rows, pages = parse_index((FIXTURES / "index13.html").read_bytes(), "https://takoboto.jp/bunpo/?page=13")
        self.assertEqual(len(rows), 43)
        self.assertEqual(pages, [])

    def test_fail_on_wrong_entry_error_page_or_missing_phrase(self):
        body = (FIXTURES / "entry725.html").read_bytes()
        for html, gid in [(b"<html>Oops</html>", 725), (body, 999),
                          (body.replace(b'id="editable_Phrase_865"', b'id="editable_Phrase_999"').replace(b'lang="ja"', b'lang="xx"'), 725)]:
            with self.assertRaises(ParseError):
                parse_entry(html, gid, TIME)

    def test_unknown_section_is_retained_and_warns(self):
        body = (FIXTURES / "entry725.html").read_bytes()
        extra = b'<div id="editable_Note_10"><div class="GrammarPartDiv"><div>Extra grammar note</div></div></div>'
        record = parse_entry(body.replace(b"</body>", extra + b"</body>"), 725, TIME)
        self.assertEqual(record["sections"][-1]["body_text"], "Extra grammar note")
        self.assertTrue(record["warnings"])

    def test_fragment_removes_active_content(self):
        from bs4 import BeautifulSoup
        from takoboto_grammar.parser import fragment
        node = BeautifulSoup('<div><script>bad()</script><a href="javascript:bad()" onclick="bad()">hello</a><img onerror="bad()"><strong>good</strong></div>', 'html.parser').div
        result = fragment(node)
        self.assertNotIn("bad", result)
        self.assertNotIn("onclick", result)
        self.assertIn("<strong>good</strong>", result)

    def test_unwrapped_content_card_is_not_silently_dropped(self):
        body = (FIXTURES / "entry725.html").read_bytes()
        extra = b'<div class="GrammarPartDiv"><div>A new standalone note</div></div>'
        record = parse_entry(body.replace(b"</body>", extra + b"</body>"), 725, TIME)
        self.assertEqual(record["sections"][-1]["kind"], "unclassified")
        self.assertIn("A new standalone note", record["sections"][-1]["body_text"])
        self.assertTrue(record["warnings"])

    def test_japanese_meaning_note_and_empty_formation(self):
        body = (FIXTURES / "entry1784.html").read_bytes()
        soup = __import__('bs4').BeautifulSoup(body, 'html.parser')
        content = soup.select_one('#editable_Meaning_1784 .GrammarPartDiv > div')
        content.append(soup.new_tag('br'))
        note = soup.new_tag('span', lang='ja')
        note.string = '追加の日本語説明'
        content.append(note)
        record = parse_entry(str(soup).encode(), 1784, TIME)
        self.assertEqual(record['meaning_notes'][0]['language'], 'ja')
        self.assertEqual(record['meaning_notes'][0]['text'], '追加の日本語説明')
        self.assertFalse(record['warnings'])
        self.assertFalse(any(s['kind'] == 'formation' for s in record['sections']))

    def test_comment_without_displayed_author(self):
        soup = __import__('bs4').BeautifulSoup((FIXTURES / 'entry725.html').read_bytes(), 'html.parser')
        card = soup.select_one('#GrammarCommentsDiv .GrammarPartDiv')
        card.find_all('div', recursive=False)[1].decompose()
        record = parse_entry(str(soup).encode(), 725, TIME)
        self.assertIsNone(record['comments'][0]['credits_raw'])
        self.assertTrue(record['comments'][0]['text'].startswith('Thanks a lot.'))


if __name__ == "__main__":
    unittest.main()
