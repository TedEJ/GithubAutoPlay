// node --test for the live fetch of the page (step S11): call limits with a fake
// clock and a fake fetch, failure statuses, "nothing is logged", "nothing is
// stored", and the merge with the SVT items. Hand-written, made-up content only;
// no network (the fake fetch is the only way out) and no browser.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import app from "../app.js";
import { fakePage } from "./fake-page.mjs";
import { FakeDOMParser } from "./xml-fake.mjs";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const realSources = JSON.parse(fs.readFileSync(path.join(ROOT, "sources.json"), "utf8"));
const keywordFile = JSON.parse(fs.readFileSync(path.join(ROOT, "politics-keywords.json"), "utf8"));
const FEED_URL = realSources.sources.find((s) => s.id === "sveriges-radio")["politics-sweden"].url;

const NOW = Date.parse("2026-11-13T13:30:00Z");
const MIN = 60 * 1000;
const NS = "http://www.w3.org/2005/Atom";
const SR_MARK = "SRMARK";

// ---------------------------------------------------------------- fixtures

function srEntry(title, n, published, summary = "Kort text.") {
  return "<entry><id>tag:example:" + n + "</id><title>" + title + "</title><summary>" + summary + "</summary>"
    + '<link rel="alternate" href="https://www.sverigesradio.se/artikel/' + (900000 + n) + '"/>'
    + "<published>" + published + "</published><updated>" + published + "</updated>"
    + "<content type=\"html\">" + SR_MARK + "-BRÖDTEXT</content></entry>";
}

function srFeed() {
  return '<?xml version="1.0" encoding="utf-8"?><feed xmlns="' + NS + '"><title>Ekot (test)</title>'
    + srEntry("Riksdagen debatterar " + SR_MARK + " ett", 1, "2026-11-13T13:20:00+01:00")
    + srEntry("Sport utan politik " + SR_MARK + " två", 2, "2026-11-13T13:21:00+01:00", "Fotboll.")
    + srEntry("Regeringen svarar " + SR_MARK + " tre", 3, "2026-11-13T12:50:00Z")
    + srEntry("Intetsägande rubrik " + SR_MARK + " fyra", 4, "2026-11-13T13:22:00+01:00", "Handlar om statsministern.")
    + "</feed>";
}

function newsFile() {
  return {
    version: 1,
    generatedAt: "2026-11-13T13:05:12Z",
    generatedAtDisplay: "2026-11-13 14:05",
    category: "politics-sweden",
    sources: [{ id: "svt", name: "SVT", status: "ok", lastSuccess: "2026-11-13T13:05:12Z", itemCount: 2 }],
    items: [
      { id: "x", sourceId: "svt", sourceName: "SVT", title: "SVT: rubrik om riksdagen",
        url: "https://www.svt.se/nyheter/inrikes/a", published: "2026-11-13T11:00:00Z", publishedDisplay: "" },
      { id: "y", sourceId: "svt", sourceName: "SVT", title: "SVT: rubrik om regeringen",
        url: "https://www.svt.se/nyheter/inrikes/b", published: "2026-11-13T12:55:00Z", publishedDisplay: "" },
    ],
  };
}

// ---------------------------------------------------------------- the fake page

function fakeStorage(initial = {}) {
  const data = { ...initial };
  const writes = [];
  return {
    data,
    writes,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { writes.push([k, String(v)]); data[k] = String(v); },
    removeItem: (k) => { writes.push([k, null]); delete data[k]; },
  };
}

// Every other way of keeping something is a spy that records any access.
function spyWindow(storage) {
  const touched = [];
  const win = { localStorage: storage };
  for (const name of ["sessionStorage", "indexedDB", "caches", "cookieStore", "navigator", "history"]) {
    Object.defineProperty(win, name, { get() { touched.push(name); return undefined; } });
  }
  return { win, touched };
}

function setup(options = {}) {
  const { doc, byId } = fakePage();
  const cookies = [];
  Object.defineProperty(doc, "cookie", { get() { cookies.push("get"); return ""; }, set(v) { cookies.push(v); } });
  const storage = options.storage || fakeStorage();
  const { win, touched } = spyWindow(storage);
  const clock = { now: NOW };
  const timers = [];
  const intervals = [];
  const calls = []; // every request: [url, init]
  const state = {
    files: { "sources.json": realSources, "news.json": newsFile(), "politics-keywords.json": keywordFile },
    feed: { body: srFeed(), status: 200, throws: false, gate: null, headers: {}, raw: null },
    ...options,
  };
  const env = {
    document: doc,
    window: win,
    now: () => clock.now,
    setInterval: (fn, ms) => { intervals.push({ fn, ms }); return intervals.length; },
    setTimeout: (fn, ms) => { timers.push({ fn, ms, cleared: false }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].cleared = true; },
    AbortController,
    DOMParser: FakeDOMParser,
    fetch: async (url, init) => {
      calls.push([url, init]);
      if (url === FEED_URL) {
        const feed = state.feed;
        if (feed.gate) await feed.gate;
        if (feed.throws) throw new TypeError("Failed to fetch " + SR_MARK + "-DETALJ");
        if (init && init.signal) {
          await new Promise((resolve, reject) => {
            if (init.signal.aborted) reject(new DOMException("aborted", "AbortError"));
            else if (!feed.hang) resolve();
            else init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          });
        }
        if (feed.raw) return feed.raw();
        return new Response(feed.body, { status: feed.status, headers: feed.headers });
      }
      if (state.gate) await state.gate;
      const body = state.files[url];
      if (body === undefined) return { ok: false, status: 404, text: async () => "" };
      return { ok: true, status: 200, text: async () => (typeof body === "string" ? body : JSON.stringify(body)) };
    },
  };
  const instance = app.createApp(env);
  const feedCalls = () => calls.filter(([u]) => u === FEED_URL);
  const wait = () => new Promise((r) => setImmediate(r));
  return { instance, byId, doc, calls, feedCalls, clock, timers, intervals, storage, touched, cookies, state, wait };
}

function headlines(byId) {
  return byId.headlines.children.map((li) => li.children[0].textContent);
}

function metas(byId) {
  return byId.headlines.children.map((li) => li.children[1].children[0].textContent);
}

function srRow(byId) {
  return byId.sources.children[1].textContent;
}

// Console spy: any call to any console method is a failure of the test.
function spyConsole() {
  const seen = [];
  const names = ["log", "info", "warn", "error", "debug", "trace", "dir", "table", "assert", "count", "time", "timeEnd"];
  const saved = {};
  for (const name of names) {
    saved[name] = console[name];
    console[name] = (...args) => { seen.push([name, args.map(String).join(" ")]); };
  }
  return { seen, restore() { for (const name of names) console[name] = saved[name]; } };
}

async function withSpy(fn) {
  const spy = spyConsole();
  try {
    await fn();
  } finally {
    spy.restore();
  }
  assert.deepEqual(spy.seen, [], "nothing was written to the console");
}

// ---------------------------------------------------------------- display

test("the SR items appear with the source name, merged with SVT, newest first, selected by the shared keywords", async () => {
  const t = setup();
  await t.instance.start();
  // Kept: 1 (riksdagen, title), 3 (regeringen, title), 4 (statsministern, only in
  // the summary). Dropped: 2 (sport).
  // Sorted by time (newest first): 12:55 SVT, 12:50 SR, 12:22 SR, 12:20 SR, 11:00 SVT.
  const order = [
    ["SVT: rubrik om regeringen", "SVT"],
    ["Regeringen svarar SRMARK tre", "Sveriges Radio"],
    ["Intetsägande rubrik SRMARK fyra", "Sveriges Radio"],
    ["Riksdagen debatterar SRMARK ett", "Sveriges Radio"],
    ["SVT: rubrik om riksdagen", "SVT"],
  ];
  assert.deepEqual(headlines(t.byId).map((h, i) => [h, metas(t.byId)[i]]), order);
  // The summary and the content are not on the page.
  const all = t.byId.headlines.children.map((li) => li.textContent).join(" ");
  assert.ok(!all.includes("BRÖDTEXT") && !all.includes("Handlar om") && !all.includes("Kort text"));
  // Link and time of an SR item.
  const li = t.byId.headlines.children[1];
  assert.equal(li.children[0].attrs.href, "https://www.sverigesradio.se/artikel/900003");
  assert.equal(li.children[0].attrs.target, "_blank");
  assert.equal(li.children[0].attrs.rel, "noopener noreferrer");
  assert.deepEqual(li.children[1].children.map((c) => c.textContent), ["Sveriges Radio", " · ", "2026-11-13 13:50"]);
  assert.equal(li.children[0].children.length, 0, "the headline is text");
});

test("the status of the source: fetched time and count in Källor, and in the line at the top", async () => {
  const t = setup();
  await t.instance.start();
  assert.match(srRow(t.byId), /Sveriges Radio/);
  assert.match(srRow(t.byId), /Urval med nyckelord – ungefärligt/);
  assert.match(srRow(t.byId), /Hämtad 14:30, 3 rubriker/);
  assert.equal(t.byId.updated.textContent, "SVT uppdaterad 2026-11-13 14:05 · Sveriges Radio hämtad 14:30");
  assert.equal(t.byId["bottom-line"].textContent,
    "Rubriker och länkar från SVT och Sveriges Radio. Klicka för att läsa hos källan.");
});

test("a headline is shown as given: entities decoded, tags and white space tidied, never cut", async () => {
  const long = "Regeringen " + "mycket ".repeat(200) + "slut";
  const t = setup();
  t.state.feed.body = '<feed xmlns="' + NS + '">'
    + srEntry("  Riksdagen &amp; &lt;b&gt;regeringen&lt;/b&gt;\n  &#229;&#228;&#246;  ", 1, "2026-11-13T13:20:00Z")
    + srEntry(long, 2, "2026-11-13T13:19:00Z") + "</feed>";
  await t.instance.start();
  const got = headlines(t.byId).filter((h) => !h.startsWith("SVT"));
  assert.deepEqual(got, ["Riksdagen & regeringen åäö", long]);
});

test("unticking Sveriges Radio hides and drops its items; ticking again within 5 minutes makes no request", async () => {
  const t = setup();
  await t.instance.start();
  const box = t.byId.sources.children[1].children[0];
  box.checked = false;
  box.fire("change");
  assert.deepEqual(headlines(t.byId), ["SVT: rubrik om regeringen", "SVT: rubrik om riksdagen"]);
  assert.equal(t.instance.state.live.get("sveriges-radio").items.length, 0, "dropped from memory");
  box.checked = true;
  box.fire("change");
  await t.wait(); await t.wait();
  assert.equal(t.feedCalls().length, 1, "the 5-minute rule holds between any two requests");
  assert.deepEqual(headlines(t.byId).length, 2, "nothing is held, so nothing is shown yet");
  assert.match(srRow(t.byId), /Inte hämtad ännu/);
  // After 5 minutes, ticking again fetches.
  box.checked = false; box.fire("change");
  t.clock.now += 5 * MIN;
  box.checked = true; box.fire("change");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2);
  assert.equal(headlines(t.byId).length, 5);
});

test("only Sveriges Radio chosen: its items alone; nothing matching gives the empty notice, not while it loads", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const t = setup({ storage: fakeStorage({ "newsReader.selectedSources": '["sveriges-radio"]' }) });
  t.state.feed.gate = gate;
  const started = t.instance.start();
  await t.wait();
  await t.wait();
  assert.equal(t.byId.empty.hidden, true, "no empty notice while the chosen source is being fetched");
  assert.match(srRow(t.byId), /Hämtar …/);
  release();
  await started;
  assert.deepEqual(headlines(t.byId).length, 3);
  assert.equal(t.byId.empty.hidden, true);

  const t2 = setup({ storage: fakeStorage({ "newsReader.selectedSources": '["sveriges-radio"]' }) });
  t2.state.feed.body = '<feed xmlns="' + NS + '">' + srEntry("Sport", 1, "2026-11-13T13:20:00Z", "Fotboll") + "</feed>";
  await t2.instance.start();
  assert.equal(t2.byId.empty.hidden, false);
  assert.equal(t2.byId.empty.textContent, "Inga nyheter från valda källor.");
});

test("the SVT items are shown when Sveriges Radio is still being fetched (SVT never waits for it)", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const t = setup();
  t.state.feed.gate = gate;
  const started = t.instance.start();
  for (let i = 0; i < 20; i++) await t.wait();
  assert.deepEqual(headlines(t.byId), ["SVT: rubrik om regeringen", "SVT: rubrik om riksdagen"]);
  assert.match(srRow(t.byId), /Hämtar …/);
  release();
  await started;
  assert.equal(headlines(t.byId).length, 5);
});

test("SR finishing before news.json does not draw an error for SVT in between", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const t = setup();
  t.state.gate = gate; // holds sources.json and news.json and the keyword list
  const started = t.instance.start();
  await t.wait();
  release();
  await started;
  assert.equal(t.byId.notices.children.length, 0);
  assert.equal(headlines(t.byId).length, 5);
});

// ---------------------------------------------------------------- the request

test("the request: the address from sources.json, credentials omit, cache no-store (R7.1)", async () => {
  const t = setup();
  await t.instance.start();
  assert.equal(FEED_URL, "https://api.sr.se/api/rss/program/83");
  assert.equal(t.feedCalls().length, 1);
  const [url, init] = t.feedCalls()[0];
  assert.equal(url, FEED_URL);
  assert.equal(init.credentials, "omit");
  assert.equal(init.cache, "no-store");
  assert.equal(init.referrerPolicy, "no-referrer", "the address of the page is not sent");
  assert.deepEqual(Object.keys(init).sort(), ["cache", "credentials", "referrerPolicy", "signal"]);
  // The timeout is 15 seconds and is cleared when the request ends.
  const timer = t.timers.find((x) => x.ms === 15000);
  assert.ok(timer);
  assert.equal(timer.cleared, true);
  // Nothing else is requested from anywhere else.
  const other = t.calls.map(([u]) => u).filter((u) => u !== FEED_URL).sort();
  assert.deepEqual(other, ["news.json", "politics-keywords.json", "sources.json"]);
});

test("a source without a usable https address is never requested and shows the failure status", async () => {
  const t = setup();
  const files = JSON.parse(JSON.stringify(realSources));
  files.sources[1]["politics-sweden"].url = "http://api.sr.se/api/rss/program/83";
  t.state.files["sources.json"] = files;
  await t.instance.start();
  assert.equal(t.feedCalls().length, 0);
  assert.equal(t.calls.filter(([u]) => /sr\.se/.test(u)).length, 0);
  assert.match(srRow(t.byId), /Sveriges Radio kunde inte hämtas just nu/);
  assert.equal(headlines(t.byId).length, 2);
});

test("a source with enabled false is not requested (R3.4)", async () => {
  const t = setup();
  const files = JSON.parse(JSON.stringify(realSources));
  files.sources[1].enabled = false;
  t.state.files["sources.json"] = files;
  await t.instance.start();
  assert.equal(t.feedCalls().length, 0);
  assert.equal(t.calls.filter(([u]) => u === "politics-keywords.json").length, 0);
});

test("the timeout aborts the request and gives the failure status", async () => {
  const t = setup();
  t.state.feed.hang = true;
  const started = t.instance.start();
  for (let i = 0; i < 20; i++) await t.wait();
  const timer = t.timers.find((x) => x.ms === 15000 && !x.cleared);
  assert.ok(timer, "a running timeout of 15 seconds");
  timer.fn();
  await started;
  assert.match(srRow(t.byId), /Sveriges Radio kunde inte hämtas just nu/);
  assert.equal(headlines(t.byId).length, 2);
});

// ---------------------------------------------------------------- call limits (R7.2)

test("one request when the page opens, not more", async () => {
  const t = setup();
  await t.instance.start();
  assert.equal(t.feedCalls().length, 1);
  await t.instance.load();
  await t.instance.load();
  assert.equal(t.feedCalls().length, 1, "reloads of SVT do not call Sveriges Radio inside 5 minutes");
});

test("Uppdatera: SVT is reloaded at once; Sveriges Radio only when 5 minutes have passed since its last request", async () => {
  const t = setup();
  await t.instance.start();
  const newsCalls = () => t.calls.filter(([u]) => u === "news.json").length;
  const button = t.byId.refresh;
  button.fire("click");
  await t.wait(); await t.wait();
  assert.equal(newsCalls(), 2);
  assert.equal(t.feedCalls().length, 1);
  t.clock.now += 5 * MIN - 1;
  button.fire("click");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(newsCalls(), 3);
  assert.equal(t.feedCalls().length, 1, "4 minutes 59.999 seconds is not enough");
  t.clock.now += 1;
  button.fire("click");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(newsCalls(), 4);
  assert.equal(t.feedCalls().length, 2);
  // And again at once: no.
  button.fire("click");
  button.fire("click");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2);
});

test("the 10-minute timer: SVT every time, Sveriges Radio at most every 10 minutes and never within 5 minutes of a request", async () => {
  const t = setup();
  await t.instance.start();
  assert.equal(t.intervals.length, 1);
  assert.equal(t.intervals[0].ms, 10 * MIN);
  const tick = async () => { t.intervals[0].fn(); for (let i = 0; i < 10; i++) await t.wait(); };
  // 5 minutes after opening the reader presses Uppdatera: a request.
  t.clock.now += 5 * MIN;
  t.byId.refresh.fire("click");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2);
  // The timer fires 10 minutes after opening, 5 minutes after that request: no request.
  t.clock.now += 5 * MIN;
  await tick();
  assert.equal(t.feedCalls().length, 2);
  assert.equal(t.calls.filter(([u]) => u === "news.json").length, 3, "SVT was reloaded");
  // 20 minutes after opening, 15 minutes after the last request: a request.
  t.clock.now += 10 * MIN;
  await tick();
  assert.equal(t.feedCalls().length, 3);
  // A tick 9 minutes later (a timer that fires early): no request.
  t.clock.now += 9 * MIN;
  await tick();
  assert.equal(t.feedCalls().length, 3);
  t.clock.now += 1 * MIN;
  await tick();
  assert.equal(t.feedCalls().length, 4);
});

test("all the requests of a long session are at least 5 minutes apart, whatever the order of the triggers", async () => {
  const t = setup();
  const times = [];
  const baseFetch = t.calls;
  await t.instance.start();
  times.push(t.clock.now);
  let seed = 7;
  const random = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  const startTimes = [];
  for (let step = 0; step < 300; step++) {
    t.clock.now += Math.floor(random() * 4 * MIN);
    const before = t.feedCalls().length;
    const r = random();
    if (r < 0.3) t.byId.refresh.fire("click");
    else if (r < 0.5) t.intervals[0].fn();
    else if (r < 0.7) { t.doc.hidden = !t.doc.hidden; t.doc.fire("visibilitychange"); }
    else if (r < 0.8) t.doc.fire("visibilitychange");
    else t.instance.load();
    for (let i = 0; i < 10; i++) await t.wait();
    if (t.feedCalls().length > before) {
      assert.equal(t.doc.hidden, false, "no request while the tab is hidden");
      startTimes.push(t.clock.now);
    }
  }
  assert.ok(startTimes.length > 5);
  for (let i = 1; i < startTimes.length; i++) {
    assert.ok(startTimes[i] - startTimes[i - 1] >= 5 * MIN, "requests " + i + " were too close");
  }
  assert.ok(startTimes[0] - times[0] >= 5 * MIN);
  assert.ok(baseFetch.length > 0);
});

test("hidden tab: no request from the timer, from Uppdatera or when the tab is opened hidden; one when it is visible", async () => {
  const t = setup();
  t.doc.hidden = true;
  await t.instance.start();
  assert.equal(t.feedCalls().length, 0, "the page was opened in a hidden tab: wait");
  assert.match(srRow(t.byId), /Inte hämtad ännu/);
  assert.equal(headlines(t.byId).length, 2, "SVT is still shown");
  t.clock.now += 30 * MIN;
  t.intervals[0].fn();
  t.doc.fire("visibilitychange"); // still hidden
  t.byId.refresh.fire("click");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 0);
  t.doc.hidden = false;
  t.doc.fire("visibilitychange");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 1);
  assert.equal(headlines(t.byId).length, 5);
  // Visible again events right after: nothing more.
  t.doc.fire("visibilitychange");
  t.doc.fire("visibilitychange");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 1);
});

test("a tab hidden for a long time: nothing while hidden, one request at once when visible (10 minutes passed)", async () => {
  const t = setup();
  await t.instance.start();
  t.doc.hidden = true;
  for (let k = 0; k < 6; k++) {
    t.clock.now += 10 * MIN;
    t.intervals[0].fn();
  }
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 1);
  t.doc.hidden = false;
  t.doc.fire("visibilitychange");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2);
  // Hidden for 4 minutes only: visible again does not request.
  t.doc.hidden = true;
  t.clock.now += 4 * MIN;
  t.doc.hidden = false;
  t.doc.fire("visibilitychange");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2);
});

test("overlapping: a request that is still running is not repeated by any trigger", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const t = setup();
  t.state.feed.gate = gate;
  const started = t.instance.start();
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 1);
  t.clock.now += 20 * MIN; // the request is "slow": every limit has passed
  t.byId.refresh.fire("click");
  t.intervals[0].fn();
  t.doc.fire("visibilitychange");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 1, "still one request");
  release();
  await started;
  assert.equal(t.feedCalls().length, 1);
});

test("a failed request is not retried before the next allowed time (R7.6)", async () => {
  const t = setup();
  t.state.feed.status = 500;
  await t.instance.start();
  assert.equal(t.feedCalls().length, 1);
  for (let k = 0; k < 4; k++) {
    t.clock.now += 1 * MIN;
    t.byId.refresh.fire("click");
    for (let i = 0; i < 10; i++) await t.wait();
  }
  assert.equal(t.feedCalls().length, 1);
  t.clock.now += 1 * MIN;
  t.state.feed.status = 200;
  t.byId.refresh.fire("click");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2);
  assert.match(srRow(t.byId), /Hämtad/);
});

test("the first timer tick calls SR even when sources.json was slow (the first request is stamped a little after the timer started)", async () => {
  const t = setup();
  // Reading sources.json takes 2 seconds on the fake clock.
  const inner = t.state.files["sources.json"];
  t.state.files["sources.json"] = { get version() { t.clock.now += 2000; return inner.version; }, sources: inner.sources };
  const start = t.clock.now;
  await t.instance.start();
  assert.equal(t.feedCalls().length, 1);
  assert.ok(t.clock.now - start >= 2000, "the delay happened");
  t.clock.now = start + 10 * MIN; // the first tick of the 10-minute timer
  t.intervals[0].fn();
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2, "SR is refreshed at the first tick");
  // Not more often: Uppdatera and a visible-again right after, and a second tick 5 minutes later.
  t.byId.refresh.fire("click");
  t.doc.fire("visibilitychange");
  t.clock.now += 5 * MIN;
  t.intervals[0].fn();
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2);
});

test("no request when sources.json cannot be read", async () => {
  const t = setup();
  delete t.state.files["sources.json"];
  await t.instance.start();
  assert.equal(t.feedCalls().length, 0);
});

// ---------------------------------------------------------------- failures

const FAILURES = {
  "network error": (s) => { s.feed.throws = true; },
  "status 500": (s) => { s.feed.status = 500; s.feed.body = "SRMARK-felsida"; },
  "status 404": (s) => { s.feed.status = 404; },
  "status 204": (s) => { s.feed.status = 204; s.feed.body = null; },
  "parse error": (s) => { s.feed.body = "<feed xmlns=\"" + NS + "\"><entry><title>SRMARK-trasig"; },
  "not Atom": (s) => { s.feed.body = '<rss version="2.0"><channel><item><title>SRMARK</title></item></channel></rss>'; },
  "not XML": (s) => { s.feed.body = "<html><body>SRMARK</body></html>"; },
  "a DOCTYPE": (s) => { s.feed.body = '<!DOCTYPE x [<!ENTITY a "SRMARK">]>' + srFeed(); },
  "oversize": (s) => { s.feed.body = srFeed() + " ".repeat(2 * 1024 * 1024 + 10); },
  "oversize by header": (s) => { s.feed.headers = { "content-length": String(50 * 1024 * 1024) }; },
  "no usable item": (s) => { s.feed.body = '<feed xmlns="' + NS + '"><entry><title>Riksdagen</title></entry></feed>'; },
};

for (const [name, apply] of Object.entries(FAILURES)) {
  test("failure (" + name + "): the SVT items stay, the status says so, nothing in the console", async () => {
    await withSpy(async () => {
      const t = setup();
      apply(t.state);
      await t.instance.start();
      if (name === "no usable item") {
        // A feed that parses but has nothing to show is a success with no items.
        assert.match(srRow(t.byId), /Hämtad 14:30, 0 rubriker/);
      } else {
        assert.match(srRow(t.byId), /Sveriges Radio kunde inte hämtas just nu/);
        assert.ok(!t.byId.updated.textContent.includes("Sveriges Radio hämtad"));
      }
      assert.deepEqual(headlines(t.byId), ["SVT: rubrik om regeringen", "SVT: rubrik om riksdagen"]);
      assert.equal(t.byId.notices.children.length, 0, "no notice about SVT");
      const page = [t.byId.notices, t.byId.headlines, t.byId.sources, t.byId.updated, t.byId.empty]
        .map((n) => n.textContent).join(" ");
      assert.ok(!page.includes("SRMARK"), "nothing from the failed response is on the page");
    });
  });
}

test("a failure after a success removes the old items (nothing stale is shown) and says so; SVT stays", async () => {
  const t = setup();
  await t.instance.start();
  assert.equal(headlines(t.byId).length, 5);
  t.state.feed.status = 500;
  t.clock.now += 10 * MIN;
  t.intervals[0].fn();
  for (let i = 0; i < 10; i++) await t.wait();
  assert.deepEqual(headlines(t.byId), ["SVT: rubrik om regeringen", "SVT: rubrik om riksdagen"]);
  assert.match(srRow(t.byId), /Sveriges Radio kunde inte hämtas just nu/);
});

test("the keyword list cannot be read: the source fails, no request goes to the feed", async () => {
  for (const bad of [undefined, "<html>", { version: 1 }, { version: 1, category: "politics-sweden", include: "x" }]) {
    const t = setup();
    if (bad === undefined) delete t.state.files["politics-keywords.json"];
    else t.state.files["politics-keywords.json"] = bad;
    await t.instance.start();
    assert.equal(t.feedCalls().length, 0);
    assert.match(srRow(t.byId), /Sveriges Radio kunde inte hämtas just nu/);
    assert.equal(headlines(t.byId).length, 2);
  }
});

test("SVT fails and Sveriges Radio works: the saved SVT copy with its notice, and the SR items", async () => {
  const storage = fakeStorage();
  const first = setup({ storage });
  await first.instance.start();
  const t = setup({ storage });
  delete t.state.files["news.json"];
  await t.instance.start();
  assert.match(t.byId.notices.children[0].textContent, /^Offline – visar sparade SVT-nyheter/);
  assert.equal(headlines(t.byId).length, 5);
});

test("SVT fails with no saved copy and Sveriges Radio works: the error notice, and the SR items", async () => {
  const t = setup();
  delete t.state.files["news.json"];
  await t.instance.start();
  assert.equal(t.byId.notices.children[0].textContent, "Kunde inte hämta nyheter. Försök igen senare.");
  assert.equal(headlines(t.byId).length, 3);
  assert.deepEqual(metas(t.byId), ["Sveriges Radio", "Sveriges Radio", "Sveriges Radio"]);
});

// ---------------------------------------------------------------- nothing is logged, nothing is stored

test("no console output at all on success, on every failure, and with hostile content", async () => {
  await withSpy(async () => {
    const hostile = '<feed xmlns="' + NS + '">'
      + srEntry("&lt;img src=x onerror=alert(1)&gt; Riksdagen &lt;script&gt;alert(2)&lt;/script&gt;", 1, "2026-11-13T13:20:00Z")
      + srEntry("Regeringen", 2, "javascript:alert(3)")
      + "<entry><title>Riksdagen</title><link href=\"javascript:alert(4)\"/></entry></feed>";
    for (const apply of [() => {}, (s) => { s.feed.body = hostile; }, ...Object.values(FAILURES)]) {
      const t = setup();
      apply(t.state);
      await t.instance.start();
      t.clock.now += 10 * MIN;
      t.intervals[0].fn();
      for (let i = 0; i < 10; i++) await t.wait();
    }
  });
});

test("the failure status names the source and says nothing about the kind of failure or the content", async () => {
  for (const [name, apply] of Object.entries(FAILURES)) {
    if (name === "no usable item") continue;
    const t = setup();
    apply(t.state);
    await t.instance.start();
      const row = srRow(t.byId).replace("Urval med nyckelord – ungefärligt", "");
    assert.equal(row, "Sveriges Radio" + "Sveriges Radio kunde inte hämtas just nu", name);
  }
});

test("memory only: nothing from Sveriges Radio is written to localStorage, sessionStorage, IndexedDB, cookies or the Cache API", async () => {
  const t = setup();
  await t.instance.start();
  t.clock.now += 6 * MIN;
  t.byId.refresh.fire("click");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 2);
  assert.equal(headlines(t.byId).length, 5);
  // Only the two known keys were written, and nothing in them is from SR.
  const keys = new Set(t.storage.writes.map(([k]) => k));
  assert.deepEqual([...keys].sort(), ["newsReader.lastNews"]);
  const everything = JSON.stringify(t.storage.writes) + JSON.stringify(t.storage.data);
  for (const bad of [SR_MARK, "sverigesradio", "Sveriges Radio", "sveriges-radio", "api.sr.se", "BRÖDTEXT", "Handlar om", "Riksdagen debatterar"]) {
    assert.ok(!everything.includes(bad), "storage holds " + bad);
  }
  const saved = JSON.parse(t.storage.data["newsReader.lastNews"]);
  assert.deepEqual([...new Set(saved.items.map((i) => i.sourceId))], ["svt"]);
  assert.deepEqual(t.touched, [], "no other storage object was even looked at");
  assert.deepEqual(t.cookies, [], "no cookie was read or written");
});

test("memory only: choosing sources writes only the ids; the saved copy after a failed SVT load has no SR item", async () => {
  const storage = fakeStorage();
  const first = setup({ storage });
  await first.instance.start();
  const box = first.byId.sources.children[1].children[0];
  box.checked = false;
  box.fire("change");
  box.checked = true;
  box.fire("change");
  assert.equal(storage.data["newsReader.selectedSources"], '["svt","sveriges-radio"]');
  // A new page that cannot read news.json shows the saved copy: SVT only, plus the live SR items.
  const second = setup({ storage });
  delete second.state.files["news.json"];
  await second.instance.start();
  const saved = JSON.stringify(storage.data);
  assert.ok(!saved.includes(SR_MARK) && !saved.includes("sverigesradio"));
});

test("storage that throws: the live items still work and nothing is retried against storage", async () => {
  const storage = { getItem() { throw new Error("x"); }, setItem() { throw new Error("x"); } };
  const t = setup({ storage });
  await t.instance.start();
  assert.equal(headlines(t.byId).length, 5);
});

test("a hostile news.json cannot bring SR items into the saved copy or the page", async () => {
  const t = setup();
  const data = newsFile();
  data.items.push({ id: "z", sourceId: "sveriges-radio", sourceName: "Sveriges Radio", title: "SRMARK-ur-fil",
    url: "https://www.sverigesradio.se/artikel/1", published: "2026-11-13T13:00:00Z", publishedDisplay: "" });
  t.state.files["news.json"] = data;
  t.state.feed.throws = true;
  await t.instance.start();
  assert.ok(!headlines(t.byId).some((h) => h.includes("SRMARK")));
  assert.ok(!t.storage.data["newsReader.lastNews"].includes("SRMARK"));
});

// ---------------------------------------------------------------- pure parts

test("liveFetchAllowed (logic.js): the rules of R7.2", async () => {
  const { default: logic } = await import("../logic.js");
  const f = logic.liveFetchAllowed;
  assert.equal(f("open", null, 1000, false), true);
  assert.equal(f("timer", null, 1000, false), true);
  assert.equal(f("open", null, 1000, true), false, "hidden: never");
  assert.equal(f("refresh", 0, 5 * MIN - 1, false), false);
  assert.equal(f("refresh", 0, 5 * MIN, false), true);
  assert.equal(f("timer", 0, 10 * MIN - 30 * 1000 - 1, false), false);
  assert.equal(f("timer", 0, 10 * MIN - 30 * 1000, false), true, "the timer may be 30 seconds early");
  assert.equal(f("timer", 0, 10 * MIN, false), true);
  assert.equal(f("choose", 0, 5 * MIN - 1, false), false);
  assert.equal(f("choose", 0, 5 * MIN, false), true);
  assert.equal(f("choose", null, 0, false), true);
  assert.equal(f("visible", 0, 10 * MIN - 1, false), false);
  assert.equal(f("visible", 0, 10 * MIN, false), true);
  assert.equal(f("refresh", 10 * MIN, 10 * MIN, false), false);
  assert.equal(f("refresh", 0, 100 * MIN, true), false);
  // A clock set back a little counts as "too soon", set back a lot as a reset.
  assert.equal(f("refresh", 10 * MIN, 9 * MIN, false), false);
  assert.equal(f("refresh", 10 * 60 * MIN, 0, false), true);
});

test("validateSources: a browser source carries its feed address from sources.json, https only", () => {
  const sources = app.validateSources(realSources);
  assert.equal(sources[1].url, "https://api.sr.se/api/rss/program/83");
  assert.equal("url" in sources[0], false);
  for (const bad of ["http://api.sr.se/x", "ftp://x/y", "javascript:alert(1)", "https://", "https://a b", "", 5, null]) {
    const copy = JSON.parse(JSON.stringify(realSources));
    copy.sources[1]["politics-sweden"].url = bad;
    assert.equal(app.validateSources(copy)[1].url, "", String(bad));
  }
});

test("browserStatus: the texts", () => {
  const source = { name: "Sveriges Radio" };
  assert.equal(app.browserStatus(source, undefined), "Inte hämtad ännu");
  assert.equal(app.browserStatus(source, { status: "idle" }), "Inte hämtad ännu");
  assert.equal(app.browserStatus(source, { status: "loading" }), "Hämtar …");
  assert.equal(app.browserStatus(source, { status: "error" }), "Sveriges Radio kunde inte hämtas just nu");
  assert.equal(app.browserStatus(source, { status: "ok", fetchedAt: Date.parse("2026-07-01T10:07:00Z"), items: [{}] }),
    "Hämtad 12:07, 1 rubrik");
});

test("visibleItems with live items: merged and sorted with the others", () => {
  const sources = app.validateSources(realSources);
  const news = app.validateNews(newsFile(), sources, NOW);
  const live = new Map([["sveriges-radio", [{ id: "q", sourceId: "sveriges-radio", sourceName: "Sveriges Radio",
    title: "SR", url: "https://www.sverigesradio.se/artikel/1", published: "2026-11-13T12:00:00Z", publishedDisplay: "x" }]]]);
  assert.deepEqual(app.visibleItems(news, ["svt", "sveriges-radio"], live).map((i) => i.title),
    ["SVT: rubrik om regeringen", "SR", "SVT: rubrik om riksdagen"]);
  assert.deepEqual(app.visibleItems(news, ["svt"], live).map((i) => i.sourceId), ["svt", "svt"]);
  assert.deepEqual(app.visibleItems(null, ["sveriges-radio"], live).map((i) => i.title), ["SR"]);
  assert.deepEqual(app.visibleItems(null, ["sveriges-radio"]), []);
});

// ---------------------------------------------------------------- attributes

test("no attribute anywhere on the page holds a Sveriges Radio headline (title, data-, aria-label, ...)", async () => {
  const t = setup();
  await t.instance.start();
  const titles = headlines(t.byId).filter((h) => h.includes(SR_MARK));
  assert.equal(titles.length, 3);
  const root = t.byId;
  const all = [];
  const walk = (n) => { all.push(n); n.children.forEach(walk); };
  for (const id of Object.keys(root)) walk(root[id]);
  walk(t.doc.documentElement);
  let checked = 0;
  for (const node of all) {
    for (const [name, value] of Object.entries(node.attrs)) {
      checked++;
      for (const title of titles) assert.ok(!value.includes(title), name + " holds a headline");
      assert.ok(!value.includes(SR_MARK + " "), name + " holds headline text");
    }
  }
  assert.ok(checked > 20, "attributes were looked at");
});

// ---------------------------------------------------------------- unticked source

test("unticked Sveriges Radio: no request on load, timer, Uppdatera or visibility; status says so", async () => {
  const t = setup({ storage: fakeStorage({ "newsReader.selectedSources": '["svt"]' }) });
  await t.instance.start();
  assert.equal(t.feedCalls().length, 0);
  assert.equal(t.calls.filter(([u]) => u === "politics-keywords.json").length, 0, "not even the keyword list");
  assert.match(srRow(t.byId), /Inte vald – ingen hämtning/);
  for (let k = 0; k < 5; k++) {
    t.clock.now += 11 * MIN;
    t.intervals[0].fn();
    t.byId.refresh.fire("click");
    t.doc.fire("visibilitychange");
    for (let i = 0; i < 10; i++) await t.wait();
  }
  assert.equal(t.feedCalls().length, 0);
  assert.deepEqual(headlines(t.byId), ["SVT: rubrik om regeringen", "SVT: rubrik om riksdagen"]);
  assert.equal(t.byId.updated.textContent, "SVT uppdaterad 2026-11-13 14:05");
});

test("ticking Sveriges Radio the first time in a page load fetches at once; the items appear", async () => {
  const t = setup({ storage: fakeStorage({ "newsReader.selectedSources": '["svt"]' }) });
  await t.instance.start();
  const box = t.byId.sources.children[1].children[0];
  box.checked = true;
  box.fire("change");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 1);
  assert.equal(headlines(t.byId).length, 5);
  assert.match(srRow(t.byId), /Hämtad 14:30, 3 rubriker/);
});

test("ticking another source does not fetch Sveriges Radio; ticking SR twice quickly gives one request", async () => {
  const t = setup({ storage: fakeStorage({ "newsReader.selectedSources": '[]' }) });
  await t.instance.start();
  const svtBox = t.byId.sources.children[0].children[0];
  const srBox = t.byId.sources.children[1].children[0];
  svtBox.checked = true; svtBox.fire("change");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 0);
  srBox.checked = true; srBox.fire("change");
  srBox.checked = false; srBox.fire("change");
  srBox.checked = true; srBox.fire("change");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 1);
  // SVT unticked and ticked 20 minutes later: SR is not requested because of that.
  t.clock.now += 20 * MIN;
  svtBox.checked = false; svtBox.fire("change");
  svtBox.checked = true; svtBox.fire("change");
  for (let i = 0; i < 10; i++) await t.wait();
  assert.equal(t.feedCalls().length, 1);
});

test("unticking while a request runs: nothing is kept when it ends", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const t = setup();
  t.state.feed.gate = gate;
  const started = t.instance.start();
  for (let i = 0; i < 10; i++) await t.wait();
  const box = t.byId.sources.children[1].children[0];
  box.checked = false; box.fire("change");
  release();
  await started;
  assert.equal(t.instance.state.live.get("sveriges-radio").items.length, 0);
  assert.equal(headlines(t.byId).length, 2);
  assert.match(srRow(t.byId), /Inte vald – ingen hämtning/);
  assert.equal(t.feedCalls().length, 1);
});

test("a long random session with ticking: never a request while unticked, never two within 5 minutes", async () => {
  const t = setup();
  await t.instance.start();
  let seed = 11;
  const random = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  const box = t.byId.sources.children[1].children[0];
  const times = [t.clock.now];
  let requests = 1;
  for (let step = 0; step < 400; step++) {
    t.clock.now += Math.floor(random() * 6 * MIN);
    const r = random();
    if (r < 0.2) t.byId.refresh.fire("click");
    else if (r < 0.35) t.intervals[0].fn();
    else if (r < 0.5) { t.doc.hidden = !t.doc.hidden; t.doc.fire("visibilitychange"); }
    else { box.checked = !box.checked; box.fire("change"); }
    for (let i = 0; i < 10; i++) await t.wait();
    if (t.feedCalls().length > requests) {
      requests = t.feedCalls().length;
      assert.equal(box.checked, true, "requested while unticked");
      assert.equal(t.doc.hidden, false, "requested while hidden");
      times.push(t.clock.now);
    }
    if (!box.checked) assert.equal(t.instance.state.live.get("sveriges-radio").items.length, 0);
  }
  assert.ok(times.length > 8);
  for (let i = 1; i < times.length; i++) assert.ok(times[i] - times[i - 1] >= 5 * MIN);
});
