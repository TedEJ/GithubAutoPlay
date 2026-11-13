# News reader

A web page that lists headlines about politics in Sweden from a few owner-approved sites (today SVT and Sveriges Radio). Each item shows the headline, the source, the publication time and a link to the original article. The page text and the news are in Swedish.

Status: skeleton (S2) plus the RSS parser and headline cleaning of the build (S4). Time handling, keywords, selection, fetching and the page come in later steps. See the [design](news-reader-design.md) for the goal, requirements, architecture and step plan.

## Files
- `sources.json`: the approved sources. SVT is collected by the build (`fetchedBy: build`, may be stored). Sveriges Radio is fetched live in the browser (`fetchedBy: browser`) and must never be stored (`storageAllowed: false`). Changes only through issues approved by the owner.
- `newsreader/`: the Python build, standard library only. So far: `model.py` (`RawEntry`: title, link, time text, description), `parse.py` (`parse_rss`: RSS 2.0 bytes to raw entries) and `select.py` (`clean_headline`, R1.3). `parse_rss` decodes by the XML declaration (UTF-8, ISO-8859-1), refuses a response over 2 MB, refuses documents that declare any entity (the XML parser itself rejects the declaration, so no external entities are resolved), and accepts only UTF-8 and ISO-8859-1 (UTF-16, UTF-32 and any other declared encoding are refused), and raises `FeedError` for empty, malformed or non-RSS documents (the root must be `<rss>`). Items with no title, link, time and description are skipped; other items are kept raw, with an empty string for a missing field. Dropping items with an empty headline or an unusable link is done later by the selection step.
- `tests/shared-cases.json`: cases shared by the Python and JavaScript tests, with the sections `cleaning` (filled), `time` and `keywords` (empty for now). Each case has `id`, `input` and `expected`. Headline cleaning is defined with fixed sets so that the JavaScript version (S9) can reproduce it exactly and does not depend on any library table:
  - Tags: `<` followed by a letter or `/` up to `>`, and `<!-- ... -->` comments, are removed (`a < b` is not a tag).
  - Entities are decoded once, in one pass: `&amp; &lt; &gt; &quot; &apos;`, numeric references (decimal and hex, any number of digits) for code points from 1 to U+10FFFF except surrogates (U+D800 to U+DFFF), and the named list `&nbsp; &laquo; &raquo; &ndash; &mdash; &hellip; &lsquo; &rsquo; &ldquo; &rdquo; &auml; &ouml; &aring; &Auml; &Ouml; &Aring; &eacute; &Eacute; &euro; &copy;` (case-sensitive). Everything else is left exactly as written: entities without a semicolon, other names, `&#0;`, surrogates, values above U+10FFFF. `&#128;` is the plain control character U+0080, not the euro sign.
  - White space is exactly U+0020, tab, LF, CR, FF, VT and U+00A0 (no-break space): runs become one space and leading and trailing ones are removed. The JavaScript version must use this explicit set, not `trim()` or `\s`. Other Unicode spaces are kept.
- `tests/fixtures/`: hand-written, invented sample feeds (`rss_svt_shape.xml` is invented, in the shape of an SVT feed) for the parser tests (no real feed content).
- `tests/test_parse.py`, `tests/test_cleaning.py`: tests of the parser and of the cleaning, the latter driven by the shared cases.
- `tests/test_sources.py`: validates `sources.json` against the rules in the design.
- `site/logic.js`: placeholder for the page logic, with a Node smoke test in `site/tests/`.
- `requirements.txt`, `pytest.ini`, `.gitignore` (lists `build/`, the output of the build).

## Run the tests locally
Needs Python 3.10 or newer and Node.js 18 or newer. From this folder (`node --test` finds the `*.test.mjs` files by itself; passing a folder name does not work on Node 22):

```
python -m pip install -r requirements.txt
python -m pytest
node --test
```

From the repository root, `bash scripts/check.sh applications/news-reader` runs the Python tests together with the other checks. The tests need no network.
