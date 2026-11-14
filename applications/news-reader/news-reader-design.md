# News reader: design

Status: design, version 7, updated 2026-11-14 by the Designer/Developer worker for issue #88 (step F2). Version 6 (2026-11-13) described politics headlines from SVT and Sveriges Radio; steps S2 to S11 of it are merged. Version 7 adds topics, several feeds per source and Riksdagen's open data as a build source (requirements R13 to R19, decisions D21 to D36, risks K15 to K20, questions Q5 to Q11, steps F1 to F8) and drops publishing on GitHub Pages (D26). In section 11, "Owner, 2026-11-14" marks a decision by the owner; "Manager proposal, 2026-11-14" marks a proposal that the owner has not confirmed yet. Until the steps F3 to F8 are merged, the code still does what version 6 says; each new requirement names its step in section 12.

The news reader is a web page that lists headlines from **a few approved sites**, grouped by **topic**: Alla nyheter, Politik, Natur and AI (D21). Until step F7 is merged the page shows politics headlines only. Each item shows the headline, the source name, the publication time and a link to the original article. The page text and the news are in Swedish.

**Design principle: a few approved sites.** The sources are an owner-approved list kept in the repository (`sources.json`). A site is added only after its feed and its terms have been checked and the owner has approved it. Visitors cannot add sources. Today the list has two sites: **SVT** and **Sveriges Radio**; Riksdagen's open data is the third (D24, step F6).

**Architecture in one paragraph (hybrid).** SVT's feed cannot be read from a browser (no CORS header), so a Python build collects SVT's politics headlines into a file `news.json`. Sveriges Radio's terms forbid storing its material, so Sveriges Radio headlines are never written to any file: the page fetches them live from Sveriges Radio's open feed in the visitor's browser, keeps them in memory only, and shows them next to the SVT items. One shared keyword list selects politics items for both. From version 7 each source has a list of feeds, one for each topic it offers; a feed address that serves several topics is fetched once (R15), and one keyword list per topic selects the items. The page is run locally only; publishing was dropped (D26).

How the facts in section 4 were established: the worker's own environment cannot reach the news sites (all were refused by its network proxy). The feed checks and the reading of terms were done by the manager in the owner's browser on 2026-11-13 and handed to the worker. Section 4 says for each fact who checked it and what is still not verified.

## 1. Goal and non-goals

### Goal
- G1. One web page that shows the newest headlines about politics in Sweden from the approved sources the reader has chosen, merged into one list, newest first. Extended by G7 (topics).
- G2. Each item shows only: headline, source name, publication time, link to the original.
- G3. The sources are a few approved sites in `sources.json`, changed only through issues that the owner approves (decision D10).
- G4. The page can run locally on the owner's computer, and can be published with what the repository already has (GitHub Pages and GitHub Actions in a public repository) if the owner decides so (Q1). **Superseded by D26 (2026-11-14): the page runs locally only; publishing is dropped.**
- G5. The logic (reading feeds, choosing the category, removing duplicates, sorting, formatting time) can be tested automatically without a browser and without a network.
- G6. Each source is used in a way that follows what its terms and robots.txt say, as far as they have been read.
- G7. The reader can choose one topic (Alla nyheter, Politik, Natur or AI) and sees the items of the chosen sources that belong to it (D21, D22; R18).

### Non-goals
- N1. No article text, no summary or lead paragraph (ingress), no images, even when the feed carries them. A feed's description or summary may be read to decide the category (R4.4) but is never stored or shown.
- N2. No categories other than politics in Sweden in the first version. **Superseded by D21 and R13: the topics are Alla nyheter, Politik, Natur and AI.**
- N3. No scraping of HTML pages. Only feeds that the sources offer are read.
- N4. No user accounts, no login, no server-side storage of the reader's choices.
- N5. No getting around paywalls, robots.txt rules, terms or any other restriction.
- N6. No matching of the same story across different sources by headline similarity.
- N7. No notifications, no search, no read/unread marking.
- N8. Visitors cannot add sources (decision D10). Visitor-defined sources would need an own proxy because of CORS (section 5, option C); a possible later step.
- N9. No use of any source's content for training AI models.
- N10. **No Sveriges Radio material is stored anywhere**: not in the repository, not in `news.json`, not on GitHub Pages, not in the browser's storage (decision D18).
- N11. No advertising, no marketing, no analytics on the page.
- N12. Official sources such as Regeringen.se (government press releases) and Riksdagen's open data are out of scope for now (decision D13). **Superseded in part by D24: Riksdagen's open data is now a source (R16). Regeringen.se stays out (D25).**
- N13. DN is not a source (decision D12).
- N14. Not used (decision D25): Göteborgs-Posten, Altinget, Aftonbladet, Expressen, SvD, Sydsvenskan, Di, DN, Omni and Regeringen.se. Reason for Göteborgs-Posten, reported by the manager and not an owner statement: Stampen Media's published TDM reservation (`https://stampenmedia.se/upphovsratt-ai/`). For the others no reason was given to the design, and the worker has not checked any.
- N15. No publishing (decision D26): the page and `news.json` stay on the owner's computer.
- N16. No choice of several topics at once and no free-text search; one topic at a time (D22).

## 2. Users and scenarios

### Users
- The owner, who **only reads** the page, on the computer where the page runs (D20; with local use only, D26, a phone cannot open `localhost`). The page is not meant to be shared.
- If the page is published on GitHub Pages (Q1), anyone who finds the address can see it, because the repository is public (risk K11). Retired with publishing (D26).
- The owner as maintainer: approves additions to and removals from the list of sources through issues.

### 2.1 Read the news (main flow)
1. The reader opens the page: locally at `http://localhost:8000/` after running the build (R12.1) (publishing at a Pages address was dropped, D26).
2. The page loads `sources.json`, `politics-keywords.json` and `news.json` from its own folder.
3. In parallel the page fetches the Sveriges Radio feed directly from Sveriges Radio (R7.1).
4. The page reads the reader's chosen sources from the browser's local storage. The first time, all sources are chosen.
5. The page shows one list, newest first, of SVT items (from `news.json`) and Sveriges Radio items (from memory) from the chosen sources: headline as a link, source name, time.
6. At the top the page shows when the SVT data was built ("SVT uppdaterad 2026-11-13 14:05") and when Sveriges Radio was fetched ("Sveriges Radio hämtad 14:07").
7. The reader clicks a headline. The original opens in a new tab.

Version 7 (from F7): step 4 also reads the saved topic (R18.3), step 5 shows only the items of the chosen topic (2.7), and the line of step 6 reads "Nyheter uppdaterade <time>" (R18.8). Between F5 and F7 the page still shows politics only (R19.8).

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

Version 7: the check in step 2 is made for each topic the source should offer, and the result is one entry per topic in the source's `feeds` list (R14.2). A topic the source does not offer simply has no entry (R13.7).

### 2.5 Remove a site from the approved list (owner, through an issue)
1. A worker deletes the entry from `sources.json`, or sets `"enabled": false` (R3.4).
2. After the merge (and the next local build), the source is gone from the page; saved choices of its id are ignored (R3.5).

### 2.6 Something is wrong
- Sveriges Radio cannot be fetched (offline, API down): the SVT items are still shown, and "Källor" says "Sveriges Radio kunde inte hämtas just nu" (R7.6). Sveriges Radio items are never shown from an old copy, because there is none (N10).
- SVT failed in the last build: its items from the last successful build are kept for up to 24 hours, and "Källor" shows "Kunde inte hämtas sedan <time>" (R6.2).
- The page is opened without a network: it shows the last saved `news.json` (SVT only) with a notice (R8.2).
- `news.json` is old (the build stopped): the page warns (R8.3).
- One feed of a source fails while another feed of the same source works (for example SVT `inrikes`): only the topics served by the failed feed show their items from the last good build (under 24 hours), and the feed's status in `news.json` is `error` (R19.3, R19.4).
- Riksdagen cannot be fetched: handled like SVT (R6.2).

### 2.7 Choose a topic (from F7)
1. The reader opens "Ämnen" (above "Källor"). It lists Alla nyheter, Politik, Natur and AI, one choice at a time. The first time, Politik is chosen until F8 (Q8).
2. The reader picks Natur. The list at once shows the items of the chosen sources whose `topics` include `nature`, newest first. No request goes to any site (R15.3).
3. The topic id is saved in local storage (R18.3).
4. A source that does not offer the topic (Riksdagen has no Natur) contributes nothing, and "Källor" says "Erbjuder inte ämnet Natur" on its row (R18.5). Until F8, the row of Sveriges Radio says "Visas inte än" for every topic except Politik (R18.9).
5. An item that matches several topics (an AI item about nature) is shown under each of them (R13.3).
6. When Riksdagen items are in the list, the line "Källa: Sveriges riksdag" is shown below the list (R16.5).

## 3. Requirements

Every requirement is numbered and testable. "Build" means the Python program that reads SVT and writes `news.json`. "Page" means the HTML page and its JavaScript. (auto py) is covered by pytest, (auto js) by Node's built-in test runner, (hand) by the owner by hand.

Version 7 (2026-11-14): R13 to R19 are new. They apply from the step named in section 12; until then the older text describes the code. Where an old requirement is extended or superseded, a pointer at the old place says so. Where R1 to R12 say "SVT" for the content of `news.json`, that means all build sources (SVT and Riksdagen) from F5 and F6.

### R1. Item content
- R1.1 (auto py) Each item in `news.json` has exactly these fields: `id`, `sourceId`, `sourceName`, `title`, `url`, `published`, `publishedDisplay`. No summary, description, content or image field (N1). Extended by R1.5: from F5 the build items of `news.json` version 2 have one more field, `topics`.
- R1.2 (auto js) Each Sveriges Radio item held in memory has exactly the same fields as R1.1 and nothing else. Extended by R1.5: from F8 an item in memory also has `topics`.
- R1.3 (auto py, auto js) `title` is plain text: HTML tags are removed, HTML and XML entities are decoded (for example `&amp;` becomes `&`), runs of white space become one space, and leading and trailing white space is removed. Nothing else in the headline is changed or cut; long headlines wrap on screen (R8.5). This keeps Sveriges Radio's headlines unmodified, as its terms require (section 4.3).
- R1.4 (auto py, auto js) An item with an empty `title`, or without a usable `url` (R9.1), is dropped.
- R1.5 (auto py, auto js) From `news.json` version 2 (R19.2) each item has the seven fields of R1.1 and one more, `topics` (a non-empty list of topic ids, R13.3): exactly eight fields, nothing else. A Sveriges Radio item held in memory has the same eight fields (from F8). Still no summary, description, content or image field (N1).

### R2. Time
- R2.1 (auto py, auto js) `published` is UTC in ISO 8601 form with a `Z`, for example `2026-11-13T13:05:00Z`, or `null` when the feed gives no usable time.
- R2.2 (auto py) The build reads RSS `pubDate` (RFC 822 date, for example `Fri, 13 Nov 2026 14:05:00 +0100`). A time without a zone is read as Europe/Stockholm.
- R2.3 (auto js) The page reads Atom `published`, falling back to `updated` (ISO 8601 with offset).
- R2.4 (auto py, auto js) `publishedDisplay` is the time in the time zone Europe/Stockholm, 24-hour clock, in the form `YYYY-MM-DD HH:MM`, for example `2026-11-13 14:05`. Summer time follows the time zone rules (for example `2026-07-01T10:00:00Z` shows as `2026-07-01 12:00`). Python and JavaScript must give the same text for the same time; the shared test cases in `tests/shared-cases.json` check this (section 9).
- R2.5 (auto py, auto js) When `published` is `null`, `publishedDisplay` is `Tid saknas`.
- R2.6 (auto py, auto js) A time more than 10 minutes after "now" (build time, or page time) is treated as `null`.
- R2.7 (auto py) `news.json` has `generatedAt` (UTC) and `generatedAtDisplay` (form of R2.4).

### R3. Approved sources and the reader's choice
- R3.1 (auto py) The approved sources are listed in `sources.json` in the repository (shape in section 7.1). Each has `fetchedBy`: `build` or `browser`. From F3 the shape is the one in section 7.5 (version 2); section 7.1 is version 1.
- R3.2 (auto py) A source with `fetchedBy: browser` must have `"storageAllowed": false` and must not appear in `news.json`; the build test fails if it does.
- R3.3 (hand) The reader's choice is a list of source ids in `localStorage` under `newsReader.selectedSources`. On the first visit all enabled sources are chosen. If storage is blocked, the page works with all sources chosen. Extended by R18.3 (the topic choice) from F7.
- R3.4 (auto py, hand) A source with `"enabled": false` is not fetched by the build and not fetched or shown by the page.
- R3.5 (hand) A saved id that is no longer in `sources.json` is ignored and removed when the reader next changes the choice. A newly added source is shown in "Källor" not ticked. Exception from F7: the one-time migration of R18.4 adds `riksdagen` to a saved choice.

### R4. Category: politics in Sweden
- R4.1 (auto py) A source supplies the category `politics-sweden` with exactly one method in `sources.json`: `feed` (a dedicated politics feed), `categoryFilter` (exact `<category>` values) or `keywordFilter` (the shared keyword list). Both current sources use `keywordFilter`, because neither has a politics feed. **Superseded by R13.2 and R14.3 from F3:** a source supplies each topic it offers with one method in its `feeds` list; the key `politics-sweden` is replaced by a feed entry with the topic `politics`.
- R4.2 (auto py) The method is chosen in this order of preference: `feed`, else `categoryFilter`, else `keywordFilter`. A source without a method fails the configuration test. From F3 this applies to each feed entry (R14.3); a topic without an entry is not offered (R13.7).
- R4.3 (auto py, auto js) The keyword list is **one shared file**, `politics-keywords.json` (section 7.2), read by the Python build and fetched by the page. Neither has its own copy of the terms. Extended by R17.1: one shared file per topic.
- R4.4 (auto py, auto js) An item matches when its headline or its description (RSS `description`, Atom `summary`), cleaned as in R1.3, contains at least one `include` term under the rules of section 7.2, after the `exclude` phrases and words have been taken out of consideration. Without a description, only the headline is used. The description is then discarded. From F4 it applies per topic, with that topic's file (R13.3, R17.1).
- R4.5 (auto py, auto js) Python and JavaScript give the same match result for every case in `tests/shared-cases.json`. From F4 it applies to every topic (R17.4).
- R4.6 (hand) In "Källor", each `keywordFilter` source shows "Urval med nyckelord – ungefärligt". Extended by R18.5 from F7.

### R5. Selection, duplicates and order
- R5.1 (auto py, auto js) At most 20 items per source: the 20 newest matching items by `published`; items with `null` time come last and only fill up to 20. From F5 the cap applies per source and topic (R13.6).
- R5.2 (auto py, auto js) Items older than 7 days before "now" are dropped.
- R5.3 (auto py, auto js) Duplicates within a source are removed by normalised URL: scheme and host in lower case, `www.` removed from the host, query string and fragment removed, trailing `/` removed. The first item in feed order is kept. From F5 the topics of merged duplicates are joined (R13.5).
- R5.4 (auto py, auto js) `id` is the first 16 hexadecimal characters of the SHA-256 of the normalised URL (JavaScript uses `crypto.subtle.digest`).
- R5.5 (auto js) The page merges the chosen sources' items and sorts them by `published`, newest first; `null` last; equal times by `sourceId`, then by `title`.

### R6. The build (SVT and any other `fetchedBy: build` source)
- R6.1 (hand, owner) Published variant only: the build runs every 30 minutes on a schedule, and by hand from the Actions tab. Local variant: the owner runs it by hand (R12.1). **Superseded by D26: the published variant is dropped; the build runs by hand (R12.1).**
- R6.2 (auto py) Each source is fetched with a timeout of 15 seconds, one request per feed per build; redirects only within `allowedHosts`. On failure (network error, status other than 200, not RSS 2.0, zero items, redirect to another host) the build keeps the source's items from the previous `news.json` if they are less than 24 hours old, and records the status `error` and the time of the last success. From F5: one request per distinct feed URL (R15.1), and the fallback is kept per feed entry (R19.4).
- R6.3 (auto py) `news.json` has a `sources` list with, for each build source: `id`, `name`, `status` (`ok`, `error` or `blocked-by-robots`), `lastSuccess`, `itemCount`. A source that is not `ok` also has an optional string `message` that says why (present only when `status` is not `ok`): fixed text or the name of an exception class, never any feed content. Extended by R19.3 from F5 (status per feed).
- R6.4 (auto py) A failing source never fails the build. The build fails only if `sources.json` or `politics-keywords.json` is invalid. From F3 it also fails for a `sources.json` of the wrong version; from F5 also for an invalid or missing keyword file of any topic (R14.5, R17.5).
- R6.5 (auto py) The build sends `User-Agent: GithubAutoPlay-news-reader/1.0` and no cookies.
- R6.6 (auto py) The build reads the host's `/robots.txt` once per run and does not fetch a path disallowed for its User-Agent (status `blocked-by-robots`). If robots.txt cannot be read, it does not fetch (status `error`).
- R6.7 (auto py) The build never fetches a `fetchedBy: browser` source.

### R7. Live fetch in the browser (Sveriges Radio and any other `fetchedBy: browser` source)
- R7.1 (hand) The page fetches the feed URL in `sources.json` directly from the source (for Sveriges Radio `https://api.sr.se/api/rss/program/83`), with `credentials: "omit"` and `cache: "no-store"`, and a timeout of 15 seconds.
- R7.2 (hand) Call load: one request when the page opens; then at most one request every 10 minutes, and only while the page is visible (paused when the tab is hidden). The "Uppdatera" button fetches again only if at least 5 minutes have passed since the last request to that source; otherwise it only reloads `news.json`. There are never two requests to the same source within 5 minutes from one open page. Counted per feed URL, not per topic (R15.3).
- R7.3 (hand) The items are kept in memory only. They are never written to `localStorage`, `sessionStorage`, IndexedDB, cookies, the Cache API, a file or a server, and never logged to the browser console or included in error messages or error reports (an error message names the source and the kind of failure only). When the page is closed they are gone.
- R7.4 (auto js) The Atom entries are mapped as in R11.2, then filtered and selected with the same rules as the build (R1.3, R1.4, R2, R4.4, R5.1 to R5.4, R9.1). From F8 with the rules of every topic that the feed serves (R13.3, R17.1).
- R7.5 (hand) Every Sveriges Radio item shows the source name "Sveriges Radio" visibly next to the headline, and the line at the bottom of the page (R8.7) names Sveriges Radio.
- R7.6 (hand) If the request fails or the feed cannot be read, the page shows the other sources' items and the status "Sveriges Radio kunde inte hämtas just nu" in "Källor"; it does not retry before the next scheduled fetch (R7.2).

### R8. Page behaviour
- R8.1 (hand) The page loads `news.json` when it opens, every 10 minutes while visible, and on "Uppdatera". A new load replaces the SVT part only when it succeeds.
- R8.2 (hand) After each successful load the page saves `news.json` (SVT only, never browser-source items) in `localStorage` under `newsReader.lastNews`. If loading fails, it shows the saved copy with "Offline – visar sparade SVT-nyheter från <generatedAtDisplay>". Without a saved copy: "Kunde inte hämta nyheter. Försök igen senare." From F7 the text says "sparade nyheter" instead of "sparade SVT-nyheter" (R18.8).
- R8.3 (hand) If `generatedAt` is more than 3 hours old by the reader's clock, the page shows "SVT-nyheterna kan vara gamla – senast uppdaterade <generatedAtDisplay>". From F7 the text says "Nyheterna" instead of "SVT-nyheterna" (R18.8).
- R8.4 (hand) If none of the chosen sources has items, the page shows "Inga nyheter från valda källor." Stays for "no source chosen"; the topic notices are in R18.6.
- R8.5 (hand) The page works on a 360-pixel-wide phone screen without sideways scrolling; long headlines wrap (nothing is cut, R1.3).
- R8.6 (hand) The page loads no scripts, fonts or styles from other sites. Its only request to another site is the feed request of R7.1. It registers no service worker and does not use the Cache API.
- R8.7 (hand) Below the list: "Rubriker och länkar från SVT och Sveriges Radio. Klicka för att läsa hos källan." The source names in this line come from `sources.json`. Extended by R18.7 (all enabled sources, and the credit text).
- R8.8 (hand) All text is in Swedish, with `<html lang="sv">` and `<meta charset="utf-8">`.
- R8.9 (hand) The page has no advertising, no marketing and no analytics (N11), and carries `<meta name="robots" content="noindex">` so that a published copy is not meant for search engines (K11).

### R9. Safety of links and text
- R9.1 (auto py, auto js) An item `url` is kept only if its scheme is `https` or `http` and its host is one of the source's `allowedHosts` or a subdomain of one. Other items are dropped. From F6, if a source has `linkHosts`, the host must equal one of them exactly (R16.2).
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

### R12. Running and hosting (local only since D26; the published variant is retired)
- R12.1 (hand) **Local variant:** from `applications/news-reader/`, the owner runs `python -m newsreader --out build` and `python -m http.server 8000 --directory build`. If `build/news.json` exists from an earlier run, the build reads it as the previous file before overwriting it, so the 24-hour fallback of R6.2 works locally too; `--previous <file>` names another file (used by the published variant), and opens `http://localhost:8000/`. Nothing is published. The build copies `site/*`, `sources.json` and `politics-keywords.json` into `build/`. The folder `build/` is listed in `.gitignore` so `news.json` is never committed. Amended by R12.3 (the server is bound to 127.0.0.1). From F5 it copies every keyword file named in `sources.json` (R14.5).
- R12.2 (hand, owner) **Published variant:** a separate workflow publishes the same `build/` content to GitHub Pages under `<Pages address>/applications/news-reader/` (decision D16). It never commits and is not a required check. **Retired 2026-11-14 (D26): publishing is dropped, and steps S12 and S13 are not done.** The text stays so that old references remain valid.
- R12.3 (hand) Local use only (D26): the owner serves `build/` with `python -m http.server 8000 --bind 127.0.0.1 --directory build`, so other computers on the network cannot reach the page, and opens `http://localhost:8000/`. `build/` is never committed (R12.1). No workflow, Pages setting or other means publishes the page. The README still shows the command without `--bind`; it is aligned in step F7.

### R13. Topics (D21, D22; new in version 7)
- R13.1 (auto py, auto js) The topics are exactly these four, in this order, with these ids and Swedish labels: `all-news` "Alla nyheter", `politics` "Politik", `nature` "Natur", `ai` "AI". They are defined once, in `sources.json` (R14.1); the build and the page take ids, order and labels from there and have no second copy.
- R13.2 (auto py, auto js) `all-news` has no keywords and takes every item of its feed. Each other topic has one keyword file (R17.1), named by the `keywords` field of the topic. A feed entry uses the method `feed` (the feed is the topic) or `keywordFilter` (R4.1) or `categoryFilter`; the topic `all-news` uses only `feed`.
- R13.3 (auto py, auto js) An item belongs to a topic when it came from a feed entry of its source with that topic and the method lets it through: `feed` always; `keywordFilter` when the topic's keyword list matches under R4.4; `categoryFilter` when a category matches. One item can belong to several topics. `topics` of the item lists all of them, in the order of R13.1, without duplicates, and has at least one entry.
- R13.4 (auto py, auto js) One function in each language, Python `topics_of` and JavaScript `topicsOf`, returns all topics of one item in one call, from its cleaned headline and description and the topic rules of the feed URL it came from. Python and JavaScript give the same list for every case in the section `topics` of `tests/shared-cases.json` (R17.4).
- R13.5 (auto py, auto js) When the same item (same normalised URL, R5.3) comes from several feed URLs of one source, it becomes one item and its topics are joined (union, order of R13.1).
- R13.6 (auto py, auto js) The age limit and the cap of R5.1 and R5.2 apply per source and per topic: of the items that belong to a topic, the 20 newest are kept. The `topics` of a kept item then lists only the topics in which it was kept; an item left with no topic is dropped. So there are at most 20 items per source in each topic, and "Alla nyheter" never shows more than 20 per source.
- R13.7 (auto py, auto js) A topic for which a source has no feed entry gives no items from that source. It is not an error and not a failed fetch.

### R14. `sources.json` version 2 (D28; new in version 7)
- R14.1 (auto py) The file has `version` 2, a `topics` list and a `sources` list (shape in section 7.5). Each topic has `id`, `label` and, for every topic except `all-news`, `keywords`. The ids are exactly those of R13.1 in that order. `keywords` is `<id>-keywords.json` (`politics-keywords.json`, `nature-keywords.json`, `ai-keywords.json`) and matches `^[a-z0-9-]+-keywords\.json$`, so it holds no `/` and no `..`. `all-news` has no `keywords`. F3 checks only this name rule; that the files exist and are valid is checked from F5 (R14.5).
- R14.2 (auto py) Each source has the fields of version 1 (`id`, `name`, `enabled`, `fetchedBy`, `storageAllowed`, `homepage`, `allowedHosts`), an optional `credit` (non-empty text, R16.5), an optional `linkHosts` (non-empty list of exact lower-case host names that item links must have, R16.2) and `feeds`, a non-empty list that replaces the version 1 key `politics-sweden`. Each feed entry has `topic`, `method`, `url` and an optional `matchOn`: the value `title` means that the keyword match reads only the headline and never the description; missing means headline and description (R4.4). If Q6 requires it, F6 adds one optional source-level time field here, with its validation.
- R14.3 (auto py) Validation: `topic` is a topic id; at most one feed entry per topic and source; `method` is `feed`, `categoryFilter` or `keywordFilter`; the topic `all-news` only uses `feed`; `url` is an https address; for a `fetchedBy: build` source the host of every feed `url` is one of its `allowedHosts` or a subdomain of one (as R6.2 requires); R3.2 holds for `fetchedBy: browser` sources. An invalid file fails the build (R6.4) with a message that names the source and the field. Each `linkHosts` entry is on `allowedHosts` or a subdomain of one; `matchOn` is allowed only with `keywordFilter`.
- R14.4 (auto py) Several feed entries of one source may have the same `url` (R15.1). A source does not have to offer every topic (R13.7).
- R14.5 (auto py) From F5, every `keywords` file named in `topics` exists in the application folder, is valid (R17.5), and the build copies these files, `sources.json` and `site/*` into `build/`. Until F5 only `politics-keywords.json` is read and copied, as today, and F3 does not need the other files to exist.
- R14.6 (auto py) No code reads both versions of `sources.json`. After F3, a file with `version` 1 is refused with the message "sources.json version 1 is no longer supported". The build copies `sources.json` into `build/` together with the page, so page and build always read the same version.

- R14.7 (auto js) From F3 the page's `validateSources` (`site/app.js`) reads version 2 and refuses version 1, and accepts `credit`, `linkHosts` and `matchOn`; `selectItems` (`site/logic.js`) and the build take the feed entry of the topic `politics` of a source (the build until F5, the page until F8). Node tests cover this, and the page behaves as before.

### R15. One fetch per distinct URL (D29; new in version 7)
- R15.1 (auto py) The build fetches each distinct feed URL once per build, however many feed entries use it. The response is parsed once and evaluated for each feed entry that uses the URL. A test with a fake fetch layer counts the feed requests (robots.txt requests are not counted): with the feeds of section 7.5, SVT costs two requests (`nyheter/rss.xml` once for three topics, `inrikes/rss.xml` once).
- R15.2 (auto py) robots.txt is read once per host and run (R6.6), and the decision applies to every feed entry on that host. A URL that is blocked or fails marks every feed entry that uses it (R19.3).
- R15.3 (hand, auto js) In the browser a feed URL is requested once per fetch round for all the topics it serves (Sveriges Radio: one request serves four topics). The call limits of R7.2 count requests to a URL, not topics. Changing the topic never causes a request. A source the reader has not chosen is not requested, and no keyword file that only it needs is fetched; ticking it makes the request (within R7.2).

### R16. Riksdagen's open data as a build source (D24, D34; new in version 7)
- R16.1 (auto py) `sources.json` has a source `riksdagen`: `name` "Riksdagen", `fetchedBy` `build`, `storageAllowed` `true` (valid only if R16.8 finds that storing is allowed), `allowedHosts` `["riksdagen.se"]`, `linkHosts` `["www.riksdagen.se"]`, `credit` "Källa: Sveriges riksdag", and feed entries for `all-news` (`feed`), `politics` (`feed`: every Riksdag document is about politics) and `ai` (`keywordFilter` with `matchOn` `title`), all with the same address. There is no `nature` entry (D24).
- R16.2 (auto py) The address is the document list in RSS form (section 4.6) with `sz=50` and the document types of Q5 (F6 starts with `prop,bet`). The RSS 2.0 parser of R11.1 is used. `title`, `link` and `pubDate` are read. `description` is not used for any matching (`matchOn` `title`, R14.2) and is never shown (N1); `author` and `guid` are never read. Only the RSS `link` is read as the item URL, and its host must equal `www.riksdagen.se` exactly (`linkHosts`, R9.1); links on other hosts, including `data.riksdagen.se` (the host of `guid` and the JSON links), are dropped.
- R16.3 (auto py) One request per build for the three feed entries (R15.1; the test counts feed requests, robots.txt excluded). The size limit of R9.4 stays at 2 MB.
- R16.4 (auto py) The build reads robots.txt of the feed host `data.riksdagen.se` as in R6.6 (the answer 404 means no rules, so allowed). The check of `https://www.riksdagen.se/robots.txt` is a manager or owner step done before F6 is taken, as in R16.8; its result goes into section 4.6. The build never fetches that host.
- R16.5 (hand) Credit and no endorsement: whenever the list contains at least one Riksdagen item, the page shows the `credit` text of the source ("Källa: Sveriges riksdag") below the list, in the line of R8.7, followed by "Sidan har inget samband med Sveriges riksdag."; the "Källor" row of Riksdagen shows the credit always. The page must not say or suggest that the Riksdag stands behind the service: the Riksdag's name is used only as the source name on items and in these two texts, never in the page title, the heading or the styling, and the page shows no Riksdag logo or image. The wording and the display name are open for the owner (Q9).
- R16.6 (auto py) The headline is the document title, cleaned as in R1.3 and never cut. Motions, which have very short titles, are not in the default feed (Q5).
- R16.7 (auto py) Time: the RSS `pubDate` has the offset +0200 also in November (Q6). Q6 is settled by a manager or owner comparison before F6 is taken. Until it is settled, R2.2 reads the offset as given. If Q6 requires another rule, F6 adds the optional field of R14.2 and tests it with time cases.
- R16.8 (hand, manager or owner) Before F6 is taken, the terms at `https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/anvandarstod/anvandningsvillkor/` are read again and the result is recorded in section 4.6, in particular whether headlines and links may be stored. If storing is not allowed, Riksdagen cannot be added (section 2.4, step 3; the feed has no CORS header, so a live fetch is not possible either): F6 is closed, and F7 and F8 are done without Riksdagen (R16.5 and R16.9 then do not apply).
- R16.9 (auto py, auto js, hand) Riksdagen is not shown without its credit. F6 adds the entry with `"enabled": false`; its tests use a copy of the file with the entry enabled. F7 sets `"enabled": true` in the same change that shows the credit text (R16.5). Consequences, handled in F7: (a) a reader with a saved `selectedSources` would not have Riksdagen ticked (R3.5), so F7 adds `riksdagen` once to a saved choice (the migration of R18.4); (b) the F6 test that the real file has the entry disabled is changed in F7 to check that it is enabled; (c) the first build against the real Riksdag feed is checked by the owner as part of the owner check of F7 (separate from the check of R16.8).

### R17. Keyword lists per topic (D23, D33; new in version 7)
- R17.1 (auto py, auto js) Each topic except `all-news` has its own keyword file, read by the build and fetched by the page, with no second copy; the file name is the one of R14.1: `politics-keywords.json` (the existing file), `nature-keywords.json` and `ai-keywords.json`. The shape and matching rules are those of section 7.2 with the additions of section 7.6.
- R17.2 (auto py, auto js) The AI list has terms in Swedish and in English (D23), for example "artificiell intelligens", "maskininlärning", "språkmodell*", "chatbot*", "ChatGPT", "OpenAI", "artificial intelligence", "machine learning", "language model" and the case-sensitive whole word `AI`. The final lists are made in F4 and tuned on live feeds.
- R17.3 (auto py, auto js) Two new kinds of terms (section 7.6): `include.phrases` (words in sequence) for multi-word terms, and `include.caseSensitiveWords` (one whole word, exact case). The word split is that of section 7.2, so `AI-regler` has the word `AI` and matches, while `AIK`, `FAIR` and `Ai Weiwei` do not. Matching order: an include phrase hits when its words occur in sequence in the lower-case word list of the text, at positions none of which was marked by an exclude phrase (the marking of rule 4 of the existing algorithm, made on the original word list); exclude words do not apply to include phrases. `caseSensitive` and `caseSensitiveWords` are tested on the NFC-normalised text with case kept and are not affected by any exclusion, as `caseSensitive` is today. Validation in the loader: `phrases` terms have two or more words, no `*`, and are lower-cased and compared for duplicates like `exclude.phrases`; a `caseSensitiveWords` term is exactly one word (letters and digits), contains at least one letter, has no `*`, is NFC and has no surrounding white space; duplicates are an error.
- R17.4 (auto py, auto js) The shared cases file is extended: each case in the section `keywords` has `input.topic` (missing means `politics`), so all three lists have cases there; a new section `topics` holds cases for R13.4 (`input`: headline, description and the feed entries of the URL; `expected`: the list of topic ids). Both test suites run all of them (R4.5).
- R17.5 (auto py) From F5, the build loads every keyword file named in `sources.json` with the loader of F4. A file must exist, have `topic` equal to the topic id, and be valid: all keys present (lists may be empty), and at least one of the four include lists non-empty. An invalid or missing file fails the build (R6.4).

### R18. The page: topics, sources and notices (D22, D32; new in version 7)
- R18.1 (hand) The page has a section "Ämnen" above "Källor": one choice at a time (radio buttons), in the order of R13.1, with the labels from `sources.json`. A topic is listed when at least one enabled source offers it (today all four).
- R18.2 (hand, auto js) The list shows the items of the chosen sources whose `topics` contain the chosen topic. The filter is by membership (D22): an item with several topics is shown under each. The filtered items are merged and sorted by R5.5. Changing the topic makes no request (R15.3).
- R18.3 (hand) The saved choice is `localStorage["newsReader.selectedTopic"]`: one string, a topic id such as `"politics"`; nothing else (no label, no content). A missing, unknown or unreadable value means `politics` until F8, which keeps the page as it was; Q8 asks whether the default becomes `all-news` after F8. If storage is blocked, the page works with `politics`.
- R18.4 (hand, auto js) Old saved state keeps working. `newsReader.selectedSources` keeps its form and meaning (R3.3, R3.5). Migration, once: when `selectedTopic` is missing and a saved `selectedSources` exists, the page adds `riksdagen` to it (if that source is enabled and not in the list) and writes both keys at once, so an unticked Riksdagen stays unticked afterwards; without a saved choice all enabled sources are chosen (R3.3). A saved `newsReader.lastNews` of version 1 is read with the topics `["all-news", "politics"]` on every item (its items were politics headlines); it has no `feeds`, so rows show no feed status for it. Version 2 is read as it is; any other version is not used, as if there were no saved copy (R8.2). The page reads `news.json` of version 1 and 2 only.
- R18.5 (hand) Each row of "Källor" lists the topics the source offers ("Ämnen: Alla nyheter, Politik, AI"). When the source has no feed entry for the chosen topic (Natur and Riksdagen), the row says "Erbjuder inte ämnet Natur", and the source stays chosen but contributes nothing. Until F8 the row of a `fetchedBy: browser` source says "Visas inte än" for every topic except Politik (R18.9). The note "Urval med nyckelord – ungefärligt" of R4.6 is shown on a row when the source's feed for the chosen topic uses `keywordFilter`. The status text of a row ("Kunde inte hämtas sedan <time>") comes from the status of the feed for the chosen topic (R19.3).
- R18.6 (hand) Notices when the list is empty: no source chosen: "Inga nyheter från valda källor." (R8.4); the chosen sources do not offer the topic: "Valda källor erbjuder inte ämnet <Ämne>."; they offer it but there are no items: "Inga nyheter i ämnet <Ämne> från valda källor." (<Ämne> is the label, for example "Natur".)
- R18.7 (hand) The line of R8.7 names every enabled source, from `sources.json`, and is followed by the credit texts of R16.5.
- R18.8 (hand) Because `news.json` holds more than SVT, the texts of R8.2 and R8.3 say "Offline – visar sparade nyheter från <generatedAtDisplay>" and "Nyheterna kan vara gamla – senast uppdaterade <generatedAtDisplay>", and the header line says "Nyheter uppdaterade <time>" for the build part. The Sveriges Radio line is unchanged.
- R18.9 (hand) Until F8 is merged, the page treats a `fetchedBy: browser` source as showing only Politik (as the S11 code does): for other topics it contributes nothing and its row says "Visas inte än". For R18.6 it counts as offering a topic when it has a feed entry for it. F8 removes this limit.

### R19. `news.json` version 2 (D30; new in version 7)
- R19.1 (auto py) `version` is 2. A top-level `topics` list holds the topic ids of `sources.json` in order. The field `category` of version 1 is gone.
- R19.2 (auto py) Each item has the eight fields of R1.5. Every id in `topics` of an item is in the top-level `topics`, in the order of R13.1, without duplicates.
- R19.3 (auto py) Each entry of `sources` has the fields of R6.3 (`id`, `name`, `status`, `lastSuccess`, `itemCount`, optional `message`) and a `feeds` list with one entry per feed entry of `sources.json`, in its order: `topic`, `status`, `lastSuccess`, `itemCount` (items of the source that have the topic) and an optional `message` under the rule of R6.3. Feed entries that use the same URL share `status`, `lastSuccess` and `message` (R15.2). When feeds differ, the source entry shows the worst status and the `message` of the first feed (in `sources.json` order) that has that status; the statuses of all feeds are listed in `feeds`. The status of the source is the worst of its feeds (`error`, then `blocked-by-robots`, then `ok`); `lastSuccess` of the source is the oldest `lastSuccess` of its feeds (`null` if one has never succeeded); `itemCount` is the number of distinct items of the source. No URL is written to `news.json`.
- R19.4 (auto py) Fallback, unchanged in kind and kept per feed entry: when a URL fails, each feed entry that uses it keeps, from the previous `news.json`, the items of that source that have that topic, if less than 24 hours have passed since the feed's previous `lastSuccess`; the kept items get only those topics added, joined with any topics from feeds that succeeded (R13.5), and the feed gets status `error`. The cap of R13.6 is applied again after the previous items have been added. A previous file of version 1 is read as: all its items have the topic `politics`, and the feed `politics` of each source has the source's `lastSuccess`; other feeds have no previous items.
- R19.5 (auto py) `generatedAt` and `generatedAtDisplay` (R2.7) are unchanged. A `fetchedBy: browser` source is never in `news.json` (R3.2).
- R19.6 (auto py) The build checks its own output against R19.1 to R19.3 before writing it, as it does for version 1.
- R19.7 (auto js) Items of a browser source in memory have the same eight fields as R1.5 and the topics of R13.3, taken from the one response of R15.3 (from F8). R7.3 is unchanged: nothing is stored.
- R19.8 (auto js, hand) From F5 the page's `validateNews` (`site/app.js`) reads `news.json` of version 1 and 2. Until F7 it shows only the items whose `topics` contain `politics`, so the list is as before. A saved `lastNews` of version 1 is shown whole, as before; version 2 as just said; other versions are not used.

## 4. Findings about the sources

### 4.1 How this was checked
Date of all checks: **2026-11-13**.
- **Worker's environment:** direct requests to the news hosts (svt.se, api.sr.se, sverigesradio.se and the earlier candidates) were refused by the environment's network proxy (HTTP 403 on connect). The worker used web search and the feed directories Feeder and Feedspot to find candidate addresses.
- **Manager, in the owner's browser:** every fact in this section marked "verified (manager)" was **checked by the manager in the owner's browser on 2026-11-13**: the SVT feeds and SVT's robots.txt, the Sveriges Radio feeds and API endpoints, Sveriges Radio's terms page and API documentation, and sverigesradio.se's robots.txt. The worker has not seen the raw responses itself. Everything not marked so is **not verified**.
- No page contained anything that looked like instructions to the worker.
- The Riksdagen facts in section 4.6 come from the F1 report (comment on issue #87, 2026-11-14). This worker has not seen the raw responses and cannot reach the site.

### 4.2 SVT (svt.se), fetched by the build

| URL | Result | Checked by |
|---|---|---|
| `https://www.svt.se/nyheter/inrikes/rss.xml` | **Domestic news feed. HTTP 200, RSS, 100 items. Fields per item: `title`, `link`, `description`, `pubDate`, `guid`. No CORS header.** | Verified (manager) |
| `https://www.svt.se/nyheter/rss.xml` | All news, HTTP 200, 100 items. | Verified (manager). Used for Alla nyheter, Natur and AI from F5 (D31). |
| `https://www.svt.se/nyheter/politik/rss.xml` | 404, no politics feed | Verified (manager) |

- No CORS header, so a page on another site cannot read the feed; SVT must be fetched by the build.
- Method: `keywordFilter` on the domestic feed. Because the feed is already limited to domestic news, keyword hits are mostly Swedish politics. Still approximate (K6).
- **robots.txt** (verified (manager)): `User-agent: *` with `Allow: /`, and the content signal `ai-train=no, search=yes, ai-input=yes`: training AI models on the content is not permitted (K7).
- **SVT's terms of use beyond robots.txt have not been read** (K12, step S1).
- **Not verified:** the host of the item links (`www.svt.se` expected; Q2), whether items carry `<category>` or images.
- Update reported by the manager: step S1 found no published SVT terms.
- Version 7: SVT's own nature and science feeds are unconfirmed (Q7). Until they are checked, Natur and AI use `nyheter/rss.xml` with keywords (D31).

### 4.3 Sveriges Radio (sverigesradio.se), fetched live in the browser

| URL | Result | Checked by |
|---|---|---|
| `https://api.sr.se/api/rss/program/83` | **Ekot text news, Atom (`application/atom+xml`), 20 entries. Fields: `id`, `title`, `summary`, `published`, `updated`, `author`, `link`, `category`, `content`. `published` and `updated` in ISO 8601 with offset (for example `+01:00`). Links to text articles on `https://www.sverigesradio.se/artikel/<number>`. `Access-Control-Allow-Origin: *`.** | Verified (manager) |
| `https://api.sr.se/api/rss/group/27511` | "Toppnyheter", Atom, stale (newest entries 2026-11-12 and older), local-news style. | Verified (manager). **Not used.** |
| `https://api.sr.se/api/v2/news`, `.../news/episodes`, `.../episodes/index?programid=5380` | JSON API with **audio episodes**. | Verified (manager). **Rejected:** audio, not articles; a separate parser; time field not verified. |

- The feed mixes all Ekot news (world, culture, sport), so it needs the keyword filter; `category` values were not reported (Q3).
- `Access-Control-Allow-Origin: *` means the page can read the feed directly in the browser, which is what makes the live fetch possible.
- The item link host is verified: `allowedHosts` is `sverigesradio.se`.
- Version 7: this one feed serves all four topics with one request (D27, R15.3). The terms are unchanged, so every term in the table below applies to every topic. Matching the items to the topics is keyword matching (R17), not machine learning (N9).

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
- Riksdagen: no CORS header (reported in F1). It does not matter, because the build fetches it.

### 4.5 Not verified
1. SVT's terms of use beyond robots.txt (step S1).
2. The host of SVT's item links, and whether SVT items carry categories or images (Q2).
3. The `category` values of the Sveriges Radio feed (Q3).
4. That GitHub's Action runners may fetch svt.se (published variant only; very likely, not tested).
5. How well the keyword list selects politics (measured in step S8 for SVT and on the live page).
6. How well the Natur and AI lists select (measured in F4 and F5 on live feeds, K15, K16).
7. Riksdagen's allowed call frequency (not stated; the build makes one call per run, by hand), the content of `https://www.riksdagen.se/robots.txt` (F6), and whether storing headlines is allowed (R16.8).
8. Whether SVT has its own nature or science feeds (Q7).

### 4.6 Riksdagen (data.riksdagen.se), fetched by the build
Source of these facts: the F1 report (issue #87, 2026-11-14). Not seen by this worker.

| Item | Fact |
|---|---|
| Call | `https://data.riksdagen.se/dokumentlista/?doktyp=prop,mot,bet&sort=datum&sortorder=desc&utformat=rss&a=s&sz=50`. RSS 2.0, so the existing parser fits. The same call with `utformat=json` also works. |
| Document types | `prop` (proposition), `mot` (motion), `bet` (committee report). Motions are by far the most numerous and have very short titles (Q5). |
| RSS item | `title`, `author` (`riksdagsinformation@riksdagen.se`, not shown), `description` (type, number and date; partly HTML-escaped; must not be shown), `link`, `guid`, `pubDate`. |
| Links | `link` points to `https://www.riksdagen.se/sv/dokument-och-lagar/dokument/...`, so `allowedHosts` is `riksdagen.se`. `guid` and the JSON links use `data.riksdagen.se`; only the RSS `link` is used. |
| Time | `pubDate` has the offset +0200 also in November, when Stockholm time is +01:00. This looks wrong in winter (Q6). |
| robots.txt | `data.riksdagen.se/robots.txt` answers 404, which is allowed under R6.6. `www.riksdagen.se/robots.txt` is checked in F6. |
| CORS | No CORS header; irrelevant, the build fetches it. |
| Size | About 365,000 hits in total; the call is capped with `sz` (50 proposed); the 2 MB limit of R9.4 stays. |
| Call frequency | Not stated. The build runs by hand and makes one call per run. |
| Credit and terms | Terms: `https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/anvandarstod/anvandningsvillkor/`. Credit text "Källa: Sveriges riksdag"; the service must not imply that the Riksdag stands behind it; no Riksdag logo or name as branding; images are not republished (R16.5). |

The terms are read again before F6 is merged (R16.8); the result is added here.

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

**Hosting (resolved 2026-11-14, D26):** the owner decided to run the page locally on localhost only and not to publish. The Pages variant of version 6 is dropped; it would have made the headline list public (K11) and `news.json` a public derived copy of SVT headlines (K12). The safeguards that matter locally stay: `build/` is not committed, the server is bound to 127.0.0.1 (R12.3), the page carries `noindex` (R8.9), and Sveriges Radio items are never stored (D18).

**Several topics and feeds (version 7, options):**

| Option | How | Verdict |
|---|---|---|
| T1. One request per topic | Each topic fetches its own feed address, also when two topics use the same one. | Rejected: duplicate requests to the same address, against "be kind, few calls" (section 4.3) and R15. |
| **T2. One request per distinct address** | Fetch each address once, then test the same items against every topic's rules that use that address. | **Chosen (D29).** Same number of requests as before for Sveriges Radio. |
| T3. Topic from the feeds' own category tags | Read `<category>` values. | Not possible now: SVT categories unverified (Q2), Sveriges Radio values not reported (Q3). |

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

### Published variant (retired, D26; the workflow of step S12 is not added)
A workflow `.github/workflows/news-reader.yml`, separate from `ci.yml`: a schedule every 30 minutes and `workflow_dispatch`; permissions `contents: read`, `pages: write`, `id-token: write`; it downloads the published `news.json` as `--previous`, runs the build into `_site/applications/news-reader/`, and deploys with the official upload-Pages-artifact and deploy-Pages actions. It never commits. A copy goes into `GitRequirements/` in the same change.

### Changes for topics (version 7, steps F3 to F8)
- New files: `nature-keywords.json` and `ai-keywords.json` next to `politics-keywords.json` (F4; section 7.6). `sources.json` becomes version 2 (F3; section 7.5).
- `keywords.py` and `site/logic.js` load one list per topic and gain the terms `include.phrases` and `include.caseSensitiveWords`, and the function that returns all topics of an item (F4; R13.4, R17).
- `build.py` fetches each distinct URL once, evaluates every feed entry on the response, writes `news.json` version 2 and keeps the fallback per feed (F5; R15, R19).
- `tests/shared-cases.json` gets `input.topic` in the section `keywords` and a new section `topics` (F4; R17.4).
- Riksdagen needs no new module: it is an RSS 2.0 feed read by the existing parser (F6; R16).
- `site/app.js` gets the "Ämnen" choice, the saved topic and the credit line (F7), and evaluates all topics of the one Sveriges Radio response (F8).

Data flow, version 7: **Build:** `sources.json` → for each enabled build source: distinct feed URLs → robots.txt per host → fetch once per URL → parse RSS → for each feed entry using the URL: clean, topic rules (`feed` or keyword list of the topic), URL check → join duplicates and topics → age limit and cap per source and topic → `news.json` version 2. **Page:** loads `sources.json`, the keyword files and `news.json`; fetches the Sveriges Radio feed once; evaluates all its topics in memory; shows the items of the chosen topic and sources.

## 7. Data and state

### 7.1 The approved sources: `sources.json` (version 1; replaced by section 7.5 in F3)
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

### 7.2 The shared keyword list: `politics-keywords.json` (the Politik list; per-topic files in section 7.6)
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

### 7.3 The reader's state in the browser (version 1; extended by section 7.8)
- `localStorage["newsReader.selectedSources"]`: list of source ids, for example `["svt", "sveriges-radio"]`. No content.
- `localStorage["newsReader.lastNews"]`: the last `news.json` (SVT only).
- Sveriges Radio items: in a JavaScript variable only (R7.3).

### 7.4 `news.json` (version 1, SVT only; replaced by section 7.7 in F5)
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
A source whose status is not `ok` has one more field, `message`, for example `{ "id": "svt", "name": "SVT", "status": "error", "lastSuccess": "2026-11-13T09:00:00Z", "itemCount": 3, "message": "fetch failed: timeout" }` (R6.3). The headline, URL and count are made up for illustration. A Sveriges Radio item in memory has the same seven fields.

### 7.5 `sources.json` version 2 (F3; D28, D31, D34)
```json
{
  "version": 2,
  "topics": [
    { "id": "all-news", "label": "Alla nyheter" },
    { "id": "politics", "label": "Politik", "keywords": "politics-keywords.json" },
    { "id": "nature", "label": "Natur", "keywords": "nature-keywords.json" },
    { "id": "ai", "label": "AI", "keywords": "ai-keywords.json" }
  ],
  "sources": [
    {
      "id": "svt", "name": "SVT", "enabled": true, "fetchedBy": "build", "storageAllowed": true,
      "homepage": "https://www.svt.se/", "allowedHosts": ["svt.se"],
      "feeds": [
        { "topic": "all-news", "method": "feed",          "url": "https://www.svt.se/nyheter/rss.xml" },
        { "topic": "politics", "method": "keywordFilter", "url": "https://www.svt.se/nyheter/inrikes/rss.xml" },
        { "topic": "nature",   "method": "keywordFilter", "url": "https://www.svt.se/nyheter/rss.xml" },
        { "topic": "ai",       "method": "keywordFilter", "url": "https://www.svt.se/nyheter/rss.xml" }
      ]
    },
    {
      "id": "sveriges-radio", "name": "Sveriges Radio", "enabled": true, "fetchedBy": "browser", "storageAllowed": false,
      "homepage": "https://www.sverigesradio.se/", "allowedHosts": ["sverigesradio.se"],
      "feeds": [
        { "topic": "all-news", "method": "feed",          "url": "https://api.sr.se/api/rss/program/83" },
        { "topic": "politics", "method": "keywordFilter", "url": "https://api.sr.se/api/rss/program/83" },
        { "topic": "nature",   "method": "keywordFilter", "url": "https://api.sr.se/api/rss/program/83" },
        { "topic": "ai",       "method": "keywordFilter", "url": "https://api.sr.se/api/rss/program/83" }
      ]
    },
    {
      "id": "riksdagen", "name": "Riksdagen", "enabled": false, "fetchedBy": "build", "storageAllowed": true,
      "homepage": "https://www.riksdagen.se/", "allowedHosts": ["riksdagen.se"],
      "linkHosts": ["www.riksdagen.se"],
      "credit": "Källa: Sveriges riksdag",
      "feeds": [
        { "topic": "all-news", "method": "feed",          "url": "https://data.riksdagen.se/dokumentlista/?doktyp=prop,bet&sort=datum&sortorder=desc&utformat=rss&a=s&sz=50" },
        { "topic": "politics", "method": "feed",          "url": "https://data.riksdagen.se/dokumentlista/?doktyp=prop,bet&sort=datum&sortorder=desc&utformat=rss&a=s&sz=50" },
        { "topic": "ai",       "method": "keywordFilter", "matchOn": "title", "url": "https://data.riksdagen.se/dokumentlista/?doktyp=prop,bet&sort=datum&sortorder=desc&utformat=rss&a=s&sz=50" }
      ]
    }
  ]
}
```
- Rules: R14. The three SVT topics Alla nyheter, Natur and AI share one address and cost one request (R15.1); Sveriges Radio's four topics cost one request (R15.3).
- Riksdagen has no `nature` entry (D24). It is `enabled: false` from F6 until F7 shows the credit text (R16.9). The `doktyp` value follows Q5 (`prop,bet` is the recommendation).
- SVT Natur and AI use `nyheter/rss.xml` with keywords because SVT's own feeds are unconfirmed (Q7); if one is found, its entry changes to method `feed` with the new address, through an issue.
- `linkHosts` (exact link host) and `matchOn` (title only) are used by Riksdagen only (R16.1, R16.2). The SVT feed entries are a manager proposal (D31). The Sveriges Radio feed is the owner's decision (D27). "storageAllowed: true" for SVT and Riksdagen stays a working assumption (K12, R16.8).

### 7.6 Keyword files per topic (F4 writes them, F5 checks them in the build; D23, D33)
- Files, named `<topic id>-keywords.json` (R14.1): `politics-keywords.json` (name kept), `nature-keywords.json`, `ai-keywords.json`. `all-news` has none.
- Shape: as in section 7.2, with `"version": 2`, the field `category` replaced by `"topic"` (the topic id; for the old file `politics`, not `politics-sweden`), and two new `include` members. All keys are required; the lists may be empty, but at least one of the four include lists must not be (as the existing loader requires for its two). The loader accepts version 2 only; the version 1 politics file is migrated in F4.

| Key | Meaning |
|---|---|
| `include.words` | single words, `*` at the end for a prefix (as today) |
| `include.phrases` | new: two or more words in sequence, no `*`, lower case |
| `include.caseSensitive` | exact substrings such as `(SD)` (as today) |
| `include.caseSensitiveWords` | new: exactly one whole word with exact case, at least one letter, no `*`, NFC |
| `exclude.words`, `exclude.phrases` | as today |

- Matching order and validation: R17.3.
- Illustration of the AI list (F4 sets the final terms; the owner can ask for changes through issues):
```json
{
  "version": 2,
  "topic": "ai",
  "include": {
    "words": ["chatgpt", "openai", "chatbot*", "språkmodell*", "maskininlärning", "deepfake*"],
    "phrases": ["artificiell intelligens", "artificial intelligence", "machine learning",
                "language model", "language models"],
    "caseSensitive": [],
    "caseSensitiveWords": ["AI"]
  },
  "exclude": { "words": [], "phrases": [] }
}
```
- `KI` (Swedish short form of artificiell intelligens, also Karolinska Institutet) is left out of the first list on purpose (K16). For Natur, a prefix such as `natur*` is not used because it matches "naturligtvis"; F4 picks specific terms, for example `naturreservat*`, `nationalpark*` and `naturvård*`, and measures them (K15).

### 7.7 `news.json` version 2 (F5; D30)
```json
{
  "version": 2,
  "generatedAt": "2026-11-14T13:05:12Z",
  "generatedAtDisplay": "2026-11-14 14:05",
  "topics": ["all-news", "politics", "nature", "ai"],
  "sources": [
    {
      "id": "svt", "name": "SVT", "status": "ok", "lastSuccess": "2026-11-14T13:05:12Z", "itemCount": 31,
      "feeds": [
        { "topic": "all-news", "status": "ok", "lastSuccess": "2026-11-14T13:05:12Z", "itemCount": 20 },
        { "topic": "politics", "status": "ok", "lastSuccess": "2026-11-14T13:05:12Z", "itemCount": 11 },
        { "topic": "nature",   "status": "ok", "lastSuccess": "2026-11-14T13:05:12Z", "itemCount": 3 },
        { "topic": "ai",       "status": "ok", "lastSuccess": "2026-11-14T13:05:12Z", "itemCount": 2 }
      ]
    }
  ],
  "items": [
    {
      "id": "3f2a9c0d1b7e4a55", "sourceId": "svt", "sourceName": "SVT",
      "title": "Exempelrubrik om riksdagen",
      "url": "https://www.svt.se/nyheter/inrikes/exempel",
      "published": "2026-11-14T12:58:00Z", "publishedDisplay": "2026-11-14 13:58",
      "topics": ["all-news", "politics"]
    }
  ]
}
```
All headlines, URLs and counts are made up. A feed that fails has `"status": "error"`, the old `lastSuccess` and a `message` as in R6.3. Feed entries with the same address (here Alla nyheter, Natur and AI) share status, `lastSuccess` and `message`. The rules are in R19.

### 7.8 The reader's state in the browser, version 7 (F7)
- `localStorage["newsReader.selectedSources"]`: unchanged (list of source ids).
- `localStorage["newsReader.selectedTopic"]` (new): one topic id, for example `"nature"`. No label, no content (R18.3).
- `localStorage["newsReader.lastNews"]`: the last `news.json`, version 1 or 2, build sources only (R18.4).
- Browser-source items (Sveriges Radio, with their `topics`): in a JavaScript variable only (R7.3, D18).

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
| (Retired, D26) Published variant: scheduled build stops or is disabled after 60 days without activity | SVT part goes stale; warning after 3 hours | R8.3, K3 |
| Reader unticks every source | "Inga nyheter från valda källor." | R8.4 |
| One feed URL fails (for example SVT `inrikes`) while another works | Only the topics of that feed show old items (under 24 h) and status `error`; the other topics are current | R19.3, R19.4 |
| One URL serves several topics (SVT `nyheter/rss.xml`, Sveriges Radio program 83) | Fetched once; every topic is tested on the same response | R15.1, R15.3 |
| Same article in two feeds of one source | One item; topics joined | R13.5 |
| An item matches several topics (an AI item about nature) | Shown under each | R13.3, R18.2 |
| Chosen topic not offered by a source (Natur, Riksdagen) | The source contributes nothing; "Erbjuder inte ämnet Natur" | R13.7, R18.5 |
| Chosen topic not offered by any chosen source | "Valda källor erbjuder inte ämnet <Ämne>." | R18.6 |
| Chosen topic has no items | "Inga nyheter i ämnet <Ämne> från valda källor." | R18.6 |
| Saved topic missing, unknown or unreadable | Politik (until F8, Q8) | R18.3 |
| Saved `lastNews` is version 1 | Items read with the topics Alla nyheter and Politik | R18.4 |
| Saved `lastNews` has another version | Not used, as if no copy was saved | R18.4, R8.2 |
| Short AI term inside another word or name (AIK, Ai Weiwei) | No match: `AI` is a case-sensitive whole word | R17.3, K16 |
| Riksdag description with HTML or escaped text | Never shown; cleaned only for the keyword match | R16.2, N1 |
| Riksdag time offset looks wrong in winter | Q6 decides; until then the offset is read as given | R16.7, Q6 |
| Riksdagen switched on without the credit text on the page | Must not happen: the source stays `enabled: false` until F7 | R16.9 |
| Riksdag API down or changes format | Failed fetch, handled like SVT | R6.2, R11.1 |
| Riksdag item whose link is on `data.riksdagen.se` or another riksdagen.se host | Dropped; only `www.riksdagen.se` links are kept | R16.2 |
| Old saved choice when Riksdagen is switched on (F7) | `riksdagen` added once; unticking it later stays | R18.4, R16.9 |
| `sources.json` of version 1 given to version 2 code | Refused with a clear message; the build fails | R14.6 |

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
`tests/shared-cases.json` holds input and expected output in three sections created empty in S2 (version 7 adds `input.topic` and the section `topics`, R17.4): headline cleaning (filled in S4), time display including summer and winter time (filled in S5), and keyword matching including the exclude words and phrases and Swedish letters (filled in S6). The Python tests of each step read it from the start, and `node --test` reads all of it in S9, so the two implementations cannot drift apart without a failing test (R4.5).

### Additions for topics (F3 to F8)
- **F3 (pytest, node --test):** `test_sources.py` checks R14 with the real file and small invalid copies: wrong version, missing `feeds`, unknown topic, two entries for one topic, `keywordFilter` on `all-news`, a build-source feed on another host, a bad `keywords` name (`/`, `..`, wrong form, not `<id>-keywords.json`), `linkHosts` not on `allowedHosts`, `matchOn` with `feed`, a version 1 file (R14.6). It checks only the name of the keyword files, not that they exist (R14.1). Node tests for `validateSources` (version 2 read, version 1 refused) and for `selectItems` with the new source shape, and a test that the page's list is unchanged (R14.7).
- **F4 (pytest and node --test):** shared cases for each topic: `keywords` cases with `input.topic` for Politik, Natur and AI (Swedish and English terms, `AI` against `AIK`, `Ai Weiwei`, `AI-regler`, `FAIR`, multi-word terms, upper and lower case, phrase with an exclude phrase around it), loader validation of the new term kinds (R17.3), and `topics` cases for the function of R13.4 (several topics for one item, one topic, `all-news` only).
- **F5 (pytest, node --test):** build tests with fake feeds: the same URL used by three topics is fetched once (the fake fetch counts feed requests, robots.txt excluded, R15.1); an item in two feeds becomes one item with joined topics (R13.5); the cap per source and topic, also after previous items are added (R13.6, R19.4); `news.json` version 2 shape (R19.1 to R19.3, including worst status and message); one failing URL keeps only its topics from the previous file (R19.4); a previous file of version 1; a blocked host marks all feed entries that use it (R15.2); every named keyword file exists and is valid, a missing or invalid one fails the build (R14.5, R17.5). Node tests for `validateNews` reading version 1 and 2, politics only until F7, and a saved version 1 copy shown whole (R19.8).
- **F6 (pytest):** a hand-written RSS sample in the Riksdag shape (made-up titles; `+0200` dates in winter; an escaped `description`; an author element; a `guid` and a link on `data.riksdagen.se`): only the `www.riksdagen.se` link is kept, `description` is not used for matching (an AI word only in the description gives no AI hit) and never reaches `news.json`, the three feed entries cost one feed request, and the real file has the entry `enabled: false` (R16.9).
- **F7 (node --test, by hand):** the pure parts of the topic choice (reading, default and migration of the saved choice including the one-time `riksdagen` addition, filtering by membership, notices, `lastNews` version 1 and 2) are tested with plain objects; the F6 test on `enabled` now checks `true`. By hand: the choice survives a reload; switching topic causes no request; Riksdagen shows the credit text, the no-connection line and no logo; old keys set in the developer tools (`selectedSources` only; a `lastNews` of version 1); "Visas inte än" on the Sveriges Radio row; the first build against the real Riksdag feed, with the check of titles, links and times (R16.9).
- **F8 (node --test, by hand):** one request to `api.sr.se` serves all four topics (also checked in the Network tab); an unticked source causes no request and no keyword-file fetch, ticking it does (R15.3); no Sveriges Radio headline is stored (the storage and console checks above). The keyword files are same-origin, so R8.6 and any content security policy need no change.
- Test samples stay hand-made and made up; no Riksdag, SVT or Sveriges Radio text is copied.

### Running the tests
- Locally: `bash scripts/check.sh applications/news-reader` for Python, and `node --test applications/news-reader/site/tests/` for JavaScript.
- In the required check `checks`: the owner adds three steps to `ci.yml` (install requirements, `python -m pytest` in `applications/news-reader`, `node --test applications/news-reader/site/tests/`) and updates the copy in `GitRequirements/` (S3).

### By hand (owner)
- Local variant (after S10 and S11): run the build and the local server, then check list order; the link opens in a new tab; choosing and unchoosing sources; reload keeps the choice; private window; offline (SVT from the saved copy, Sveriges Radio not shown, the right notices); stale warning (edit `generatedAt`); 360 px width; Swedish letters; the source name on every Sveriges Radio item; the bottom line.
- Storage check: in the browser's developer tools, Application tab, no Sveriges Radio headline appears in local storage, session storage, IndexedDB, cookies or Cache Storage, and no service worker is registered. The Console shows no Sveriges Radio headline, also after a forced failure (for example offline, or a blocked `api.sr.se` request in the Network tab).
- Call check: in the Network tab, one request to `api.sr.se` on page load; "Uppdatera" within 5 minutes makes no new request; a hidden tab makes no requests.
- Keyword quality: read the live list for obvious false positives and missing politics news. For Sveriges Radio this is done only by reading the live page; no copy is saved (N10).
- Published variant (S13): retired with D26; not done.

## 10. Risks and open questions

### 10.1 Risks

| # | Risk | Handling |
|---|---|---|
| K1 | (Retired, D26: no published variant.) svt.se may block or rate-limit GitHub runners (published variant). | Seen as `error`; then fewer runs or local only. |
| K2 | A feed changes address or format. | Status in "Källor" and the stale warning; fix by issue. |
| K3 | (Retired, D26.) Published variant: scheduled workflows in public repositories are disabled after 60 days without activity. | Stale warning; owner re-enables. |
| K4 | (Retired, D26.) Scheduled runs can be delayed. | Accepted; the warning uses 3 hours. |
| K6 | The keyword filter is approximate: false positives (another country's government in Sveriges Radio's mixed feed; a passing mention in SVT) and false negatives (a headline naming only a person). | Note on the page (R4.6); exclude terms; list maintained through issues. |
| K7 | SVT's robots.txt says `ai-train=no`. | Nothing is trained (N9); test samples are hand-written. |
| K8 | Sveriges Radio's terms. **Resolved for the design**: read by the manager (section 4.3); the design answers each term (no storage, live fetch, no modification, source named, few calls, no ads, no training). | Keep the table in section 4.3 up to date when the terms change (K9). |
| K9 | Sveriges Radio's terms may change. | The owner re-reads `https://sverigesradio.se/artikel/api-villkor` before any change to the page and, since the page is not published (D26), before every step that changes what is shown from Sveriges Radio (F8) and when the terms are reported to have changed; `enabled: false` if needed. |
| K10 | Sveriges Radio's open API is no longer maintained and may stop or change. | The page keeps working with SVT (R7.6); the source is disabled if it stays broken. |
| K11 | (Retired, D26: the owner chose local only; safeguards R12.3, R8.9 and the ignored `build/` stay.) **Public visibility.** The owner only reads, but in the published variant the page and `news.json` are on public GitHub Pages of a public repository, so the headline list is publicly visible to anyone with the address, whatever the intent. `noindex` (R8.9) asks search engines not to list it, but does not hide it. | **Owner decision (Q1):** do not publish and run locally only (recommended), or publish and accept that it is public. |
| K12 | **SVT derived copy.** `news.json` stores SVT headlines and links: a derived copy, on the owner's computer in the local variant and publicly on Pages in the published variant. SVT's terms beyond robots.txt have not been read. | Step S1 reads SVT's terms before anything is published; if storing is not allowed, SVT cannot be used (it has no CORS header for a live fetch, section 2.4). Version 7: **the risk has grown**: the copy now holds up to 20 items per topic from the whole SVT news feed, not only politics, plus Riksdagen items. The owner accepted storing headlines and links on 2026-11-13; the widening needs the owner's confirmation (Q11, before F5). Step S1 found no published SVT terms (reported by the manager). |
| K13 | (Retired, D26: local use.) Sveriges Radio's terms speak of reception in Sweden. A published page can be opened from abroad. | Not an issue in the local variant; part of Q1. |
| K14 | The Python and JavaScript rules could drift apart. | Shared keyword file and shared test cases (R4.3, R4.5). |

| K15 | **Keyword quality per topic (Politik, Natur).** A list is approximate. Natur: a prefix such as `natur*` matches "naturligtvis" and "naturgas"; general words such as "miljö" or "djur" match much that is not about nature. Politik: K6 stays. | Specific terms and exclude words and phrases; F4 measures each list on made-up shared cases, and F5 and the owner read the live lists; lists change through issues. The note of R4.6 and R18.5 is shown for every keyword topic. |
| K16 | **AI keywords.** "AI" is short and has other meanings (Ai Weiwei, the pinyin and Italian "ai", Amnesty International, the team AIK, "FAIR"); the Swedish short form "KI" is also Karolinska Institutet; Swedish and English terms must both be covered (D23); a case-insensitive match on "ai" would give many false hits; a case-sensitive substring match would hit "AIK" and "FAIR". | `AI` is a case-sensitive whole word (R17.3); `KI` is left out of the first list; multi-word terms are phrases; English terms are listed next to Swedish ones; shared cases contain the false-hit examples; a headline written in capitals can give a false hit and is accepted. |
| K17 | **Riksdagen terms and credit.** The service must give the credit text and must not imply that the Riksdag stands behind it; no logo, no images; whether storing headlines is allowed is not yet checked by the worker. | R16.5, R16.8 and R16.9: terms read again before F6; the source stays `enabled: false` until the credit text is on the page (F7); the owner checks the wording by hand. |
| K18 | **Riksdag feed facts.** About 365,000 hits; motions are many and have very short titles (Q5); the `+0200` offset in November (Q6); allowed call frequency not stated; the API is not ours. | `sz=50`; the 2 MB limit; document types per Q5; one call per run, by hand; Q6 settled in F6; a changed feed is a failed fetch (R6.2). |
| K19 | **More requests and a larger derived copy (see also K12, Q11).** Several feeds per source mean more addresses; `news.json` holds up to 20 items per source and topic, so also SVT headlines that are not politics. | One request per distinct address (R15); robots.txt per host (R6.6); the local-only use (D26) and K12 stay. |
| K20 | **Old saved state.** A reader's browser can hold `selectedSources`, a `lastNews` of version 1 and no topic. | R18.3 and R18.4 (including the one-time addition of `riksdagen` to a saved choice) with tests of the pure parts and a hand check with old keys set in the developer tools. |

K5 (DN's terms) was removed when DN was dropped (D12); the other numbers are kept so that earlier references stay valid.

### 10.2 Remaining open questions

| # | Question | Proposed way to settle it |
|---|---|---|
| Q1 | Publish on GitHub Pages, or run locally only? (K11, K12, K13) | **Closed 2026-11-14 by D26: local only, no publishing.** |
| Q2 | Which host do SVT's item links use, and do SVT items carry categories? | Manager or owner looks at the feed in S1. |
| Q3 | Which `category` values do Sveriges Radio's entries carry, and could they replace the keyword filter? | Manager or owner looks at the feed (S14). |
| Q4 | GitHub settings (Pages source, Actions permissions, `github-pages` environment). | **Closed 2026-11-14 by D26:** S12 is not done. |
| Q5 | **Open decision for the owner (from F1):** which Riksdag document types? `prop` (propositions), `bet` (committee reports) and `mot` (motions). The F1 call used `prop,mot,bet`; motions are by far the most numerous and have very short titles. | **Manager proposal, awaiting the owner:** `prop` and `bet` only; motions can be added later through an issue. F6 starts with `prop,bet` unless the owner says otherwise before F6 is taken. |
| Q6 | Riksdag time: `pubDate` has the offset +0200 also in November, when Stockholm time is +01:00. Trust the offset, read the clock part as Europe/Stockholm time for this source, or use `systemdatum` of the JSON form (a second call)? | Manager or owner compares one real `pubDate` with the JSON `systemdatum` by hand **before F6 is taken** (R16.7). If the offset is wrong, F6 reads the clock part as Stockholm time for this source only (an optional source-level field, R14.2, no second call); otherwise it trusts the offset. |
| Q7 | Does SVT have its own nature or science feed (unconfirmed)? | Manager or owner looks in a browser (workers cannot reach svt.se). If found, the Natur or AI entry of SVT changes to method `feed` through an issue. Not blocking: keywords on `nyheter/rss.xml` are used meanwhile (D31). |
| Q8 | Which topic is chosen the first time, and for readers with only old saved choices? | **Manager proposal:** Politik until F8, which keeps the page as it was (R18.3); after F8 the owner decides whether the default becomes Alla nyheter (one word in R18.3 and one test). Open. |
| Q9 | Riksdagen: the display name "Riksdagen" (R16.1), the line "Sidan har inget samband med Sveriges riksdag." (R16.5) and `storageAllowed: true` (R16.8). | **Manager proposal:** keep name and line as written; the owner confirms them in the hand test of F7. If R16.8 finds that storing is not allowed, Riksdagen is out (section 2.4) and F6 is closed. |
| Q10 | Should F3 and F5 be `no-auto-merge`? They change page code (`validateSources`, `selectItems`, `validateNews`) although the reader should see no change. | **Manager recommendation:** keep auto-merge only if the page behaviour is unchanged and proved by tests (R14.7, R19.8); otherwise `no-auto-merge`. Owner decides. |
| Q11 | Does the owner accept storing SVT headlines and links for all news topics (up to 20 per topic from `nyheter/rss.xml`, K12), now that S1 found no published SVT terms (reported by the manager)? The owner accepted the storing of headlines and links on 2026-11-13. | The owner answers before F5 is taken; if not accepted, F5 keeps SVT to politics. |

### 10.3 What was checked about hosting in the repository (kept as a record; not needed after D26)
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
| D8 | 20 items per source, 7 days, headlines never cut; build every 30 minutes (published variant); page refresh every 10 minutes while visible; Sveriges Radio at most once per 5 minutes; stale warning after 3 hours. From F5 the cap is per source and topic (R13.6); the parts about publishing are retired (D26). | Worker, recommended |
| D9 | A publishing workflow, if any, never commits to `main`. (Moot after D26.) | Worker, recommended |
| D10 | Design principle: a few approved sites, listed in `sources.json` in the repository and approved by the owner; visitors cannot add sources. | Owner |
| D11 | Omni was removed from the design. | Owner |
| D12 | DN was dropped. | Owner |
| D13 | Regeringen.se and Riksdagen are out of scope for now. **Superseded in part by D24 (Riksdagen is a source) and D25 (Regeringen.se stays out).** | Owner |
| D14 | The repository is public. | Owner |
| D15 | The page text and the news are in Swedish. | Owner |
| D16 | Everything lives in `applications/news-reader/`; a published page uses the same path (the published part is retired, D26). | Owner |
| D17 | Sveriges Radio is a source through the Ekot Atom feed `https://api.sr.se/api/rss/program/83`, named "Sveriges Radio"; the episode API and the stale "Toppnyheter" feed are not used. | Owner (via manager) |
| D18 | Sveriges Radio material is never stored: fetched live in the browser, kept in memory only. | Owner (via manager), from Sveriges Radio's terms |
| D19 | The owner checks GitHub's Pages and Actions settings before the Pages step. (Retired, D26.) | Owner |
| D20 | The owner's use is reading only, not sharing. | Owner |
| D21 | Topics, in this order, with ids and Swedish labels: `all-news` "Alla nyheter", `politics` "Politik", `nature` "Natur", `ai` "AI". Supersedes N2. | Owner, 2026-11-14 |
| D22 | One topic choice on the page. One item can match several topics, so the choice filters by membership of the topic. | Owner, 2026-11-14 |
| D23 | AI keywords are in Swedish and in English. | Owner, 2026-11-14 |
| D24 | Sources: SVT, Sveriges Radio (only the Ekot feed, program 83, `https://api.sr.se/api/rss/program/83`) and Riksdagen's open data. Riksdagen has Alla nyheter, Politik and AI, but not Natur. Supersedes D13 for Riksdagen. | Owner, 2026-11-14 |
| D25 | Not used at all: Göteborgs-Posten, Altinget, Aftonbladet, Expressen, SvD, Sydsvenskan, Di, DN, Omni and Regeringen.se (N14). | Owner, 2026-11-14 |
| D26 | Local use only, no publishing. Steps S12 and S13 are dropped. | Owner, 2026-11-14 |
| D27 | Sveriges Radio is used through program 83 for all four topics (D17 stays). | Owner, 2026-11-14 |
| D28 | `sources.json` version 2: a `topics` list and, for each source, a `feeds` list with `topic`, `method` and `url`; an optional `credit` (R14). | Manager proposal, 2026-11-14 |
| D29 | Each distinct feed URL is fetched once, in the build and in the browser; the topics are tested on the same response (R15). | Manager proposal, 2026-11-14 |
| D30 | `news.json` version 2: `topics` per item and as a list, status per feed, the cap per source and topic, the 24-hour fallback per feed (R13.6, R19). | Manager proposal, 2026-11-14 |
| D31 | SVT feeds: Alla nyheter `https://www.svt.se/nyheter/rss.xml` without filter; Politik `https://www.svt.se/nyheter/inrikes/rss.xml` with keywords (as today); Natur and AI `nyheter/rss.xml` with keywords, because SVT's own feeds are unconfirmed (Q7). | Manager proposal, 2026-11-14 |
| D32 | Page: section "Ämnen" with a single choice, saved as one topic id in `newsReader.selectedTopic`; old saved choices keep working; first choice Politik until F8 (Q8) (R18). | Manager proposal, 2026-11-14 |
| D33 | Keyword files `politics-keywords.json` (kept), `nature-keywords.json`, `ai-keywords.json`; new term kinds `include.phrases` and `include.caseSensitiveWords`; AI risks in K16 (R17). | Manager proposal, 2026-11-14 |
| D34 | Riksdagen: Politik by the feed itself, AI by keywords; credit text "Källa: Sveriges riksdag"; no logo, no images, description never read or shown; the source stays `enabled: false` until the credit text is on the page; document types per Q5 (R16). | Manager proposal, 2026-11-14 |
| D35 | Unchanged: Sveriges Radio items in memory only (D18, R7.3) for all topics; robots.txt rule, 2 MB limit, 24-hour fallback and the call limits of R7.2. SVT: the owner accepted storing headlines and links on 2026-11-13 (earlier decision); widening it to all news topics (20 items per topic from the whole news feed) is not yet confirmed by the owner (Q11, K12). | Manager proposal, 2026-11-14 (no change in behaviour except the open widening) |
| D36 | Consequences of D26: goal G4, requirements R6.1 (published part) and R12.2, steps S12 and S13, questions Q1 and Q4, decisions D9, D16 (published part) and D19, and risks K1, K3, K4, K11 and K13 are retired; they stay in the text with a pointer so that references remain valid. Safeguards for local use: `build/` is not committed (R12.1), the server is bound to 127.0.0.1 (R12.3), the page keeps `noindex` (R8.9), Sveriges Radio items are never stored (D18). | Manager proposal, 2026-11-14 |

## 12. Step plan

Each step is meant to become one issue. Version 7 adds the steps F1 to F8 (with their issue numbers) after S14. Levels are from WORKFLOW.md section 1. "Owner only" and "Manager or owner" steps cannot be done by a worker (GitHub settings, workflow files, or a browser that can reach the news sites).

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
| S12 | **Dropped 2026-11-14 by the owner (D26).** Was: check GitHub Settings > Pages and > Actions (Q4), set the Pages source, and add `.github/workflows/news-reader.yml` with its copy in `GitRequirements/` | – | – | – | R6.1, R12.2, Q4 (all retired) |
| S13 | **Dropped 2026-11-14 by the owner (D26).** Was: test the live page and two scheduled runs | – | – | – | Section 9 (published variant, retired) |
| S14 | **Manager or owner, optional:** list the `category` values of the Sveriges Radio feed; if they mark Swedish politics, open an issue to switch to `categoryFilter` | Low | no (no pull request) | none | Q3 |
| F1 (#87) | **Manager or owner (done):** check Riksdagen's open data (feed, fields, terms, robots.txt) and report the facts in a comment on the issue | Low | no (no pull request) | none | Section 4.6, Q5, Q6, K17, K18 |
| F2 (#88) | Design update (this document): topics, several feeds per source, Riksdagen's open data, no publishing | Medium | no | F1 | R13 to R19 written; D21 to D36; K15 to K20; Q5 to Q11; this step plan |
| F3 (#89) | News reader: `sources.json` version 2 with `topics` and `feeds` per source (SVT and Sveriges Radio entries as in section 7.5, no Riksdagen yet); validation in `build.py` and in `app.js` (name rule of the keyword files only, not their existence); the build and `selectItems` read the feed entry of the topic `politics`; the page behaves as before, proved by tests | Medium | open (Q10) | F2 | R13.1, R13.2 (configuration), R14.1 to R14.4, R14.5 (name rule), R14.6, R14.7, R3.1, R4.1, R4.2, R6.4 (`sources.json` part) |
| F4 (#90) | News reader: `nature-keywords.json` and `ai-keywords.json`; `politics-keywords.json` version 2; generalised matching (`include.phrases`, `include.caseSensitiveWords`, one list per topic) in `keywords.py` and `site/logic.js`; shared cases per topic and the section `topics`; the function that returns all topics of an item, in Python and JavaScript | Medium | no | F2 | R4.3, R4.4, R4.5, R13.4, R17.1 to R17.4, K15, K16 |
| F5 (#91) | News reader: `news.json` version 2 (topics per item and as a list, status per feed), the SVT feeds of section 7.5, one fetch per distinct URL, the fallback per feed (version 1 files still read), the check that every named keyword file exists and is valid; the page reads version 1 and 2 and shows politics only until F7 | **High** | open (Q10) | F3, F4, and Q11 answered | R1.5 (build), R13.3, R13.5, R13.6, R13.7 (build), R14.5 (existence and copy), R15.1, R15.2, R17.5, R19.1 to R19.6, R19.8, R5.1, R5.3, R6.2, R6.3, R6.4 (keyword part), K19 |
| F6 (#92) | News reader: Riksdagen's open data as a build source: the entry (with `credit`, `linkHosts`, `matchOn`, `enabled: false`), the exact link host rule, tests with a hand-written sample, robots.txt of the feed host. Before F6 is taken, a manager or owner step settles R16.8 (terms), the robots.txt of `www.riksdagen.se`, Q5 and Q6 | High | no | F1, F3, F5 | R9.1 (`linkHosts`), R16.1 to R16.4, R16.6, R16.7, R16.8 (recorded), R16.9 (disabled part), K17, K18 |
| F7 (#93) | News reader: the page: section "Ämnen" for build sources, the saved topic (default Politik) with old saved choices still working and the one-time addition of `riksdagen`, notices, rows in "Källor" ("Visas inte än" for Sveriges Radio), the credit text, Riksdagen switched on (`enabled: true`, the F6 test changed), texts of R18.8, README server command (R12.3); the owner checks the first real Riksdag build | Medium | **yes** (user-visible; the owner tests by hand per section 9) | F5, F6 | R16.5, R16.9 (switch-on), R18.1 to R18.9, R3.3, R3.5, R4.6, R8.2, R8.3, R8.4, R8.7, R12.3 |
| F8 (#94) | News reader: Sveriges Radio with several topics from one request in the browser (`app.js`, `logic.js`); items in memory with `topics`; no request for an unticked source; the default topic is decided by the owner (Q8) | Medium | **yes** (user-visible; the owner repeats the storage, console and call checks of section 9) | F4, F7 | R1.2, R1.5 (page), R7.2, R7.4, R13.3 and R13.7 (page), R15.3, R19.7, R18.2 (browser items), R18.9 (removed) |

Notes:
- Publishing was dropped (D26): S12 and S13 are not done and stay in the table so that references remain valid. The plan continues with F3 to F8, then the owner's hand tests.
- F3 and F4 can be done in parallel after F2: F3 checks only the name of the keyword files, so it does not need the files of F4. F5 needs both, and Q11. F6 needs F5 (and the facts of F1). F7 needs F5 and F6. F8 needs F4 and F7.
- The reader sees no change until F7 (topics): after F3 to F6 the page still shows politics only. F8 completes the topics for Sveriges Radio. F6 leaves Riksdagen switched off so that no Riksdagen item is shown without its credit text (R16.9).
- Levels (changed by the manager after review): F5 is **High** (build, news file and page code change together); the manager updates the label of issue #91. F6 is High because of the unchecked terms and time question. F3 to F8 change what the build writes or what the page reads, so Q10 asks whether F3 and F5 should be `no-auto-merge`.
- The manager step before F6 (R16.8, the robots.txt of `www.riksdagen.se`, Q5, Q6) is not a pull request.
- S2 depends on S1 because `storageAllowed` and `allowedHosts` for SVT come from S1.
- S2 creates `tests/shared-cases.json` with empty sections, so S4 and S5 can fill their sections in parallel; S6 fills the keyword section; S9 runs all of it in JavaScript.
- S8 and S9 can be done in parallel after S6 (S8 also needs S7).
- The `id` (R5.4) and the final item shape (R1.1) belong to S7; S4 only produces raw entries.
- S3 should follow S2 directly. Until it is done, each worker runs the Python and Node tests locally and says so in the report.
- Every requirement in section 3 is listed in the "Covers" column of at least one step.
