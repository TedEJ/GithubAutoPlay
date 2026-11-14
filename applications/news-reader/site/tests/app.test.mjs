import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import app from "../app.js";

const SITE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.join(SITE, "..");
const realSources = JSON.parse(fs.readFileSync(path.join(ROOT, "sources.json"), "utf8"));

const NOW = Date.parse("2026-11-13T13:30:00Z");
// The project's own sources.json has Riksdagen switched off (owner decision D41, certificate chain problem).
// The tests of the Riksdagen code paths use a copy with the entry enabled.
const riksdagenOn = JSON.parse(JSON.stringify(realSources));
riksdagenOn.sources.find((s) => s.id === "riksdagen").enabled = true;
const SOURCES = app.validateSources(realSources);
const SOURCES_ON = app.validateSources(riksdagenOn);
const SVT = SOURCES.find((s) => s.id === "svt");

function newsFile(overrides = {}) {
  return {
    version: 1,
    generatedAt: "2026-11-13T13:05:12Z",
    generatedAtDisplay: "2026-11-13 14:05",
    category: "politics-sweden",
    sources: [{ id: "svt", name: "SVT", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 2 }],
    items: [
      {
        id: "x", sourceId: "svt", sourceName: "SVT", title: "Äldre rubrik om riksdagen",
        url: "https://www.svt.se/nyheter/inrikes/a", published: "2026-11-13T11:00:00Z",
        publishedDisplay: "bogus",
      },
      {
        id: "y", sourceId: "svt", sourceName: "SVT", title: "Nyare rubrik om regeringen",
        url: "https://www.svt.se/nyheter/inrikes/b", published: "2026-11-13T12:58:00Z",
        publishedDisplay: "bogus",
      },
    ],
    ...overrides,
  };
}

// ---------------------------------------------------------------- sources

test("validateSources keeps enabled sources and only the fields the page uses", () => {
  assert.deepEqual(SOURCES.map((s) => s.id), ["svt", "sveriges-radio"]); // Riksdagen is off in the real file (D41)
  assert.deepEqual(SOURCES_ON.map((s) => s.id), ["svt", "sveriges-radio", "riksdagen"]);
  assert.deepEqual(Object.keys(SVT).sort(), ["allowedHosts", "feeds", "fetchedBy", "id", "name"]);
  assert.equal("method" in SVT, false, "no method of its own any more");
  const off = JSON.parse(JSON.stringify(riksdagenOn));
  off.sources[1].enabled = false;
  assert.deepEqual(app.validateSources(off).map((s) => s.id), ["svt", "riksdagen"]);
});

test("validateSources: the real Riksdagen entry is switched off (D41) and left out; an enabled copy is read", () => {
  const raw = realSources.sources.find((s) => s.id === "riksdagen");
  assert.equal(raw.enabled, false);
  assert.equal(SOURCES.some((s) => s.id === "riksdagen"), false);
  assert.deepEqual(raw.linkHosts, ["www.riksdagen.se"]);
  assert.equal(raw.timeZone, "Europe/Stockholm");
  assert.deepEqual(app.validateSources(riksdagenOn).map((s) => s.id), ["svt", "sveriges-radio", "riksdagen"]);
  const riksdagen = SOURCES_ON.find((s) => s.id === "riksdagen");
  // Only the fields the page uses: the topics with their methods and the credit text, but no
  // linkHosts, timeZone or address; a build source has no address.
  assert.deepEqual(Object.keys(riksdagen).sort(), ["allowedHosts", "credit", "feeds", "fetchedBy", "id", "name"]);
  assert.equal(riksdagen.fetchedBy, "build");
  assert.equal(riksdagen.credit, "Källa: Sveriges riksdag");
  assert.deepEqual(riksdagen.feeds, [
    { topic: "all-news", method: "feed" }, { topic: "politics", method: "feed" },
    { topic: "ai", method: "keywordFilter", matchOn: "title" }]); // no Natur (D24); matchOn is kept for F8
  assert.deepEqual(riksdagen.allowedHosts, ["riksdagen.se"]);
});

test("validateSources rejects unusable files", () => {
  for (const bad of [null, [], "x", {}, { version: 3, sources: [] }, { version: 2, sources: [] },
    { version: 2, sources: [{ id: 1 }] }, { version: 2, sources: "x" }]) {
    assert.equal(app.validateSources(bad), null);
  }
});

// sources.json version 2 (F3, R14.7): hand-written samples, not the real file.
const TOPICS = [
  { id: "all-news", label: "Alla nyheter" },
  { id: "politics", label: "Politik", keywords: "politics-keywords.json" },
  { id: "nature", label: "Natur", keywords: "nature-keywords.json" },
  { id: "ai", label: "AI", keywords: "ai-keywords.json" },
];
const ALL = "https://build.example.invalid/all.xml";
const POL = "https://build.example.invalid/politics.xml";
const LIVE = "https://live.example.invalid/feed";
const v2File = (extra = {}) => ({
  version: 2,
  topics: TOPICS,
  sources: [
    { id: "b", name: "Build", enabled: true, fetchedBy: "build", storageAllowed: true,
      homepage: "https://build.example.invalid/", allowedHosts: ["example.invalid"],
      feeds: [
        { topic: "all-news", method: "feed", url: ALL },
        { topic: "politics", method: "keywordFilter", url: POL },
        { topic: "nature", method: "keywordFilter", url: ALL },
        { topic: "ai", method: "keywordFilter", matchOn: "title", url: ALL },
      ], ...extra },
    { id: "l", name: "Live", enabled: true, fetchedBy: "browser", storageAllowed: false,
      homepage: "https://live.example.invalid/", allowedHosts: ["example.invalid"],
      feeds: TOPICS.map((t) => ({ topic: t.id, method: t.id === "all-news" ? "feed" : "keywordFilter", url: LIVE })) },
  ],
});

test("validateSources reads version 2: the politics feed entry gives the method and, for a browser source, the address", () => {
  const got = app.validateSources(v2File());
  const feeds = [{ topic: "all-news", method: "feed" }, { topic: "politics", method: "keywordFilter" },
    { topic: "nature", method: "keywordFilter" }, { topic: "ai", method: "keywordFilter" }];
  const withTitle = (list) => list.map((f) => (f.topic === "ai" ? { ...f, matchOn: "title" } : f));
  assert.deepEqual(got, [
    { id: "b", name: "Build", fetchedBy: "build", allowedHosts: ["example.invalid"], feeds: withTitle(feeds) },
    { id: "l", name: "Live", fetchedBy: "browser", allowedHosts: ["example.invalid"], url: LIVE,
      feeds },
  ]);
});

test("validateSources: the order of the feed entries does not matter, other topics are not read", () => {
  const data = v2File();
  data.sources[0].feeds.reverse();
  data.sources[0].feeds.find((f) => f.topic === "nature").method = "categoryFilter";
  assert.equal("method" in app.validateSources(data)[0], false);
  assert.deepEqual(app.validateSources(data)[0].feeds.map((f) => f.topic), ["all-news", "politics", "nature", "ai"]);
});

test("validateSources accepts credit, linkHosts and matchOn without showing them", () => {
  const data = v2File({ credit: "Källa: Exempel", linkHosts: ["www.example.invalid"] });
  const got = app.validateSources(data);
  assert.equal(got.length, 2);
  assert.deepEqual(Object.keys(got[0]).sort(), ["allowedHosts", "credit", "feeds", "fetchedBy", "id", "name"]);
  assert.equal(got[0].credit, "Källa: Exempel");
  assert.equal("linkHosts" in got[0], false);
});

test("validateSources refuses version 1 (R14.6, R14.7)", () => {
  const v1 = { version: 1, sources: [{ id: "b", name: "Build", enabled: true, fetchedBy: "build",
    allowedHosts: ["example.invalid"], "politics-sweden": { method: "keywordFilter", url: POL } }] };
  assert.equal(app.validateSources(v1), null);
  for (const version of ["2", 2.5, null, undefined, 0]) assert.equal(app.validateSources({ ...v2File(), version }), null);
});

test("validateSources: a source without a politics entry still has its other feeds; entries without a method text are ignored", () => {
  const data = v2File();
  data.sources[0].feeds = data.sources[0].feeds.filter((f) => f.topic !== "politics");
  data.sources[1].feeds = data.sources[1].feeds.filter((f) => f.topic !== "politics");
  const [b, l] = app.validateSources(data);
  assert.equal(b.feeds.some((f) => f.topic === "politics"), false);
  // F8: the address is the one address of all the feed entries, so it stays without a politics entry.
  assert.equal(l.url, LIVE);
  for (const feeds of [undefined, null, "x", [], [null, 5, { topic: "politics" }]]) {
    const copy = v2File();
    copy.sources[0].feeds = feeds;
    assert.deepEqual(app.validateSources(copy)[0].feeds, []);
  }
});

test("validateSources: the real file gives SVT and Sveriges Radio as before F3, with their topics, and nothing else", () => {
  const all = [{ topic: "all-news", method: "feed" }];
  assert.deepEqual(SOURCES, [
    { id: "svt", name: "SVT", fetchedBy: "build", allowedHosts: ["svt.se"],
      feeds: [...all, { topic: "politics", method: "keywordFilter" }, { topic: "nature", method: "keywordFilter" },
        { topic: "ai", method: "keywordFilter" }] },
    { id: "sveriges-radio", name: "Sveriges Radio", fetchedBy: "browser", allowedHosts: ["sverigesradio.se"],
      url: "https://api.sr.se/api/rss/program/83",
      feeds: [...all, { topic: "politics", method: "keywordFilter" }, { topic: "nature", method: "keywordFilter" },
        { topic: "ai", method: "keywordFilter" }] },
  ]);
});

test("readTopicList: the known topics in the order of R13.1 with their labels, nothing else", () => {
  assert.deepEqual(app.readTopicList(realSources).map((t) => t.id + "=" + t.label),
    ["all-news=Alla nyheter", "politics=Politik", "nature=Natur", "ai=AI"]);
  const messy = { topics: [{ id: "ai", label: "AI" }, { id: "sport", label: "Sport" }, { id: "politics" },
    { id: "all-news", label: "Alla" }, null, 5] };
  assert.deepEqual(app.readTopicList(messy), [{ id: "all-news", label: "Alla" }, { id: "ai", label: "AI" }]);
  for (const bad of [null, [], "x", {}, { topics: "x" }]) assert.deepEqual(app.readTopicList(bad), []);
});

test("joinNames and the bottom line come from the source names", () => {
  assert.equal(app.joinNames(["SVT"]), "SVT");
  assert.equal(app.joinNames(["A", "B"]), "A och B");
  assert.equal(app.joinNames(["A", "B", "C"]), "A, B och C");
  assert.equal(
    app.bottomLine(SOURCES),
    "Rubriker och länkar från SVT och Sveriges Radio. Klicka för att läsa hos källan.");
  assert.equal(
    app.bottomLine(SOURCES_ON),
    "Rubriker och länkar från SVT, Sveriges Radio och Riksdagen. Klicka för att läsa hos källan.");
});

// ---------------------------------------------------------------- news.json

test("validateNews returns a clean copy and recomputes time, name and id", () => {
  const news = app.validateNews(newsFile(), SOURCES, NOW);
  assert.equal(news.generatedAtDisplay, "2026-11-13 14:05");
  assert.equal(news.items.length, 2);
  const item = news.items[1];
  assert.deepEqual(Object.keys(item).sort(),
    ["id", "published", "publishedDisplay", "sourceId", "sourceName", "title", "topics", "url"]);
  assert.deepEqual(item.topics, ["all-news", "politics"]); // a version 1 item was a politics headline (R18.4)
  assert.equal(news.version, 2);
  assert.equal(item.publishedDisplay, "2026-11-13 13:58");
  assert.match(item.id, /^[0-9a-f]{16}$/);
  assert.notEqual(item.id, "y");
  // Idempotent: a clean copy validates to itself (it is what is saved).
  assert.deepEqual(app.validateNews(JSON.parse(JSON.stringify(news)), SOURCES, NOW), news);
});

test("validateNews never reads extra fields (N1)", () => {
  const data = newsFile();
  data.items[0].description = "Brödtext";
  data.items[0].image = "https://example.invalid/x.png";
  const news = app.validateNews(data, SOURCES, NOW);
  assert.ok(!("description" in news.items[0]) && !("image" in news.items[0]));
});

test("validateNews drops bad items and keeps the rest", () => {
  const data = newsFile();
  const good = data.items[0];
  data.items.push(
    null, 5, "x", [],
    { ...good, title: "" },
    { ...good, title: "   " },
    { ...good, title: 7 },
    { ...good, title: "x".repeat(2001) },
    { ...good, url: "javascript:alert(1)" },
    { ...good, url: "data:text/html,x" },
    { ...good, url: "https://evil.example/a" },
    { ...good, url: "https://evilsvt.se/a" },
    { ...good, url: "ftp://www.svt.se/a" },
    { ...good, url: 5 },
    { ...good, sourceId: "other" },
    { ...good, sourceId: "sveriges-radio", url: "https://www.sverigesradio.se/artikel/1" },
    { ...good, sourceId: undefined },
    { ...good, url: "https://svt.se/nyheter/inrikes/a?x=1" }, // duplicate by normalised URL
  );
  const news = app.validateNews(data, SOURCES, NOW);
  assert.deepEqual(news.items.map((i) => i.url), [
    "https://www.svt.se/nyheter/inrikes/a", "https://www.svt.se/nyheter/inrikes/b"]);
});

test("validateNews: time rules (future time and missing time)", () => {
  const data = newsFile();
  data.items[0].published = "2026-11-13T14:00:00Z"; // more than 10 minutes after NOW
  data.items[1].published = null;
  const news = app.validateNews(data, SOURCES, NOW);
  assert.equal(news.items[0].published, null);
  assert.equal(news.items[0].publishedDisplay, "Tid saknas");
  assert.equal(news.items[1].publishedDisplay, "Tid saknas");
});

test("validateNews takes the source name from sources.json", () => {
  const data = newsFile();
  data.items[0].sourceName = "<b>Falsk</b>";
  assert.equal(app.validateNews(data, SOURCES, NOW).items[0].sourceName, "SVT");
});

test("validateNews rejects an unusable file", () => {
  for (const bad of [null, [], "x", 5, {}, { version: 3, generatedAt: "2026-11-13T13:05:12Z", items: [] },
    newsFile({ version: 0 }), newsFile({ version: "2" }), newsFile({ version: 2.5 }), newsFile({ version: 3 }),
    newsFile({ generatedAt: "not a time" }), newsFile({ generatedAt: 5 }), newsFile({ items: "x" }),
    newsFile({ items: {} })]) {
    assert.equal(app.validateNews(bad, SOURCES, NOW), null);
  }
});

test("validateNews limits the number of items and cleans the source statuses", () => {
  const data = newsFile();
  const base = data.items[0];
  data.items = [];
  for (let i = 0; i < 600; i++) data.items.push({ ...base, url: "https://www.svt.se/a/" + i });
  data.sources = [
    { id: "svt", status: "error", lastSuccess: "2026-11-13T09:00:00Z", itemCount: 3, message: "fetch failed: timeout" },
    { id: "svt", status: "weird" },
    { id: "other", status: "ok" },
    "x",
  ];
  const news = app.validateNews(data, SOURCES, NOW);
  assert.equal(news.items.length, 500);
  assert.deepEqual(news.sources, [{
    id: "svt", name: "SVT", status: "error", lastSuccess: "2026-11-13T09:00:00Z", itemCount: 3,
    message: "fetch failed: timeout",
  }]);
});

// ---------------------------------------------------------------- news.json version 2 (F5, R19.8)

// A hand-written version 2 file: the two politics items of newsFile() plus items of other topics,
// and a Sveriges Radio item that must never be read from a file (N10).
function newsFileV2(overrides = {}) {
  const v1 = newsFile();
  const base = { id: "x", sourceId: "svt", sourceName: "SVT", publishedDisplay: "bogus" };
  return {
    version: 2,
    generatedAt: "2026-11-13T13:05:12Z",
    generatedAtDisplay: "2026-11-13 14:05",
    topics: ["all-news", "politics", "nature", "ai"],
    sources: [{
      id: "svt", name: "SVT", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 5,
      feeds: [
        { topic: "all-news", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 4 },
        { topic: "politics", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 2 },
        { topic: "nature", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 1 },
        { topic: "ai", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 1 },
      ],
    }],
    items: [
      { ...v1.items[0], topics: ["all-news", "politics"] },
      { ...v1.items[1], topics: ["all-news", "politics", "ai"] },
      { ...base, title: "Naturrubrik", url: "https://www.svt.se/nyheter/natur/1", published: "2026-11-13T13:00:00Z",
        topics: ["all-news", "nature"] },
      { ...base, title: "Vanlig rubrik", url: "https://www.svt.se/nyheter/2", published: "2026-11-13T13:01:00Z",
        topics: ["all-news"] },
      { ...base, title: "AI-rubrik", url: "https://www.svt.se/nyheter/3", published: "2026-11-13T13:02:00Z",
        topics: ["ai"] },
    ],
    ...overrides,
  };
}

test("validateNews reads version 2: topics per item, the topic list and the status of each feed", () => {
  const news = app.validateNews(newsFileV2(), SOURCES, NOW);
  assert.equal(news.version, 2);
  assert.deepEqual(news.topics, ["all-news", "politics", "nature", "ai"]);
  assert.deepEqual(news.items.map((i) => i.topics), [
    ["all-news", "politics"], ["all-news", "politics", "ai"], ["all-news", "nature"], ["all-news"], ["ai"]]);
  assert.equal(news.sources[0].itemCount, 5);
  assert.deepEqual(news.sources[0].feeds.map((f) => [f.topic, f.status, f.itemCount]),
    [["all-news", "ok", 4], ["politics", "ok", 2], ["nature", "ok", 1], ["ai", "ok", 1]]);
  assert.deepEqual(Object.keys(news.items[0]).sort(),
    ["id", "published", "publishedDisplay", "sourceId", "sourceName", "title", "topics", "url"]);
  // Idempotent: the saved copy validates to itself.
  assert.deepEqual(app.validateNews(JSON.parse(JSON.stringify(news)), SOURCES, NOW), news);
});

test("validateNews: a version 1 file has the topics Alla nyheter and Politik and no feeds", () => {
  const news = app.validateNews(newsFile(), SOURCES, NOW);
  assert.deepEqual(news.topics, ["all-news", "politics"]);
  assert.ok(news.items.every((i) => i.topics.join() === "all-news,politics"));
  assert.ok(!("feeds" in news.sources[0]));
});

test("validateNews: topics of a version 2 item are sorted, deduplicated and filtered to known ids", () => {
  const data = newsFileV2();
  data.items[0].topics = ["ai", "politics", "politics", "sport", 5, "all-news"];
  data.topics = ["ai", "ai", "nope", "all-news"];
  const news = app.validateNews(data, SOURCES, NOW);
  assert.deepEqual(news.items[0].topics, ["all-news", "politics", "ai"]);
  assert.deepEqual(news.topics, ["all-news", "ai"]);
});

test("validateNews: a version 2 item without a usable topic list is dropped (R1.5)", () => {
  const data = newsFileV2();
  const good = data.items[0];
  const { topics: _unused, ...withoutTopics } = good;
  data.items.push(withoutTopics, { ...good, url: "https://www.svt.se/x/1", topics: [] },
    { ...good, url: "https://www.svt.se/x/2", topics: "politics" },
    { ...good, url: "https://www.svt.se/x/3", topics: ["sport"] },
    { ...good, url: "https://www.svt.se/x/4", topics: null },
    { ...good, url: "https://www.svt.se/x/5", topics: { 0: "politics" } });
  assert.equal(app.validateNews(data, SOURCES, NOW).items.length, 5);
});

test("validateNews: a version 2 file without a topic list or feeds is still usable", () => {
  const data = newsFileV2();
  delete data.topics;
  delete data.sources[0].feeds;
  const news = app.validateNews(data, SOURCES, NOW);
  assert.deepEqual(news.topics, []);
  assert.ok(!("feeds" in news.sources[0]));
  assert.equal(news.items.length, 5);
});

test("validateNews cleans the feed statuses of a version 2 file", () => {
  const data = newsFileV2();
  data.sources[0].feeds = [
    { topic: "politics", status: "error", lastSuccess: "2026-11-13T09:00:00Z", itemCount: 3, message: "fetch failed: timeout",
      url: "https://secret.example/x" },
    { topic: "nature", status: "blocked-by-robots", lastSuccess: "bad", itemCount: -4, message: 7 },
    { topic: "sport", status: "ok" }, { topic: "ai", status: "weird" }, null, "x",
  ];
  assert.deepEqual(app.validateNews(data, SOURCES, NOW).sources[0].feeds, [
    { topic: "politics", status: "error", lastSuccess: "2026-11-13T09:00:00Z", itemCount: 3, message: "fetch failed: timeout" },
    { topic: "nature", status: "blocked-by-robots", lastSuccess: null, itemCount: 0 },
  ]);
});

test("validateNews never reads a Sveriges Radio item from a version 2 file either (N10)", () => {
  const data = newsFileV2();
  data.items.push({ ...data.items[0], sourceId: "sveriges-radio", url: "https://www.sverigesradio.se/artikel/1",
    title: "SR-rubrik" });
  assert.ok(!app.validateNews(data, SOURCES, NOW).items.some((i) => i.sourceId === "sveriges-radio"));
});

test("visibleItems: until F7 only the items of Politik are shown, so the list is as before (R19.8)", () => {
  const news = app.validateNews(newsFileV2(), SOURCES, NOW);
  assert.deepEqual(app.visibleItems(news, ["svt"]).map((i) => i.title),
    ["Nyare rubrik om regeringen", "Äldre rubrik om riksdagen"]);
  // The very same list as from the version 1 file that had only these two items.
  const fromV1 = app.visibleItems(app.validateNews(newsFile(), SOURCES, NOW), ["svt"]);
  assert.deepEqual(app.visibleItems(news, ["svt"]).map(({ topics, ...rest }) => rest), fromV1.map(({ topics, ...rest }) => rest));
  assert.deepEqual(app.visibleItems(news, []), []);
});

test("visibleItems: live items with topics are shown by topic next to the Politik items of the file", () => {
  const news = app.validateNews(newsFileV2(), SOURCES, NOW);
  const live = new Map([["sveriges-radio", [{ id: "l1", sourceId: "sveriges-radio", sourceName: "Sveriges Radio",
    title: "Ekot-rubrik", url: "https://www.sverigesradio.se/artikel/9", published: "2026-11-13T13:20:00Z",
    publishedDisplay: "2026-11-13 14:20", topics: ["all-news", "politics"] }]]]);
  assert.deepEqual(app.visibleItems(news, ["svt", "sveriges-radio"], live).map((i) => i.title),
    ["Ekot-rubrik", "Nyare rubrik om regeringen", "Äldre rubrik om riksdagen"]);
});

test("sourceRows: before F7 the row of a version 2 entry uses the politics feed, so the count is the visible items (R19.8)", () => {
  const news = app.validateNews(newsFileV2(), SOURCES, NOW);
  assert.equal(app.sourceRows(SOURCES, news, ["svt"])[0].status, "Hämtad, 2 rubriker");
  assert.equal(app.visibleItems(news, ["svt"]).length, 2);
});

function rowStatus(data) {
  return app.sourceRows(SOURCES, app.validateNews(data, SOURCES, NOW), ["svt"])[0].status;
}

function withFeeds(changes) {
  const data = newsFileV2();
  data.sources[0].feeds = data.sources[0].feeds.map((f) => (changes[f.topic] ? { ...f, ...changes[f.topic] } : f));
  return data;
}

test("sourceRows: only the all-news feed failed, the row stays Hämtad while the politics items are fresh", () => {
  const failed = { status: "error", lastSuccess: "2026-11-13T09:00:00Z", message: "fetch failed: timeout" };
  const data = withFeeds({ "all-news": failed, nature: failed, ai: failed });
  data.sources[0].status = "error";
  data.sources[0].lastSuccess = "2026-11-13T09:00:00Z";
  data.sources[0].message = "fetch failed: timeout";
  assert.equal(rowStatus(data), "Hämtad, 2 rubriker");
});

test("sourceRows: a failed politics feed shows the failure with its own last success", () => {
  const data = withFeeds({ politics: { status: "error", lastSuccess: "2026-11-13T09:00:00Z", message: "x", itemCount: 1 } });
  assert.equal(rowStatus(data), "Kunde inte hämtas sedan 2026-11-13 10:00");
  assert.equal(rowStatus(withFeeds({ politics: { status: "error", lastSuccess: null, message: "x" } })), "Kunde inte hämtas");
  assert.equal(rowStatus(withFeeds({ politics: { status: "blocked-by-robots", message: "x" } })),
    "Blockerad enligt källans robots.txt");
});

test("sourceRows: without feeds, or without a politics feed entry, the source-level fields are used", () => {
  const data = newsFileV2();
  delete data.sources[0].feeds;
  // The status comes from the source-level fields; the count is the items shown for the topic (F7).
  assert.equal(rowStatus(data), "Hämtad, 2 rubriker");
  const other = newsFileV2();
  other.sources[0].feeds = other.sources[0].feeds.filter((f) => f.topic !== "politics");
  other.sources[0].itemCount = 7;
  other.sources[0].status = "error";
  other.sources[0].lastSuccess = "2026-11-13T09:00:00Z";
  assert.equal(rowStatus(other), "Kunde inte hämtas sedan 2026-11-13 10:00");
  assert.equal(rowStatus(newsFile()), "Hämtad, 2 rubriker"); // version 1
});

test("parseSavedNews: text from storage is validated", () => {
  const text = JSON.stringify(newsFile());
  assert.ok(app.parseSavedNews(text, SOURCES, NOW));
  for (const bad of [null, undefined, "", "{", "null", "[]", "x".repeat(2000001), JSON.stringify({ version: 1 })]) {
    assert.equal(app.parseSavedNews(bad, SOURCES, NOW), null);
  }
});

// ---------------------------------------------------------------- choice

test("parseSelected: first visit and unreadable values choose every source (R3.3)", () => {
  for (const text of [null, undefined, "", "{", "5", "{}", '"svt"', '[1]', '["svt", 2]']) {
    assert.deepEqual(app.parseSelected(text, SOURCES), ["svt", "sveriges-radio"]);
    assert.deepEqual(app.parseSelected(text, SOURCES_ON), ["svt", "sveriges-radio", "riksdagen"]);
  }
  assert.deepEqual(app.parseSelected("x".repeat(20000), SOURCES), ["svt", "sveriges-radio"]);
});

test("parseSelected: a saved choice, including an empty one, is kept (R3.5)", () => {
  assert.deepEqual(app.parseSelected('["sveriges-radio"]', SOURCES), ["sveriges-radio"]);
  assert.deepEqual(app.parseSelected("[]", SOURCES), []);
  // Unknown ids are ignored; a source that is not in the saved list is not chosen.
  assert.deepEqual(app.parseSelected('["gone", "svt"]', SOURCES), ["svt"]);
  const withNew = [...SOURCES, { ...SVT, id: "new", name: "Ny" }];
  assert.deepEqual(app.parseSelected('["svt","sveriges-radio"]', withNew), ["svt", "sveriges-radio"]);
});

test("visibleItems: chosen sources only, newest first", () => {
  const news = app.validateNews(newsFile(), SOURCES, NOW);
  assert.deepEqual(app.visibleItems(news, ["svt"]).map((i) => i.title),
    ["Nyare rubrik om regeringen", "Äldre rubrik om riksdagen"]);
  assert.deepEqual(app.visibleItems(news, []), []);
  assert.deepEqual(app.visibleItems(news, ["sveriges-radio"]), []);
  assert.deepEqual(app.visibleItems(null, ["svt"]), []);
});

// ---------------------------------------------------------------- notices and rows

test("decideNotices: error, offline and stale", () => {
  const news = app.validateNews(newsFile(), SOURCES, NOW);
  assert.deepEqual(app.decideNotices(null, false, NOW),
    [{ kind: "error", text: "Kunde inte hämta nyheter. Försök igen senare." }]);
  assert.deepEqual(app.decideNotices(news, false, NOW), []);
  assert.deepEqual(app.decideNotices(news, true, NOW), [
    { kind: "offline", text: "Offline – visar sparade nyheter från 2026-11-13 14:05" }]);
  // Exactly 3 hours is not stale; one second more is.
  const generated = Date.parse("2026-11-13T13:05:12Z");
  assert.deepEqual(app.decideNotices(news, false, generated + 3 * 3600 * 1000), []);
  assert.deepEqual(app.decideNotices(news, false, generated + 3 * 3600 * 1000 + 1000), [
    { kind: "stale", text: "Nyheterna kan vara gamla – senast uppdaterade 2026-11-13 14:05" }]);
  const both = app.decideNotices(news, true, generated + 4 * 3600 * 1000);
  assert.deepEqual(both.map((n) => n.kind), ["offline", "stale"]);
});

test("sourceRows: note, checkbox and status (R4.6, R6.2)", () => {
  const news = app.validateNews(newsFile(), SOURCES, NOW);
  let rows = app.sourceRows(SOURCES, news, ["svt"]);
  assert.deepEqual(rows[0], {
    id: "svt", name: "SVT", checked: true, topics: "", note: "Urval med nyckelord – ungefärligt", credit: "",
    status: "Hämtad, 2 rubriker",
  });
  assert.equal(rows[1].checked, false);
  assert.equal(rows[1].note, "Urval med nyckelord – ungefärligt");
  assert.equal(rows[1].status, "Inte vald – ingen hämtning"); // unticked (S11)
  assert.equal(app.sourceRows(SOURCES, news, ["svt", "sveriges-radio"])[1].status, "Inte hämtad ännu");
  const failed = newsFile({ sources: [{ id: "svt", status: "error", lastSuccess: "2026-11-13T09:00:00Z", itemCount: 1 }] });
  rows = app.sourceRows(SOURCES, app.validateNews(failed, SOURCES, NOW), ["svt"]);
  assert.equal(rows[0].status, "Kunde inte hämtas sedan 2026-11-13 10:00");
  assert.equal(app.sourceRows(SOURCES, null, [])[0].status, "Status okänd");
});

// ---------------------------------------------------------------- fake DOM

class Node_ {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.attrs = {};
    this.listeners = {};
    this._text = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.className = "";
  }
  get firstChild() { return this.children[0] || null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  appendChild(c) { this.children.push(c); return c; }
  replaceChildren() {
    // Like a browser: removing the focused element moves the focus to the body.
    const active = this.doc && this.doc.activeElement;
    if (active && this.children.some((c) => c === active || c.find((n) => n === active).length)) {
      this.doc.activeElement = null;
    }
    this.children = [];
    this._text = "";
  }
  focus() { if (this.doc) this.doc.activeElement = this; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  fire(type) { for (const fn of this.listeners[type] || []) fn({ target: this }); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  find(pred, out = []) {
    if (pred(this)) out.push(this);
    for (const c of this.children) c.find(pred, out);
    return out;
  }
}

function fakePage() {
  const ids = ["updated", "refresh", "notices", "headlines", "empty", "sources", "sources-section", "topics", "topics-section", "bottom-line"];
  const byId = {};
  const doc = new Node_("document");
  doc.hidden = false;
  doc.activeElement = null;
  doc.documentElement = new Node_("html");
  const make = (tag) => { const n = new Node_(tag); n.doc = doc; return n; };
  for (const id of ids) byId[id] = make("x");
  doc.getElementById = (id) => byId[id] || null;
  doc.createElement = make;
  return { doc, byId };
}

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
  };
}

function setup({ files, storage, window, gate } = {}) {
  const { doc, byId } = fakePage();
  const calls = [];
  const intervals = [];
  const clock = { now: NOW };
  const env = {
    document: doc,
    window: window || { localStorage: storage },
    now: () => clock.now,
    setInterval: (fn, ms) => { intervals.push({ fn, ms }); return intervals.length; },
    setTimeout: () => 0,
    clearTimeout: () => {},
    fetch: async (url) => {
      calls.push(url);
      if (gate) await gate;
      const body = files[url];
      if (body === undefined) return { ok: false, status: 404, text: async () => "" };
      return { ok: true, status: 200, text: async () => (typeof body === "string" ? body : JSON.stringify(body)) };
    },
  };
  const instance = app.createApp(env);
  return { instance, byId, calls, doc, intervals, clock };
}

function headlinesOf(byId) {
  return byId.headlines.children.map((li) => li.children[0].textContent);
}

test("page: shows SVT headlines newest first with headline, source, time and a safe link", async () => {
  const storage = fakeStorage();
  const { instance, byId, doc } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, storage });
  await instance.start();
  assert.deepEqual(headlinesOf(byId), ["Nyare rubrik om regeringen", "Äldre rubrik om riksdagen"]);
  const li = byId.headlines.children[0];
  const link = li.children[0];
  assert.equal(link.tag, "a");
  assert.equal(link.attrs.href, "https://www.svt.se/nyheter/inrikes/b");
  assert.equal(link.attrs.target, "_blank");
  assert.equal(link.attrs.rel, "noopener noreferrer");
  const meta = li.children[1];
  assert.deepEqual(meta.children.map((c) => c.textContent), ["SVT", " · ", "2026-11-13 13:58"]);
  assert.equal(meta.children[2].attrs.datetime, "2026-11-13T12:58:00Z");
  assert.equal(byId.updated.textContent, "Nyheter uppdaterade 2026-11-13 14:05");
  assert.equal(byId.empty.hidden, true);
  assert.equal(byId.notices.children.length, 0);
  assert.equal(byId["sources-section"].hidden, false);
  assert.match(doc.documentElement.className, /\bjs\b/);
  assert.equal(byId["bottom-line"].textContent,
    "Rubriker och länkar från SVT och Sveriges Radio. Klicka för att läsa hos källan.");
  assert.ok(JSON.parse(storage.data["newsReader.lastNews"]).items.length === 2);
});

test("page: the headline is written as text, never as markup", async () => {
  const data = newsFile();
  data.items[0].title = "<img src=x onerror=alert(1)> & <b>fet</b>";
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": data } });
  await instance.start();
  const link = byId.headlines.children[1].children[0];
  assert.equal(link.children.length, 0);
  assert.equal(link.textContent, "<img src=x onerror=alert(1)> & <b>fet</b>");
});

test("page: Källor lists each source with note and status; the Sveriges Radio row says it could not be fetched here", async () => {
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() } });
  await instance.start();
  const rows = byId.sources.children;
  assert.equal(rows.length, 2); // no Riksdagen row while it is switched off (D41)
  const text = rows.map((r) => r.textContent);
  assert.match(text[0], /SVT/);
  assert.match(text[0], /Urval med nyckelord – ungefärligt/);
  assert.match(text[0], /Hämtad, 2 rubriker/);
  assert.match(text[1], /Sveriges Radio/);
  // This fake serves neither the keyword list nor the feed: the live fetch fails (R7.6).
  assert.match(text[1], /Sveriges Radio kunde inte hämtas just nu/);
  const input = rows[0].children[0];
  const label = rows[0].children[1];
  const ids = rows.flatMap((r) => [r.children[0].attrs.id, r.children[2].attrs.id]);
  assert.equal(new Set(ids).size, 4);
  assert.ok(ids.every((id) => /^src-(cb|info)-[0-9]+$/.test(id)));
  assert.equal(input.attrs["aria-describedby"], rows[0].children[2].attrs.id);
  assert.equal(input.attrs.type, "checkbox");
  assert.equal(label.tag, "label");
  assert.equal(label.attrs.for, input.attrs.id);
  assert.equal(input.checked, true);
});

test("page: unticking a source updates the list at once and saves the choice (R3.3)", async () => {
  const storage = fakeStorage();
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, storage });
  await instance.start();
  const box = (i) => byId.sources.children[i].children[0];
  box(0).checked = false;
  box(0).fire("change");
  assert.deepEqual(headlinesOf(byId), []);
  assert.equal(byId.empty.hidden, false);
  // Sveriges Radio is still chosen but gives nothing here: the topic notice of R18.6.
  assert.equal(byId.empty.textContent, "Inga nyheter i ämnet Politik från valda källor.");
  assert.equal(storage.data["newsReader.selectedSources"], '["sveriges-radio"]');
  box(1).checked = false;
  box(1).fire("change");
  assert.equal(byId.empty.textContent, "Inga nyheter från valda källor.");
  assert.equal(storage.data["newsReader.selectedSources"], "[]");
  box(0).checked = true;
  box(0).fire("change");
  assert.equal(headlinesOf(byId).length, 2);
  assert.equal(byId.empty.hidden, true);
  assert.equal(storage.data["newsReader.selectedSources"], '["svt"]');
});

test("page: a saved choice is used, unknown saved ids are dropped on the next change (R3.5)", async () => {
  const storage = fakeStorage({ "newsReader.selectedSources": '["gone","svt"]' });
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, storage });
  await instance.start();
  assert.equal(byId.sources.children[0].children[0].checked, true);
  assert.equal(byId.sources.children[1].children[0].checked, false);
  byId.sources.children[1].children[0].checked = true;
  byId.sources.children[1].children[0].fire("change");
  // Riksdagen is switched off (D41), so the one-time migration adds nothing.
  assert.equal(storage.data["newsReader.selectedSources"], '["svt","sveriges-radio"]');
});

test("page: all sources unticked saved earlier gives the empty notice", async () => {
  const storage = fakeStorage({ "newsReader.selectedSources": "[]" });
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, storage });
  await instance.start();
  assert.equal(byId.empty.hidden, false);
});

test("page: works when localStorage is blocked (throws)", async () => {
  const window = {};
  Object.defineProperty(window, "localStorage", { get() { throw new Error("blocked"); } });
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, window });
  await instance.start();
  assert.equal(headlinesOf(byId).length, 2);
  byId.sources.children[0].children[0].checked = false;
  byId.sources.children[0].children[0].fire("change");
  assert.equal(headlinesOf(byId).length, 0);
});

test("page: works when storage methods throw", async () => {
  const storage = { getItem() { throw new Error("x"); }, setItem() { throw new Error("x"); } };
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, storage });
  await instance.start();
  assert.equal(headlinesOf(byId).length, 2);
});

test("page: news.json fails, a saved copy is shown with the offline notice (R8.2)", async () => {
  const saved = app.validateNews(newsFile(), SOURCES, NOW);
  const storage = fakeStorage({ "newsReader.lastNews": JSON.stringify(saved) });
  const { instance, byId } = setup({ files: { "sources.json": realSources }, storage });
  await instance.start();
  assert.equal(headlinesOf(byId).length, 2);
  assert.equal(byId.notices.children[0].textContent, "Offline – visar sparade nyheter från 2026-11-13 14:05");
  assert.equal(byId.updated.textContent, "Nyheter uppdaterade 2026-11-13 14:05");
});

test("page: a bad saved copy is ignored; without any copy the error notice is shown", async () => {
  for (const initial of [{}, { "newsReader.lastNews": "{" }, { "newsReader.lastNews": '{"version":1}' }]) {
    const { instance, byId } = setup({ files: { "sources.json": realSources }, storage: fakeStorage(initial) });
    await instance.start();
    assert.equal(byId.notices.children[0].textContent, "Kunde inte hämta nyheter. Försök igen senare.");
    assert.equal(byId.headlines.children.length, 0);
    assert.equal(byId.empty.hidden, true);
  }
});

test("page: an unusable news.json counts as a failed load", async () => {
  const { instance, byId } = setup({
    files: { "sources.json": realSources, "news.json": "<html>not json</html>" } });
  await instance.start();
  assert.equal(byId.notices.children[0].textContent, "Kunde inte hämta nyheter. Försök igen senare.");
});

test("page: a version 1 sources.json gives the same generic failure text and no list (R14.6)", async () => {
  const v1 = { version: 1, sources: [{ id: "svt", name: "SVT", enabled: true, fetchedBy: "build",
    allowedHosts: ["svt.se"], "politics-sweden": { method: "keywordFilter", url: "https://www.svt.se/x.xml" } }] };
  const { instance, byId } = setup({ files: { "sources.json": v1, "news.json": newsFile() } });
  await instance.start();
  assert.equal(byId.notices.children[0].textContent, "Kunde inte hämta nyheter. Försök igen senare.");
  assert.equal(byId.headlines.children.length, 0);
  assert.equal(byId["sources-section"].hidden, true);
});

test("page: sources.json missing gives the error notice and no list", async () => {
  const { instance, byId } = setup({ files: { "news.json": newsFile() } });
  await instance.start();
  assert.equal(byId.notices.children[0].textContent, "Kunde inte hämta nyheter. Försök igen senare.");
  assert.equal(byId.headlines.children.length, 0);
  assert.equal(byId["sources-section"].hidden, true);
});

test("page: old data gives the stale notice (R8.3)", async () => {
  const data = newsFile({ generatedAt: "2026-11-13T09:00:00Z" });
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": data } });
  await instance.start();
  assert.equal(byId.notices.children[0].textContent,
    "Nyheterna kan vara gamla – senast uppdaterade 2026-11-13 10:00");
});

test("page: a failed reload keeps what is shown; a good reload replaces it (R8.1)", async () => {
  const files = { "sources.json": realSources, "news.json": newsFile() };
  const { instance, byId } = setup({ files });
  await instance.start();
  delete files["news.json"];
  await instance.load();
  assert.equal(headlinesOf(byId).length, 2);
  assert.match(byId.notices.children[0].textContent, /^Offline – visar sparade/);
  const data = newsFile();
  data.items.pop();
  files["news.json"] = data;
  await instance.load();
  assert.equal(headlinesOf(byId).length, 1);
  assert.equal(byId.notices.children.length, 0);
});

test("page: an item of a Sveriges Radio in news.json is never shown (N10)", async () => {
  const data = newsFile();
  data.items.push({ ...data.items[0], sourceId: "sveriges-radio", sourceName: "Sveriges Radio",
    url: "https://www.sverigesradio.se/artikel/1", title: "SR-rubrik" });
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": data } });
  await instance.start();
  assert.ok(!headlinesOf(byId).includes("SR-rubrik"));
});

test("page: saved copy plus failed sources.json keeps the failure text (nothing to check links against)", async () => {
  const saved = app.validateNews(newsFile(), SOURCES, NOW);
  const storage = fakeStorage({ "newsReader.lastNews": JSON.stringify(saved) });
  const { instance, byId } = setup({ files: { "news.json": newsFile() }, storage });
  await instance.start();
  assert.equal(byId.headlines.children.length, 0);
  assert.equal(byId.notices.children[0].textContent, "Kunde inte hämta nyheter. Försök igen senare.");
});

// ---------------------------------------------------------------- refresh, focus, notices

test("refresh: an interval of exactly 10 minutes loads again", async () => {
  const { instance, calls, intervals } = setup({ files: { "sources.json": realSources, "news.json": newsFile() } });
  await instance.start();
  assert.equal(intervals.length, 1);
  assert.equal(intervals[0].ms, 10 * 60 * 1000);
  assert.equal(app.REFRESH_MS, 10 * 60 * 1000);
  const before = calls.filter((u) => u === "news.json").length;
  intervals[0].fn();
  await new Promise((r) => setImmediate(r));
  assert.equal(calls.filter((u) => u === "news.json").length, before + 1);
});

test("refresh: nothing is loaded while the tab is hidden; it loads when visible again", async () => {
  const { instance, calls, intervals, doc, clock } = setup({
    files: { "sources.json": realSources, "news.json": newsFile() } });
  await instance.start();
  const count = () => calls.filter((u) => u === "news.json").length;
  const start = count();
  doc.hidden = true;
  intervals[0].fn();
  doc.fire("visibilitychange");
  await new Promise((r) => setImmediate(r));
  assert.equal(count(), start);
  // Visible again, less than 10 minutes after the last load: no load.
  doc.hidden = false;
  clock.now += 9 * 60 * 1000;
  doc.fire("visibilitychange");
  await new Promise((r) => setImmediate(r));
  assert.equal(count(), start);
  // Visible again, 10 minutes after the last load: load.
  clock.now += 60 * 1000;
  doc.fire("visibilitychange");
  await new Promise((r) => setImmediate(r));
  assert.equal(count(), start + 1);
  // The timer loads again once the tab is visible.
  intervals[0].fn();
  await new Promise((r) => setImmediate(r));
  assert.equal(count(), start + 2);
});

test("refresh: a load that is already running is not started twice", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const { instance, calls } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, gate });
  const first = instance.start();
  const second = instance.load();
  const third = instance.load();
  assert.equal(calls.length, 1, "only one request while a load is running");
  release();
  await Promise.all([first, second, third]);
  assert.deepEqual(calls.filter((u) => u.endsWith(".json")).sort(),
    ["ai-keywords.json", "nature-keywords.json", "news.json", "politics-keywords.json", "sources.json"]);
  await instance.load();
  assert.equal(calls.filter((u) => u === "news.json").length, 2);
});

test("refresh: the button is never disabled (that would drop the focus), it is marked busy", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, gate });
  const done = instance.start();
  assert.equal(byId.refresh.attrs["aria-busy"], "true");
  assert.equal(byId.refresh.disabled, false);
  release();
  await done;
  assert.equal(byId.refresh.attrs["aria-busy"], "false");
  assert.equal(byId.refresh.disabled, false);
});

test("focus: a reload of unchanged data does not touch the list or the notices", async () => {
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() } });
  await instance.start();
  const link = byId.headlines.children[0].children[0];
  const firstLi = byId.headlines.children[0];
  link.focus();
  byId.refresh.focus();
  await instance.load();
  assert.equal(byId.headlines.children[0], firstLi, "same list elements");
  assert.equal(byId.refresh.doc.activeElement, byId.refresh);
  link.focus();
  await instance.load();
  assert.equal(link.doc.activeElement, link);
});

test("focus: when the list changes, the focus goes to the same headline if it is still there", async () => {
  const files = { "sources.json": realSources, "news.json": newsFile() };
  const { instance, byId, doc } = setup({ files });
  await instance.start();
  // Focus the older headline, then a new item appears first.
  const older = byId.headlines.children[1].children[0];
  older.focus();
  const data = newsFile();
  data.items.push({ ...data.items[0], title: "Helt ny rubrik", url: "https://www.svt.se/nyheter/inrikes/c",
    published: "2026-11-13T13:20:00Z" });
  files["news.json"] = data;
  await instance.load();
  assert.equal(headlinesOf(byId).length, 3);
  assert.ok(doc.activeElement);
  assert.equal(doc.activeElement.textContent, "Äldre rubrik om riksdagen");
  // The focused headline disappears: no focus is invented.
  files["news.json"] = newsFile();
  files["news.json"].items.shift();
  await instance.load();
  assert.equal(doc.activeElement, null);
});

test("notices: a notice that did not change is not rewritten (no new announcement)", async () => {
  const data = newsFile({ generatedAt: "2026-11-13T09:00:00Z" });
  const { instance, byId, clock } = setup({ files: { "sources.json": realSources, "news.json": data } });
  await instance.start();
  const notice = byId.notices.children[0];
  assert.match(notice.textContent, /kan vara gamla/);
  clock.now += 10 * 60 * 1000;
  await instance.load();
  assert.equal(byId.notices.children[0], notice, "the same element, not rebuilt");
});

test("R1.4: an item with an empty or blank headline is dropped", () => {
  const data = newsFile();
  data.items[0].title = "";
  data.items[1].title = " \t\u00a0 ";
  assert.deepEqual(app.validateNews(data, SOURCES, NOW).items, []);
});

test("sourceRows: error with no last success says only that it could not be fetched", () => {
  const file = newsFile({ sources: [{ id: "svt", status: "error", lastSuccess: null, itemCount: 0 }] });
  const rows = app.sourceRows(SOURCES, app.validateNews(file, SOURCES, NOW), ["svt"]);
  assert.equal(rows[0].status, "Kunde inte hämtas");
  assert.ok(!rows[0].status.includes("Tid saknas"));
});

// ---------------------------------------------------------------- the page with version 2 (F5, R19.8)

test("page: a version 2 news.json shows exactly the list that the version 1 file gave", async () => {
  const v1 = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, storage: fakeStorage() });
  await v1.instance.start();
  const storage = fakeStorage();
  const v2 = setup({ files: { "sources.json": realSources, "news.json": newsFileV2() }, storage });
  await v2.instance.start();
  assert.deepEqual(headlinesOf(v2.byId), headlinesOf(v1.byId));
  assert.deepEqual(headlinesOf(v2.byId), ["Nyare rubrik om regeringen", "Äldre rubrik om riksdagen"]);
  assert.deepEqual(v2.byId.headlines.children.map((li) => li.children[1].textContent),
    v1.byId.headlines.children.map((li) => li.children[1].textContent));
  assert.equal(v2.byId.updated.textContent, v1.byId.updated.textContent);
  assert.equal(v2.byId.notices.children.length, 0);
  assert.equal(v2.byId.empty.hidden, true);
  // The saved copy is a clean version 2 copy that holds every item with its topics, and nothing else.
  const saved = JSON.parse(storage.data["newsReader.lastNews"]);
  assert.equal(saved.version, 2);
  assert.equal(saved.items.length, 5);
  assert.ok(saved.items.every((i) => Array.isArray(i.topics)));
});

test("page: a version 2 file without any Politik item gives the empty notice, as an empty version 1 file did", async () => {
  const data = newsFileV2();
  data.items = data.items.filter((i) => !i.topics.includes("politics"));
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": data } });
  await instance.start();
  assert.equal(byId.headlines.children.length, 0);
  assert.equal(byId.empty.hidden, false);
  // Sources are chosen and offer the topic, but nothing is in it (R18.6).
  assert.equal(byId.empty.textContent, "Inga nyheter i ämnet Politik från valda källor.");
});

test("page: the Källor row says Hämtad with the count of the politics feed of a version 2 file (R19.8)", async () => {
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFileV2() } });
  await instance.start();
  const status = byId.sources.children[0].find((n) => n.className === "source-status")[0];
  assert.equal(status.textContent, "Hämtad, 2 rubriker");
});

test("page: news.json fails, a saved version 2 copy shows the Politik items only, with the offline notice", async () => {
  const saved = app.validateNews(newsFileV2(), SOURCES, NOW);
  const storage = fakeStorage({ "newsReader.lastNews": JSON.stringify(saved) });
  const { instance, byId } = setup({ files: { "sources.json": realSources }, storage });
  await instance.start();
  assert.deepEqual(headlinesOf(byId), ["Nyare rubrik om regeringen", "Äldre rubrik om riksdagen"]);
  assert.equal(byId.notices.children[0].textContent, "Offline – visar sparade nyheter från 2026-11-13 14:05");
});

test("page: a saved version 1 copy, as an older page wrote it, is shown whole (R19.8)", async () => {
  // The raw text an older page saved: version 1, seven fields per item, `category`.
  const oldText = JSON.stringify({ ...newsFile(), sources: [{ id: "svt", name: "SVT", status: "ok",
    lastSuccess: "2026-11-13T13:05:12Z", itemCount: 2 }] });
  const storage = fakeStorage({ "newsReader.lastNews": oldText });
  const { instance, byId } = setup({ files: { "sources.json": realSources }, storage });
  await instance.start();
  assert.deepEqual(headlinesOf(byId), ["Nyare rubrik om regeringen", "Äldre rubrik om riksdagen"]);
  assert.equal(byId.notices.children[0].textContent, "Offline – visar sparade nyheter från 2026-11-13 14:05");
  // Reading it again as text from storage gives topics to every item.
  assert.ok(app.parseSavedNews(oldText, SOURCES, NOW).items.every((i) => i.topics.join() === "all-news,politics"));
});

test("page: a saved copy of another version is not used", async () => {
  for (const version of [0, 3, "2"]) {
    const storage = fakeStorage({ "newsReader.lastNews": JSON.stringify(newsFileV2({ version })) });
    const { instance, byId } = setup({ files: { "sources.json": realSources }, storage });
    await instance.start();
    assert.equal(byId.notices.children[0].textContent, "Kunde inte hämta nyheter. Försök igen senare.");
    assert.equal(byId.headlines.children.length, 0);
  }
});

// ---------------------------------------------------------------- topics, Riksdagen and the migration (F7)

// A hand-made news.json version 2 with SVT and Riksdagen items in every topic.
function newsFileF7() {
  const t = (hour) => "2026-11-13T" + hour + ":00:00Z";
  const svt = (title, path, hour, topics) => ({ id: "x", sourceId: "svt", sourceName: "SVT", title,
    url: "https://www.svt.se/nyheter/" + path, published: t(hour), publishedDisplay: "x", topics });
  const rd = (title, path, hour, topics) => ({ id: "x", sourceId: "riksdagen", sourceName: "Riksdagen", title,
    url: "https://www.riksdagen.se/sv/dokument-och-lagar/dokument/" + path, published: t(hour), publishedDisplay: "x", topics });
  const feeds = (extra) => ["all-news", "politics", "nature", "ai"].filter((id) => !extra.without || !extra.without.includes(id))
    .map((topic) => ({ topic, status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 9 }));
  return {
    version: 2,
    generatedAt: "2026-11-13T13:05:12Z",
    generatedAtDisplay: "2026-11-13 14:05",
    topics: ["all-news", "politics", "nature", "ai"],
    sources: [
      { id: "svt", name: "SVT", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 5, feeds: feeds({}) },
      { id: "riksdagen", name: "Riksdagen", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 2,
        feeds: feeds({ without: ["nature"] }) },
    ],
    items: [
      svt("SVT politik", "inrikes/1", "12", ["all-news", "politics"]),
      svt("SVT natur", "natur/2", "11", ["all-news", "nature"]),
      svt("SVT AI och natur", "vetenskap/3", "10", ["all-news", "nature", "ai"]),
      svt("SVT övrigt", "sport/4", "09", ["all-news"]),
      rd("Riksdagen proposition", "proposition/a_1", "08", ["all-news", "politics"]),
      rd("Riksdagen AI-betänkande", "betankande/b_2", "07", ["all-news", "politics", "ai"]),
    ],
  };
}

function titlesOf(byId) {
  return byId.headlines.children.map((li) => li.children[0].textContent);
}

function radios(byId) {
  return byId.topics.find((n) => n.attrs.type === "radio")[0];
}

function pick(byId, label) {
  const row = byId.topics.children.find((r) => r.children[1].textContent === label);
  row.children[0].checked = true;
  row.children[0].fire("change");
}

function rowOf(byId, name) {
  return byId.sources.children.find((r) => r.children[1].textContent === name);
}

function statusOf(byId, name) {
  return rowOf(byId, name).find((n) => n.className === "source-status")[0].textContent;
}

function f7Setup(extra = {}) {
  return setup({ files: { "sources.json": riksdagenOn, "news.json": newsFileF7() }, storage: fakeStorage(), ...extra });
}

test("topics: one radio button per topic from sources.json, in order, Politik chosen the first time (R18.1, R18.3)", async () => {
  const { instance, byId } = f7Setup();
  await instance.start();
  assert.equal(byId["topics-section"].hidden, false);
  const rows = byId.topics.children;
  assert.deepEqual(rows.map((r) => r.children[1].textContent), ["Alla nyheter", "Politik", "Natur", "AI"]);
  assert.ok(rows.every((r) => r.children[0].attrs.type === "radio" && r.children[0].attrs.name === "topic"));
  assert.ok(rows.every((r) => r.children[1].tag === "label" && r.children[1].attrs.for === r.children[0].attrs.id));
  assert.deepEqual(rows.map((r) => r.children[0].checked), [false, true, false, false]);
  assert.equal(new Set(rows.map((r) => r.children[0].attrs.id)).size, 4);
  assert.deepEqual(titlesOf(byId), ["SVT politik", "Riksdagen proposition", "Riksdagen AI-betänkande"]);
});

test("topics: switching shows the items of that topic at once, an item with several topics under each, and makes no request (R18.2, R15.3)", async () => {
  const storage = fakeStorage();
  const { instance, byId, calls } = f7Setup({ storage });
  await instance.start();
  const before = calls.length;
  pick(byId, "Natur");
  assert.deepEqual(titlesOf(byId), ["SVT natur", "SVT AI och natur"]);
  pick(byId, "AI");
  assert.deepEqual(titlesOf(byId), ["SVT AI och natur", "Riksdagen AI-betänkande"]);
  pick(byId, "Alla nyheter");
  assert.equal(titlesOf(byId).length, 6);
  assert.deepEqual(byId.topics.children.map((r) => r.children[0].checked), [true, false, false, false]);
  assert.equal(calls.length, before, "no request for a topic change");
  assert.equal(storage.data["newsReader.selectedTopic"], "all-news");
  assert.equal(byId.empty.hidden, true);
});

test("topics: the source rows follow the topic: offered topics, Erbjuder inte ämnet, the count of the visible items (R18.5)", async () => {
  const { instance, byId } = f7Setup();
  await instance.start();
  const rd = () => rowOf(byId, "Riksdagen").textContent;
  assert.match(rowOf(byId, "SVT").textContent, /Ämnen: Alla nyheter, Politik, Natur, AI/);
  assert.match(rd(), /Ämnen: Alla nyheter, Politik, AI/);
  assert.equal(statusOf(byId, "SVT"), "Hämtad, 1 rubrik");
  assert.equal(statusOf(byId, "Riksdagen"), "Hämtad, 2 rubriker");
  assert.match(rowOf(byId, "SVT").textContent, /Urval med nyckelord – ungefärligt/); // politics: keywordFilter
  assert.doesNotMatch(rd(), /Urval med nyckelord/); // politics: feed
  pick(byId, "Natur");
  assert.equal(statusOf(byId, "SVT"), "Hämtad, 2 rubriker");
  assert.equal(statusOf(byId, "Riksdagen"), "Erbjuder inte ämnet Natur");
  assert.doesNotMatch(statusOf(byId, "Sveriges Radio"), /Visas inte än/); // F8: no stopgap any more
  pick(byId, "AI");
  assert.match(rd(), /Urval med nyckelord – ungefärligt/); // ai: keywordFilter
  assert.equal(statusOf(byId, "Riksdagen"), "Hämtad, 1 rubrik");
  pick(byId, "Politik");
  assert.notEqual(statusOf(byId, "Sveriges Radio"), "Visas inte än");
});

test("topics: the credit of Riksdagen is always in its row, in the bottom line only while a Riksdagen item is listed (R16.5)", async () => {
  const { instance, byId } = f7Setup();
  await instance.start();
  const CREDIT = "Källa: Sveriges riksdag";
  const bottom = () => byId["bottom-line"].textContent;
  assert.equal(bottom(), "Rubriker och länkar från SVT, Sveriges Radio och Riksdagen. Klicka för att läsa hos källan. " +
    CREDIT + ". Sidan har inget samband med Sveriges riksdag.");
  assert.equal(app.DISCLAIMER_RIKSDAGEN, "Sidan har inget samband med Sveriges riksdag.");
  assert.match(rowOf(byId, "Riksdagen").textContent, new RegExp(CREDIT));
  assert.doesNotMatch(rowOf(byId, "SVT").textContent, /Källa:/);
  pick(byId, "Natur"); // Riksdagen has no items here
  assert.ok(!bottom().includes(CREDIT) && !bottom().includes("samband"));
  assert.match(rowOf(byId, "Riksdagen").textContent, new RegExp(CREDIT), "the row shows it always");
  pick(byId, "AI");
  assert.ok(bottom().includes(CREDIT));
  // Riksdagen unticked: no item, no credit in the line, still in the row.
  const box = rowOf(byId, "Riksdagen").children[0];
  box.checked = false;
  box.fire("change");
  assert.ok(!bottom().includes(CREDIT));
  assert.match(rowOf(byId, "Riksdagen").textContent, new RegExp(CREDIT));
});

test("topics: Riksdagen items are shown with the source name Riksdagen and a safe link", async () => {
  const { instance, byId } = f7Setup();
  await instance.start();
  const li = byId.headlines.children[1];
  assert.equal(li.children[0].attrs.href, "https://www.riksdagen.se/sv/dokument-och-lagar/dokument/proposition/a_1");
  assert.equal(li.children[1].children[0].textContent, "Riksdagen");
});

test("topics: notices for an empty list, by topic and source choice (R18.6)", async () => {
  const data = newsFileF7();
  data.items = data.items.filter((i) => i.sourceId === "riksdagen");
  const { instance, byId } = setup({ files: { "sources.json": riksdagenOn, "news.json": data }, storage: fakeStorage() });
  await instance.start();
  const tick = (name, on) => { const b = rowOf(byId, name).children[0]; b.checked = on; b.fire("change"); };
  tick("SVT", false);
  tick("Sveriges Radio", false);
  pick(byId, "Natur");
  // Only Riksdagen is chosen and it has no Natur feed.
  assert.equal(byId.empty.hidden, false);
  assert.equal(byId.empty.textContent, "Valda källor erbjuder inte ämnet Natur.");
  tick("SVT", true); // SVT offers Natur but has no item in it
  assert.equal(byId.empty.textContent, "Inga nyheter i ämnet Natur från valda källor.");
  pick(byId, "Politik");
  assert.equal(byId.empty.hidden, true);
  tick("SVT", false);
  tick("Riksdagen", false);
  assert.equal(byId.empty.textContent, "Inga nyheter från valda källor.");
  pick(byId, "Alla nyheter");
  assert.equal(byId.empty.textContent, "Inga nyheter från valda källor.");
});

test("topics: Sveriges Radio counts as offering a topic, so its notice is the one for no items (R18.9)", async () => {
  const { instance, byId } = f7Setup({ storage: fakeStorage({ "newsReader.selectedSources": '["sveriges-radio"]',
    "newsReader.selectedTopic": "nature" }) });
  await instance.start();
  assert.equal(byId.empty.textContent, "Inga nyheter i ämnet Natur från valda källor.");
});

test("topics: the saved topic is only an id, survives a reload, and an unknown one is ignored (R18.3)", async () => {
  const storage = fakeStorage();
  const first = f7Setup({ storage });
  await first.instance.start();
  pick(first.byId, "AI");
  assert.equal(storage.data["newsReader.selectedTopic"], "ai");
  const second = f7Setup({ storage });
  await second.instance.start();
  assert.deepEqual(second.byId.topics.children.map((r) => r.children[0].checked), [false, false, false, true]);
  assert.deepEqual(titlesOf(second.byId), ["SVT AI och natur", "Riksdagen AI-betänkande"]);
  for (const bad of ["sport", "", "AI", "Natur", '"ai"', "{}", "x".repeat(5000)]) {
    const t = f7Setup({ storage: fakeStorage({ "newsReader.selectedTopic": bad }) });
    await t.instance.start();
    assert.deepEqual(t.byId.topics.children.map((r) => r.children[0].checked), [false, true, false, false], bad);
  }
});

test("topics: only the allowed keys are written, with ids and nothing else (R18.3, N10)", async () => {
  const storage = fakeStorage();
  const { instance, byId } = f7Setup({ storage });
  await instance.start();
  pick(byId, "Natur");
  const box = rowOf(byId, "SVT").children[0];
  box.checked = false;
  box.fire("change");
  assert.deepEqual(Object.keys(storage.data).sort(),
    ["newsReader.lastNews", "newsReader.selectedSources", "newsReader.selectedTopic"]);
  assert.equal(storage.data["newsReader.selectedTopic"], "nature");
  assert.equal(storage.data["newsReader.selectedSources"], '["sveriges-radio","riksdagen"]');
});

test("migration: an old saved choice gets Riksdagen once, together with the topic Politik (R18.4, R16.9)", async () => {
  const storage = fakeStorage({ "newsReader.selectedSources": '["svt"]' });
  const { instance, byId } = f7Setup({ storage });
  await instance.start();
  assert.equal(storage.data["newsReader.selectedSources"], '["svt","riksdagen"]');
  assert.equal(storage.data["newsReader.selectedTopic"], "politics");
  assert.deepEqual(byId.sources.children.map((r) => r.children[0].checked), [true, false, true]);
  assert.deepEqual(titlesOf(byId), ["SVT politik", "Riksdagen proposition", "Riksdagen AI-betänkande"]);
  // The reader unticks Riksdagen: it stays unticked after a reload.
  const box = rowOf(byId, "Riksdagen").children[0];
  box.checked = false;
  box.fire("change");
  const again = f7Setup({ storage });
  await again.instance.start();
  assert.deepEqual(again.byId.sources.children.map((r) => r.children[0].checked), [true, false, false]);
  assert.equal(storage.data["newsReader.selectedSources"], '["svt"]');
});

test("migration: an unticked Riksdagen stays unticked when the page is opened again before any other change", async () => {
  // The migration wrote both keys at once, so a second visit sees a saved topic and does nothing.
  const storage = fakeStorage({ "newsReader.selectedSources": '["svt","sveriges-radio"]' });
  await f7Setup({ storage }).instance.start();
  storage.setItem("newsReader.selectedSources", '["svt","sveriges-radio"]');
  await f7Setup({ storage }).instance.start();
  assert.equal(storage.data["newsReader.selectedSources"], '["svt","sveriges-radio"]');
});

test("migration: skipped for an empty saved list, a list that has Riksdagen, a saved topic, no saved choice (R18.4)", async () => {
  const cases = [
    [{ "newsReader.selectedSources": "[]" }, "[]", undefined],
    [{ "newsReader.selectedSources": '["riksdagen","svt"]' }, '["riksdagen","svt"]', undefined],
    [{ "newsReader.selectedSources": '["svt"]', "newsReader.selectedTopic": "ai" }, '["svt"]', "ai"],
    [{}, undefined, undefined],
    [{ "newsReader.selectedSources": "not json" }, "not json", undefined],
  ];
  for (const [initial, selected, topic] of cases) {
    const storage = fakeStorage(initial);
    await f7Setup({ storage }).instance.start();
    assert.equal(storage.data["newsReader.selectedSources"], selected, JSON.stringify(initial));
    assert.equal(storage.data["newsReader.selectedTopic"], topic, JSON.stringify(initial));
  }
});

test("migration: nothing is added when Riksdagen is not an enabled source", async () => {
  const off = JSON.parse(JSON.stringify(riksdagenOn));
  off.sources.find((s) => s.id === "riksdagen").enabled = false;
  const storage = fakeStorage({ "newsReader.selectedSources": '["svt"]' });
  const { instance, byId } = setup({ files: { "sources.json": off, "news.json": newsFileF7() }, storage });
  await instance.start();
  assert.equal(storage.data["newsReader.selectedSources"], '["svt"]');
  assert.equal(storage.data["newsReader.selectedTopic"], undefined);
  assert.equal(byId.sources.children.length, 2);
  // Riksdagen items in the file are not shown when the source is off.
  assert.deepEqual(titlesOf(byId), ["SVT politik"]);
});

test("old state: a version 1 saved copy is read with Alla nyheter and Politik and works with the topic choice", async () => {
  const oldText = JSON.stringify({ ...newsFile(), sources: [{ id: "svt", name: "SVT", status: "ok",
    lastSuccess: "2026-11-13T13:05:12Z", itemCount: 2 }] });
  const storage = fakeStorage({ "newsReader.lastNews": oldText, "newsReader.selectedSources": '["svt"]' });
  const { instance, byId } = setup({ files: { "sources.json": riksdagenOn }, storage });
  await instance.start();
  assert.deepEqual(titlesOf(byId), ["Nyare rubrik om regeringen", "Äldre rubrik om riksdagen"]);
  assert.equal(statusOf(byId, "SVT"), "Hämtad, 2 rubriker"); // no feeds in a version 1 file: source-level status
  pick(byId, "Alla nyheter");
  assert.equal(titlesOf(byId).length, 2);
  pick(byId, "Natur");
  assert.deepEqual(titlesOf(byId), []);
  assert.equal(byId.empty.textContent, "Inga nyheter i ämnet Natur från valda källor.");
  assert.equal(byId.notices.children[0].textContent, "Offline – visar sparade nyheter från 2026-11-13 14:05");
});

test("topics: stale, offline and failure notices stay (R8.2, R8.3, R18.8)", async () => {
  const stale = newsFileF7();
  stale.generatedAt = "2026-11-13T09:00:00Z";
  const a = setup({ files: { "sources.json": riksdagenOn, "news.json": stale }, storage: fakeStorage() });
  await a.instance.start();
  assert.equal(a.byId.notices.children[0].textContent, "Nyheterna kan vara gamla – senast uppdaterade 2026-11-13 10:00");
  const b = setup({ files: { "sources.json": riksdagenOn }, storage: fakeStorage() });
  await b.instance.start();
  assert.equal(b.byId.notices.children[0].textContent, "Kunde inte hämta nyheter. Försök igen senare.");
  assert.equal(b.byId["topics-section"].hidden, false, "the topic choice still works for the Sveriges Radio items");
});

test("topics: a reload does not rebuild the radio buttons or the notices; the focus stays on the radio button", async () => {
  const { instance, byId, doc } = f7Setup();
  await instance.start();
  const first = radios(byId);
  first.focus();
  const container = byId.topics.children.slice();
  await instance.load("refresh");
  assert.equal(radios(byId), first);
  assert.deepEqual(byId.topics.children, container);
  assert.equal(doc.activeElement, first);
  pick(byId, "Natur");
  assert.equal(radios(byId), first, "choosing does not rebuild them either");
});

test("topics: a failing or blocked storage does not stop the choice", async () => {
  const storage = { getItem() { throw new Error("x"); }, setItem() { throw new Error("x"); } };
  const { instance, byId } = f7Setup({ storage });
  await instance.start();
  pick(byId, "Natur");
  assert.deepEqual(titlesOf(byId), ["SVT natur", "SVT AI och natur"]);
  const window = {};
  Object.defineProperty(window, "localStorage", { get() { throw new Error("blocked"); } });
  const other = f7Setup({ window });
  await other.instance.start();
  pick(other.byId, "AI");
  assert.equal(titlesOf(other.byId).length, 2);
});

test("topics: a sources.json without a topics list gives no choice and keeps Politik", async () => {
  const noTopics = JSON.parse(JSON.stringify(riksdagenOn));
  delete noTopics.topics;
  const { instance, byId } = setup({ files: { "sources.json": noTopics, "news.json": newsFileF7() }, storage: fakeStorage() });
  await instance.start();
  assert.equal(byId["topics-section"].hidden, true);
  assert.deepEqual(titlesOf(byId), ["SVT politik", "Riksdagen proposition", "Riksdagen AI-betänkande"]);
});

// The pure parts.

test("visibleItems: by topic membership, live items by their own topics (R18.2, F8)", () => {
  const news = app.validateNews(newsFileF7(), SOURCES_ON, NOW);
  const live = new Map([["sveriges-radio", [{ id: "l1", sourceId: "sveriges-radio", sourceName: "Sveriges Radio",
    title: "Ekot", url: "https://www.sverigesradio.se/artikel/9", published: "2026-11-13T13:20:00Z",
    publishedDisplay: "x", topics: ["all-news", "politics"] }]]]);
  const all = ["svt", "sveriges-radio", "riksdagen"];
  assert.deepEqual(app.visibleItems(news, all, live, "politics").map((i) => i.title),
    ["Ekot", "SVT politik", "Riksdagen proposition", "Riksdagen AI-betänkande"]);
  assert.ok(app.visibleItems(news, all, live, "all-news").some((i) => i.title === "Ekot"));
  for (const topic of ["nature", "ai"]) {
    assert.ok(!app.visibleItems(news, all, live, topic).some((i) => i.title === "Ekot"), topic);
  }
  // An item without a list of topics is in no topic.
  const bare = new Map([["sveriges-radio", [{ ...live.get("sveriges-radio")[0], topics: undefined }]]]);
  for (const topic of ["all-news", "politics", "nature", "ai"]) {
    assert.ok(!app.visibleItems(news, all, bare, topic).some((i) => i.title === "Ekot"), topic);
  }
  assert.deepEqual(app.visibleItems(news, all, live, "nature").map((i) => i.title), ["SVT natur", "SVT AI och natur"]);
  assert.deepEqual(app.visibleItems(news, ["riksdagen"], live, "nature"), []);
  assert.deepEqual(app.visibleItems(news, ["svt"], undefined, "sport"), []);
});

test("sourceRows: topics, credit and status by chosen topic", () => {
  const news = app.validateNews(newsFileF7(), SOURCES_ON, NOW);
  const topics = app.readTopicList(realSources);
  const rows = app.sourceRows(SOURCES_ON, news, ["svt", "riksdagen"], undefined, "nature", topics);
  assert.deepEqual(rows.map((r) => r.status), ["Hämtad, 2 rubriker", "Inte vald – ingen hämtning", "Erbjuder inte ämnet Natur"]);
  assert.equal(rows[2].credit, "Källa: Sveriges riksdag");
  assert.equal(rows[2].topics, "Ämnen: Alla nyheter, Politik, AI");
  assert.equal(rows[0].credit, "");
  assert.equal(app.sourceRows(SOURCES_ON, news, ["sveriges-radio"], undefined, "ai", topics)[1].status, "Inte hämtad ännu");
});

test("buildStatus: a failed feed of the chosen topic shows its own failure, other topics stay Hämtad", () => {
  const data = newsFileF7();
  const feed = data.sources[0].feeds.find((f) => f.topic === "nature");
  feed.status = "error";
  feed.lastSuccess = "2026-11-13T09:00:00Z";
  const news = app.validateNews(data, SOURCES_ON, NOW);
  assert.equal(app.sourceRows(SOURCES_ON, news, ["svt"], undefined, "nature")[0].status, "Kunde inte hämtas sedan 2026-11-13 10:00");
  assert.equal(app.sourceRows(SOURCES_ON, news, ["svt"], undefined, "ai")[0].status, "Hämtad, 1 rubrik");
});

test("bottomLine: credit and disclaimer only for a source with an item in the list", () => {
  const item = { sourceId: "riksdagen" };
  assert.ok(app.bottomLine(SOURCES_ON, [item]).endsWith(" Källa: Sveriges riksdag. " + app.DISCLAIMER_RIKSDAGEN));
  assert.ok(!app.bottomLine(SOURCES_ON, [{ sourceId: "svt" }]).includes("Källa"));
  assert.ok(!app.bottomLine(SOURCES_ON).includes("Källa"));
});

// ---------------------------------------------------------------- forbidden things

function read(name) {
  return fs.readFileSync(path.join(SITE, name), "utf8");
}

test("index.html: the Content-Security-Policy is exactly the intended one", () => {
  const html = read("index.html");
  const m = /<meta http-equiv="Content-Security-Policy" content="([^"]*)">/.exec(html);
  assert.ok(m, "CSP meta tag");
  assert.equal(m[1],
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self' https://api.sr.se; base-uri 'none'; form-action 'none'");
  assert.ok(!/\*/.test(m[1]) && !/unsafe/.test(m[1]));
  // Only connect-src names another site, and only the one that S11 needs.
  const other = m[1].split(";").map((d) => d.trim()).filter((d) => /https?:|\/\//.test(d));
  assert.deepEqual(other, ["connect-src 'self' https://api.sr.se"]);
});

test("index.html: the refresh button and Källor need the script", () => {
  const html = read("index.html");
  assert.match(html, /<button[^>]*id="refresh"[^>]*class="[^"]*needs-js/);
  assert.match(html, /<section id="sources-section"[^>]* hidden>/);
  assert.match(read("style.css"), /html:not\(\.js\) \.needs-js \{ display: none; \}/);
});

test("index.html: structure, language, noindex, no inline script or handler", () => {
  const html = read("index.html");
  assert.match(html, /<html lang="sv">/);
  assert.match(html, /<meta charset="utf-8">/);
  assert.match(html, /<meta name="robots" content="noindex">/);
  assert.match(html, /Content-Security-Policy/);
  assert.match(html, /<h2[^>]*>Källor<\/h2>/);
  assert.match(html, /<h2[^>]*>Ämnen<\/h2>/);
  assert.match(html, /<section id="topics-section"[^>]* hidden>/);
  assert.match(html, /<div id="topics"[^>]*role="radiogroup"/);
  assert.ok(html.indexOf("topics-section") < html.indexOf("sources-section"), "Ämnen above Källor");
  assert.ok(!/<script(?![^>]*\ssrc=)[^>]*>/i.test(html), "inline script");
  assert.ok(!/<script[^>]*>\s*\S/i.test(html.replace(/<script[^>]*src=[^>]*>\s*<\/script>/gi, "")), "script body");
  assert.ok(!/\son[a-z]+\s*=/i.test(html), "event handler attribute");
  assert.ok(!/javascript:/i.test(html));
  assert.ok(!/<style/i.test(html) && !/\sstyle\s*=/i.test(html), "inline style");
});

for (const name of ["index.html", "app.js", "atom.js", "style.css"]) {
  test(name + ": no forbidden constructs", () => {
    let text = read(name);
    // The two addresses that are allowed to appear: the one site named in the CSP
    // and the Atom namespace name (a name, never requested).
    if (name === "index.html") text = text.replace("https://api.sr.se", "");
    if (name === "atom.js") text = text.replace('"http://www.w3.org/2005/Atom"', "");
    const forbidden = [
      [/innerHTML|outerHTML|insertAdjacentHTML|document\.write/, "HTML injection"],
      [/\beval\s*\(|new\s+Function\s*\(|setTimeout\s*\(\s*["'`]|setInterval\s*\(\s*["'`]/, "eval"],
      [/https?:\/\//i, "absolute address"],
      [/(^|[^A-Za-z0-9_])\/\/[a-z0-9.-]+\.[a-z]{2,}\//i, "protocol-relative address"],
      [/serviceWorker/i, "service worker"],
      [/\bcaches\b|CacheStorage/, "Cache API"],
      [/sessionStorage|indexedDB|document\.cookie/, "other storage"],
      [/@import|url\(/, "css import or url"],
      [/XMLHttpRequest|sendBeacon|WebSocket|EventSource/, "other network API"],
      [/console\./, "console output"],
    ];
    for (const [re, what] of forbidden) {
      assert.ok(!re.test(text), name + " contains " + what);
    }
  });
}

test("app.js: only the own files are fetched by name; the feed address comes from sources.json", () => {
  const text = read("app.js");
  const calls = text.match(/fetchJson\("[^"]*"\)/g) || [];
  assert.deepEqual(calls.sort(), ['fetchJson("news.json")', 'fetchJson("sources.json")']);
  // The keyword files are fetched under the names that sources.json gives (F8), never by a name in the script.
  assert.deepEqual(text.match(/fetchJson\(entry\.keywords\)/g), ["fetchJson(entry.keywords)"]);
  assert.ok(!/-keywords\.json/.test(text.split("\n").filter((l) => !l.trim().startsWith("//")).join("\n").replace(/"-keywords\.json"/g, "")),
    "no keyword file name in app.js except the name rule");
  // One call of fetch for the own files, and the feed request goes through atom.js.
  assert.equal((text.match(/env\.fetch\(/g) || []).length, 1);
  assert.equal((text.match(/atom\.fetchAtom\(/g) || []).length, 1);
  assert.ok(!/sr\.se/i.test(text), "no Sveriges Radio address in app.js");
});

test("atom.js: no DOM rendering, no storage, no timers, no console", () => {
  const code = read("atom.js").split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
  for (const re of [/\bdocument\b/, /\bwindow\b/, /createElement|appendChild|textContent\s*=/,
    /localStorage|sessionStorage|indexedDB|\bcaches\b|cookie/, /setTimeout|setInterval|Date\.now/,
    /console/, /\bsr\.se\b/i]) {
    assert.ok(!re.test(code), "atom.js uses " + re);
  }
});

// ---------------------------------------------------------------- the real file: Riksdagen switched off (D41)

test("real sources.json (Riksdagen off, D41): all four topics are offered, no Riksdagen row, no migration, no credit", async () => {
  const storage = fakeStorage({ "newsReader.selectedSources": '["svt"]' });
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFileF7() }, storage });
  await instance.start();
  // SVT offers every topic, so the choice stays Alla nyheter, Politik, Natur, AI.
  assert.deepEqual(byId.topics.children.map((r) => r.children[1].textContent), ["Alla nyheter", "Politik", "Natur", "AI"]);
  assert.deepEqual(byId.sources.children.map((r) => r.children[1].textContent), ["SVT", "Sveriges Radio"]);
  assert.equal(byId.sources.children.some((r) => /Riksdag/.test(r.textContent)), false);
  // No migration: the saved choice is untouched and no topic is saved.
  assert.equal(storage.data["newsReader.selectedSources"], '["svt"]');
  assert.equal(storage.data["newsReader.selectedTopic"], undefined);
  // Riksdagen items in the file are not listed under any topic, and the bottom line has no credit.
  for (const label of ["Alla nyheter", "Politik", "Natur", "AI"]) {
    pick(byId, label);
    assert.equal(titlesOf(byId).some((t) => /^Riksdagen/.test(t)), false, label);
  }
  assert.equal(byId["bottom-line"].textContent,
    "Rubriker och länkar från SVT och Sveriges Radio. Klicka för att läsa hos källan.");
});
