# News reader: design

Status: design proposal, no code yet. Written 2026-11-13 by the Designer/Developer worker; revised the same day with findings and decisions from the manager and the owner.

The news reader is a web page that lists headlines about **politics in Sweden** from a fixed set of news sites, starting with dn.se and omni.se. Each item shows the headline, the source name, the publication time and a link to the original article.

How the facts in section 4 were established: the worker's own environment could not reach dn.se or omni.se (refused by its network proxy). The feed checks and the robots.txt readings were then done by the manager in the owner's browser on 2026-11-13 and handed to the worker. Section 4 says for each fact who checked it and what is still not verified.

## 1. Goal and non-goals

### Goal
- G1. One web page that shows the newest headlines about politics in Sweden from the sources the visitor has chosen, merged into one list, newest first.
- G2. Each item shows only: headline, source name, publication time, link to the original article.
- G3. The visitor chooses which of the sources in the repository's catalogue to show. The catalogue itself is changed through issues and pull requests (decision D10).
- G4. The page can be hosted by what the repository already has: a GitHub repository with GitHub Pages and GitHub Actions.
- G5. The logic (reading feeds, choosing the category, removing duplicates, sorting, formatting time) can be tested automatically without a browser and without a network, in the same way as Countdown.

### Non-goals
- N1. No article text, no summary or lead paragraph (ingress), no images, even when the feed carries them. A feed's description may be read by the build to decide the category (R4.4) but is never stored or shown.
- N2. No categories other than politics in Sweden in the first version. The data shape allows more categories later.
- N3. No scraping of HTML pages. Only feeds that the sources publish are read.
- N4. No user accounts, no login, no server-side storage of the visitor's choices.
- N5. No getting around paywalls, robots.txt rules or any other restriction. Links go to the original article as it is.
- N6. No matching of the same story across different sources by headline similarity (only exact duplicates are removed, see R5.3).
- N7. No notifications, no search, no read/unread marking.
- N8. Visitors cannot add sources of their own in version 1 (decision D10; a later possibility is described in section 5, option C).

## 2. Users and scenarios

### Users
- The owner, who reads the page in a browser on a computer or phone.
- Anyone else the owner gives the address to. The page is public when it is on GitHub Pages of a public repository; each browser keeps its own choice of sources. Because of the terms risk in section 10.1, the address should not be shared widely before step S1 is settled.
- The owner as maintainer: adds or removes sources in the catalogue through issues (2.4).

### 2.1 Read the news (main flow)
1. The visitor opens the page address.
2. The page loads the latest published news file (`news.json`, see section 7).
3. The page reads the visitor's chosen sources from the browser's local storage. The first time there is no choice yet, so all enabled sources in the catalogue are chosen.
4. The page shows one list, newest first, of the items from the chosen sources: headline (as a link), source name, time.
5. At the top the page shows when the news file was built ("Senast uppdaterad 2026-11-13 14:05").
6. The visitor clicks a headline. The original article opens in a new tab.

### 2.2 Hide a source (visitor)
1. The visitor opens "Källor" (sources) on the page. It shows every enabled source in the catalogue with a check box and its status. Sources selected by keywords (Omni) carry the note "Urval med nyckelord – ungefärligt".
2. The visitor clears the check box for Omni.
3. The list updates at once and no longer shows items from Omni. The choice is saved in local storage and is still there after a reload.

### 2.3 Show a source again (visitor)
1. The visitor opens "Källor" and ticks the source.
2. The list updates at once with that source's items (they are already in `news.json`, because the build reads every enabled catalogue source).

### 2.4 Add a source to the catalogue (owner, through an issue)
1. The owner opens an issue "Add source X to the news reader", with the site name and, if known, its feed.
2. A worker checks the feed (format, fields, whether there is a politics feed, categories) and the site's robots.txt and terms, as far as the environment allows, and reports what it could not check.
3. The worker adds one entry to `sources.json` with the right method (section 7.1) and a test with a hand-written sample in the same shape.
4. After the merge, the next scheduled build reads the new source. It appears in "Källor" for every visitor, not ticked (R3.4).

### 2.5 Remove a source from the catalogue (owner, through an issue)
1. The owner opens an issue, for example because a source asked not to be shown.
2. A worker either deletes the entry from `sources.json`, or sets `"enabled": false` to keep the entry for later (R3.7).
3. After the merge and the next build, the source's items are no longer in `news.json`, and the page ignores the id in visitors' saved choices (R3.5).

### 2.6 Something is wrong
- The page is opened without a network: it shows the last news it showed in this browser, with a notice (R7.2).
- A source failed in the last build: its items from the last successful build are still shown for up to 24 hours, and "Källor" shows "Kunde inte hämtas sedan <time>" next to it (R6.2, R6.3).
- The news file itself is old (the scheduled job stopped): the page shows a warning (R7.3).

## 3. Requirements

Every requirement is numbered and testable. "Build" means the scheduled job that reads the feeds and writes `news.json`. "Page" means the HTML page. Requirements marked (auto) are covered by automated tests; (hand) are tested by the owner by hand.

### R1. Item content
- R1.1 (auto) Each item in `news.json` has exactly these fields: `id`, `sourceId`, `sourceName`, `title`, `url`, `published`, `publishedDisplay`, `category`. No other fields. In particular no summary, description, content or image field (N1).
- R1.2 (auto) `title` is plain text: HTML tags are removed, HTML and XML entities are decoded (for example `&amp;` becomes `&` and `&#229;` becomes `å`), runs of white space become one space, and leading and trailing white space is removed.
- R1.3 (auto) A `title` longer than 200 characters is cut at 199 characters and gets the character `…` at the end, so it is at most 200 characters. Characters are counted as Unicode code points, so Swedish letters count as one.
- R1.4 (auto) An item with an empty `title` after R1.2, or without a usable `url` (R8.1), is dropped.

### R2. Time
- R2.1 (auto) `published` is stored in UTC in ISO 8601 form with a `Z`, for example `2026-11-13T13:05:00Z`, or `null` when the feed gives no usable time.
- R2.2 (auto) The build reads RSS `pubDate` (RFC 822 date, for example `Fri, 13 Nov 2026 14:05:00 +0100`) and Atom `published`, falling back to Atom `updated` (RFC 3339). A time without a zone is read as Europe/Stockholm.
- R2.3 (auto) `publishedDisplay` is the time in the time zone Europe/Stockholm, 24-hour clock, in the form `YYYY-MM-DD HH:MM`, for example `2026-11-13 14:05`. Summer time is handled by the time zone rules (for example `2026-07-01T10:00:00Z` shows as `2026-07-01 12:00`).
- R2.4 (auto) When `published` is `null`, `publishedDisplay` is `Tid saknas`.
- R2.5 (auto) A time more than 10 minutes after the build time is treated as no usable time (`null`), so a wrong date in a feed cannot keep an item at the top.
- R2.6 (auto) The "last built" time on the page comes from `generatedAt` in `news.json`; the build also writes `generatedAtDisplay` in the same form as R2.3.

### R3. Sources and the visitor's choice
- R3.1 (auto) The catalogue of sources is the file `sources.json` in the repository (shape in section 7.1). Visitors cannot add sources (N8).
- R3.2 (hand) The visitor's choice is a list of source ids saved in the browser's `localStorage` under the key `newsReader.selectedSources`.
- R3.3 (hand) When the key does not exist (first visit), all sources in `news.json` are chosen.
- R3.4 (hand) A source added to the catalogue after the visitor's first visit is not chosen automatically; it is shown in "Källor" as not ticked.
- R3.5 (hand) A saved id that is no longer in `news.json` is ignored and removed from the saved list the next time the visitor changes the choice.
- R3.6 (hand) If `localStorage` cannot be read or written (private mode or blocked storage), the page still works with the default choice of R3.3, and changes last until the page is closed.
- R3.7 (auto) A source with `"enabled": false` in `sources.json` is not fetched and does not appear in `news.json`.

### R4. Category: politics in Sweden
- R4.1 (auto) The category id is `politics-sweden`. A source supplies it with exactly one of three methods, set in `sources.json`:
  - `feed`: a dedicated politics feed. Every item in that feed belongs to the category.
  - `categoryFilter`: a general feed, where an item belongs to the category only if one of its RSS `<category>` or Atom `<category term>` values matches one of the listed values exactly, ignoring case and leading and trailing white space.
  - `keywordFilter`: a general feed, where an item belongs to the category when its headline or description matches the keyword list (R4.4).
- R4.2 (auto) The method is chosen per source in this order of preference: `feed` if the source has a politics feed, else `categoryFilter` if its items carry usable categories, else `keywordFilter`. Keywords are used only for sources set to `keywordFilter`.
- R4.3 (auto) A source without any method for the category is a configuration error: the test of `sources.json` fails.
- R4.4 (auto) The keyword list is the file `politics-keywords.json` (shape in section 7.2). An item matches when its headline or its description (after the cleaning of R1.2) contains at least one `include` term under the matching rules of section 7.2 and no `exclude` term. The description is used only for this test and is then discarded (N1).
- R4.5 (hand) In "Källor", a source using `keywordFilter` shows the note "Urval med nyckelord – ungefärligt", so the visitor knows the selection is approximate.

### R5. Selection, duplicates and order
- R5.1 (auto) At most 20 items per source are kept in `news.json`: the 20 newest by `published` among the items that belong to the category. Items with `published` `null` come after all dated items and fill the 20 only if fewer than 20 dated items exist.
- R5.2 (auto) Items with `published` older than 7 days before the build time are dropped.
- R5.3 (auto) Duplicates are removed by normalised URL: the scheme and host are made lower case, `www.` is removed from the host, the query string and the fragment are removed, and a trailing `/` is removed. Within one source the first item in feed order is kept. Across sources the item from the source listed first in `sources.json` is kept.
- R5.4 (auto) `id` is the first 16 hexadecimal characters of the SHA-256 of the normalised URL, so the same article always gets the same id.
- R5.5 (auto) The items in `news.json` are sorted by `published`, newest first; items with `null` last; equal times are ordered by `sourceId`, then by `title`.
- R5.6 (hand) The page shows the items of the chosen sources in the order of `news.json`. It does not sort again.

### R6. Refresh and errors in the build
- R6.1 (hand, owner) The build runs every 30 minutes on a schedule, and can be started by hand from the Actions tab.
- R6.2 (auto) Each source is fetched with a timeout of 15 seconds and one request per feed per build; HTTP redirects are followed only within the source's `allowedHosts`. If a fetch fails (network error, HTTP status other than 200, not parseable as RSS 2.0 or Atom, zero items, or a redirect to another host), the build keeps that source's items from the previously published `news.json` if they are less than 24 hours old, and records the status `error` with the time of the last success.
- R6.3 (auto) `news.json` has a `sources` list with one entry per enabled catalogue source: `id`, `name`, `method`, `status` (`ok`, `error` or `blocked-by-robots`), `lastSuccess` (UTC time or `null`), `itemCount`.
- R6.4 (auto) A failing source never makes the whole build fail. The build fails (non-zero exit code, so no new file is published) only if `sources.json` or `politics-keywords.json` is invalid.
- R6.5 (auto) The build sends the request header `User-Agent: GithubAutoPlay-news-reader/1.0` and no cookies.
- R6.6 (auto) Before fetching a feed, the build reads the host's `/robots.txt` once per run and does not fetch a feed path that is disallowed for its User-Agent. Such a source gets the status `blocked-by-robots` and keeps no old items. If robots.txt cannot be read, the feed is not fetched and the status is `error`. The build never changes its User-Agent to get past a rule (N5).

### R7. Page behaviour, refresh, offline
- R7.1 (hand) The page loads `news.json` when it opens, again every 10 minutes while it is open, and when the visitor presses the button "Uppdatera". A new load replaces the list only when it succeeds.
- R7.2 (hand) After each successful load the page saves the file in `localStorage` under `newsReader.lastNews`. If loading fails, the page shows the saved copy with the notice "Offline – visar sparade nyheter från <generatedAtDisplay>". If there is no saved copy, it shows "Kunde inte hämta nyheter. Försök igen senare."
- R7.3 (hand) If `generatedAt` is more than 3 hours before the viewer's clock, the page shows "Nyheterna kan vara gamla – senast uppdaterad <generatedAtDisplay>".
- R7.4 (hand) If none of the chosen sources has items, the page shows "Inga nyheter från valda källor."
- R7.5 (hand) The page works on a phone screen 360 pixels wide without sideways scrolling; long headlines wrap.
- R7.6 (hand) The page loads no scripts, fonts or styles from other sites.
- R7.7 (hand) The page text is in Swedish (see Q3).
- R7.8 (hand) Below the list the page shows the line "Rubriker och länkar från respektive källa. Klicka för att läsa hos källan." so it is clear that the content belongs to the sources.

### R8. Safety of links and text
- R8.1 (auto) An item `url` is kept only if its scheme is `https` or `http` and its host is one of the source's `allowedHosts` in `sources.json` or ends with `.` plus one of them. Other items are dropped. `http` links are kept as they are (not rewritten).
- R8.2 (hand) The page writes all text with `textContent`, never with `innerHTML`, so a headline cannot inject HTML.
- R8.3 (hand) Each link opens in a new tab with `target="_blank"` and `rel="noopener noreferrer"`.
- R8.4 (auto) The build reads feeds with an XML parser that does not resolve external entities, and refuses a response larger than 2 MB.

### R9. Encoding
- R9.1 (auto) The build decodes each feed by the encoding in its XML declaration (UTF-8 and ISO-8859-1 must both work) and writes `news.json` as UTF-8. Å, ä, ö, é and other letters come through unchanged.
- R9.2 (hand) The page declares `<meta charset="utf-8">`.

## 4. Findings about the sources

### 4.1 How this was checked
Date of all checks: **2026-11-13**.

- **Worker's environment:** direct requests to `https://www.dn.se/robots.txt`, `https://www.dn.se/rss/`, `https://www.dn.se/rss/politik/`, `https://www.dn.se/rss/nyheter/politik/`, `https://www.dn.se/nyheter/politik/rss/`, `https://omni.se/robots.txt`, `https://omni.se/rss`, `https://omni.se/rss.xml` and `https://omni.se/feed` were refused by the environment's network proxy (HTTP 403 on connect). The worker therefore first used two third-party feed directories, Feeder (feeder.co) and Feedspot (rss.feedspot.com), to find candidate addresses.
- **Manager, in the owner's browser:** checked the DN politics feed, the Omni feed, Omni's other candidate addresses, and both sites' robots.txt. The results below marked "verified (manager)" come from that check. The worker has not seen the raw responses itself.
- No page or feed contained anything that looked like instructions to the worker.

### 4.2 dn.se (Dagens Nyheter)

| URL | Result | Checked by |
|---|---|---|
| `https://www.dn.se/rss/om/svensk-politik/` | **Politics feed. Exists, 100 items.** | Verified (manager). First found on Feedspot `https://rss.feedspot.com/dagensnyheter_rss_feeds/`. |
| `https://www.dn.se/rss/` | Main news feed. Feeder reports about 61 items per day and shows a summary and an image per item. | Feeder only, not verified directly. Not used. |
| `https://www.dn.se/rss/debatt/` | DN Debatt opinion pieces. | Feeder only, not verified directly. Not used (decision D12). |
| `https://www.dn.se/rss/sverige/`, `https://www.dn.se/rss/ekonomi/` | Domestic news, economy. | Feedspot and Feeder only, not verified directly. Not used. |

Fields of the politics feed:
- Verified: it is a feed with 100 items.
- **Not verified:** the format (RSS 2.0 is expected because the address is `/rss/`), the exact form of `pubDate`, whether items carry `<description>`, `<category>` or an image element, the link host of the items (`www.dn.se` is expected), and whether the feed sends a CORS header. Feeder shows summaries and images for other dn.se feeds, so this feed probably carries them too. The design drops them in any case (N1, R1.1).
- The parser (step S4) must therefore handle both a feed with and without these elements, and the worker of step S2 must confirm the item link host before setting `allowedHosts` (Q4).

Method for dn.se: `feed` with `https://www.dn.se/rss/om/svensk-politik/`.

**What dn.se says about use (as read by the manager in `https://www.dn.se/robots.txt` on 2026-11-13):** Bonnier News reserves all rights and prohibits scraping, aggregation, and text and data extraction without written permission, and the file blocks many AI crawlers, among them ClaudeBot and Claude-User. The RSS feed is at the same time publicly offered. The worker has not read the file itself and has not found a separate statement from DN about how its RSS feeds may be used. Whether the feed paths are disallowed for a generic User-Agent was not reported; R6.6 makes the build follow whatever the file says. This document gives no legal advice; the consequences are in section 10.1.

### 4.3 omni.se (Omni)

| URL | Result | Checked by |
|---|---|---|
| `https://omni.se/rss.xml` | **General feed. HTTP 200, `application/rss+xml`, 203 items, no categories, no CORS header, `Cache-Control: no-store`.** | Verified (manager) |
| `https://omni.se/politik/rss.xml`, `https://omni.se/politik/rss`, `https://omni.se/politik/feed`, `https://omni.se/t/svensk-politik`, `https://omni.se/t/politik` | 404 or no feed | Verified (manager) |
| `https://omni.se/rss.xml?section=politik`, `https://omni.se/rss.xml?category=politik` | Parameter ignored, the same 203 items | Verified (manager) |

So Omni has a feed, but **no politics-specific feed and no categories** to filter on.

Fields of the Omni feed:
- Verified: RSS, 203 items, no `<category>` elements.
- **Not verified:** the exact form of `pubDate`, whether every item has a `<description>` (the owner's decision to match on the description assumes there is one; R4.4 works with headline only when it is missing), whether items carry images, and which host the item links point to. Omni summarises news from other media, so a link may point to omni.se or to the original publisher. `allowedHosts` must be set from what the feed actually contains (Q4), otherwise R8.1 drops the items.

Method for omni.se: `keywordFilter` on `https://omni.se/rss.xml` (decision D11). The limits of this method are described in section 10.1, risk K6.

**What omni.se says about use:** robots.txt (read by the manager) allows `/` and disallows only `/nyhetsmix$`, `/debug$`, `/sj$` and `/strawberry$`, so `/rss.xml` is allowed. Omni's terms of use were not found by the worker's web search and were not reported as read; **not verified** (Q2).

### 4.4 Can a browser read these feeds directly?
No, for Omni: the manager verified that `https://omni.se/rss.xml` sends no CORS header, so a page on another site cannot read it. For DN the CORS header was not checked. The recommended design does not depend on it.

### 4.5 Summary of what is not verified
1. The exact XML fields of both feeds (`pubDate` form, `<description>`, image elements) and the host of the item links.
2. Whether DN's robots.txt disallows the feed path for a generic User-Agent (handled by R6.6 either way).
3. Omni's terms of use.
4. CORS headers on the DN feed.
5. That GitHub's Action runners are allowed to fetch dn.se and omni.se (very likely, not tested).
6. How well the keyword list selects Omni's politics items (measured in step S7 against a saved sample, see section 9).

## 5. Options considered and the recommendation

### Option A: pure static page that fetches the feeds in the browser
- How: `index.html` on GitHub Pages; JavaScript fetches each feed and parses it.
- Breaks: the browser blocks reading another site's response unless that site allows it (CORS). Verified for Omni: no CORS header, so it cannot work. DN not checked.
- Benefit: visitors could type any feed address.
- Verdict: rejected, because it does not work for Omni and probably not for DN, and its logic would be JavaScript that the current check `checks` cannot test (it has only Python).

### Option B: static page plus a public CORS proxy
- How: like A, but each request goes through a public relay service that adds the CORS header.
- Costs and breaks: every visitor's requests go through an unknown third party; free relays are often slow, rate-limited or shut down; the third party can change the content. It would also hide who is fetching from the news sites, which goes against N5 and the DN terms risk.
- Verdict: rejected.

### Option C: page plus our own small proxy or serverless function
- How: a small function on a separate serverless platform fetches a feed on request and returns it with a CORS header.
- Costs: needs an account and deployment outside GitHub, which this repository cannot host (GitHub Pages serves only static files). Needs credentials for deployment, which the workflow rules keep away from Claude. A proxy that fetches any URL can be misused by others unless restricted to a list.
- Verdict: not for version 1. **This is what visitor-defined sources would need later**: because of CORS, letting a visitor type in any feed requires an own proxy like this (or a local program, option E). That is a later step for the owner to decide (follow-up, not in the step plan).

### Option D (recommended): scheduled build on GitHub Actions publishes a static `news.json`; the page reads it
- How: a Python program in `applications/news-reader/` reads the catalogue `sources.json` and the keyword list, fetches each enabled source's feed, parses, filters, removes duplicates, sorts and writes `news.json`. A GitHub Actions workflow runs it every 30 minutes and publishes `index.html`, `app.js`, `style.css` and `news.json` to GitHub Pages with the official Pages deployment action. The page reads `news.json` from its own site, so there is no CORS problem.
- Why:
  - Works with what the repository has: GitHub Actions and GitHub Pages.
  - No CORS problem and no third party in between.
  - Each feed is fetched once per run for all visitors (48 requests per feed per day), and robots.txt is respected (R6.6).
  - All logic is Python, which the required check `checks` already runs with `pytest` (after the owner adds a step, S3). The page stays thin.
  - The published file never contains summaries or images (N1), because the build drops them.
  - Sources live in the repository, which is the owner's decision D10.
- Costs and limits:
  - Visitors cannot add sources (N8).
  - Freshness is at best the schedule (30 minutes), and GitHub may delay scheduled runs at busy times.
  - The workflow file and the Pages setting can only be added by the owner (S10).
  - The build must not commit `news.json` to `main`: direct pushes to `main` are blocked by the ruleset, and a commit every 30 minutes would fill the history. That is why it publishes to Pages as a deployment artifact instead of committing.
  - In a private repository GitHub Pages needs a paid plan, and Actions minutes count against a monthly quota (Q1).

### Option E: run on the owner's own computer
- How: `python -m newsreader.serve` builds `news.json` and serves the page on `http://localhost`.
- Benefit: no hosting, and the list of feeds could be edited locally.
- Costs: only works on a computer with Python while the program runs; not on a phone; not shareable.
- Verdict: not chosen, but it reuses the same Python modules as D, so it is a cheap later addition.

### Decision
Option D. It is the only option that works with the repository's hosting, does not depend on CORS or on third parties, and keeps the logic testable in the existing check.

## 6. Architecture of the recommendation

```
applications/news-reader/
  README.md                 project description, how to run and test
  news-reader-design.md     this document
  requirements.txt          pytest (the build itself uses only the Python standard library)
  pytest.ini
  sources.json              the catalogue of sources (section 7.1)
  politics-keywords.json    the keyword list for keywordFilter sources (section 7.2)
  newsreader/
    __init__.py
    model.py                NewsItem and SourceStatus data classes; no I/O
    parse.py                RSS 2.0 and Atom bytes -> list of raw entries; no network
    timeutil.py             parse dates, convert to UTC, format Europe/Stockholm (R2)
    select.py               feed and categoryFilter rules, URL check, title cleaning,
                            cut to length, de-duplicate, drop old, cap per source,
                            sort (R1, R4.1 to R4.3, R5, R8.1)
    keywords.py             load and validate politics-keywords.json, match a
                            headline and description (R4.4)
    robots.py               decide with urllib.robotparser whether a feed may be
                            fetched (R6.6); takes robots.txt text, no network
    build.py                orchestration: read sources.json, fetch, call the pure
                            modules, merge with the previous news.json, write news.json
    fetch.py                the only module that uses the network (urllib, timeout,
                            size limit, User-Agent); replaced by a fake in tests
    __main__.py             python -m newsreader --out <folder> [--previous <news.json>]
  site/
    index.html              page skeleton, Swedish text
    app.js                  thin page layer (below)
    style.css
  tests/
    fixtures/               hand-written sample feeds (section 9)
    test_parse.py
    test_timeutil.py
    test_select.py
    test_keywords.py
    test_robots.py
    test_sources_config.py
    test_build.py           uses a fake fetch function, no network
```

### Pure logic (tested without browser or network)
`parse.py`, `timeutil.py`, `select.py`, `keywords.py`, `robots.py`, `model.py`, and `build.py` with an injected fetch function. These take bytes and values in and give values out. `build.py` gets the fetch function and the current time as parameters, so tests control both.

### Network layer
`fetch.py` only: one function `fetch(url) -> bytes` that applies the timeout and redirect rule (R6.2), the 2 MB limit (R8.4) and the User-Agent (R6.5). It is the only place that imports `urllib.request`.

### Page layer (thin, tested by hand)
`app.js` does only this:
1. Fetch `news.json` from the same folder (R7.1); save or fall back to `localStorage` (R7.2).
2. Read and write the chosen sources in `localStorage` (R3.2 to R3.6).
3. Show `items` whose `sourceId` is chosen, in file order, with `textContent` and safe links (R5.6, R8.2, R8.3).
4. Show "Källor" with check boxes, the status of each source and the keyword note (R4.5, R6.3).
5. Show the notices of R7.2, R7.3, R7.4 and R7.8.

It does no parsing, no time conversion and no sorting; `publishedDisplay` and `generatedAtDisplay` come ready from the build. The only clock comparison in the page is the staleness warning in R7.3.

### Publishing (owner-added workflow, step S10)
A workflow `.github/workflows/news-reader.yml`, separate from `ci.yml`:
- triggers: a schedule every 30 minutes, and `workflow_dispatch`;
- permissions: `contents: read`, `pages: write`, `id-token: write`;
- steps: check out; set up Python; download the currently published `news.json` from the Pages site as `--previous` (ignore a failure the first time); run `python -m newsreader --out _site --previous previous.json` in `applications/news-reader`; copy `site/*` into `_site`; upload with the official upload-Pages-artifact action; deploy with the official deploy-Pages action.
- It must not be added as a required check, and it must not commit.

## 7. Data and state

### 7.1 The catalogue: `sources.json` (in the repository)
```json
{
  "version": 1,
  "sources": [
    {
      "id": "dn",
      "name": "DN",
      "enabled": true,
      "homepage": "https://www.dn.se/",
      "allowedHosts": ["dn.se"],
      "categories": {
        "politics-sweden": { "method": "feed", "url": "https://www.dn.se/rss/om/svensk-politik/" }
      }
    },
    {
      "id": "omni",
      "name": "Omni",
      "enabled": true,
      "homepage": "https://omni.se/",
      "allowedHosts": ["omni.se"],
      "categories": {
        "politics-sweden": { "method": "keywordFilter", "url": "https://omni.se/rss.xml" }
      }
    }
  ]
}
```
- `id`: lower-case letters, digits and `-`, unique.
- `enabled`: `true` or `false` (R3.7).
- A `categoryFilter` method looks like `{ "method": "categoryFilter", "url": "<general feed>", "values": ["Politik"] }`. No source uses it today.
- `allowedHosts` for Omni is a placeholder until the item link host is known (Q4).
- Changes to this file are made only through issues and pull requests (decision D10).

### 7.2 The keyword list: `politics-keywords.json` (in the repository)
```json
{
  "version": 1,
  "category": "politics-sweden",
  "include": {
    "words": ["riksdag*", "regering*", "statsminister*", "partiledar*",
              "talman*", "oppositionsledar*", "Rosenbad", "budgetproposition*",
              "riksdagsval*", "Socialdemokrat*", "Moderat*", "Sverigedemokrat*",
              "Centerpartiet", "Vänsterpartiet", "Kristdemokrat*", "Liberalerna",
              "Miljöpartiet"],
    "caseSensitive": ["(S)", "(M)", "(SD)", "(C)", "(V)", "(KD)", "(L)", "(MP)"]
  },
  "exclude": {
    "words": []
  }
}
```
Matching rules (R4.4):
- `words`: case-insensitive, compared after Unicode NFC normalisation. A term matches a whole word; a term ending in `*` matches any word that starts with the term without the `*` (so `riksdag*` matches "riksdagen" and "riksdagsledamot"). Word boundaries are letters and digits, including å, ä, ö and é.
- `caseSensitive`: exact text, including the brackets, so "(S)" after a politician's name matches but the letter "s" does not.
- `exclude`: an item that matches any exclude term is not selected even if it matches an include term. It starts empty and is filled through issues when false positives are found.
- The lists above are the starting proposal. Step S7 checks them against a saved Omni sample and adjusts them. Words that are too broad on their own, such as "minister", "val" and "parti", are deliberately left out, because they also match foreign politics and other news.

### 7.3 The visitor's choice (in the browser)
- `localStorage["newsReader.selectedSources"]` = JSON list of source ids, for example `["dn"]`.
- `localStorage["newsReader.lastNews"]` = the last `news.json` that loaded successfully (R7.2). Its size stays small: at most 20 items per source.
- Nothing about the visitor is stored anywhere else.

### 7.4 The published file: `news.json`
```json
{
  "version": 1,
  "generatedAt": "2026-11-13T13:05:12Z",
  "generatedAtDisplay": "2026-11-13 14:05",
  "category": "politics-sweden",
  "sources": [
    { "id": "dn", "name": "DN", "method": "feed", "status": "ok", "lastSuccess": "2026-11-13T13:05:12Z", "itemCount": 20 },
    { "id": "omni", "name": "Omni", "method": "keywordFilter", "status": "ok", "lastSuccess": "2026-11-13T13:05:12Z", "itemCount": 14 }
  ],
  "items": [
    {
      "id": "3f2a9c0d1b7e4a55",
      "sourceId": "dn",
      "sourceName": "DN",
      "title": "Exempelrubrik om riksdagen",
      "url": "https://www.dn.se/sverige/exempel/",
      "published": "2026-11-13T12:58:00Z",
      "publishedDisplay": "2026-11-13 13:58",
      "category": "politics-sweden"
    }
  ]
}
```
The headline, URL and counts above are made up for illustration.

## 8. Edge cases and failure modes

| Case | What happens | Requirement |
|---|---|---|
| A source is down, times out or answers with an error | Its previous items (under 24 h old) are kept; status `error`; other sources unaffected | R6.2, R6.3, R6.4 |
| A feed changes format (not RSS 2.0 or Atom, or the XML is broken) | Treated as a failed fetch; previous items kept; `error` shown in "Källor" | R6.2 |
| A feed moves (HTTP redirect) | Followed within the source's allowed hosts; a redirect to another host counts as an error | R6.2 |
| A feed suddenly has zero items | Treated as a failure, so the page does not go empty because of a temporary problem | R6.2 |
| robots.txt disallows the feed, or cannot be read | Feed not fetched; status `blocked-by-robots` or `error` | R6.6 |
| A source asks not to be shown | Owner sets `"enabled": false` or removes the entry (flow 2.5) | R3.7 |
| Omni item about Swedish politics without any listed term | Not shown (false negative) | R4.4, K6 |
| Omni item about foreign politics that mentions "regeringen" | Shown (false positive) until an exclude term is added | R4.4, K6 |
| Omni item without description | Matched on headline only | R4.4 |
| The whole scheduled job stops (disabled, quota used up) | `news.json` stops changing; the page warns after 3 hours | R7.3 |
| GitHub disables a scheduled workflow after 60 days without repository activity (public repositories) | Same as above; the owner re-enables it | R7.3, K3 |
| Same article twice in one feed, or in two sources | Removed by normalised URL | R5.3 |
| Same story in DN and Omni with different links | Both are shown (not a duplicate by this design) | N6 |
| Item without time | Kept, shown "Tid saknas", sorted last | R2.4, R5.1 |
| Time in the future (wrong feed data) | More than 10 minutes ahead is treated as no time | R2.5 |
| Time without zone, or summer/winter time change | Read as Europe/Stockholm; shown via time zone rules | R2.2, R2.3 |
| Very long headline | Cut to 200 characters with `…`; wraps on screen | R1.3, R7.5 |
| HTML or entities in a headline | Tags removed, entities decoded, written as text | R1.2, R8.2 |
| Swedish letters, ISO-8859-1 feed | Decoded by the declared encoding; output UTF-8 | R9.1, R9.2 |
| A link to an unlisted host, a `javascript:` or `data:` link | Item dropped | R8.1 |
| Opening the link | New tab, no access back to the reader page | R8.3 |
| A huge or hostile feed | Over 2 MB refused; external entities not resolved | R8.4 |
| Article behind a paywall | Shown and linked as any other | N5 |
| Browser offline | Last saved copy with a notice | R7.2 |
| Local storage blocked | Default choice, page still works | R3.6 |
| A chosen source is removed from the catalogue | Ignored | R3.5 |
| The visitor unticks every source | "Inga nyheter från valda källor." | R7.4 |

## 9. Testing strategy

### Automated (pytest, no network, no browser)
Tests live in `applications/news-reader/tests/` and use **hand-written sample feeds** in `tests/fixtures/`, written in the shape of RSS 2.0 and Atom with made-up Swedish headlines. They are not copies of real DN or Omni content. Planned samples:
1. `rss_politics_basic.xml`: RSS 2.0, 25 items, `pubDate` in `+0100` and `+0200`, with `<description>`, `<category>` and an image element (to prove they are dropped).
2. `rss_iso8859.xml`: declared ISO-8859-1, headlines with å, ä, ö, é.
3. `rss_edge_cases.xml`: empty title, title with HTML tags and entities, a 300-character title, no `pubDate`, a future date, a date older than 7 days, a `javascript:` link, a link to a foreign host, two items with the same URL differing only in query string.
4. `atom_basic.xml`: Atom with `published` on some entries and only `updated` on others.
5. `rss_category_filter.xml`: a general feed where only some items carry the category value `Politik`.
6. `rss_keyword_filter.xml`: a general feed without categories, in the shape of the Omni feed, with made-up items that should match (each include term at least once, prefix forms, "(SD)" after a name), items that should not match ("s" alone, "minister" in foreign news, sports), an item without description, and an item that matches only through its description.
7. `not_a_feed.html` and `broken.xml`: to test the failure path.
8. `robots_allow.txt`, `robots_disallow_rss.txt`: to test R6.6.
9. `previous_news.json`: a published file, to test that items of a failing source are kept for under 24 hours and dropped after.

What the tests cover: every requirement marked (auto) in section 3, plus a test that `sources.json` and `politics-keywords.json` in the repository are valid. `build.py` is tested with a fake fetch function (returns fixture bytes, or raises a timeout) and a fixed "now", including the time zone examples in R2.3 for both winter and summer time.

How well the keyword list works cannot be proven by tests with made-up data. In step S7 the worker (or the owner, if the worker cannot reach omni.se) saves one real copy of `https://omni.se/rss.xml` **outside the repository**, runs the filter on it, and reports in the pull request how many items matched, and, by reading the matched and unmatched headlines, roughly how many false positives and false negatives there were. The real copy is not committed (the brief says not to copy news content into the repository).

How the tests run:
- Locally: `bash scripts/check.sh applications/news-reader` (the script takes the project folder as an argument) and, as today, `bash scripts/check.sh` for Countdown.
- In the required check `checks`: `ci.yml` today runs only the Countdown tests and the script tests. Two steps must be added to the `checks` job (install requirements and run `python -m pytest` in `applications/news-reader`). That is a workflow change only the owner can make (step S3). Until then the news-reader tests do not protect pull requests.

### By hand (owner)
- The page (S9): with a locally built `news.json` served by `python -m http.server` in the output folder: list order, link opens in a new tab, choosing and unchoosing sources, reload keeps the choice, private window, offline (browser developer tools "Offline"), stale warning (edit `generatedAt`), "Inga nyheter" message, keyword note on Omni, credit line, phone width 360 px, Swedish letters.
- After S10 (this is step S11): the live Pages address shows news from both sources; a manual run from the Actions tab updates "Senast uppdaterad"; after an hour there have been two scheduled runs; reading the Omni items for obvious false positives.

## 10. Risks and open questions

### 10.1 Risks

**K5. DN's terms (main risk).** As read by the manager on 2026-11-13, `https://www.dn.se/robots.txt` says that Bonnier News reserves all rights and prohibits scraping, aggregation, and text and data extraction without written permission, and it blocks many AI crawlers, including ClaudeBot and Claude-User. DN does offer the politics feed publicly. A page that collects DN headlines next to other sources can be seen as aggregation. This document gives no legal advice. What the design does about it:
- It shows only headline, source name, time and link, never text or images (D2, N1).
- It fetches the feed once per run for all visitors, sends an honest User-Agent, follows robots.txt and never gets around a rule (R6.5, R6.6, N5).
- DN can be switched off with one line, `"enabled": false` (R3.7).
- **Recommendation: contact Bonnier News / DN and ask whether showing headlines and links from the politics feed on this page is acceptable, before the page address is shared widely** (step S1). Until there is an answer, keep the page for the owner's own use. If the answer is no, set DN to `"enabled": false`.

**K6. Omni keyword filter is approximate.** Omni has no politics feed and no categories (section 4.3), so Omni items are chosen by keywords in the headline and description (D11). Consequences:
- False positives: foreign politics ("regeringen" in another country), or news that only mentions a party in passing, can appear.
- False negatives: Swedish politics news that uses none of the listed terms, for example a headline that names only a minister by name, will be missed.
- The list needs care over time: new party leaders, new party names or new topics. It is changed through issues like `sources.json`.
- The page says so ("Urval med nyckelord – ungefärligt", R4.5).
- Omni's terms of use are not verified (Q2); its robots.txt allows the feed.

| # | Risk | Proposed handling |
|---|---|---|
| K1 | dn.se or omni.se may block or rate-limit GitHub runners. | Seen in the first runs after S10 (status `error`); then decide on fewer runs or dropping the source. |
| K2 | A feed changes address or format without notice. | `error` status and the stale warning make it visible; fix by issue. |
| K3 | Scheduled workflows in public repositories are disabled after 60 days without activity. | The stale warning (R7.3) makes it visible; owner re-enables in the Actions tab. |
| K4 | Scheduled runs can be delayed at busy times. | Accepted; R7.3 uses 3 hours, well above the 30-minute schedule. |
| K5 | DN's terms prohibit aggregation without written permission. | See above: contact Bonnier News / DN (S1); `enabled: false` if refused. |
| K6 | The Omni keyword filter selects approximately. | See above: measure in S7, maintain the list through issues, show the note. |

### 10.2 Open questions

| # | Question | Proposed way to settle it |
|---|---|---|
| Q1 | Is the repository public? GitHub Pages in a private repository needs a paid plan, and in a private repository 48 runs per day count against the monthly Actions minutes. | Owner checks before S10. If private: run every 60 minutes instead of 30 (R6.1) or reconsider hosting. |
| Q2 | What do Omni's terms of use say about showing its headlines and links on another site? | Owner reads them in S1, as for DN. |
| Q3 | Page language: Swedish UI text (as Passningsspelet) or English (as Countdown)? | Owner decides before S9. Recommendation: Swedish, since the content is Swedish. |
| Q4 | Which host do the item links of the two feeds point to (`www.dn.se`; omni.se or the original publisher)? This sets `allowedHosts`. | The worker of S2 checks it if the environment allows; otherwise the owner opens each feed in a browser and reports the host of a few links. |
| Q5 | Does GitHub Pages already serve something else from this repository (for example Passningsspelet)? A Pages deployment from Actions replaces the whole site. | Owner checks the Pages settings before S10. If something is already published, the news reader goes to a sub-folder `news-reader/` of the same deployment, and the workflow builds both. |

## 11. Decisions

| # | Decision | Made by | Why |
|---|---|---|---|
| D1 | The deliverable of the design task is a design document only. | Owner | |
| D2 | Items show headline, source, time and link only; no text, no summaries, no images, even if the feed has them. | Owner | Avoids copying content; also part of the answer to the DN terms risk (K5). |
| D3 | Architecture: option D (scheduled build on GitHub Actions, static `news.json` on GitHub Pages). | Worker, recommended | Section 5. |
| D4 | All logic in Python, standard library only; the page is a thin JavaScript layer. | Worker, recommended | Testable in the existing `checks` with `pytest`; no new tools. |
| D5 | Category comes from a dedicated feed when one exists, else from exact `<category>` values, else from the keyword list. | Worker, after D11 | Most reliable method first (R4.2). |
| D6 | No HTML scraping and no getting around robots.txt or other restrictions. | Worker, recommended; in line with the owner's "do not bypass anything" | N3, N5, R6.6. |
| D7 | Time shown as `YYYY-MM-DD HH:MM` in Europe/Stockholm, computed in the build. | Worker, recommended | Testable, unambiguous. |
| D8 | 20 items per source, 7 days, build every 30 minutes, page reload every 10 minutes, stale warning after 3 hours. | Worker, recommended | Section 3. |
| D9 | The build publishes to Pages and never commits to `main`. | Worker, recommended | Direct pushes to `main` are blocked, and commit noise. |
| D10 | Sources live in the repository (`sources.json`, changed through issues). Visitors cannot add their own sources in version 1. Visitor-defined sources would need an own proxy because of CORS (option C) and are a possible later step. | Owner (answers the former question about "the user defines the sites") | |
| D11 | Omni is read from its general feed `https://omni.se/rss.xml` and filtered with a keyword list on headline and description, kept in `politics-keywords.json`. | Owner (answers the former question about Omni) | Omni has no politics feed and no categories (section 4.3). |
| D12 | DN uses its politics feed `https://www.dn.se/rss/om/svensk-politik/`; DN Debatt (opinion) is not included. | Manager verified the feed; leaving out opinion is the worker's recommendation | News only in version 1. |
| D13 | The DN terms risk is accepted for building, with a recommendation to contact Bonnier News / DN before the page is shared widely. | Owner | Section 10.1, K5. |

## 12. Step plan

Each step is meant to become one issue. Levels are from WORKFLOW.md section 1. "Owner only" steps cannot be done by Claude.

| Step | Title | Level | `no-auto-merge` | Depends on | Covers |
|---|---|---|---|---|---|
| S1 | **Owner only:** contact Bonnier News / DN about showing headlines and links, and read Omni's terms of use | Low | no (no pull request) | none | K5, Q2 |
| S2 | News reader: project folder, README, `requirements.txt`, `pytest.ini`, `sources.json` for DN and Omni (with `allowedHosts` per Q4), entry in `applications/README.md`, and a test that validates `sources.json` | Low | no | none | R3.1, R3.7 (config field), R4.1 and R4.3 (config shape) |
| S3 | **Owner only:** add the news-reader test steps to the `checks` job in `ci.yml` | Low | no | S2 | Section 9 (tests in the required check) |
| S4 | News reader: feed parser for RSS 2.0 and Atom, title cleaning, encoding, with hand-written sample feeds | Medium | no | S2 | R1.1, R1.2, R1.3, R1.4, R8.4 (parser part), R9.1 |
| S5 | News reader: time handling (UTC, Europe/Stockholm, display form) | Low | no | S2 | R2.1, R2.2, R2.3, R2.4, R2.5, R2.6 |
| S6 | News reader: `feed` and `categoryFilter` methods, URL check, de-duplicate, age limit, cap per source, sort | Medium | no | S4, S5 | R4.1 (feed, categoryFilter), R4.2, R4.3, R5.1, R5.2, R5.3, R5.4, R5.5, R8.1 |
| S7 | News reader: keyword filter, `politics-keywords.json`, its validation, and a measured check against one saved Omni sample kept outside the repository | Medium | no | S6 | R4.1 (keywordFilter), R4.4, K6 |
| S8 | News reader: build command with fetch layer, robots.txt rule, `enabled` flag, merge with previous file, `news.json`, and a draft of the publishing workflow in the README for the owner | Medium | no | S7 | R3.7, R6.2, R6.3, R6.4, R6.5, R6.6, R8.4 (size limit), section 6 workflow text |
| S9 | News reader: the page (`index.html`, `app.js`, `style.css`) | Medium | **yes** (user-visible; owner tests by hand per section 9) | S8 | R3.2, R3.3, R3.4, R3.5, R3.6, R4.5, R5.6, R7.1, R7.2, R7.3, R7.4, R7.5, R7.6, R7.7, R7.8, R8.2, R8.3, R9.2 |
| S10 | **Owner only:** set GitHub Pages source to "GitHub Actions" (after Q1 and Q5) and add `.github/workflows/news-reader.yml` from the draft in S8 | Low | yes if done as a pull request | S8, S9 | R6.1 |
| S11 | **Owner only:** test the live page and two scheduled runs; share the address widely only after S1 has an answer | Low | n/a | S1, S10 | Section 9, hand tests after publishing; K5 |

Notes on the plan:
- S1 does not block the code. It blocks only wide sharing of the page (S11).
- S4 and S5 can be done in parallel after S2.
- S3 should be done right after S2, so that S4 to S9 are protected by the required check. If S3 is late, each worker runs `bash scripts/check.sh applications/news-reader` locally and says so in the report.
- The owner's answer to Q3 is needed before S9; Q1 and Q5 before S10; Q4 is settled in S2; Q2 in S1.
- Every requirement in section 3 is listed in the "Covers" column of at least one step.
