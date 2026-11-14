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
const SOURCES = app.validateSources(realSources);
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
  assert.deepEqual(SOURCES.map((s) => s.id), ["svt", "sveriges-radio"]);
  assert.deepEqual(Object.keys(SVT).sort(), ["allowedHosts", "fetchedBy", "id", "method", "name"]);
  assert.equal(SVT.method, "keywordFilter");
  const off = JSON.parse(JSON.stringify(realSources));
  off.sources[1].enabled = false;
  assert.deepEqual(app.validateSources(off).map((s) => s.id), ["svt"]);
});

test("validateSources rejects unusable files", () => {
  for (const bad of [null, [], "x", {}, { version: 2, sources: [] }, { version: 1, sources: [] },
    { version: 1, sources: [{ id: 1 }] }, { version: 1, sources: "x" }]) {
    assert.equal(app.validateSources(bad), null);
  }
});

test("joinNames and the bottom line come from the source names", () => {
  assert.equal(app.joinNames(["SVT"]), "SVT");
  assert.equal(app.joinNames(["A", "B"]), "A och B");
  assert.equal(app.joinNames(["A", "B", "C"]), "A, B och C");
  assert.equal(
    app.bottomLine(SOURCES),
    "Rubriker och länkar från SVT och Sveriges Radio. Klicka för att läsa hos källan.");
});

// ---------------------------------------------------------------- news.json

test("validateNews returns a clean copy and recomputes time, name and id", () => {
  const news = app.validateNews(newsFile(), SOURCES, NOW);
  assert.equal(news.generatedAtDisplay, "2026-11-13 14:05");
  assert.equal(news.items.length, 2);
  const item = news.items[1];
  assert.deepEqual(Object.keys(item).sort(),
    ["id", "published", "publishedDisplay", "sourceId", "sourceName", "title", "url"]);
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
  for (const bad of [null, [], "x", 5, {}, { version: 2, generatedAt: "2026-11-13T13:05:12Z", items: [] },
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
    { kind: "offline", text: "Offline – visar sparade SVT-nyheter från 2026-11-13 14:05" }]);
  // Exactly 3 hours is not stale; one second more is.
  const generated = Date.parse("2026-11-13T13:05:12Z");
  assert.deepEqual(app.decideNotices(news, false, generated + 3 * 3600 * 1000), []);
  assert.deepEqual(app.decideNotices(news, false, generated + 3 * 3600 * 1000 + 1000), [
    { kind: "stale", text: "SVT-nyheterna kan vara gamla – senast uppdaterade 2026-11-13 14:05" }]);
  const both = app.decideNotices(news, true, generated + 4 * 3600 * 1000);
  assert.deepEqual(both.map((n) => n.kind), ["offline", "stale"]);
});

test("sourceRows: note, checkbox and status (R4.6, R6.2)", () => {
  const news = app.validateNews(newsFile(), SOURCES, NOW);
  let rows = app.sourceRows(SOURCES, news, ["svt"]);
  assert.deepEqual(rows[0], {
    id: "svt", name: "SVT", checked: true, note: "Urval med nyckelord – ungefärligt",
    status: "Hämtad, 2 rubriker",
  });
  assert.equal(rows[1].checked, false);
  assert.equal(rows[1].note, "Urval med nyckelord – ungefärligt");
  assert.equal(rows[1].status, "Inte hämtad ännu"); // no live state yet (S11)
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
  const ids = ["updated", "refresh", "notices", "headlines", "empty", "sources", "sources-section", "bottom-line"];
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
  assert.equal(byId.updated.textContent, "SVT uppdaterad 2026-11-13 14:05");
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
  assert.equal(rows.length, 2);
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
  const svtBox = byId.sources.children[0].children[0];
  svtBox.checked = false;
  svtBox.fire("change");
  assert.deepEqual(headlinesOf(byId), []);
  assert.equal(byId.empty.hidden, false);
  assert.equal(byId.empty.textContent, "Inga nyheter från valda källor.");
  assert.equal(storage.data["newsReader.selectedSources"], '["sveriges-radio"]');
  svtBox.checked = true;
  svtBox.fire("change");
  assert.equal(headlinesOf(byId).length, 2);
  assert.equal(byId.empty.hidden, true);
  assert.equal(storage.data["newsReader.selectedSources"], '["svt","sveriges-radio"]');
});

test("page: a saved choice is used, unknown saved ids are dropped on the next change (R3.5)", async () => {
  const storage = fakeStorage({ "newsReader.selectedSources": '["gone","svt"]' });
  const { instance, byId } = setup({ files: { "sources.json": realSources, "news.json": newsFile() }, storage });
  await instance.start();
  assert.equal(byId.sources.children[0].children[0].checked, true);
  assert.equal(byId.sources.children[1].children[0].checked, false);
  byId.sources.children[1].children[0].checked = true;
  byId.sources.children[1].children[0].fire("change");
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
  assert.equal(byId.notices.children[0].textContent, "Offline – visar sparade SVT-nyheter från 2026-11-13 14:05");
  assert.equal(byId.updated.textContent, "SVT uppdaterad 2026-11-13 14:05");
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
    "SVT-nyheterna kan vara gamla – senast uppdaterade 2026-11-13 10:00");
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
    ["news.json", "politics-keywords.json", "sources.json"]);
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
  assert.deepEqual(calls.sort(),
    ['fetchJson("news.json")', 'fetchJson("politics-keywords.json")', 'fetchJson("sources.json")']);
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
