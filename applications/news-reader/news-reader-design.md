# News reader: design

Status: design proposal, no code yet. Written 2026-11-13 by the Designer/Developer worker and revised five times the same day with findings and decisions from the manager and the owner (version 6).

The news reader is a web page that lists headlines about **politics in Sweden** from **a few approved sites**. Each item shows the headline, the source name, the publication time and a link to the original article. The page text and the news are in Swedish.

**Design principle: a few approved sites.** The sources are an owner-approved list kept in the repository (`sources.json`). A site is added only after its feed and its terms have been checked and the owner has approved it. Visitors cannot add sources. Today the list has two sites: **SVT** and **Sveriges Radio**.

**Architecture in one paragraph (hybrid).** SVT's feed cannot be read from a browser (no CORS header), so a Python build collects SVT's politics headlines into a file `news.json`. Sveriges Radio's terms forbid storing its material, so Sveriges Radio headlines are never written to any file: the page fetches them live from Sveriges Radio's open feed in the visitor's browser, keeps them in memory only, and shows them next to the SVT items. One shared keyword list selects politics items for both. The owner decides whether the page is published on GitHub Pages or only run locally (Q1).

How the facts in section 4 were established: the worker's own environment cannot reach the news sites (all were refused by its network proxy). The feed checks and the reading of terms were done by the manager in the owner's browser on 2026-11-13 and handed to the worker. Section 4 says for each fact who checked it and what is still not verified.

## 1. Goal and non-goals

### Goal
- G1. One web page that shows the newest headlines about politics in Sweden from the approved sources the reader has chosen, merged into one list, newest first.
- G2. Each item shows only: headline, source name, publication time, link to the original.
- G3. The sources are a few approved sites in `sources.json`, changed only through issues that the owner approves (decision D10).
- G4. The page can run locally on the owner's computer, and can be published with what the repository already has (GitHub Pages and GitHub Actions in a public repository) if the owner decides so (Q1).
- G5. The logic (reading feeds, choosing the category, removing duplicates, sorting, formatting time) can be tested automatically without a browser and without a network.
- G6. Each source is used in a way that follows what its terms and robots.txt say, as far as they have been read.

### Non-goals
- N1. No article text, no summary or lead paragraph (ingress), no images, even when the feed carries them. A feed's description or summary may be read to decide the category (R4.4) but is never stored or shown.
- N2. No categories other than politics in Sweden in the first version.
- N3. No scraping of HTML pages. Only feeds that the sources offer are read.
- N4. No user accounts, no login, no server-side storage of the reader's choices.
- N5. No getting around paywalls, robots.txt rules, terms or any other restriction.
- N6. No matching of the same story across different sources by headline similarity.
- N7. No notifications, no search, no read/unread marking.
- N8. Visitors cannot add sources (decision D10). Visitor-defined sources would need an own proxy because of CORS (section 5, option C); a possible later step.
- N9. No use of any source's content for training AI models.
- N10. **No Sveriges Radio material is stored anywhere**: not in the repository, not in `news.json`, not on GitHub Pages, not in the browser's storage (decision D18).
- N11. No advertising, no marketing, no analytics on the page.
- N12. Official sources such as Regeringen.se (government press releases) and Riksdagen's open data are out of scope for now (decision D13).
- N13. DN is not a source (decision D12).

## 2. Users and scenarios

### Users
- The owner, who **only reads** the page, on a computer or a phone (decision D20). The page is not meant to be shared.
- If the page is published on GitHub Pages (Q1), anyone who finds the address can see it, because the repository is public (risk K11).
- The owner as maintainer: approves additions to and removals from the list of sources through issues.

### 2.1 Read the news (main flow)
1. The reader opens the page: locally at `http://localhost:8000/` after running the build (R12.1), or at the Pages address if the owner has chosen to publish (R12.2).
2. The page loads `sources.json`, `politics-keywords.json` and `news.json` from its own folder.
3. In parallel the page fetches the Sveriges Radio feed directly from Sveriges Radio (R7.1).
4. The page reads the reader's chosen sources from the browser's local storage. The first time, all sources are chosen.
5. The page shows one list, newest first, of SVT items (from `news.json`) and Sveriges Radio items (from memory) from the chosen sources: headline as a link, source name, time.
6. At the top the page shows when the SVT data was built ("SVT uppdaterad 2026-11-13 14:05") and when Sveriges Radio was fetched ("Sveriges Radio hämtad 14:07").
7. The reader clicks a headline. The original opens in a new tab.

### 2.2 Hide a source
1. The reader opens "Källor" (sources). It lists every approved source with a check box, its status, and the note "Urval med nyckelord – ungefärligt" (both sources are selected by keywords).
2. The reader clears the check box for SVT.
3. The list updates at once without SVT. The choice (only the source ids) is saved in local storage.

### 2.3 Show a source again
1. The reader ticks the source in "Källor".
2. The list updates at once.

### 2.4 Add a site to the approved list (owner, through an issue)
1. The owner opens an issue "Add source X to the news reader".
2. The manager or the owner checks, in a browser (workers cannot reach news sites): the feed (format, fields, item count, politics feed or categories, CORS header) and the site's terms and robots.txt.
3. The terms decide **where** the source may be fetched:
   - If storing headlines and links is allowed, the source can be collected by the build into `news.json` (`"fetchedBy": "build"`), which needs no CORS header.
   - If storing is not allowed, the source can only be used if its feed sends a CORS header that allows the page, and is then fetched live in the browser (`"fetchedBy": "browser"`), as Sveriges Radio.
   - If neither is possible, the source cannot be added.
4. The owner approves. A worker adds one entry to `sources.json` and a test with a hand-written sample in the same shape.

### 2.5 Remove a site from the approved list (owner, through an issue)
1. A worker deletes the entry from `sources.json`, or sets `"enabled": false` (R3.4).
2. After the merge (and, in the published variant, the next build), the source is gone from the page; saved choices of its id are ignored (R3.5).

### 2.6 Something is wrong
- Sveriges Radio cannot be fetched (offline, API down): the SVT items are still shown, and "Källor" says "Sveriges Radio kunde inte hämtas just nu" (R7.6). Sveriges Radio items are never shown from an old copy, because there is none (N10).
- SVT failed in the last build: its items from the last successful build are kept for up to 24 hours, and "Källor" shows "Kunde inte hämtas sedan <time>" (R6.2).
- The page is opened without a network: it shows the last saved `news.json` (SVT only) with a notice (R8.2).
- `news.json` is old (the build stopped): the page warns (R8.3).

## 3. Requirements

Every requirement is numbered and testable. "Build" means the Python program that reads SVT and writes `news.json`. "Page" means the HTML page and its JavaScript. (auto py) is covered by pytest, (auto js) by Node's built-in test runner, (hand) by the owner by hand.

### R1. Item content
- R1.1 (auto py) Each item in `news.json` has exactly these fields: `id`, `sourceId`, `sourceName`, `title`, `url`, `published`, `publishedDisplay`. No summary, description, content or image field (N1).
- R1.2 (auto js) Each Sveriges Radio item held in memory has exactly the same fields as R1.1 and nothing else.
- R1.3 (auto py, auto js) `title` is plain text: HTML tags are removed, HTML and XML entities are decoded (for example `&amp;` becomes `&`), runs of white space become one space, and leading and trailing white space is removed. Nothing else in the headline is changed or cut; long headlines wrap on screen (R8.5). This keeps Sveriges Radio's headlines unmodified, as its terms require (section 4.3).
- R1.4 (auto py, auto js) An item with an empty `title`, or without a usable `url` (R9.1), is dropped.

### R2. Time
- R2.1 (auto py, auto js) `published` is UTC in ISO 8601 form with a `Z`, for example `2026-11-13T13:05:00Z`, or `null` when the feed gives no usable time.
- R2.2 (auto py) The build reads RSS `pubDate` (RFC 822 date, for example `Fri, 13 Nov 2026 14:05:00 +0100`). A time without a zone is read as Europe/Stockholm.
- R2.3 (auto js) The page reads Atom `published`, falling back to `updated` (ISO 8601 with offset).
- R2.4 (auto py, auto js) `publishedDisplay` is the time in the time zone Europe/Stockholm, 24-hour clock, in the form `YYYY-MM-DD HH:MM`, for example `2026-11-13 14:05`. Summer time follows the time zone rules (for example `2026-07-01T10:00:00Z` shows as `2026-07-01 12:00`). Python and JavaScript must give the same text for the same time; the shared test cases in `tests/shared-cases.json` check this (section 9).
- R2.5 (auto py, auto js) When `published` is `null`, `publishedDisplay` is `Tid saknas`.
- R2.6 (auto py, auto js) A time more than 10 minutes after "now" (build time, or page time) is treated as `null`.
- R2.7 (auto py) `news.json` has `generatedAt` (UTC) and `generatedAtDisplay` (form of R2.4).

### R3. Approved sources and the reader's choice
- R3.1 (auto py) The approved sources are listed in `sources.json` in the repository (shape in section 7.1). Each has `fetchedBy`: `build` or `browser`.
- R3.2 (auto py) A source with `fetchedBy: browser` must have `"storageAllowed": false` and must not appear in `news.json`; the build test fails if it does.
- R3.3 (hand) The reader's choice is a list of source ids in `localStorage` under `newsReader.selectedSources`. On the first visit all enabled sources are chosen. If storage is blocked, the page works with all sources chosen.
- R3.4 (auto py, hand) A source with `"enabled": false` is not fetched by the build and not fetched or shown by the page.
- R3.5 (hand) A saved id that is no longer in `sources.json` is ignored and removed when the reader next changes the choice. A newly added source is shown in "Källor" not ticked.

### R4. Category: politics in Sweden
- R4.1 (auto py) A source supplies the category `politics-sweden` with exactly one method in `sources.json`: `feed` (a dedicated politics feed), `categoryFilter` (exact `<category>` values) or `keywordFilter` (the shared keyword list). Both current sources use `keywordFilter`, because neither has a politics feed.
- R4.2 (auto py) The method is chosen in this order of preference: `feed`, else `categoryFilter`, else `keywordFilter`. A source without a method fails the configuration test.
- R4.3 (auto py, auto js) The keyword list is **one shared file**, `politics-keywords.json` (section 7.2), read by the Python build and fetched by the page. Neither has its own copy of the terms.
- R4.4 (auto py, auto js) An item matches when its headline or its description (RSS `description`, Atom `summary`), cleaned as in R1.3, contains at least one `include` term under the rules of section 7.2, after the `exclude` phrases and words have been taken out of consideration. Without a description, only the headline is used. The description is then discarded.
- R4.5 (auto py, auto js) Python and JavaScript give the same match result for every case in `tests/shared-cases.json`.
- R4.6 (hand) In "Källor", each `keywordFilter` source shows "Urval med nyckelord – ungefärligt".

### R5. Selection, duplicates and order
- R5.1 (auto py, auto js) At most 20 items per source: the 20 newest matching items by `published`; items with `null` time come last and only fill up to 20.
- R5.2 (auto py, auto js) Items older than 7 days before "now" are dropped.
- R5.3 (auto py, auto js) Duplicates within a source are removed by normalised URL: scheme and host in lower case, `www.` removed from the host, query string and fragment removed, trailing `/` removed. The first item in feed order is kept.
- R5.4 (auto py, auto js) `id` is the first 16 hexadecimal characters of the SHA-256 of the normalised URL (JavaScript uses `crypto.subtle.digest`).
- R5.5 (auto js) The page merges the chosen sources' items and sorts them by `published`, newest first; `null` last; equal times by `sourceId`, then by `title`.

### R6. The build (SVT and any other `fetchedBy: build` source)
- R6.1 (hand, owner) Published variant only: the build runs every 30 minutes on a schedule, and by hand from the Actions tab. Local variant: the owner runs it by hand (R12.1).
- R6.2 (auto py) Each source is fetched with a timeout of 15 seconds, one request per feed per build; redirects only within `allowedHosts`. On failure (network error, status other than 200, not RSS 2.0, zero items, redirect to another host) the build keeps the source's items from the previous `news.json` if they are less than 24 hours old, and records the status `error` and the time of the last success.
- R6.3 (auto py) `news.json` has a `sources` list with, for each build source: `id`, `name`, `status` (`ok`, `error` or `blocked-by-robots`), `lastSuccess`, `itemCount`.
- R6.4 (auto py) A failing source never fails the build. The build fails only if `sources.json` or `politics-keywords.json` is invalid.
- R6.5 (auto py) The build sends `User-Agent: GithubAutoPlay-news-reader/1.0` and no cookies.
- R6.6 (auto py) The build reads the host's `/robots.txt` once per run and does not fetch a path disallowed for its User-Agent (status `blocked-by-robots`). If robots.txt cannot be read, it does not fetch (status `error`).
- R6.7 (auto py) The build never fetches a `fetchedBy: browser` source.

### R7. Live fetch in the browser (Sveriges Radio and any other `fetchedBy: browser` source)
- R7.1 (hand) The page fetches the feed URL in `sources.json` directly from the source (for Sveriges Radio `https://api.sr.se/api/rss/program/83`), with `credentials: "omit"` and `cache: "no-store"`, and a timeout of 15 seconds.
- R7.2 (hand) Call load: one request when the page opens; then at most one request every 10 minutes, and only while the page is visible (paused when the tab is hidden). The "Uppdatera" button fetches again only if at least 5 minutes have passed since the last request to that source; otherwise it only reloads `news.json`. There are never two requests to the same source within 5 minutes from one open page.
- R7.3 (hand) The items are kept in memory only. They are never written to `localStorage`, `sessionStorage`, IndexedDB, cookies, the Cache API, a file or a server, and never logged to the browser console or included in error messages or error reports (an error message names the source and the kind of failure only). When the page is closed they are gone.
- R7.4 (auto js) The Atom entries are mapped as in R11.2, then filtered and selected with the same rules as the build (R1.3, R1.4, R2, R4.4, R5.1 to R5.4, R9.1).
- R7.5 (hand) Every Sveriges Radio item shows the source name "Sveriges Radio" visibly next to the headline, and the line at the bottom of the page (R8.7) names Sveriges Radio.
- R7.6 (hand) If the request fails or the feed cannot be read, the page shows the other sources' items and the status "Sveriges Radio kunde inte hämtas just nu" in "Källor"; it does not retry before the next scheduled fetch (R7.2).

### R8. Page behaviour
- R8.1 (hand) The page loads `news.json` when it opens, every 10 minutes while visible, and on "Uppdatera". A new load replaces the SVT part only when it succeeds.
- R8.2 (hand) After each successful load the page saves `news.json` (SVT only, never browser-source items) in `localStorage` under `newsReader.lastNews`. If loading fails, it shows the saved copy with "Offline – visar sparade SVT-nyheter från <generatedAtDisplay>". Without a saved copy: "Kunde inte hämta nyheter. Försök igen senare."
- R8.3 (hand) If `generatedAt` is more than 3 hours old by the reader's clock, the page shows "SVT-nyheterna kan vara gamla – senast uppdaterade <generatedAtDisplay>".
- R8.4 (hand) If none of the chosen sources has items, the page shows "Inga nyheter från valda källor."
- R8.5 (hand) The page works on a 360-pixel-wide phone screen without sideways scrolling; long headlines wrap (nothing is cut, R1.3).
- R8.6 (hand) The page loads no scripts, fonts or styles from other sites. Its only request to another site is the feed request of R7.1. It registers no service worker and does not use the Cache API.
- R8.7 (hand) Below the list: "Rubriker och länkar från SVT och Sveriges Radio. Klicka för att läsa hos källan." The source names in this line come from `sources.json`.
- R8.8 (hand) All text is in Swedish, with `<html lang="sv">` and `<meta charset="utf-8">`.
- R8.9 (hand) The page has no advertising, no marketing and no analytics (N11), and carries `<meta name="robots" content="noindex">` so that a published copy is not meant for search engines (K11).

### R9. Safety of links and text
- R9.1 (auto py, auto js) An item `url` is kept only if its scheme is `https` or `http` and its host is one of the source's `allowedHosts` or a subdomain of one. Other items are dropped.
- R9.2 (hand) The page writes all text with `textContent`, never `innerHTML`.
- R9.3 (hand) Each link has `target="_blank"` and `rel="noopener noreferrer"`.
- R9.4 (auto py) The build's XML parser does not resolve external entities, and the build refuses a response larger than 2 MB. (The browser's `DOMParser` does not load external entities.)

### R10. Encoding
- R10.1 (auto py) The build decodes each feed by its XML declaration (UTF-8 and ISO-8859-1) and writes `news.json` as UTF-8. Å, ä, ö and é come through unchanged.
- R10.2 (auto js) The keyword match and the headline cleaning handle å, ä, ö and é (shared cases).

### R11. Feed formats
| Item field | RSS 2.0 (SVT, read by the build) | Atom (Sveriges Radio, read by the page) |
|---|---|---|
| `title` | `<item><title>` | `<entry><title>` |
| `url` | `<item><link>` text | `<entry><link href="…">` with `rel="alternate"` or no `rel`; the first if several |
| `published` | `<pubDate>` | `<published>`, falling back to `<updated>` |
| used only for the keyword match, then discarded | `<description>` | `<summary>` |
| never read | `<guid>`, image elements, `<category>` (unless `categoryFilter`) | `<content>`, `<author>`, `<id>`, `<category>` (unless `categoryFilter`) |

- R11.1 (auto py) The build maps RSS 2.0 items as in the table. A document whose root is not `<rss>` is a failed fetch.
- R11.2 (auto js) The page maps Atom entries as in the table. `<content>` (which may hold article text) is never read. A document whose root is not Atom `<feed>` is a failed fetch. The mapping from an XML document to plain entries (using `DOMParser`) is tested by hand; everything after that is tested by (auto js).

### R12. Running and hosting (two variants; the owner chooses, Q1)
- R12.1 (hand) **Local variant:** from `applications/news-reader/`, the owner runs `python -m newsreader --out build` and `python -m http.server 8000 --directory build`. If `build/news.json` exists from an earlier run, the build reads it as the previous file before overwriting it, so the 24-hour fallback of R6.2 works locally too; `--previous <file>` names another file (used by the published variant), and opens `http://localhost:8000/`. Nothing is published. The build copies `site/*`, `sources.json` and `politics-keywords.json` into `build/`. The folder `build/` is listed in `.gitignore` so `news.json` is never committed.
- R12.2 (hand, owner) **Published variant:** a separate workflow publishes the same `build/` content to GitHub Pages under `<Pages address>/applications/news-reader/` (decision D16). It never commits and is not a required check.

## 4. Findings about the sources

### 4.1 How this was checked
Date of all checks: **2026-11-13**.
- **Worker's environment:** direct requests to the news hosts (svt.se, api.sr.se, sverigesradio.se and the earlier candidates) were refused by the environment's network proxy (HTTP 403 on connect). The worker used web search and the feed directories Feeder and Feedspot to find candidate addresses.
- **Manager, in the owner's browser:** every fact in this section marked "verified (manager)" was **checked by the manager in the owner's browser on 2026-11-13**: the SVT feeds and SVT's robots.txt, the Sveriges Radio feeds and API endpoints, Sveriges Radio's terms page and API documentation, and sverigesradio.se's robots.txt. The worker has not seen the raw responses itself. Everything not marked so is **not verified**.
- No page contained anything that looked like instructions to the worker.

### 4.2 SVT (svt.se), fetched by the build

| URL | Result | Checked by |
|---|---|---|
| `https://www.svt.se/nyheter/inrikes/rss.xml` | **Domestic news feed. HTTP 200, RSS, 100 items. Fields per item: `title`, `link`, `description`, `pubDate`, `guid`. No CORS header.** | Verified (manager) |
| `https://www.svt.se/nyheter/rss.xml` | All news, HTTP 200, 100 items. | Verified (manager). Not used. |
| `https://www.svt.se/nyheter/politik/rss.xml` | 404, no politics feed | Verified (manager) |

- No CORS header, so a page on another site cannot read the feed; SVT must be fetched by the build.
- Method: `keywordFilter` on the domestic feed. Because the feed is already limited to domestic news, keyword hits are mostly Swedish politics. Still approximate (K6).
- **robots.txt** (verified (manager)): `User-agent: *` with `Allow: /`, and the content signal `ai-train=no, search=yes, ai-input=yes`: training AI models on the content is not permitted (K7).
- **SVT's terms of use beyond robots.txt have not been read** (K12, step S1).
- **Not verified:** the host of the item links (`www.svt.se` expected; Q2), whether items carry `<category>` or images.

### 4.3 Sveriges Radio (sverigesradio.se), fetched live in the browser

| URL | Result | Checked by |
|---|---|---|
| `https://api.sr.se/api/rss/program/83` | **Ekot text news, Atom (`application/atom+xml`), 20 entries. Fields: `id`, `title`, `summary`, `published`, `updated`, `author`, `link`, `category`, `content`. `published` and `updated` in ISO 8601 with offset (for example `+01:00`). Links to text articles on `https://www.sverigesradio.se/artikel/<number>`. `Access-Control-Allow-Origin: *`.** | Verified (manager) |
| `https://api.sr.se/api/rss/group/27511` | "Toppnyheter", Atom, stale (newest entries 2026-11-12 and older), local-news style. | Verified (manager). **Not used.** |
| `https://api.sr.se/api/v2/news`, `.../news/episodes`, `.../episodes/index?programid=5380` | JSON API with **audio episodes**. | Verified (manager). **Rejected:** audio, not articles; a separate parser; time field not verified. |

- The feed mixes all Ekot news (world, culture, sport), so it needs the keyword filter; `category` values were not reported (Q3).
- `Access-Control-Allow-Origin: *` means the page can read the feed directly in the browser, which is what makes the live fetch possible.
- The item link host is verified: `allowedHosts` is `sverigesradio.se`.

**Sveriges Radio's terms** (verified (manager): read on 2026-11-13 at `https://sverigesradio.se/artikel/api-villkor`, updated 2025-08-29; API documentation `https://api.sr.se/api/documentation/v2/index.html`). In summary, as reported:
- The open API is no longer maintained but can still be used; no registration; no call limits, but "be kind, few calls".
- The material may only be used through linking and/or streaming, for reception in Sweden.
- It may not be stored, downloaded, copied or preserved, other than temporary copies made by the service that uses the API.
- It may not be modified.
- It must be clear that the material comes from Sveriges Radio.
- No use for marketing without approval; no advertising tied directly to the material.
- No use for machine learning without approval.
- Sveriges Radio may ask for anonymised usage data.
- The use must not harm Sveriges Radio's independence or credibility.
- The terms may change.

**sverigesradio.se robots.txt** (verified (manager)): allows search indexing, disallows AI-training crawlers and some AI user agents. It governs the website, not the api.sr.se API. The page does not crawl the website; the reader's own browser opens an article only when the reader clicks.

How the design follows these terms (this is a design response, not legal advice):

| Term | Design response |
|---|---|
| Only linking and/or streaming | Each item is a headline that links to the article on sverigesradio.se. No article text is shown (N1). |
| Not stored, downloaded, copied or preserved, other than temporary copies | Fetched live in the reader's browser, kept in memory only, `cache: "no-store"`, never written to any storage or file, never in the repository, `news.json` or Pages (N10, R7.3). Tests use hand-written made-up samples only (section 9). |
| Not modified | Headlines are shown as given, only decoded and with white space tidied; never cut (R1.3). |
| Clear that it comes from Sveriges Radio | Source name on every item and in the bottom line (R7.5, R8.7). |
| No marketing, no ads tied to the material | No ads, no marketing on the page (R8.9). |
| No machine learning | Nothing is trained (N9). |
| Be kind, few calls | One call per page load and at most one per 5 minutes, paused when hidden (R7.2). |
| Reception in Sweden | The reader is in Sweden. A published page could be opened from abroad (K13). |
| Anonymised usage data on request | The page collects no data; the owner could only report how the page works (K9). |
| Terms may change; API unmaintained | Risks K9 and K10; Sveriges Radio can be switched off with `"enabled": false`. |

### 4.4 Can a browser read the feeds directly?
- SVT: no (verified, no CORS header), so the build reads it.
- Sveriges Radio: yes (verified, `Access-Control-Allow-Origin: *`), so the page reads it.

### 4.5 Not verified
1. SVT's terms of use beyond robots.txt (step S1).
2. The host of SVT's item links, and whether SVT items carry categories or images (Q2).
3. The `category` values of the Sveriges Radio feed (Q3).
4. That GitHub's Action runners may fetch svt.se (published variant only; very likely, not tested).
5. How well the keyword list selects politics (measured in step S8 for SVT and on the live page).

## 5. Options considered and the recommendation

| Option | How | SVT | Sveriges Radio | Verdict |
|---|---|---|---|---|
| A. Browser only | The page fetches every feed itself. | **Breaks**: no CORS header. | Works. | Rejected: SVT cannot be read. |
| B. Browser plus a public CORS proxy | Requests go through a public relay. | Works, through a third party. | Works. | Rejected: unknown third party, unreliable, hides who fetches (N5), and the relay would make copies of Sveriges Radio material. |
| C. Own proxy or serverless function | Our own function fetches on request. | Works. | Works. | Not now: needs hosting and credentials outside GitHub. It is what visitor-defined sources would need later (N8). |
| D. Build only | A scheduled build writes all sources into `news.json`. | Works. | **Breaks the terms**: Sveriges Radio headlines would be stored in `news.json` and on Pages. | Rejected after reading the terms (D18). Was the recommendation before. |
| E. Run locally only | The owner runs the build and a local server. | Works. | Works (the page fetches it live). | Kept as a **hosting variant** of F (R12.1), not a separate design. |
| **F. Hybrid (recommended)** | The build collects SVT into `news.json`; the page fetches Sveriges Radio live and keeps it in memory; one shared keyword list. | Works (build). | Works and stores nothing. | **Recommended.** |

Why F:
- It is the only option that reads both sources and follows Sveriges Radio's no-storage term.
- It needs no third party and no credentials.
- The build logic is Python, tested by `pytest` in the existing check. The browser logic is a small pure JavaScript module tested by Node's built-in test runner, and the shared keyword list and shared test cases keep the two in step.

What F costs:
- Two implementations of the same rules (Python and JavaScript). Mitigation: one shared keyword file and one shared file of test cases that both test suites must pass (R4.5, K14).
- The JavaScript tests need Node in the required check, which only the owner can add (S3). Node is installed in this worker's environment (v22); it is normally preinstalled on GitHub's `ubuntu-latest` runners, but that has not been tested in this repository.
- Sveriges Radio items depend on the reader's network at the time of reading; there is no offline copy (by design).

**Hosting (Q1), the owner decides:**
- Local only (R12.1): nothing is public; no workflow file and no Pages setting are needed; the owner runs the build when reading. Recommended to start with, because the owner only reads (D20), SVT's terms are not read yet (K12), and publishing makes the list public (K11).
- Published on Pages (R12.2): the page updates itself every 30 minutes and works on a phone, but the headline list is public, and `news.json` is a public derived copy of SVT headlines and links.

## 6. Architecture of the recommendation

```
applications/news-reader/
  README.md                 description, how to run locally, how to test
  news-reader-design.md     this document
  requirements.txt          pytest (the build uses only the Python standard library)
  pytest.ini
  .gitignore                build/
  sources.json              the approved sources (section 7.1)            shared
  politics-keywords.json    the keyword list (section 7.2)                 shared
  newsreader/               Python build (SVT)
    model.py                NewsItem, SourceStatus; no I/O
    parse.py                RSS 2.0 bytes -> raw entries (R11.1); no network
    timeutil.py             dates, UTC, Europe/Stockholm display (R2)
    keywords.py             load politics-keywords.json, match (R4.4)
    select.py               cleaning, URL check, de-duplicate, age, cap, id (R1, R5, R9.1)
    robots.py               robots.txt decision (R6.6); text in, no network
    fetch.py                the only network module (timeout, size limit, User-Agent)
    build.py                orchestration; fetch and "now" injected; writes build/
    __main__.py             python -m newsreader --out build [--previous <file>]
                            (default previous: <out>/news.json if it exists)
  site/                     the page (copied into build/ by the build)
    index.html              skeleton, Swedish text
    logic.js                pure ES module, no DOM, no network: keyword match,
                            cleaning, URL check, time display, select, merge, sort
    atom.js                 DOMParser: Atom text -> plain entries (R11.2)
    app.js                  fetching, timers, storage of choices, rendering
    style.css
    tests/logic.test.mjs    node --test; reads ../../tests/shared-cases.json
  tests/
    fixtures/               hand-written samples (section 9)
    shared-cases.json       cases for keyword match, cleaning and time display,
                            used by both pytest and node --test
    test_*.py
```

### Data flow
1. **Build (Python):** `sources.json` → for each `fetchedBy: build` source: robots.txt check → fetch → parse RSS → clean → keyword filter (`politics-keywords.json`) → URL check → de-duplicate → age limit → cap → `news.json`, plus a copy of `site/`, `sources.json` and `politics-keywords.json`, all into `build/`.
2. **Page (browser):** loads `sources.json`, `politics-keywords.json` and `news.json` from its own folder → for each `fetchedBy: browser` source: fetch the feed live → `atom.js` → `logic.js` (clean, keyword filter, URL check, de-duplicate, age limit, cap) → memory → `logic.js` merges with the SVT items and sorts → `app.js` renders.

### Pure logic and the thin layers
- Tested without browser or network: all Python modules except `fetch.py`, and `site/logic.js`.
- Thin layers, tested by hand: `fetch.py` (network), `site/atom.js` (`DOMParser`), `site/app.js` (DOM, timers, `fetch`, `localStorage`).

### Published variant only (owner-added workflow, step S12)
A workflow `.github/workflows/news-reader.yml`, separate from `ci.yml`: a schedule every 30 minutes and `workflow_dispatch`; permissions `contents: read`, `pages: write`, `id-token: write`; it downloads the published `news.json` as `--previous`, runs the build into `_site/applications/news-reader/`, and deploys with the official upload-Pages-artifact and deploy-Pages actions. It never commits. A copy goes into `GitRequirements/` in the same change.

## 7. Data and state

### 7.1 The approved sources: `sources.json`
```json
{
  "version": 1,
  "sources": [
    {
      "id": "svt",
      "name": "SVT",
      "enabled": true,
      "fetchedBy": "build",
      "storageAllowed": true,
      "homepage": "https://www.svt.se/",
      "allowedHosts": ["svt.se"],
      "politics-sweden": { "method": "keywordFilter", "url": "https://www.svt.se/nyheter/inrikes/rss.xml" }
    },
    {
      "id": "sveriges-radio",
      "name": "Sveriges Radio",
      "enabled": true,
      "fetchedBy": "browser",
      "storageAllowed": false,
      "homepage": "https://www.sverigesradio.se/",
      "allowedHosts": ["sverigesradio.se"],
      "politics-sweden": { "method": "keywordFilter", "url": "https://api.sr.se/api/rss/program/83" }
    }
  ]
}
```
- `storageAllowed: true` for SVT is a working assumption until step S1 has read SVT's terms (K12).
- `allowedHosts` for SVT is expected and must be confirmed (Q2).
- Changes only through issues approved by the owner (D10).

### 7.2 The shared keyword list: `politics-keywords.json`
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
    "words": ["moderat", "moderata"],
    "phrases": ["amerikanska regeringen", "brittiska regeringen", "danska regeringen",
                "finska regeringen", "franska regeringen", "israeliska regeringen",
                "kinesiska regeringen", "norska regeringen", "ryska regeringen",
                "tyska regeringen", "ukrainska regeringen"]
  }
}
```
Matching rules, defined so that Python and JavaScript give the same result:
- The text is Unicode NFC-normalised and split into words: maximal runs of Unicode letters (category L) and decimal digits (category Nd). Python checks `unicodedata.category`; JavaScript uses the regular expression `[\p{L}\p{Nd}]+` with the `u` flag.
- `words` terms are compared in lower case: both the term and each word of the text are lowercased (Python `str.lower`, JavaScript `toLowerCase`) after NFC normalisation. A term matches a whole word; a term ending in `*` matches any word that starts with the term without the `*`.
- `caseSensitive` terms match as exact substrings, brackets included.
- `exclude.phrases` are removed from the text before the include terms are tested (compared in lower case, as whole words in sequence). So "Tyska regeringen kritiserar riksdagen" still matches through "riksdagen", while "Tyska regeringen sänker skatten" does not match.
- `exclude.words` are words that never count as a hit, even when an include term would match them. They handle the adjective "moderat" (moderate), which `Moderat*` would otherwise match; "Moderaterna" and "moderatledaren" still match. The consequence is that the rare official name "Moderata samlingspartiet" is not matched.
- Exclusion never drops a whole item; it only removes words and phrases from consideration. The exclude lists are maintained through issues when false positives are found.
- "minister", "val" and "parti" are left out on purpose: too broad.

### 7.3 The reader's state in the browser
- `localStorage["newsReader.selectedSources"]`: list of source ids, for example `["svt", "sveriges-radio"]`. No content.
- `localStorage["newsReader.lastNews"]`: the last `news.json` (SVT only).
- Sveriges Radio items: in a JavaScript variable only (R7.3).

### 7.4 `news.json` (SVT only)
```json
{
  "version": 1,
  "generatedAt": "2026-11-13T13:05:12Z",
  "generatedAtDisplay": "2026-11-13 14:05",
  "category": "politics-sweden",
  "sources": [
    { "id": "svt", "name": "SVT", "status": "ok", "lastSuccess": "2026-11-13T13:05:12Z", "itemCount": 11 }
  ],
  "items": [
    {
      "id": "3f2a9c0d1b7e4a55",
      "sourceId": "svt",
      "sourceName": "SVT",
      "title": "Exempelrubrik om riksdagen",
      "url": "https://www.svt.se/nyheter/inrikes/exempel",
      "published": "2026-11-13T12:58:00Z",
      "publishedDisplay": "2026-11-13 13:58"
    }
  ]
}
```
The headline, URL and count are made up for illustration. A Sveriges Radio item in memory has the same seven fields.

## 8. Edge cases and failure modes

| Case | What happens | Requirement |
|---|---|---|
| SVT is down, times out or answers with an error | Previous SVT items (under 24 h) kept; status `error` | R6.2, R6.3 |
| SVT feed changes format | Failed fetch; previous items kept | R6.2, R11.1 |
| robots.txt disallows the SVT feed, or cannot be read | Not fetched; `blocked-by-robots` or `error` | R6.6 |
| Sveriges Radio API down (it is unmaintained) or the reader is offline | SVT items shown; "Sveriges Radio kunde inte hämtas just nu"; no old copy | R7.6, N10 |
| Sveriges Radio feed changes format or drops the CORS header | Same as above; the owner disables the source if it lasts | R7.6, R3.4, K10 |
| Reader presses "Uppdatera" repeatedly | Sveriges Radio fetched at most once per 5 minutes | R7.2 |
| Page left open in a hidden tab | No Sveriges Radio requests until visible again | R7.2 |
| A source asks not to be shown, or its terms change | Owner sets `"enabled": false` | R3.4, K9 |
| Politics item without any listed term | Not shown (false negative) | R4.4, K6 |
| Sveriges Radio item about another country's government | Shown (false positive) until an exclude term is added | R4.4, K6 |
| Item without description or summary | Headline only is matched | R4.4 |
| Atom entry with `updated` but no `published` | `updated` used | R2.3 |
| Atom entry with several links | `alternate` (or no `rel`) link used | R11.2 |
| Item without time | Kept, "Tid saknas", sorted last | R2.5, R5.1, R5.5 |
| Time in the future | More than 10 minutes ahead treated as no time | R2.6 |
| Summer/winter time | Europe/Stockholm rules, same in Python and JavaScript | R2.4 |
| Very long headline | Not cut; wraps | R1.3, R8.5 |
| HTML or entities in a headline | Tags removed, entities decoded, written as text | R1.3, R9.2 |
| Swedish letters | Same handling in Python and JavaScript | R10.1, R10.2 |
| A link to another host, `javascript:` or `data:` | Item dropped | R9.1 |
| A huge or hostile RSS feed | Over 2 MB refused; no external entities | R9.4 |
| Same article twice in one feed | Removed by normalised URL | R5.3 |
| Same story in SVT and Sveriges Radio | Both shown | N6 |
| Local storage blocked | All sources chosen; page works | R3.3 |
| Published variant: scheduled build stops or is disabled after 60 days without activity | SVT part goes stale; warning after 3 hours | R8.3, K3 |
| Reader unticks every source | "Inga nyheter från valda källor." | R8.4 |

## 9. Testing strategy

### Python (pytest, no network)
Hand-written, made-up samples in `tests/fixtures/` (not copies of SVT or Sveriges Radio content):
1. `rss_svt_shape.xml`: RSS 2.0 in SVT's shape (`title`, `link`, `description`, `pubDate`, `guid`), 25 items, `+0100` and `+0200` dates, items that should and should not match the keywords, one with an image element (must be dropped).
2. `rss_iso8859.xml`: ISO-8859-1 with å, ä, ö, é.
3. `rss_edge_cases.xml`: empty title, HTML and entities in a title, a 300-character title (must not be cut), no `pubDate`, a future date, a date older than 7 days, a `javascript:` link, a foreign host, two URLs differing only in query string.
4. `not_a_feed.html`, `broken.xml`, `atom_in_build.xml` (Atom given to the build: failed fetch).
5. `robots_allow.txt`, `robots_disallow_rss.txt`.
6. `previous_news.json`.
7. `sources.json` checks: every source has one method; a `browser` source has `storageAllowed: false`; the build never fetches it and never writes it into `news.json` (R3.2, R6.7).

### JavaScript (node --test, no network, no browser)
`site/tests/logic.test.mjs` tests `site/logic.js` with plain objects as input (the output of `atom.js`), and with a hand-written list of entries in the Sveriges Radio shape (`title`, `summary`, `published`, `updated`, `link`, plus `content` that must be ignored). It covers R1.2 to R1.4, R2.3 to R2.6, R4.4, R5.1 to R5.5, R9.1 and R10.2.

### Shared cases
`tests/shared-cases.json` holds input and expected output in three sections created empty in S2: headline cleaning (filled in S4), time display including summer and winter time (filled in S5), and keyword matching including the exclude words and phrases and Swedish letters (filled in S6). The Python tests of each step read it from the start, and `node --test` reads all of it in S9, so the two implementations cannot drift apart without a failing test (R4.5).

### Running the tests
- Locally: `bash scripts/check.sh applications/news-reader` for Python, and `node --test applications/news-reader/site/tests/` for JavaScript.
- In the required check `checks`: the owner adds three steps to `ci.yml` (install requirements, `python -m pytest` in `applications/news-reader`, `node --test applications/news-reader/site/tests/`) and updates the copy in `GitRequirements/` (S3).

### By hand (owner)
- Local variant (after S10 and S11): run the build and the local server, then check list order; the link opens in a new tab; choosing and unchoosing sources; reload keeps the choice; private window; offline (SVT from the saved copy, Sveriges Radio not shown, the right notices); stale warning (edit `generatedAt`); 360 px width; Swedish letters; the source name on every Sveriges Radio item; the bottom line.
- Storage check: in the browser's developer tools, Application tab, no Sveriges Radio headline appears in local storage, session storage, IndexedDB, cookies or Cache Storage, and no service worker is registered. The Console shows no Sveriges Radio headline, also after a forced failure (for example offline, or a blocked `api.sr.se` request in the Network tab).
- Call check: in the Network tab, one request to `api.sr.se` on page load; "Uppdatera" within 5 minutes makes no new request; a hidden tab makes no requests.
- Keyword quality: read the live list for obvious false positives and missing politics news. For Sveriges Radio this is done only by reading the live page; no copy is saved (N10).
- Published variant (S13): the Pages address shows both sources; a manual run updates the SVT time; two scheduled runs in an hour.

## 10. Risks and open questions

### 10.1 Risks

| # | Risk | Handling |
|---|---|---|
| K1 | svt.se may block or rate-limit GitHub runners (published variant). | Seen as `error`; then fewer runs or local only. |
| K2 | A feed changes address or format. | Status in "Källor" and the stale warning; fix by issue. |
| K3 | Published variant: scheduled workflows in public repositories are disabled after 60 days without activity. | Stale warning; owner re-enables. |
| K4 | Scheduled runs can be delayed. | Accepted; the warning uses 3 hours. |
| K6 | The keyword filter is approximate: false positives (another country's government in Sveriges Radio's mixed feed; a passing mention in SVT) and false negatives (a headline naming only a person). | Note on the page (R4.6); exclude terms; list maintained through issues. |
| K7 | SVT's robots.txt says `ai-train=no`. | Nothing is trained (N9); test samples are hand-written. |
| K8 | Sveriges Radio's terms. **Resolved for the design**: read by the manager (section 4.3); the design answers each term (no storage, live fetch, no modification, source named, few calls, no ads, no training). | Keep the table in section 4.3 up to date when the terms change (K9). |
| K9 | Sveriges Radio's terms may change. | The owner re-reads `https://sverigesradio.se/artikel/api-villkor` before any change to the page and at least when the page is published; `enabled: false` if needed. |
| K10 | Sveriges Radio's open API is no longer maintained and may stop or change. | The page keeps working with SVT (R7.6); the source is disabled if it stays broken. |
| K11 | **Public visibility.** The owner only reads, but in the published variant the page and `news.json` are on public GitHub Pages of a public repository, so the headline list is publicly visible to anyone with the address, whatever the intent. `noindex` (R8.9) asks search engines not to list it, but does not hide it. | **Owner decision (Q1):** do not publish and run locally only (recommended), or publish and accept that it is public. |
| K12 | **SVT derived copy.** `news.json` stores SVT headlines and links: a derived copy, on the owner's computer in the local variant and publicly on Pages in the published variant. SVT's terms beyond robots.txt have not been read. | Step S1 reads SVT's terms before anything is published; if storing is not allowed, SVT cannot be used (it has no CORS header for a live fetch, section 2.4). |
| K13 | Sveriges Radio's terms speak of reception in Sweden. A published page can be opened from abroad. | Not an issue in the local variant; part of Q1. |
| K14 | The Python and JavaScript rules could drift apart. | Shared keyword file and shared test cases (R4.3, R4.5). |

K5 (DN's terms) was removed when DN was dropped (D12); the other numbers are kept so that earlier references stay valid.

### 10.2 Remaining open questions

| # | Question | Proposed way to settle it |
|---|---|---|
| Q1 | Publish on GitHub Pages, or run locally only? (K11, K12, K13) | Owner decides. Recommendation: local only to start with; publish only after S1 and only if the owner accepts a public page. |
| Q2 | Which host do SVT's item links use, and do SVT items carry categories? | Manager or owner looks at the feed in S1. |
| Q3 | Which `category` values do Sveriges Radio's entries carry, and could they replace the keyword filter? | Manager or owner looks at the feed (S14). |
| Q4 | GitHub settings (Pages source, Actions permissions, `github-pages` environment). | Owner checks them in S12 (published variant only), as the owner has said. |

### 10.3 What was checked about hosting in the repository
Checked by the worker on 2026-11-13 on a branch from `origin/main` (commit `4afc4a7`): `.github/workflows/` has only `auto-merge.yml` and `ci.yml`; no `gh-pages` branch on `origin`; no `CNAME`, `.nojekyll` or `_config.yml`; no mention of Pages in `README.md`, `WORKFLOW.md` or `GitRequirements/README.md`; `GitRequirements/` keeps copies of the workflows that must stay identical; `ci.yml` does not run news-reader tests. The GitHub API and the Pages address could not be reached from the worker's environment, so whether Pages is on is not verified; the owner checks the settings (Q4).

## 11. Decisions

| # | Decision | Made by |
|---|---|---|
| D1 | The deliverable of the design task is a design document only. | Owner |
| D2 | Items show headline, source, time and link only. | Owner |
| D3 | Architecture: hybrid (option F): SVT through the Python build into `news.json`, Sveriges Radio live in the browser. | Worker, after D18 |
| D4 | Build logic in Python (standard library); browser logic in one small pure JavaScript module; both tested without network. | Worker, recommended |
| D5 | Category from a politics feed if one exists, else from `<category>` values, else from the shared keyword list. | Worker, recommended |
| D6 | No scraping and no getting around robots.txt, terms or other restrictions. | Owner and worker |
| D7 | Time shown as `YYYY-MM-DD HH:MM` in Europe/Stockholm. | Worker, recommended |
| D8 | 20 items per source, 7 days, headlines never cut; build every 30 minutes (published variant); page refresh every 10 minutes while visible; Sveriges Radio at most once per 5 minutes; stale warning after 3 hours. | Worker, recommended |
| D9 | A publishing workflow, if any, never commits to `main`. | Worker, recommended |
| D10 | Design principle: a few approved sites, listed in `sources.json` in the repository and approved by the owner; visitors cannot add sources. | Owner |
| D11 | Omni was removed from the design. | Owner |
| D12 | DN was dropped. | Owner |
| D13 | Regeringen.se and Riksdagen are out of scope for now. | Owner |
| D14 | The repository is public. | Owner |
| D15 | The page text and the news are in Swedish. | Owner |
| D16 | Everything lives in `applications/news-reader/`; a published page uses the same path. | Owner |
| D17 | Sveriges Radio is a source through the Ekot Atom feed `https://api.sr.se/api/rss/program/83`, named "Sveriges Radio"; the episode API and the stale "Toppnyheter" feed are not used. | Owner (via manager) |
| D18 | Sveriges Radio material is never stored: fetched live in the browser, kept in memory only. | Owner (via manager), from Sveriges Radio's terms |
| D19 | The owner checks GitHub's Pages and Actions settings before the Pages step. | Owner |
| D20 | The owner's use is reading only, not sharing. | Owner |

## 12. Step plan

Each step is meant to become one issue. Levels are from WORKFLOW.md section 1. "Owner only" and "Manager or owner" steps cannot be done by a worker (GitHub settings, workflow files, or a browser that can reach the news sites).

| Step | Title | Level | `no-auto-merge` | Depends on | Covers |
|---|---|---|---|---|---|
| S1 | **Manager or owner:** read SVT's terms of use; note the host of SVT's item links and whether items carry categories | Low | no (no pull request) | none | K12, Q2 |
| S2 | News reader: project folder, README (local run), `requirements.txt`, `pytest.ini`, `.gitignore` with `build/`, `sources.json` with SVT and Sveriges Radio, `tests/shared-cases.json` with empty sections `cleaning`, `time` and `keywords`, a placeholder `site/logic.js` with one Node smoke test, entry in `applications/README.md`, and a test that validates `sources.json` | Low | no | S1 | R3.1, R3.2 (configuration part), R4.1, R4.2, R12.1 (`.gitignore`) |
| S3 | **Owner only:** add the news-reader steps (pytest and `node --test`) to the `checks` job in `ci.yml`, and update `GitRequirements/ci.yml` | Low | no | S2 | Section 9 (tests in the required check) |
| S4 | News reader: RSS 2.0 parser for the build (raw entries: title, link, time text, description), headline cleaning with its cases in the `cleaning` section of `tests/shared-cases.json`, encoding, with hand-written samples | Medium | no | S2 | R1.3 (Python), R9.4, R10.1, R11.1 |
| S5 | News reader: time handling in Python, with its cases in the `time` section of `tests/shared-cases.json` | Low | no | S2 | R2.1, R2.2, R2.4 (Python), R2.5, R2.6, R2.7 |
| S6 | News reader: the shared keyword list `politics-keywords.json` (include terms, exclude words and exclude phrases), its cases in the `keywords` section of `tests/shared-cases.json`, and keyword matching in Python | Medium | no | S4, S5 | R4.3, R4.4 (Python), R4.5 (Python side) |
| S7 | News reader: selection in Python (URL check, empty-title and URL drop, de-duplicate, age, cap, `id`), producing items with exactly the R1.1 fields | Medium | no | S6 | R1.1 (item shape), R1.4 (Python), R5.1 to R5.4 (Python), R9.1 (Python) |
| S8 | News reader: build command (fetch layer, robots.txt rule, `enabled`, skip browser sources, previous file with the local default, writes `build/` with `news.json`, `site/`, `sources.json`, `politics-keywords.json`), and a check of the keyword list against the SVT feed done by the owner or manager on the local build output | Medium | no | S7 | R1.1 (`news.json`), R3.2 (`news.json` part), R3.4 (build), R6.2 to R6.7, R12.1 (build part), K6 (SVT) |
| S9 | News reader: `site/logic.js` (cleaning, keyword match with excludes, URL check, time display, select, `id`, merge, sort) with `node --test`, passing all shared cases | Medium | no | S6 | R1.2, R1.3 (JS), R1.4 (JS), R2.1 (JS), R2.3, R2.4 (JS), R2.5 (JS), R2.6 (JS), R4.4 (JS), R4.5 (JS side), R5.1 to R5.5 (JS), R9.1 (JS), R10.2 |
| S10 | News reader: the page, part 1, SVT and choices (`index.html`, `app.js`, `style.css`): `news.json`, merged list, "Källor" with choices, offline copy, stale and empty notices, bottom line, Swedish text, safe links, `noindex`, no service worker and no Cache API | Medium | **yes** (user-visible; owner tests by hand per section 9, local variant) | S8, S9 | R3.3, R3.4 (page), R3.5, R4.6, R8.1 to R8.9, R9.2, R9.3 |
| S11 | News reader: the page, part 2, Sveriges Radio live fetch (`atom.js`, additions to `app.js`): fetch with `credentials: "omit"` and `cache: "no-store"`, the shared keyword list in the browser, memory only, no logging of content, call limits and pause when hidden, source name, failure status | Medium | **yes** (user-visible; owner does the storage, console and call checks of section 9) | S10 | R4.3 (page), R7.1 to R7.6, R11.2 |
| S12 | **Owner only, published variant only (Q1):** check GitHub Settings > Pages and > Actions (Q4), set the Pages source to "GitHub Actions", and add `.github/workflows/news-reader.yml` with its copy in `GitRequirements/`; the worker of S8 provides a draft in the README if the owner asks | Low | yes if done as a pull request | S1, S11 | R6.1, R12.2, Q4 |
| S13 | **Owner only, published variant only:** test the live page and two scheduled runs | Low | n/a | S12 | Section 9 (published variant) |
| S14 | **Manager or owner, optional:** list the `category` values of the Sveriges Radio feed; if they mark Swedish politics, open an issue to switch to `categoryFilter` | Low | no (no pull request) | none | Q3 |

Notes:
- In the local variant the plan ends with S11 and the owner's hand tests; S12 and S13 are done only if the owner decides to publish (Q1).
- S2 depends on S1 because `storageAllowed` and `allowedHosts` for SVT come from S1.
- S2 creates `tests/shared-cases.json` with empty sections, so S4 and S5 can fill their sections in parallel; S6 fills the keyword section; S9 runs all of it in JavaScript.
- S8 and S9 can be done in parallel after S6 (S8 also needs S7).
- The `id` (R5.4) and the final item shape (R1.1) belong to S7; S4 only produces raw entries.
- S3 should follow S2 directly. Until it is done, each worker runs the Python and Node tests locally and says so in the report.
- Every requirement in section 3 is listed in the "Covers" column of at least one step.
