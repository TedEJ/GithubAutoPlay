# News reader: design

Status: design proposal, no code yet. Written 2026-11-13 by the Designer/Developer worker.

The news reader is a web page that lists headlines about **politics in Sweden** from news sites that the user chooses, for example dn.se and omni.se. Each item shows the headline, the source name, the publication time and a link to the original article.

Important up front: **the source research in section 4 could not be done by fetching dn.se or omni.se directly.** Both hosts were refused by the network policy of the environment this design was written in. Every feed address in this document is therefore marked *not verified*, and step S1 in the step plan (section 12) is a check by the owner that must be done before any code depends on these addresses.

## 1. Goal and non-goals

### Goal
- G1. One web page that shows the newest headlines about politics in Sweden from the sources the user has chosen, merged into one list, newest first.
- G2. Each item shows only: headline, source name, publication time, link to the original article.
- G3. The user chooses which sources to show, and can add and remove sources.
- G4. The page can be hosted by what the repository already has: a GitHub repository with GitHub Pages and GitHub Actions.
- G5. The logic (reading feeds, choosing the category, removing duplicates, sorting, formatting time) can be tested automatically without a browser and without a network, in the same way as Countdown.

### Non-goals
- N1. No article text, no summary or lead paragraph (ingress), no images, even when the feed carries them.
- N2. No categories other than politics in Sweden in the first version. The data shape allows more categories later.
- N3. No scraping of HTML pages. A source without a usable feed is not read (see section 4.3 and requirement R4.3).
- N4. No user accounts, no login, no server-side storage of the user's choices.
- N5. No getting around paywalls. Links go to the original article as it is; if the article is behind a paywall, that is the source's decision.
- N6. No matching of the same story across different sources by headline similarity (only exact duplicates are removed, see R5.3).
- N7. No notifications, no search, no read/unread marking.

## 2. Users and scenarios

### Users
- The owner, who reads the page in a browser on a computer or phone.
- Anyone else the owner gives the address to. The page is public when it is on GitHub Pages of a public repository; each browser keeps its own choice of sources.
- The owner as maintainer: adds new sources to the catalogue of sources (see 2.4).

### 2.1 Read the news (main flow)
1. The user opens the page address.
2. The page loads the latest published news file (`news.json`, see section 7).
3. The page reads the user's chosen sources from the browser's local storage. The first time there is no choice yet, so all sources in the catalogue that have a politics feed are chosen.
4. The page shows one list, newest first, of the items from the chosen sources: headline (as a link), source name, time.
5. At the top the page shows when the news file was built ("Senast uppdaterad 2026-11-13 14:05").
6. The user clicks a headline. The original article opens in a new tab.

### 2.2 Remove a source
1. The user opens "Källor" (sources) on the page. It shows every source in the catalogue with a check box, and next to sources that cannot be used for politics the text "Ingen politikkälla".
2. The user clears the check box for omni.se.
3. The list updates at once and no longer shows items from omni.se. The choice is saved in local storage and is still there after a reload.

### 2.3 Add a source that is already in the catalogue
1. The user opens "Källor" and ticks a source.
2. The list updates at once with that source's items (they are already in `news.json`, because the build reads every catalogue source).

### 2.4 Add a source that is not in the catalogue
The page cannot read a new site by itself (see section 5: a browser cannot read other sites' feeds, and the build job only reads the catalogue). So adding a new site is a change to the repository:
1. The owner opens an issue "Add source X to the news reader", with the site name and, if known, its politics feed.
2. A worker checks the feed (format, fields, category) and the site's terms, and adds one entry to `sources.json` with a test that uses a saved, hand-written sample in the same shape.
3. After the merge, the next scheduled build reads the new source, and it appears in "Källor" for every user, not ticked (R3.4).

This is the main difference from what the owner described ("the user defines the sites"). See open question Q1 in section 10.

### 2.5 Something is wrong
- The page is opened without a network: it shows the last news it showed in this browser, with the notice "Offline – visar sparade nyheter från <time>" (R7.2).
- A source failed in the last build: its items from the last successful build are still shown, and "Källor" shows "Kunde inte hämtas sedan <time>" next to it (R6.2, R6.3).
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
- R2.6 (auto) The "last built" time on the page comes from `generatedAt` in `news.json` and is shown in the same form as R2.3.

### R3. Sources and the user's choice
- R3.1 (auto) The catalogue of sources is the file `sources.json` (shape in section 7.1). The build reads every source in it that has a method for the category.
- R3.2 (hand) The user's choice is a list of source ids saved in the browser's `localStorage` under the key `newsReader.selectedSources`.
- R3.3 (hand) When the key does not exist (first visit), all catalogue sources that have a politics method are chosen.
- R3.4 (hand) A source added to the catalogue after the user's first visit is not chosen automatically; it is shown in "Källor" as not ticked.
- R3.5 (hand) A saved id that is no longer in the catalogue is ignored and removed from the saved list the next time the user changes the choice.
- R3.6 (hand) If `localStorage` cannot be read or written (private mode or blocked storage), the page still works with the default choice of R3.3, and changes last until the page is closed.

### R4. Category: politics in Sweden
- R4.1 (auto) The category id is `politics-sweden`. A source can supply it in one of two ways, set in `sources.json`:
  - `feed`: a dedicated politics feed. Every item in that feed belongs to the category.
  - `categoryFilter`: a general feed, where an item belongs to the category only if one of its RSS `<category>` or Atom `<category term>` values matches one of the listed values exactly, ignoring case and leading and trailing white space.
- R4.2 (auto) Headline words are never used to decide the category.
- R4.3 (auto) A source with neither method for the category gets no items, and the build records the status `no-category-feed` for it. The page shows "Ingen politikkälla" next to it in "Källor" and never shows items for it.

### R5. Selection, duplicates and order
- R5.1 (auto) At most 20 items per source are kept in `news.json`: the 20 newest by `published`. Items with `published` `null` come after all dated items and fill the 20 only if fewer than 20 dated items exist.
- R5.2 (auto) Items with `published` older than 7 days before the build time are dropped.
- R5.3 (auto) Duplicates are removed by normalised URL: the scheme and host are made lower case, `www.` is removed from the host, the query string and the fragment are removed, and a trailing `/` is removed. Within one source the first item in feed order is kept. Across sources the item from the source listed first in `sources.json` is kept.
- R5.4 (auto) `id` is the first 16 hexadecimal characters of the SHA-256 of the normalised URL, so the same article always gets the same id.
- R5.5 (auto) The items in `news.json` are sorted by `published`, newest first; items with `null` last; equal times are ordered by `sourceId`, then by `title`.
- R5.6 (hand) The page shows the items of the chosen sources in the order of `news.json`. It does not sort again.

### R6. Refresh and errors in the build
- R6.1 (hand, owner) The build runs every 30 minutes on a schedule, and can be started by hand from the Actions tab.
- R6.2 (auto) Each source is fetched with a timeout of 15 seconds and one request per feed per build; HTTP redirects are followed only within the source's `allowedHosts`. If a fetch fails (network error, HTTP status other than 200, not parseable as RSS 2.0 or Atom, or zero items, or a redirect to a host outside the source's `allowedHosts`), the build keeps that source's items from the previously published `news.json` if they are less than 24 hours old, and records the status `error` with the time of the last success.
- R6.3 (auto) `news.json` has a `sources` list with one entry per catalogue source: `id`, `name`, `status` (`ok`, `error` or `no-category-feed`), `lastSuccess` (UTC time or `null`), `itemCount`.
- R6.4 (auto) A failing source never makes the whole build fail. The build fails (non-zero exit code, so no new file is published) only if `sources.json` is invalid.
- R6.5 (auto) The build sends the request header `User-Agent: GithubAutoPlay-news-reader/1.0` and no cookies.

### R7. Page behaviour, refresh, offline
- R7.1 (hand) The page loads `news.json` when it opens, again every 10 minutes while it is open, and when the user presses the button "Uppdatera". A new load replaces the list only when it succeeds.
- R7.2 (hand) After each successful load the page saves the file in `localStorage` under `newsReader.lastNews`. If loading fails, the page shows the saved copy with the notice "Offline – visar sparade nyheter från <generatedAt>". If there is no saved copy, it shows "Kunde inte hämta nyheter. Försök igen senare."
- R7.3 (hand) If `generatedAt` is more than 3 hours before the viewer's clock, the page shows "Nyheterna kan vara gamla – senast uppdaterad <time>".
- R7.4 (hand) If none of the chosen sources has items, the page shows "Inga nyheter från valda källor."
- R7.5 (hand) The page works on a phone screen 360 pixels wide without sideways scrolling; long headlines wrap.
- R7.6 (hand) The page loads no scripts, fonts or styles from other sites.
- R7.7 (hand) The page text is in Swedish (see Q5).

### R8. Safety of links and text
- R8.1 (auto) An item `url` is kept only if its scheme is `https` or `http` and its host is the source's host or ends with `.` plus one of the source's `allowedHosts` in `sources.json`. Other items are dropped. `http` links are kept as they are (not rewritten).
- R8.2 (hand) The page writes all text with `textContent`, never with `innerHTML`, so a headline cannot inject HTML.
- R8.3 (hand) Each link opens in a new tab with `target="_blank"` and `rel="noopener noreferrer"`.
- R8.4 (auto) The build reads feeds with an XML parser that does not resolve external entities, and refuses a response larger than 2 MB.

### R9. Encoding
- R9.1 (auto) The build decodes each feed by the encoding in its XML declaration (UTF-8 and ISO-8859-1 must both work) and writes `news.json` as UTF-8. Å, ä, ö, é and other letters come through unchanged.
- R9.2 (hand) The page declares `<meta charset="utf-8">`.

## 4. Findings about the sources

### 4.1 How this was checked, and what could not be checked
Checked on **2026-11-13**.

- Direct requests from this environment to `https://www.dn.se/robots.txt`, `https://www.dn.se/rss/`, `https://www.dn.se/rss/politik/`, `https://www.dn.se/rss/nyheter/politik/`, `https://www.dn.se/nyheter/politik/rss/`, `https://omni.se/robots.txt`, `https://omni.se/rss`, `https://omni.se/rss.xml` and `https://omni.se/feed` were all refused by the environment's network proxy (HTTP 403 on connect, a policy refusal). The web-fetch tool also reported the sites `www.dn.se` and `omni.se` as blocked. **No feed, robots.txt or terms page of dn.se or omni.se was read directly.**
- What is reported below comes from two third-party feed directories that list these feeds and show their recent items: Feeder (feeder.co) and Feedspot (rss.feedspot.com). They show the feed as rendered by their own reader, not the raw XML. So the format details (exact XML element names) are **not verified**.
- No page asked this worker to do anything; nothing in the fetched pages looked like instructions.

### 4.2 dn.se (Dagens Nyheter)

| Feed URL (not verified directly) | What the evidence says | Seen where |
|---|---|---|
| `https://www.dn.se/rss/` | Main news feed. About 61 items per day, 441 in the last 7 days. Per item: headline with link, time, a short summary, image. | Feeder page `https://feeder.co/discover/5d5e097e2f/dn-se-rss`, and Feedspot |
| `https://www.dn.se/rss/om/svensk-politik/` | Listed as "Dagens Nyheter » Politik". This is the candidate politics feed. Item fields, item count and whether it is still working: **not verified**. | Feedspot page `https://rss.feedspot.com/dagensnyheter_rss_feeds/` (updated 2026-08-20 according to the page) |
| `https://www.dn.se/rss/sverige/` | "Sverige" (domestic news, broader than politics). | Feedspot |
| `https://www.dn.se/rss/ekonomi/` | Economy. Shows 12 latest items with summary and image. | Feeder `https://feeder.co/discover/b6e11a4eee/dn-se-rss` |
| `https://www.dn.se/rss/debatt/` | DN Debatt opinion pieces, 7 to 11 per week. Political, but opinion, not news. | Feeder `https://feeder.co/discover/d2d3510072/dn-se-rss` |
| `https://www.dn.se/nyheter/m/rss/` | Listed by Feeder as "Nyheter", tagged News, Politics, Sweden. What `/m/` means is unknown. | Feeder `https://feeder.co/discover/9b9806558b/dn-se-rss` |

Feedspot lists 18 dn.se feeds in total. The other ones (Kultur, Hälsa, Göteborg, Stockholm, Skåne, Motor, Vetenskap, Världen, Mat & Dryck, Sport, Norra Sverige, Psykologi, Privatekonomi, Recept) are not about politics in Sweden.

The pattern `https://www.dn.se/rss/om/<topic>/` (used for `svensk-politik`, `halsa`, `psykologi`, `privatekonomi`, `recept`) suggests that DN publishes one feed per topic tag. That is an inference, not a verified fact.

**Recommendation for dn.se:** method `feed` with `https://www.dn.se/rss/om/svensk-politik/`, provided step S1 confirms it. If it does not exist, use `categoryFilter` on `https://www.dn.se/rss/` only if the raw XML shows `<category>` values that mark politics (not verified that it does). `https://www.dn.se/rss/debatt/` is left out: it is opinion, and mixing it in would change what "news" means for the user (see Q4).

**Images and summaries:** both directories show a short summary and an image for dn.se items, so the feeds very likely carry a `<description>` and an image element. The design deliberately drops them (N1, R1.1).

**Paywall:** many dn.se articles need a subscription. The link still goes to the original article (N5).

**Terms and robots.txt for dn.se:** not read, because the site was blocked. A web search for DN's terms about RSS use found nothing. **Not verified** what DN says about showing its headlines and links on another site. To be checked by the owner in S1.

### 4.3 omni.se (Omni)

- Feeder's page for omni.se (`https://feeder.co/discover/15971fb28a/omni-se`) says that Omni "has no RSS feed of its own" and that Feeder builds a feed by reading the omni.se front page itself. Feeder showed 12 items, last updated on 2026-11-13.
- No other directory listed an omni.se feed. No public API for Omni was found. Wikipedia describes Omni as a news aggregator from Schibsted that summarises news from other media; some content needs a subscription (Omni Mer, Omni Ekonomi). Wikipedia does not mention RSS or an API.
- Whether omni.se has a politics section page, and at which address, was **not verified**.

**Conclusion for omni.se:** no politics feed and no general feed were found. Under R4.3 omni.se gets the status `no-category-feed` and shows "Ingen politikkälla". The design does not scrape the omni.se front page (N3): HTML scraping breaks without warning when the page changes, and the terms were not readable. See Q2.

**Terms and robots.txt for omni.se:** not read, because the site was blocked; a web search for Omni's terms of use did not find them. **Not verified.**

### 4.4 Can a browser read these feeds directly?
Whether dn.se sends the header `Access-Control-Allow-Origin` on its feeds could not be checked. Large news sites usually do not, and without it a page on another site cannot read the feed (CORS). The recommended design does not depend on the answer.

### 4.5 Summary of what is not verified
1. That `https://www.dn.se/rss/om/svensk-politik/` exists, is RSS 2.0, and how many items it has.
2. The exact XML fields of any dn.se feed (`pubDate` form, `<category>` values, image element).
3. dn.se and omni.se robots.txt and terms of use about feeds and headlines on other sites.
4. That omni.se has no feed (only Feeder's statement).
5. CORS headers on dn.se feeds.
6. That GitHub's Action runners are allowed to fetch dn.se (very likely, not tested).

## 5. Options considered and the recommendation

### Option A: pure static page that fetches the feeds in the browser
- How: `index.html` on GitHub Pages; JavaScript fetches each feed URL the user typed and parses it.
- Breaks: the browser blocks reading another site's response unless that site allows it (CORS). Large news sites usually do not (not verified for dn.se, section 4.4). omni.se has no feed at all. If the feed is blocked, nothing works.
- Benefit: the user could type any feed address, which matches "the user defines the sites" best.
- Verdict: rejected, because it most likely does not work at all, and its logic would be JavaScript that the current check `checks` cannot test (it has only Python).

### Option B: static page plus a public CORS proxy
- How: like A, but each request goes through a public relay service that adds the CORS header.
- Costs and breaks: every user's requests go through an unknown third party; free relays are often slow, rate-limited or shut down; the third party can change the content. It also hides who is fetching from the news site.
- Verdict: rejected for reliability and trust.

### Option C: page plus our own small proxy or serverless function
- How: a small function (for example on a separate serverless platform) fetches a feed on request and returns it with a CORS header.
- Costs: needs an account and deployment outside GitHub, which this repository cannot host (GitHub Pages serves only static files). Needs credentials for deployment, which the workflow rules keep away from Claude. A proxy that fetches any URL can be misused by others unless it is restricted to a list, which brings back the catalogue of option D anyway.
- Verdict: rejected for now; a possible later step if typing any feed address becomes a must (Q1).

### Option D (recommended): scheduled build on GitHub Actions publishes a static `news.json`; the page reads it
- How: a Python program in `applications/news-reader/` reads the catalogue `sources.json`, fetches each politics feed, parses, filters, removes duplicates, sorts and writes `news.json`. A GitHub Actions workflow runs it every 30 minutes and publishes `index.html`, `app.js`, `style.css`, `news.json` to GitHub Pages with the official Pages deployment action. The page reads `news.json` from its own site, so there is no CORS problem.
- Why:
  - Works with what the repository has: GitHub Actions and GitHub Pages.
  - No CORS problem and no third party in between.
  - Each feed is fetched once per run for all readers (48 requests per feed per day), which is polite to the news sites.
  - All logic is Python, which the required check `checks` already runs with `pytest` (after the owner adds a step, S3). The page stays thin.
  - The published file never contains summaries or images (N1), because the build drops them.
- Costs and limits:
  - Only sources in the catalogue can be shown. Adding a site is an issue and a pull request (flow 2.4). This differs from the owner's wording; see Q1.
  - Freshness is at best the schedule (30 minutes), and GitHub may delay scheduled runs at busy times.
  - The workflow file and the Pages setting can only be added by the owner (S9).
  - The build must not commit `news.json` to `main`: direct pushes to `main` are blocked by the ruleset, and a commit every 30 minutes would fill the history. That is why it publishes to Pages as a deployment artifact instead of committing.
  - In a private repository GitHub Pages needs a paid plan, and Actions minutes count against a monthly quota (see Q3).

### Option E: run on the user's own computer
- How: the user runs `python -m newsreader.serve` which builds `news.json` from any feeds the user lists and serves the page on `http://localhost`.
- Benefit: the user can add any feed without a pull request.
- Costs: only works on a computer with Python and while the program runs; not on a phone; not shareable.
- Verdict: not chosen as the main design, but it reuses the same Python modules as D, so it is a cheap later addition (follow-up idea, not in the step plan).

### Decision
Option D. It is the only option that works with the repository's hosting, does not depend on unverified CORS behaviour or on third parties, and keeps the logic testable in the existing check.

## 6. Architecture of the recommendation

```
applications/news-reader/
  README.md                 project description, how to run and test
  news-reader-design.md     this document
  requirements.txt          pytest (the build itself uses only the Python standard library)
  pytest.ini
  sources.json              the catalogue of sources (section 7.1)
  newsreader/
    __init__.py
    model.py                NewsItem and SourceStatus data classes; no I/O
    parse.py                RSS 2.0 and Atom bytes -> list of raw entries; no network
    timeutil.py             parse dates, convert to UTC, format Europe/Stockholm (R2)
    select.py               category rule, URL check, title cleaning, cut to length,
                            de-duplicate, drop old, cap per source, sort (R1, R4, R5, R8.1)
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
    test_build.py           uses a fake fetch function, no network
```

### Pure logic (tested without browser or network)
`parse.py`, `timeutil.py`, `select.py`, `model.py`, and `build.py` with an injected fetch function. These take bytes and values in and give values out. `build.py` gets the fetch function and the current time as parameters, so tests control both.

### Network layer
`fetch.py` only: one function `fetch(url) -> bytes` that applies the timeout (R6.2), the 2 MB limit (R8.4) and the User-Agent (R6.5). It is the only place that imports `urllib.request`.

### Page layer (thin, tested by hand)
`app.js` does only this:
1. Fetch `news.json` from the same folder (R7.1); save or fall back to `localStorage` (R7.2).
2. Read and write the chosen sources in `localStorage` (R3.2 to R3.6).
3. Show `items` whose `sourceId` is chosen, in file order, with `textContent` and safe links (R5.6, R8.2, R8.3).
4. Show "Källor" with check boxes and the status of each source (R4.3, R6.3).
5. Show the notices of R7.2, R7.3 and R7.4.

It does no parsing, no time conversion and no sorting; `publishedDisplay` comes ready from the build. The only clock comparison in the page is the staleness warning in R7.3.

### Publishing (owner-added workflow, step S9)
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
      "homepage": "https://www.dn.se/",
      "allowedHosts": ["dn.se"],
      "categories": {
        "politics-sweden": { "method": "feed", "url": "https://www.dn.se/rss/om/svensk-politik/" }
      }
    },
    {
      "id": "omni",
      "name": "Omni",
      "homepage": "https://omni.se/",
      "allowedHosts": ["omni.se"],
      "categories": {}
    }
  ]
}
```
- `id`: lower-case letters, digits and `-`, unique.
- A `categoryFilter` method looks like `{ "method": "categoryFilter", "url": "<general feed>", "values": ["Politik"] }`.
- The DN URL is the candidate from section 4.2 and is used only after S1 confirms it.

### 7.2 The user's choice (in the browser)
- `localStorage["newsReader.selectedSources"]` = JSON list of source ids, for example `["dn"]`.
- `localStorage["newsReader.lastNews"]` = the last `news.json` that loaded successfully (R7.2). Its size stays small: at most 20 items per source.
- Nothing about the user is stored anywhere else.

### 7.3 The published file: `news.json`
```json
{
  "version": 1,
  "generatedAt": "2026-11-13T13:05:12Z",
  "category": "politics-sweden",
  "sources": [
    { "id": "dn", "name": "DN", "status": "ok", "lastSuccess": "2026-11-13T13:05:12Z", "itemCount": 20 },
    { "id": "omni", "name": "Omni", "status": "no-category-feed", "lastSuccess": null, "itemCount": 0 }
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
The headline and URL above are made up for illustration.

## 8. Edge cases and failure modes

| Case | What happens | Requirement |
|---|---|---|
| A source is down, times out or answers with an error | Its previous items (under 24 h old) are kept; status `error`; other sources unaffected | R6.2, R6.3, R6.4 |
| A feed changes format (not RSS 2.0 or Atom, or the XML is broken) | Treated as a failed fetch; previous items kept; the owner sees `error` in "Källor" | R6.2 |
| A feed moves (HTTP redirect) | Redirects are followed within the same allowed hosts; a redirect to another host counts as an error | R6.2, R8.1 |
| A feed suddenly has zero items | Treated as a failure, so the page does not go empty because of a temporary problem | R6.2 |
| The whole scheduled job stops (disabled, quota used up) | `news.json` stops changing; the page warns after 3 hours | R7.3 |
| GitHub disables a scheduled workflow after 60 days without repository activity (public repositories) | Same as above; the owner re-enables it | R7.3, risk K3 |
| Same article twice in one feed, or in two sources | Removed by normalised URL | R5.3 |
| Same story, different articles in two sources | Both are shown (not a duplicate by this design) | N6 |
| Item without time | Kept, shown "Tid saknas", sorted last | R2.4, R5.1 |
| Time in the future (wrong feed data) | More than 10 minutes ahead is treated as no time | R2.5 |
| Time without zone, or summer/winter time change | Read as Europe/Stockholm; shown via time zone rules | R2.2, R2.3 |
| Very long headline | Cut to 200 characters with `…`; wraps on screen | R1.3, R7.5 |
| HTML or entities in a headline | Tags removed, entities decoded, written as text | R1.2, R8.2 |
| Swedish letters, ISO-8859-1 feed | Decoded by the declared encoding; output UTF-8 | R9.1, R9.2 |
| A link to another site, `javascript:` or `data:` link | Item dropped | R8.1 |
| Opening the link | New tab, no access back to the reader page | R8.3 |
| A huge or hostile feed | Over 2 MB refused; external entities not resolved | R8.4 |
| Source without a politics feed (omni.se today) | Shown as "Ingen politikkälla", never scraped | R4.3, N3 |
| Article behind a paywall | Shown and linked as any other | N5 |
| Browser offline | Last saved copy with a notice | R7.2 |
| Local storage blocked | Default choice, page still works | R3.6 |
| A chosen source is removed from the catalogue | Ignored | R3.5 |
| The user unticks every source | "Inga nyheter från valda källor." | R7.4 |

## 9. Testing strategy

### Automated (pytest, no network, no browser)
Tests live in `applications/news-reader/tests/` and use **hand-written sample feeds** in `tests/fixtures/`, written in the shape of RSS 2.0 and Atom with made-up Swedish headlines. They are not copies of real dn.se content. Planned samples:
1. `rss_politics_basic.xml`: RSS 2.0, 25 items, `pubDate` in `+0100` and `+0200`, with `<description>`, `<category>` and an image element (to prove they are dropped).
2. `rss_iso8859.xml`: declared ISO-8859-1, headlines with å, ä, ö, é.
3. `rss_edge_cases.xml`: empty title, title with HTML tags and entities, a 300-character title, no `pubDate`, a future date, a date older than 7 days, a `javascript:` link, a link to a foreign host, two items with the same URL differing only in query string.
4. `atom_basic.xml`: Atom with `published` on some entries and only `updated` on others.
5. `rss_category_filter.xml`: a general feed where only some items carry the category value `Politik`.
6. `not_a_feed.html` and `broken.xml`: to test the failure path.
7. `previous_news.json`: a published file, to test that items of a failing source are kept for under 24 hours and dropped after.

What the tests cover: every requirement marked (auto) in section 3. `build.py` is tested with a fake fetch function (returns fixture bytes, or raises a timeout) and a fixed "now", including the time zone examples in R2.3 for both winter and summer time.

How they run:
- Locally: `bash scripts/check.sh applications/news-reader` (the script takes the project folder as an argument) and, as today, `bash scripts/check.sh` for Countdown.
- In the required check `checks`: `ci.yml` today runs only the Countdown tests and the script tests. Two steps must be added to the `checks` job (install requirements and run `python -m pytest` in `applications/news-reader`). That is a workflow change only the owner can make (step S3). Until then the news-reader tests do not protect pull requests.

Optionally, a real feed snapshot fetched once by the owner can be used locally to confirm that the parser handles the real dn.se shape; it is not committed (the brief says not to copy news content into the repository).

### By hand (owner)
- The feed check in S1 (open the URLs, read terms).
- The page (S7): with a locally built `news.json` served by `python -m http.server` in the output folder: list order, link opens in a new tab, choosing and unchoosing sources, reload keeps the choice, private window, offline (browser developer tools "Offline"), stale warning (edit `generatedAt`), "Inga nyheter" message, phone width 360 px, Swedish letters.
- After S9 (this is step S10): the live Pages address shows news; a manual run from the Actions tab updates "Senast uppdaterad"; after an hour there have been two scheduled runs.

## 10. Risks and open questions

| # | Question or risk | Proposed way to settle it |
|---|---|---|
| Q1 | The owner said the user defines the sites. In this design the user chooses from a catalogue, and new sites are added by issue. Is that acceptable? | Owner decides. Recommendation: accept the catalogue for version 1; consider option E (local mode) later if typing any feed is needed. |
| Q2 | omni.se has no feed (per Feeder; not verified directly). Keep it in the catalogue as "Ingen politikkälla", drop it, or replace it? | Owner checks omni.se in S1. Recommendation: keep it listed as "Ingen politikkälla" so the behaviour is visible, and add another Swedish source with a verified politics feed in a later issue after checking its feed and terms. |
| Q3 | Is the repository public? GitHub Pages in a private repository needs a paid plan, and in a private repository 48 runs per day count against the monthly Actions minutes. | Owner checks. If private: run every 60 minutes instead of 30 (R6.1) or reconsider hosting. |
| Q4 | Should opinion (DN Debatt) count as "politics in Sweden"? | Owner decides. Recommendation: no, news only, in version 1. |
| Q5 | Page language: Swedish UI text (as Passningsspelet) or English (as Countdown)? | Owner decides. Recommendation: Swedish, since the content is Swedish. |
| Q6 | Is the DN politics feed `https://www.dn.se/rss/om/svensk-politik/` real and current, and does it contain only Swedish politics? | Step S1: owner opens it in a browser and reports format, number of items and a few category values. |
| Q7 | What do DN's and Omni's terms say about showing headlines and links on another site? | Step S1: owner reads the terms and robots.txt and notes what they say. This design gives no legal advice. If the terms forbid it, the project stops for that source. |
| Q8 | Does GitHub Pages already serve something else from this repository (for example Passningsspelet)? A Pages deployment from Actions replaces the whole site. | Owner checks the Pages settings. If something is already published, the news reader goes to a sub-folder `news-reader/` of the same deployment, and the workflow must build both. |
| K1 | dn.se may block or rate-limit GitHub runners. | Seen in the first runs after S9 (status `error`); then decide on fewer runs or another source. |
| K2 | A feed changes address or format without notice. | `error` status and the stale warning make it visible; fix by issue. |
| K3 | Scheduled workflows in public repositories are disabled after 60 days without activity. | The stale warning (R7.3) makes it visible; owner re-enables in the Actions tab. |
| K4 | Scheduled runs can be delayed at busy times. | Accepted; R7.3 uses 3 hours, well above the 30-minute schedule. |

## 11. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Deliverable of this task is a design document only. | Owner decision. |
| D2 | Items show headline, source, time, link only; summaries and images are dropped even if present. | Owner decision; also avoids copying content. |
| D3 | Architecture: option D (scheduled build on GitHub Actions, static `news.json` on GitHub Pages). | Section 5. |
| D4 | All logic in Python, standard library only; page is a thin JavaScript layer. | Testable in the existing `checks` with `pytest`; no new tools. |
| D5 | Category comes from a dedicated feed or exact `<category>` values, never from headline words. | Reliability (R4.2). |
| D6 | No HTML scraping. | Fragile, and terms not verified (N3). |
| D7 | Time shown as `YYYY-MM-DD HH:MM` in Europe/Stockholm, computed in the build. | Testable, unambiguous. |
| D8 | 20 items per source, 7 days, build every 30 minutes, page reload every 10 minutes, stale warning after 3 hours. | Section 3. |
| D9 | The build publishes to Pages and never commits to `main`. | Direct pushes to `main` are blocked, and commit noise. |

## 12. Step plan

Each step is meant to become one issue. Levels are from WORKFLOW.md section 1. "Owner only" steps cannot be done by Claude.

| Step | Title | Level | `no-auto-merge` | Depends on | Covers |
|---|---|---|---|---|---|
| S1 | **Owner only:** check the dn.se and omni.se feeds and terms | Low | no (no pull request) | none | Q2, Q6, Q7; section 4.5 items 1 to 4 |
| S2 | News reader: project folder, README, `requirements.txt`, `pytest.ini`, `sources.json` with the result of S1, entry in `applications/README.md`, and a test that validates `sources.json` | Low | no | S1 | R3.1, R4.1 (catalogue shape), R4.3 (Omni entry) |
| S3 | **Owner only:** add the news-reader test steps to the `checks` job in `ci.yml` | Low | no | S2 | Section 9 (tests in the required check) |
| S4 | News reader: feed parser for RSS 2.0 and Atom, title cleaning, encoding, with hand-written sample feeds | Medium | no | S2 | R1.1, R1.2, R1.3, R1.4, R8.4 (parser part), R9.1 |
| S5 | News reader: time handling (UTC, Europe/Stockholm, display form) | Low | no | S2 | R2.1, R2.2, R2.3, R2.4, R2.5, R2.6 (format function) |
| S6 | News reader: category rule, URL check, de-duplicate, age limit, cap per source, sort | Medium | no | S4, S5 | R4.1, R4.2, R4.3, R5.1, R5.2, R5.3, R5.4, R5.5, R8.1 |
| S7 | News reader: build command with fetch layer, merge with previous file, `news.json`, and a draft of the publishing workflow in the README for the owner | Medium | no | S6 | R6.2, R6.3, R6.4, R6.5, R8.4 (size limit), section 6 workflow text |
| S8 | News reader: the page (`index.html`, `app.js`, `style.css`) | Medium | **yes** (user-visible; owner tests by hand per section 9) | S7 | R2.6 (display), R3.2, R3.3, R3.4, R3.5, R3.6, R5.6, R7.1, R7.2, R7.3, R7.4, R7.5, R7.6, R7.7, R8.2, R8.3, R9.2 |
| S9 | **Owner only:** set GitHub Pages source to "GitHub Actions" (after Q3 and Q8) and add `.github/workflows/news-reader.yml` from the draft in S7 | Low | yes if done as a pull request | S7, S8 | R6.1 |
| S10 | **Owner only:** test the live page and two scheduled runs | Low | n/a | S9 | Section 9, hand tests after publishing |

Notes on the plan:
- S4 and S5 can be done in parallel after S2.
- S3 should be done right after S2, so that S4 to S8 are protected by the required check. If S3 is late, each worker runs `bash scripts/check.sh applications/news-reader` locally (and says so in the report).
- The owner's answers to Q1, Q4 and Q5 are needed before S8; Q3 and Q8 before S9; Q2, Q6 and Q7 are answered by S1.
- Every requirement in section 3 is listed in the "Covers" column of at least one step.
