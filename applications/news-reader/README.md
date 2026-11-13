# News reader

A web page that lists headlines about politics in Sweden from a few owner-approved sites (today SVT and Sveriges Radio). Each item shows the headline, the source, the publication time and a link to the original article. The page text and the news are in Swedish.

Status: skeleton only (step S2 of the plan). The folder holds the configuration and the test setup; the build, the page and the logic come in later steps. See the [design](news-reader-design.md) for the goal, requirements, architecture and step plan.

## Files
- `sources.json`: the approved sources. SVT is collected by the build (`fetchedBy: build`, may be stored). Sveriges Radio is fetched live in the browser (`fetchedBy: browser`) and must never be stored (`storageAllowed: false`). Changes only through issues approved by the owner.
- `tests/shared-cases.json`: cases shared by the Python and JavaScript tests, with the sections `cleaning`, `time` and `keywords` (empty for now).
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
