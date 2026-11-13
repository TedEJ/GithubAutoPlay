# News reader: design

Status: design proposal, no code yet. Written 2026-11-13 by the Designer/Developer worker; revised twice the same day with findings and decisions from the manager and the owner (version 3).

The news reader is a web page that lists headlines about **politics in Sweden** from a fixed set of Swedish news sources, starting with DN (dn.se) and SVT (svt.se). Each item shows the headline, the source name, the publication time and a link to the original article. The page text and the news are in Swedish.

How the facts in section 4 were established: the worker's own environment cannot reach the news sites (dn.se, svt.se, omni.se, api.sr.se, regeringen.se and data.riksdagen.se are all refused by its network proxy). The feed and API checks were done by the manager in the owner's browser on 2026-11-13 and handed to the worker. Section 4 says for each fact who checked it and what is still not verified.

## 1. Goal and non-goals

### Goal
- G1. One web page that shows the newest headlines about politics in Sweden from the sources the visitor has chosen, merged into one list, newest first.
- G2. Each item shows only: headline, source name, publication time, link to the original.
- G3. The visitor chooses which of the sources in the repository's catalogue to show. The catalogue is changed through issues and pull requests (decision D10).
- G4. The page is hosted with what the repository already has: GitHub Pages and GitHub Actions in a public repository.
- G5. The logic (reading feeds, choosing the category, removing duplicates, sorting, formatting time) can be tested automatically without a browser and without a network, in the same way as Countdown.

### Non-goals
- N1. No article text, no summary or lead paragraph (ingress), no images, even when the feed carries them. A feed's description may be read by the build to decide the category (R4.4) but is never stored or shown.
- N2. No categories other than politics in Sweden in the first version. The data shape allows more categories later.
- N3. No scraping of HTML pages. Only feeds and APIs that the sources offer are read.
- N4. No user accounts, no login, no server-side storage of the visitor's choices.
- N5. No getting around paywalls, robots.txt rules or any other restriction. Links go to the original as it is.
- N6. No matching of the same story across different sources by headline similarity (only exact duplicates are removed, see R5.3).
- N7. No notifications, no search, no read/unread marking.
- N8. Visitors cannot add sources of their own in version 1 (decision D10; a later possibility is described in section 5, option C).
- N9. No use of any source's content for training AI models (see SVT's content signal in section 4.3). The build only makes a list of headlines and links.

## 2. Users and scenarios

### Users
- The owner, who reads the page in a browser on a computer or phone.
- Anyone else the owner gives the address to. The repository is public, so the page on GitHub Pages is public; each browser keeps its own choice of sources. Because of the DN terms risk (section 10.1), the address should not be shared widely before step S1 is settled.
- The owner as maintainer: adds or removes sources in the catalogue through issues (2.4, 2.5).

### 2.1 Read the news (main flow)
1. The visitor opens the page address.
2. The page loads the latest published news file (`news.json`, see section 7).
3. The page reads the visitor's chosen sources from the browser's local storage. The first time there is no choice yet, so all sources in `news.json` are chosen.
4. The page shows one list, newest first, of the items from the chosen sources: headline (as a link), source name, time.
5. At the top the page shows when the news file was built ("Senast uppdaterad 2026-11-13 14:05").
6. The visitor clicks a headline. The original opens in a new tab.

### 2.2 Hide a source (visitor)
1. The visitor opens "Källor" (sources) on the page. It shows every source in `news.json` with a check box and its status. Sources selected by keywords (SVT) carry the note "Urval med nyckelord – ungefärligt".
2. The visitor clears the check box for SVT.
3. The list updates at once and no longer shows items from SVT. The choice is saved in local storage and is still there after a reload.

### 2.3 Show a source again (visitor)
1. The visitor opens "Källor" and ticks the source.
2. The list updates at once with that source's items (they are already in `news.json`, because the build reads every enabled catalogue source).

### 2.4 Add a source to the catalogue (owner, through an issue)
1. The owner opens an issue "Add source X to the news reader", with the site name and, if known, its feed or API.
2. The manager or the owner checks the feed or API in a browser (format, fields, item count, whether there is a politics feed, categories, CORS header) and the source's robots.txt and terms, because workers cannot reach news sites. The candidates in section 4.6 are examples.
3. A worker adds one entry to `sources.json` with the right method (section 7.1) and a test with a hand-written sample in the same shape. A source whose format the parser does not read yet needs a parser step first (as S13 for Sveriges Radio).
4. After the merge, the next scheduled build reads the new source. It appears in "Källor" for every visitor, not ticked (R3.4).

### 2.5 Remove a source from the catalogue (owner, through an issue)
1. The owner opens an issue, for example because a source asked not to be shown.
2. A worker either deletes the entry from `sources.json`, or sets `"enabled": false` to keep it for later (R3.7).
3. After the merge and the next build, the source's items are no longer in `news.json`, and the page ignores the id in visitors' saved choices (R3.5).

### 2.6 Something is wrong
- The page is opened without a network: it shows the last news it showed in this browser, with a notice (R7.2).
- A source failed in the last build: its items from the last successful build are still shown for up to 24 hours, and "Källor" shows "Kunde inte hämtas sedan <time>" next to it (R6.2, R6.3).
- The news file itself is old (the scheduled job stopped): the page shows a warning (R7.3).

## 3. Requirements

Every requirement is numbered and testable. "Build" means the scheduled job that reads the feeds and writes `news.json`. "Page" means the HTML page. Requirements marked (auto) are covered by automated tests; (hand) are tested by the owner by hand.

### R1. Item content
- R1.1 (auto) Each item in `news.json` has exactly these fields: `id`, `sourceId`, `sourceName`, `title`, `url`, `published`, `publishedDisplay`, `category`. No other fields. In particular no summary, description, content, audio or image field (N1).
- R1.2 (auto) `title` is plain text: HTML tags are removed, HTML and XML entities are decoded (for example `&amp;` becomes `&` and `&#229;` becomes `å`), runs of white space become one space, and leading and trailing white space is removed.
- R1.3 (auto) A `title` longer than 200 characters is cut at 199 characters and gets the character `…` at the end, so it is at most 200 characters. Characters are counted as Unicode code points, so Swedish letters count as one.
- R1.4 (auto) An item with an empty `title` after R1.2, or without a usable `url` (R8.1), is dropped.

### R2. Time
- R2.1 (auto) `published` is stored in UTC in ISO 8601 form with a `Z`, for example `2026-11-13T13:05:00Z`, or `null` when the feed gives no usable time.
- R2.2 (auto) The build reads RSS `pubDate` (RFC 822 date, for example `Fri, 13 Nov 2026 14:05:00 +0100`) and Atom `published`, falling back to Atom `updated` (RFC 3339). A time without a zone is read as Europe/Stockholm.
- R2.3 (auto) `publishedDisplay` is the time in the time zone Europe/Stockholm, 24-hour clock, in the form `YYYY-MM-DD HH:MM`, for example `2026-11-13 14:05`. Summer time is handled by the time zone rules (for example `2026-07-01T10:00:00Z` shows as `2026-07-01 12:00`).
- R2.4 (auto) When `published` is `null`, `publishedDisplay` is `Tid saknas`.
- R2.5 (auto) A time more than 10 minutes after the build time is treated as no usable time (`null`), so a wrong date in a feed cannot keep an item at the top.
- R2.6 (auto) The build writes `generatedAt` (UTC) and `generatedAtDisplay` (same form as R2.3) in `news.json`; the page shows `generatedAtDisplay` as "Senast uppdaterad".

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
- R4.4 (auto) The keyword list is the file `politics-keywords.json` (shape and matching rules in section 7.2). An item matches when its headline or its description (after the cleaning of R1.2) contains at least one `include` term and no `exclude` term. When an item has no description, only the headline is used. The description is used only for this test and is then discarded (N1).
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
- R6.2 (auto) Each source is fetched with a timeout of 15 seconds and one request per feed per build; HTTP redirects are followed only within the source's `allowedHosts`. If a fetch fails (network error, HTTP status other than 200, not parseable in the source's format, zero items, or a redirect to another host), the build keeps that source's items from the previously published `news.json` if they are less than 24 hours old, and records the status `error` with the time of the last success.
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
- R7.7 (hand) All page text is in Swedish (decision D15), with `<html lang="sv">`.
- R7.8 (hand) Below the list the page shows the line "Rubriker och länkar från respektive källa. Klicka för att läsa hos källan." so it is clear that the content belongs to the sources.

### R8. Safety of links and text
- R8.1 (auto) An item `url` is kept only if its scheme is `https` or `http` and its host is one of the source's `allowedHosts` in `sources.json` or ends with `.` plus one of them. Other items are dropped. `http` links are kept as they are (not rewritten).
- R8.2 (hand) The page writes all text with `textContent`, never with `innerHTML`, so a headline cannot inject HTML.
- R8.3 (hand) Each link opens in a new tab with `target="_blank"` and `rel="noopener noreferrer"`.
- R8.4 (auto) The build reads feeds with an XML parser that does not resolve external entities, and refuses a response larger than 2 MB.

### R9. Encoding
- R9.1 (auto) The build decodes each feed by the encoding in its XML declaration (UTF-8 and ISO-8859-1 must both work) and writes `news.json` as UTF-8. Å, ä, ö, é and other letters come through unchanged.
- R9.2 (hand) The page declares `<meta charset="utf-8">`.

### R10. Hosting
- R10.1 (hand, owner) Everything for the news reader lives in `applications/news-reader/` in the repository, and the page is published under the same path on GitHub Pages: `<Pages address>/applications/news-reader/` (decision D16).
- R10.2 (hand, owner) The publishing workflow is separate from `ci.yml`, never commits, and is not a required check.

### R11. Optional source: Sveriges Radio episodes (only if the owner says yes to Q1)
- R11.1 (auto) The build can read episode lists from the Sveriges Radio API (JSON) as a source format `sr-episodes`, mapping the episode title to `title` and the episode page address to `url`. The audio file address and the description are never stored (N1); the description is used only for the keyword match (R4.4).
- R11.2 (auto) The source's `name` in `sources.json` says that it is audio, for example "Ekot (ljud)", so the visitor can see that the link goes to a radio episode and not to an article.
- R11.3 (auto) The time field of an episode is read if the API gives one; which field that is has not been verified (section 4.4). Without a usable time, R2.4 applies.

## 4. Findings about the sources

### 4.1 How this was checked
Date of all checks: **2026-11-13**.

- **Worker's environment:** direct requests to dn.se, svt.se, omni.se, api.sr.se, regeringen.se and data.riksdagen.se were refused by the environment's network proxy (HTTP 403 on connect). The worker used web search and the feed directories Feeder (feeder.co) and Feedspot (rss.feedspot.com) to find candidate addresses, and could read one page on riksdagen.se (the open data terms, section 4.6).
- **Manager, in the owner's browser:** checked DN, SVT, the Sveriges Radio API and robots.txt files. Results marked "verified (manager)" come from that check; the worker has not seen the raw responses itself.
- No page or feed contained anything that looked like instructions to the worker.

Omni (omni.se) was examined in the previous version and has been **removed from the design** by the owner (decision D11).

### 4.2 DN (dn.se)

| URL | Result | Checked by |
|---|---|---|
| `https://www.dn.se/rss/om/svensk-politik/` | **Politics feed. Exists, 100 items.** | Verified (manager). First found on Feedspot `https://rss.feedspot.com/dagensnyheter_rss_feeds/`. |
| `https://www.dn.se/rss/` | Main news feed. Feeder shows a summary and an image per item. | Feeder only, not verified directly. Not used. |
| `https://www.dn.se/rss/debatt/` | DN Debatt opinion pieces. | Feeder only, not verified directly. Not used (decision D12). |

Fields of the politics feed:
- Verified: it is a feed with 100 items.
- **Not verified:** the format (RSS 2.0 is expected because the address is `/rss/`), the exact form of `pubDate`, whether items carry `<description>`, `<category>` or an image element, the link host of the items (`www.dn.se` is expected), and whether the feed sends a CORS header. The design drops descriptions and images in any case (N1, R1.1).

Method for DN: `feed`.

**What DN says about use (as read by the manager in `https://www.dn.se/robots.txt`):** Bonnier News reserves all rights and prohibits scraping, aggregation, and text and data extraction without written permission, and the file blocks many AI crawlers, among them ClaudeBot and Claude-User. The RSS feed is at the same time publicly offered. Whether the feed path is disallowed for a generic User-Agent was not reported; R6.6 makes the build follow whatever the file says. This document gives no legal advice; see section 10.1, K5.

### 4.3 SVT (svt.se)

| URL | Result | Checked by |
|---|---|---|
| `https://www.svt.se/nyheter/inrikes/rss.xml` | **Domestic news feed. HTTP 200, 100 items. Fields per item: `title`, `link`, `description`, `pubDate`, `guid`. No CORS header.** | Verified (manager) |
| `https://www.svt.se/nyheter/rss.xml` | All news. HTTP 200, 100 items. | Verified (manager). Not used: the domestic feed already narrows to Sweden. |
| `https://www.svt.se/nyheter/politik/rss.xml` | 404, no politics feed | Verified (manager) |

- Whether items carry `<category>` elements or images was not reported: **not verified**. If categories exist and mark politics, the method could change to `categoryFilter` later (R4.2).
- The host of the item links was not reported (`www.svt.se` is expected): **not verified**, needed for `allowedHosts` (Q5).

Method for SVT: `keywordFilter` on `https://www.svt.se/nyheter/inrikes/rss.xml` (decision D11). Because the feed is already limited to domestic news, keywords such as "regeringen" will mostly mean the Swedish government, which makes the filter more precise than on a general feed. It is still approximate (K6).

**What SVT says about use (as read by the manager in `https://www.svt.se/robots.txt`):** `User-agent: *` with `Allow: /`, and a content signal `ai-train=no, search=yes, ai-input=yes`, meaning that training AI models on the content is not permitted. The news reader does not train anything: it makes a list of headlines and links (N9). Real SVT copies used to measure the keyword filter are kept outside the repository and are not used for training (section 9). SVT's terms of use beyond robots.txt were not read: **not verified**.

### 4.4 Sveriges Radio (api.sr.se), optional

| URL | Result | Checked by |
|---|---|---|
| `https://api.sr.se/api/v2/news` and `https://api.sr.se/api/v2/news/index` | Open, JSON, `Access-Control-Allow-Origin: *`. Lists 20 news programmes, among them Ekot senaste nytt (id 5380), Ekot nyhetssändning (id 4540) and the regional P4 channels. | Verified (manager) |
| `https://api.sr.se/api/v2/news/episodes` and `https://api.sr.se/api/v2/episodes/index?programid=5380` | **Audio episodes**, with fields `id`, `title`, `description`, `url`, `program`. | Verified (manager) |
| `https://api.sr.se/api/v2/articles` and `https://api.sr.se/api/v2/news/categories` | HTTP 500 | Verified (manager) |

- The API does **not** give text articles by topic. What it gives are radio episodes (Ekot broadcasts), each with a title and a description. A news reader item for SR would therefore be an episode title linking to an episode page, not an article.
- **Not verified:** which field holds the publication time of an episode and in which form; whether a `format=json` parameter is needed (the manager reported JSON, the exact query was not reported); whether `url` is the episode web page on sverigesradio.se or something else; SR's terms of use for the API.
- Because the API sends `Access-Control-Allow-Origin: *`, a page could even call it directly from the browser. The design still reads it in the build like every other source, so that the page has one data path and one place for filtering and tests.
- Method if used: `keywordFilter` on the Ekot senaste nytt episodes (programme id 5380), source name "Ekot (ljud)" (R11). It is **not enabled in version 1**; see Q1 and step S13.

### 4.5 Can a browser read the news feeds directly?
No for SVT (verified: no CORS header). Not checked for DN. Yes for the SR API, but that does not help with the other sources. The recommended design reads every source in the build, so this does not matter for it.

### 4.6 Candidates not yet verified (for the manager to check)
These were found by the worker through web search and feed directories. None has been fetched. Each needs the check in flow 2.4 step 2 before it can be added.

| Candidate | What was found | What it is | What must be checked |
|---|---|---|---|
| Sveriges Radio RSS | Feeder lists `https://api.sr.se/api/rss/program/83` ("Nyheter (Ekot)") and `http://api.sr.se/api/rss/group/27511` ("Toppnyheter från Sveriges Radio"), and P4 regional feeds of the form `https://api.sr.se/api/rss/program/<id>`. Feeder lists no politics or inrikes feed for SR. | Possibly text news items, not only episodes. | Whether the items are articles or episodes; fields; time; whether any feed is about politics; terms. If one carries text news with times, it may be better than R11. |
| Regeringen.se press releases | Feeder lists feeds at `https://www.regeringen.se/Filter/RssFeed?...` with long filter parameters, and a page `https://www.regeringen.se/pressmeddelanden/`. | Official government press releases, not news journalism. | That a press-release feed exists and its exact address; fields; whether the owner wants official press releases in a news list. |
| Riksdagen open data (data.riksdagen.se) | The terms page `https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/anvandarstod/anvandningsvillkor/` was read by the worker: the data is free to use and share if the source is given as "Källa: Sveriges riksdag"; a service must not suggest that the Riksdag runs or endorses it; copyrighted material such as images needs permission. No licence name or fee is given. | Official data (documents, votes, calendar), not news. | Which endpoint would give a readable list (for example new documents or votes), its format and fields, and whether the owner wants official data in a news list. If used, the page must show "Källa: Sveriges riksdag". |

## 5. Options considered and the recommendation

### Option A: pure static page that fetches the feeds in the browser
- How: `index.html` on GitHub Pages; JavaScript fetches each feed and parses it.
- Breaks: the browser blocks reading another site's response unless that site allows it (CORS). Verified for SVT: no CORS header, so it cannot work. DN not checked. Only the SR API allows it.
- Verdict: rejected. It does not work for SVT, and its logic would be JavaScript that the current check `checks` cannot test (it has only Python).

### Option B: static page plus a public CORS proxy
- How: like A, but each request goes through a public relay service that adds the CORS header.
- Costs and breaks: every visitor's requests go through an unknown third party; free relays are often slow, rate-limited or shut down; the third party can change the content. It would also hide who is fetching from the news sites, which goes against N5.
- Verdict: rejected.

### Option C: page plus our own small proxy or serverless function
- How: a small function on a separate serverless platform fetches a feed on request and returns it with a CORS header.
- Costs: needs an account and deployment outside GitHub, which this repository cannot host (GitHub Pages serves only static files). Needs credentials for deployment, which the workflow rules keep away from Claude. A proxy that fetches any URL can be misused unless restricted to a list.
- Verdict: not for version 1. **This is what visitor-defined sources would need later**: because of CORS, letting a visitor type in any feed requires an own proxy like this (or a local program, option E). A possible later step for the owner to decide.

### Option D (recommended): scheduled build on GitHub Actions publishes a static `news.json`; the page reads it
- How: a Python program in `applications/news-reader/` reads `sources.json` and the keyword list, fetches each enabled source, parses, filters, removes duplicates, sorts and writes `news.json`. A GitHub Actions workflow runs it every 30 minutes and publishes the page and `news.json` to GitHub Pages under `applications/news-reader/` with the official Pages deployment actions. The page reads `news.json` from its own site, so there is no CORS problem.
- Why:
  - Works with what the repository has: GitHub Actions and GitHub Pages; the repository is public, so Pages and Actions minutes are free (decision D14).
  - No CORS problem and no third party in between.
  - Each feed is fetched once per run for all visitors (48 requests per feed per day), and robots.txt is respected (R6.6).
  - All logic is Python, which the required check `checks` already runs with `pytest` (after the owner adds a step, S3). The page stays thin.
  - The published file never contains descriptions, images or audio (N1), because the build drops them.
  - Sources live in the repository (decision D10).
- Costs and limits:
  - Visitors cannot add sources (N8).
  - Freshness is at best the schedule (30 minutes), and GitHub may delay scheduled runs at busy times.
  - The workflow file and the Pages setting can only be added by the owner (S10).
  - The build must not commit `news.json` to `main`: direct pushes to `main` are blocked by the ruleset, and a commit every 30 minutes would fill the history. It publishes to Pages as a deployment artifact instead.

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
    parse_sr.py             (only with step S13) SR API episode JSON -> raw entries
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
`parse.py`, `parse_sr.py`, `timeutil.py`, `select.py`, `keywords.py`, `robots.py`, `model.py`, and `build.py` with an injected fetch function. These take bytes and values in and give values out. `build.py` gets the fetch function and the current time as parameters, so tests control both.

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
- steps: check out; set up Python; download the currently published `applications/news-reader/news.json` from the Pages site as `--previous` (ignore a failure the first time); run `python -m newsreader --out _site/applications/news-reader --previous previous.json` in `applications/news-reader`; copy `site/*` into `_site/applications/news-reader/`; upload `_site` with the official upload-Pages-artifact action; deploy with the official deploy-Pages action.
- It must not be added as a required check, and it must not commit (R10.2).
- A copy of the file goes into `GitRequirements/` in the same change, because `GitRequirements/README.md` says the copies there must stay identical to the real workflows.
- A deployment from Actions replaces the whole Pages site. Today nothing in the repository suggests that Pages is in use (section 10.3), but if another project is published later, the same workflow must build both into `_site`.

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
      "format": "rss",
      "categories": {
        "politics-sweden": { "method": "feed", "url": "https://www.dn.se/rss/om/svensk-politik/" }
      }
    },
    {
      "id": "svt",
      "name": "SVT",
      "enabled": true,
      "homepage": "https://www.svt.se/",
      "allowedHosts": ["svt.se"],
      "format": "rss",
      "categories": {
        "politics-sweden": { "method": "keywordFilter", "url": "https://www.svt.se/nyheter/inrikes/rss.xml" }
      }
    }
  ]
}
```
- `id`: lower-case letters, digits and `-`, unique.
- `enabled`: `true` or `false` (R3.7).
- `format`: `rss` (RSS 2.0 or Atom, detected from the content), or `sr-episodes` (only after step S13).
- A `categoryFilter` method looks like `{ "method": "categoryFilter", "url": "<general feed>", "values": ["Politik"] }`. No source uses it today.
- `allowedHosts` are the expected hosts; they must be confirmed from the item links (Q5).
- If step S13 is done, an entry `{ "id": "sr-ekot", "name": "Ekot (ljud)", "format": "sr-episodes", "allowedHosts": ["sverigesradio.se"], ... }` is added with the episode address of section 4.4; its exact URL and host are settled in S12.
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
- The list applies to every source with `keywordFilter`: SVT inrikes now, and SR Ekot episodes if step S13 is done.
- The lists above are the starting proposal. Step S7 checks them against a saved SVT inrikes copy and adjusts them. Words that are too broad on their own, such as "minister", "val" and "parti", are deliberately left out.

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
    { "id": "svt", "name": "SVT", "method": "keywordFilter", "status": "ok", "lastSuccess": "2026-11-13T13:05:12Z", "itemCount": 11 }
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
| A feed changes format (not parseable, or the XML is broken) | Treated as a failed fetch; previous items kept; `error` shown in "Källor" | R6.2 |
| A feed moves (HTTP redirect) | Followed within the source's allowed hosts; a redirect to another host counts as an error | R6.2 |
| A feed suddenly has zero items | Treated as a failure, so the page does not go empty because of a temporary problem | R6.2 |
| robots.txt disallows the feed, or cannot be read | Feed not fetched; status `blocked-by-robots` or `error` | R6.6 |
| A source asks not to be shown | Owner sets `"enabled": false` or removes the entry (flow 2.5) | R3.7 |
| SVT item about Swedish politics without any listed term | Not shown (false negative) | R4.4, K6 |
| SVT inrikes item that matches a term but is not politics (for example "regeringen" in a crime story) | Shown (false positive) until an exclude term is added | R4.4, K6 |
| Item without description | Matched on headline only | R4.4 |
| SR episode (if S13 is done) | Shown with the source name "Ekot (ljud)", links to the episode | R11.1, R11.2 |
| The whole scheduled job stops (disabled, error in the workflow) | `news.json` stops changing; the page warns after 3 hours | R7.3 |
| GitHub disables a scheduled workflow after 60 days without repository activity (applies to this public repository) | Same as above; the owner re-enables it | R7.3, K3 |
| Same article twice in one feed, or in two sources | Removed by normalised URL | R5.3 |
| Same story in DN and SVT | Both are shown (different links, not a duplicate by this design) | N6 |
| Item without time | Kept, shown "Tid saknas", sorted last | R2.4, R5.1 |
| Time in the future (wrong feed data) | More than 10 minutes ahead is treated as no time | R2.5 |
| Time without zone, or summer/winter time change | Read as Europe/Stockholm; shown via time zone rules | R2.2, R2.3 |
| Very long headline | Cut to 200 characters with `…`; wraps on screen | R1.3, R7.5 |
| HTML or entities in a headline | Tags removed, entities decoded, written as text | R1.2, R8.2 |
| Swedish letters, ISO-8859-1 feed | Decoded by the declared encoding; output UTF-8 | R9.1, R9.2 |
| A link to an unlisted host, a `javascript:` or `data:` link | Item dropped | R8.1 |
| Opening the link | New tab, no access back to the reader page | R8.3 |
| A huge or hostile feed | Over 2 MB refused; external entities not resolved | R8.4 |
| Article behind a paywall (DN) | Shown and linked as any other | N5 |
| Browser offline | Last saved copy with a notice | R7.2 |
| Local storage blocked | Default choice, page still works | R3.6 |
| A chosen source is removed from the catalogue | Ignored | R3.5 |
| The visitor unticks every source | "Inga nyheter från valda källor." | R7.4 |

## 9. Testing strategy

### Automated (pytest, no network, no browser)
Tests live in `applications/news-reader/tests/` and use **hand-written sample feeds** in `tests/fixtures/`, with made-up Swedish headlines. They are not copies of real DN, SVT or SR content. Planned samples:
1. `rss_politics_basic.xml`: RSS 2.0, 25 items, `pubDate` in `+0100` and `+0200`, with `<description>`, `<category>` and an image element (to prove they are dropped).
2. `rss_iso8859.xml`: declared ISO-8859-1, headlines with å, ä, ö, é.
3. `rss_edge_cases.xml`: empty title, title with HTML tags and entities, a 300-character title, no `pubDate`, a future date, a date older than 7 days, a `javascript:` link, a link to a foreign host, two items with the same URL differing only in query string.
4. `atom_basic.xml`: Atom with `published` on some entries and only `updated` on others.
5. `rss_category_filter.xml`: a general feed where only some items carry the category value `Politik`.
6. `rss_keyword_filter.xml`: a feed in the shape of SVT inrikes (`title`, `link`, `description`, `pubDate`, `guid`), with made-up items that should match (each include term at least once, prefix forms, "(SD)" after a name), items that should not match ("s" alone, "minister" in another context, sports, weather), an item without description, and an item that matches only through its description.
7. `not_a_feed.html` and `broken.xml`: to test the failure path.
8. `robots_allow.txt`, `robots_disallow_rss.txt`: to test R6.6.
9. `previous_news.json`: a published file, to test that items of a failing source are kept for under 24 hours and dropped after.
10. Only with step S13: `sr_episodes.json`, a hand-written file in the shape reported in section 4.4, with and without a time field.

What the tests cover: every requirement marked (auto) in section 3, plus a test that `sources.json` and `politics-keywords.json` in the repository are valid. `build.py` is tested with a fake fetch function (returns fixture bytes, or raises a timeout) and a fixed "now", including the time zone examples in R2.3 for both winter and summer time.

How well the keyword list works cannot be proven with made-up data. In step S7 the owner (or the manager in the owner's browser, since workers cannot reach svt.se) saves one real copy of `https://www.svt.se/nyheter/inrikes/rss.xml` **outside the repository**; the worker or the owner runs the filter on it and reports in the pull request how many items matched and, by reading the matched and unmatched headlines, roughly how many false positives and false negatives there were. The copy is not committed and is not used for anything else (N9).

How the tests run:
- Locally: `bash scripts/check.sh applications/news-reader` (the script takes the project folder as an argument) and, as today, `bash scripts/check.sh` for Countdown.
- In the required check `checks`: `ci.yml` today runs the Countdown tests, the script tests and the Reviewer verdict step. Two steps must be added to the `checks` job (install requirements and run `python -m pytest` in `applications/news-reader`), and the copy in `GitRequirements/ci.yml` updated to match. That is a workflow change only the owner can make (step S3). Until then the news-reader tests do not protect pull requests.

### By hand (owner)
- The page (S9): with a locally built `news.json` served by `python -m http.server` in the output folder: list order, link opens in a new tab, choosing and unchoosing sources, reload keeps the choice, private window, offline (browser developer tools "Offline"), stale warning (edit `generatedAt`), "Inga nyheter" message, keyword note on SVT, credit line, phone width 360 px, Swedish letters.
- After S10 (this is step S11): the live address `<Pages address>/applications/news-reader/` shows news from both sources; a manual run from the Actions tab updates "Senast uppdaterad"; after an hour there have been two scheduled runs; reading the SVT items for obvious false positives.

## 10. Risks and open questions

### 10.1 Risks

**K5. DN's terms (main risk).** As read by the manager on 2026-11-13, `https://www.dn.se/robots.txt` says that Bonnier News reserves all rights and prohibits scraping, aggregation, and text and data extraction without written permission, and it blocks many AI crawlers, including ClaudeBot and Claude-User. DN does offer the politics feed publicly. A page that collects DN headlines next to other sources can be seen as aggregation. This document gives no legal advice. What the design does about it:
- It shows only headline, source name, time and link, never text or images (D2, N1).
- It fetches the feed once per run for all visitors, sends an honest User-Agent, follows robots.txt and never gets around a rule (R6.5, R6.6, N5).
- DN can be switched off with one line, `"enabled": false` (R3.7).
- **Recommendation: contact Bonnier News / DN and ask whether showing headlines and links from the politics feed on this page is acceptable, before the page address is shared widely** (step S1). Until there is an answer, keep the page for the owner's own use. If the answer is no, set DN to `"enabled": false`.

**K6. The keyword filter is approximate.** SVT has no politics feed (section 4.3), so SVT inrikes items are chosen by keywords in the headline and description (D11); the same applies to SR episodes if they are added. Consequences:
- False positives: a domestic item that mentions the government or a party in passing (for example a crime or weather story quoting a minister) can appear.
- False negatives: Swedish politics news that uses none of the listed terms, for example a headline that names only a minister by name, will be missed.
- The list needs care over time: new party leaders, new party names or new topics. It is changed through issues like `sources.json`.
- The page says so ("Urval med nyckelord – ungefärligt", R4.5).

**K7. SVT's AI-training signal.** SVT's robots.txt says `ai-train=no` (no training of AI models on its content), `search=yes`, `ai-input=yes`. The news reader is a list of headlines and links and trains nothing (N9). The development process uses Claude: workers only read hand-written fixtures, and the one real SVT copy for measuring the filter (S7) is kept outside the repository. SVT's other terms were not read.

| # | Risk | Proposed handling |
|---|---|---|
| K1 | dn.se or svt.se may block or rate-limit GitHub runners. | Seen in the first runs after S10 (status `error`); then decide on fewer runs or dropping the source. |
| K2 | A feed changes address or format without notice. | `error` status and the stale warning make it visible; fix by issue. |
| K3 | Scheduled workflows in public repositories are disabled after 60 days without activity. | The stale warning (R7.3) makes it visible; owner re-enables in the Actions tab. |
| K4 | Scheduled runs can be delayed at busy times. | Accepted; R7.3 uses 3 hours, well above the 30-minute schedule. |
| K5 | DN's terms prohibit aggregation without written permission. | Contact Bonnier News / DN (S1); `enabled: false` if refused. |
| K6 | The keyword filter selects approximately. | Measure in S7, maintain the list through issues, show the note. |
| K7 | SVT does not permit AI training on its content. | Headline-and-link list only; real copies stay outside the repository. |

### 10.2 Remaining open questions

| # | Question | Proposed way to settle it |
|---|---|---|
| Q1 | Should Sveriges Radio Ekot **audio episodes** be a source (R11, step S13), given that they are episodes, not articles? | Owner decides after S12. Recommendation: first let the manager check the SR RSS candidates (section 4.6); if none gives text news, add the episodes as "Ekot (ljud)". |
| Q2 | Should official sources (Regeringen press releases, Riksdagen open data) be in a news list at all? | Owner decides. Recommendation: not in version 1; they are official statements and data, not journalism, and would need their own label and, for Riksdagen, the credit "Källa: Sveriges riksdag". |
| Q3 | Answer from Bonnier News / DN (K5). | Owner contacts them (S1). |
| Q4 | GitHub settings that only the owner can see (section 10.3). | Owner checks before S10. |
| Q5 | Which host do the item links of DN and SVT point to? This sets `allowedHosts`. | Manager or owner opens each feed in a browser and reports the host of a few links, before S2 is merged. |

### 10.3 What was checked about hosting (former Q4)
Checked by the worker in the repository on 2026-11-13, on a fresh branch from `origin/main` (commit `4afc4a7`):
- `.github/workflows/` contains only `auto-merge.yml` and `ci.yml`. There is no Pages workflow.
- The remote branches of `origin` include no `gh-pages` branch.
- There is no `CNAME`, `.nojekyll` or `_config.yml` file anywhere in the repository.
- `README.md`, `WORKFLOW.md` and `GitRequirements/README.md` do not mention GitHub Pages.
- `GitRequirements/` keeps reading copies of the workflows that must stay identical to the real ones; a new workflow needs a copy there (S10).
- `ci.yml` runs only the Countdown tests, the script tests and the Reviewer verdict step; it does not run news-reader tests (S3).

Tried but not possible from the worker's environment: the GitHub API for the repository and the Pages address `https://tedej.github.io/GithubAutoPlay/` were both refused by the environment's proxy, so whether Pages is already switched on was **not verified**.

Only the owner can check, in the repository's settings on GitHub:
1. Settings > Pages: whether Pages is on and what it publishes today; the source must be set to "GitHub Actions" for this design.
2. Settings > Actions > General: that Actions are allowed to run, and the default workflow permissions.
3. Settings > Environments > `github-pages` (created when Pages from Actions is turned on): that deployments from `main` are allowed.

## 11. Decisions

| # | Decision | Made by |
|---|---|---|
| D1 | The deliverable of the design task is a design document only. | Owner |
| D2 | Items show headline, source, time and link only; no text, no summaries, no images, no audio, even if the source has them. | Owner |
| D3 | Architecture: option D (scheduled build on GitHub Actions, static `news.json` on GitHub Pages). | Worker, recommended (section 5) |
| D4 | All logic in Python, standard library only; the page is a thin JavaScript layer. | Worker, recommended |
| D5 | Category comes from a dedicated feed when one exists, else from exact `<category>` values, else from the keyword list. | Worker, recommended |
| D6 | No HTML scraping and no getting around robots.txt or other restrictions. | Owner ("do not bypass anything") and worker |
| D7 | Time shown as `YYYY-MM-DD HH:MM` in Europe/Stockholm, computed in the build. | Worker, recommended |
| D8 | 20 items per source, 7 days, build every 30 minutes, page reload every 10 minutes, stale warning after 3 hours. | Worker, recommended; 30 minutes confirmed by the owner (D14) |
| D9 | The build publishes to Pages and never commits to `main`. | Worker, recommended |
| D10 | Sources live in the repository (`sources.json`, changed through issues). Visitors cannot add their own sources in version 1; that would need an own proxy because of CORS (option C) and is a possible later step. | Owner |
| D11 | Omni is removed from the design. Sources are Swedish news sources with officially offered feeds or open APIs: DN (politics feed) and SVT (inrikes feed with the keyword list on headline and description, kept in `politics-keywords.json`). | Owner |
| D12 | DN uses its politics feed `https://www.dn.se/rss/om/svensk-politik/`; DN Debatt (opinion) is not included. | Manager verified the feed; leaving out opinion is the worker's recommendation |
| D13 | The DN terms risk is accepted for building, with a recommendation to contact Bonnier News / DN before the page is shared widely. | Owner |
| D14 | The repository is public, so GitHub Pages and Actions minutes are free; the build runs every 30 minutes. | Owner (former Q1) |
| D15 | The page text and the news are in Swedish. | Owner (former Q3) |
| D16 | Everything for the news reader lives in `applications/news-reader/`, and the page is published under the same path on Pages. | Owner (former Q5) |
| D17 | Sveriges Radio is an optional source of Ekot episode titles, clearly labelled as audio, not enabled in version 1 (Q1). | Owner (via manager), worker's labelling |

## 12. Step plan

Each step is meant to become one issue. Levels are from WORKFLOW.md section 1. "Owner only" and "Manager or owner" steps cannot be done by a worker, because they need GitHub settings or a browser that can reach the news sites.

| Step | Title | Level | `no-auto-merge` | Depends on | Covers |
|---|---|---|---|---|---|
| S1 | **Owner only:** contact Bonnier News / DN about showing headlines and links | Low | no (no pull request) | none | K5, Q3 |
| S2 | News reader: project folder, README, `requirements.txt`, `pytest.ini`, `sources.json` for DN and SVT (with `allowedHosts` per Q5), entry in `applications/README.md`, and a test that validates `sources.json` | Low | no | none | R3.1, R3.7 (config field), R4.1 and R4.3 (config shape), R10.1 (folder) |
| S3 | **Owner only:** add the news-reader test steps to the `checks` job in `ci.yml`, and update `GitRequirements/ci.yml` | Low | no | S2 | Section 9 (tests in the required check) |
| S4 | News reader: feed parser for RSS 2.0 and Atom, title cleaning, encoding, with hand-written sample feeds | Medium | no | S2 | R1.1, R1.2, R1.3, R1.4, R8.4 (parser part), R9.1 |
| S5 | News reader: time handling (UTC, Europe/Stockholm, display form) | Low | no | S2 | R2.1, R2.2, R2.3, R2.4, R2.5, R2.6 |
| S6 | News reader: `feed` and `categoryFilter` methods, URL check, de-duplicate, age limit, cap per source, sort | Medium | no | S4, S5 | R4.1 (feed, categoryFilter), R4.2, R4.3, R5.1, R5.2, R5.3, R5.4, R5.5, R8.1 |
| S7 | News reader: keyword filter, `politics-keywords.json`, its validation, and a measured check against one saved SVT inrikes copy kept outside the repository | Medium | no | S6 | R4.1 (keywordFilter), R4.4, K6, K7 |
| S8 | News reader: build command with fetch layer, robots.txt rule, `enabled` flag, merge with previous file, `news.json`, and a draft of the publishing workflow in the README for the owner | Medium | no | S7 | R3.7, R6.2, R6.3, R6.4, R6.5, R6.6, R8.4 (size limit), R10.2 (draft), section 6 workflow text |
| S9 | News reader: the page (`index.html`, `app.js`, `style.css`) in Swedish | Medium | **yes** (user-visible; owner tests by hand per section 9) | S8 | R3.2, R3.3, R3.4, R3.5, R3.6, R4.5, R5.6, R7.1, R7.2, R7.3, R7.4, R7.5, R7.6, R7.7, R7.8, R8.2, R8.3, R9.2 |
| S10 | **Owner only:** check the settings in section 10.3, set Pages source to "GitHub Actions", and add `.github/workflows/news-reader.yml` from the draft in S8 together with its copy in `GitRequirements/` | Low | yes if done as a pull request | S8, S9 | R6.1, R10.1 (published path), R10.2, Q4 |
| S11 | **Owner only:** test the live page and two scheduled runs; share the address widely only after S1 has an answer | Low | n/a | S1, S10 | Section 9, hand tests after publishing; K5 |
| S12 | **Manager or owner:** check the candidate sources in section 4.6 (SR RSS feeds, Regeringen press releases, Riksdagen open data) and the open points about the SR API in section 4.4, and report | Low | no (no pull request) | none | Q1, Q2 (input), section 4.6 |
| S13 | Optional, only if the owner says yes to Q1: Sveriges Radio Ekot episodes as a source "Ekot (ljud)" (`parse_sr.py`, fixture, `sources.json` entry) | Medium | **yes** (adds a visible source) | S8, S12 | R11.1, R11.2, R11.3 |

Notes on the plan:
- S1 and S12 do not block the code. S1 blocks only wide sharing of the page (S11).
- S4 and S5 can be done in parallel after S2.
- S3 should be done right after S2, so that S4 to S9 are protected by the required check. If S3 is late, each worker runs `bash scripts/check.sh applications/news-reader` locally and says so in the report.
- Q5 is needed before S2 is merged; Q4 before S10; Q1 and Q2 after S12.
- A new source found in S12 (other than SR episodes) becomes its own issue through flow 2.4.
- Every requirement in section 3 is listed in the "Covers" column of at least one step.
