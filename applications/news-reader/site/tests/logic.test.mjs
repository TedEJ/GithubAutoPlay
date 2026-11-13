// node --test (run from applications/news-reader, no arguments).
// Part 1 runs every case of tests/shared-cases.json against logic.js, the same
// cases the Python tests run. Part 2 holds JavaScript-only tests.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import vm from "node:vm";
import logic from "../logic.js";

const here = new URL(".", import.meta.url);
const readJson = (rel) => JSON.parse(readFileSync(new URL(rel, here), "utf-8"));
const shared = readJson("../../tests/shared-cases.json");
const keywordData = readJson("../../politics-keywords.json");
const sources = readJson("../../sources.json").sources;
const keywords = logic.validateKeywords(keywordData);

// ---- shared cases ------------------------------------------------------------

test("shared cases file has the three sections, all non-empty", () => {
  assert.deepEqual(Object.keys(shared).sort(), ["cleaning", "keywords", "time"]);
  for (const section of Object.values(shared)) assert.ok(section.length > 0);
});

test("shared cases: cleaning", () => {
  for (const c of shared.cleaning) {
    assert.equal(logic.cleanHeadline(c.input), c.expected, c.id);
  }
});

test("shared cases: time (published and publishedDisplay)", () => {
  for (const c of shared.time) {
    const published = logic.publishedUtc(c.input.text, c.input.now);
    assert.equal(published, c.expected.published, c.id);
    assert.equal(logic.displayTime(published), c.expected.publishedDisplay, c.id);
  }
});

test("shared cases: keywords", () => {
  for (const c of shared.keywords) {
    const got = logic.matchesKeywords(keywords, c.input.headline, c.input.description);
    assert.equal(got, c.expected.match, c.id);
  }
});

// ---- cleaning ----------------------------------------------------------------

test("cleaning: details", () => {
  assert.equal(logic.cleanHeadline("a &amp;amp; b"), "a &amp; b");
  assert.equal(logic.cleanHeadline("a < b"), "a < b");
  assert.equal(logic.cleanHeadline("&#0; &#xD800; &#1114112; &bogus; &amp"), "&#0; &#xD800; &#1114112; &bogus; &amp");
  assert.equal(logic.cleanHeadline("&#128512;"), "\u{1F600}");
  assert.equal(logic.cleanHeadline("&#128;"), "\u0080");
  assert.equal(logic.cleanHeadline("&constructor; &__proto__;"), "&constructor; &__proto__;");
  assert.equal(logic.cleanHeadline("  a  \n b "), "a b");
  assert.equal(logic.cleanHeadline("a b"), "a b"); // not in the white space set
  assert.equal(logic.cleanHeadline("x<!-- c\n -->y"), "xy");
  assert.equal(logic.cleanHeadline("&#99999999999999999999;"), "&#99999999999999999999;");
});

// ---- keywords ----------------------------------------------------------------

test("keywords: validation follows keywords.py", () => {
  const ok = { version: 1, category: "politics-sweden",
    include: { words: ["Riksdag*"], caseSensitive: ["(S)"] }, exclude: { words: ["Moderat"], phrases: ["Tyska Regeringen"] } };
  const k = logic.validateKeywords(ok);
  assert.ok(k.includePrefixes.includes("riksdag"));
  assert.ok(k.excludeWords.has("moderat"));
  assert.deepEqual(k.excludePhrases, [["tyska", "regeringen"]]);
  assert.deepEqual(k.caseSensitive, ["(S)"]);
  const bad = (change) => assert.throws(() => logic.validateKeywords(change(structuredClone(ok))), logic.KeywordsError);
  bad((d) => { d.version = 2; return d; });
  bad((d) => { d.category = "x"; return d; });
  bad((d) => { d.extra = 1; return d; });
  bad((d) => { d.include.words = ["a b"]; return d; });
  bad((d) => { d.include.words = ["riksdag", "RIKSDAG"]; return d; });
  bad((d) => { d.include.words = [" riksdag"]; return d; });
  bad((d) => { d.include.words = [""]; return d; });
  bad((d) => { d.include.words = ["*"]; return d; });
  bad((d) => { d.include.words = [1]; return d; });
  bad((d) => { d.include.caseSensitive = ["(1)"]; return d; });
  bad((d) => { d.include.caseSensitive = ["é(S)"]; return d; }); // not NFC
  bad((d) => { d.exclude.words = ["mod*"]; return d; });
  bad((d) => { d.exclude.phrases = ["ensam"]; return d; });
  bad((d) => { d.exclude.phrases = ["två  ord"]; return d; });
  bad((d) => { d.include.words = []; d.include.caseSensitive = []; return d; });
  bad(() => null);
});

test("keywords: the real file loads and matches as described", () => {
  assert.equal(logic.matchesKeywords(keywords, "Riksdagen röstar om budgeten"), true);
  assert.equal(logic.matchesKeywords(keywords, "Vädret i helgen"), false);
  assert.equal(logic.matchesKeywords(keywords, "Vädret", "Regeringen presenterar"), true);
  assert.equal(logic.matchesKeywords(keywords, "Vädret", null), false);
  assert.equal(logic.matchesKeywords(keywords, "Beskedet (SD) kom"), true);
  assert.equal(logic.matchesKeywords(keywords, "Beskedet (sd) kom"), false);
  assert.equal(logic.matchesKeywords(keywords, "<b>Riksdag</b>"), true);
  assert.equal(logic.matchesKeywords(keywords, "RIKS&shy;DAG"), false);
});

// ---- URL check ---------------------------------------------------------------

test("url: check and normalisation (R5.3, R9.1)", () => {
  const hosts = ["svt.se"];
  const ok = (u, want) => assert.equal(logic.checkUrl(u, hosts), want, u);
  ok("https://www.svt.se/nyheter/a?x=1#f", "https://svt.se/nyheter/a");
  ok("HTTP://WWW.SVT.SE/Nyheter/A/", "http://svt.se/Nyheter/A");
  ok("  https://svt.se/  ", "https://svt.se");
  ok("https://svt.se///", "https://svt.se");
  ok("https://nyheter.svt.se/a", "https://nyheter.svt.se/a");
  ok("https://svt.se?x=1", "https://svt.se");
  ok("https://svt.se/%C3%A5", "https://svt.se/%C3%A5");
  ok("https://evilsvt.se/a", null);
  ok("https://svt.se.evil.com/a", null);
  ok("https://svt.se@evil.com/", null);
  ok("https://evil.com@svt.se/", null);
  ok("https://svt.se:443/a", null);
  ok("https://svt.se./a", null);
  ok("javascript:alert(1)", null);
  ok("data:text/html,x", null);
  ok("ftp://svt.se/a", null);
  ok("//svt.se/a", null);
  ok("/nyheter/a", null);
  ok("https://svt.se/a b", null);
  ok("https://svt.se/å", null);
  ok("https://svt.se\\@evil.com/", null);
  ok("https://svt.se/a\nb", null);
  ok("https://sv­t.se/", null);
  ok("https://[::1]/", null);
  ok("https:///a", null);
  ok("", null);
  ok(undefined, null);
  ok(5, null);
  assert.equal(logic.checkUrl("https://www.sverigesradio.se/artikel/1", ["sverigesradio.se"]),
    "https://sverigesradio.se/artikel/1");
});

// ---- id ----------------------------------------------------------------------

test("id: SHA-256 matches node:crypto", () => {
  for (const s of ["", "abc", "https://svt.se/nyheter/a", "x".repeat(55), "x".repeat(56), "x".repeat(63),
    "x".repeat(64), "x".repeat(119), "x".repeat(120), "å".repeat(40), "\u{1F600}".repeat(30)]) {
    assert.equal(logic.sha256Hex(s), createHash("sha256").update(s, "utf8").digest("hex"), JSON.stringify(s));
  }
  assert.equal(logic.sha256Hex("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  assert.equal(logic.itemId("https://svt.se/nyheter/a"),
    createHash("sha256").update("https://svt.se/nyheter/a").digest("hex").slice(0, 16));
  assert.equal(logic.itemId("https://svt.se/x"), "65197a66fb270320"); // same as Python item_id
});

// ---- time --------------------------------------------------------------------

const NOW = "2026-11-13T13:05:12Z";

test("time: daylight saving transitions", () => {
  const d = (utc) => logic.displayTime(utc);
  assert.equal(d("2026-03-29T00:59:59Z"), "2026-03-29 01:59");
  assert.equal(d("2026-03-29T01:00:00Z"), "2026-03-29 03:00");
  assert.equal(d("2026-10-25T00:59:59Z"), "2026-10-25 02:59");
  assert.equal(d("2026-10-25T01:00:00Z"), "2026-10-25 02:00");
  assert.equal(d("1979-07-01T10:00:00Z"), "1979-07-01 11:00"); // no summer time yet
  assert.equal(d("1980-04-06T00:59:59Z"), "1980-04-06 01:59");
  assert.equal(d("1980-04-06T01:00:00Z"), "1980-04-06 03:00");
  assert.equal(d("1980-09-28T01:00:00Z"), "1980-09-28 02:00");
  assert.equal(d("1995-09-24T01:00:00Z"), "1995-09-24 02:00");
  assert.equal(d("1996-09-29T10:00:00Z"), "1996-09-29 12:00");
  assert.equal(d("1996-10-27T01:00:00Z"), "1996-10-27 02:00");
  assert.equal(d("9998-07-01T10:00:00Z"), "9998-07-01 12:00");
  assert.equal(d(null), "Tid saknas");
  assert.throws(() => d("2026-11-13 12:00"), Error);
  assert.throws(() => d("2026-02-30T00:00:00Z"), Error);
  assert.throws(() => d("9999-12-31T23:30:00Z"), Error);
});

test("time: local times in the skipped and the repeated hour", () => {
  assert.equal(logic.publishedUtc("2026-03-29T02:30:00", NOW), "2026-03-29T01:30:00Z");
  assert.equal(logic.publishedUtc("2026-10-25T02:30:00", NOW), "2026-10-25T00:30:00Z");
  assert.equal(logic.publishedUtc("2026-10-25T03:30:00", NOW), "2026-10-25T02:30:00Z");
  assert.equal(logic.publishedUtc("2026-03-29T01:59:59", NOW), "2026-03-29T00:59:59Z");
  assert.equal(logic.publishedUtc("2026-03-29T03:00:00", NOW), "2026-03-29T01:00:00Z");
});

test("time: formats and limits", () => {
  const p = (t) => logic.publishedUtc(t, NOW);
  assert.equal(p("Fri, 13 Nov 2026 14:05:00 +0100"), "2026-11-13T13:05:00Z");
  assert.equal(p("13 Nov 2026 12:00 GMT"), "2026-11-13T12:00:00Z");
  assert.equal(p("13 nov 2026 07:00 est"), "2026-11-13T12:00:00Z");
  assert.equal(p("2026-11-13T12:00:00.123+01"), "2026-11-13T11:00:00Z");
  assert.equal(p("2026-11-13T12:00z"), "2026-11-13T12:00:00Z");
  assert.equal(p("\t2026-11-13T12:00:00Z\n"), "2026-11-13T12:00:00Z");
  assert.equal(p(" 2026-11-13T12:00:00Z"), null); // U+00A0 is not trimmed here
  assert.equal(p("2026-11-13T12:00:60Z"), null);
  assert.equal(p("2026-02-29T12:00:00Z"), null);
  assert.equal(p("2024-02-29T12:00:00Z"), "2024-02-29T12:00:00Z");
  assert.equal(p("1900-02-29T12:00:00Z"), null);
  assert.equal(p("2026-11-13T12:00:00+24:00"), null);
  assert.equal(p("2026-11-13T12:00:00+01:60"), null);
  assert.equal(p("1969-12-31T23:59:59Z"), null);
  assert.equal(p("1970-01-01T00:00:00Z"), "1970-01-01T00:00:00Z");
  assert.equal(p("1970-01-01T00:30:00+01:00"), "1969-12-31T23:30:00Z");
  assert.equal(logic.displayTime("1969-12-31T23:30:00Z"), "1970-01-01 00:30");
  assert.equal(logic.publishedUtc("9998-12-31T23:59:00-23:59", "9998-12-31T23:59:59Z"), null);
  assert.equal(logic.publishedUtc("9998-12-31T12:00:00Z", "9999-01-01T00:00:00Z"), "9998-12-31T12:00:00Z");
  assert.equal(p(undefined), null);
  assert.equal(p(5), null);
  assert.equal(p(""), null);
});

test("time: now as a parameter, 10 minute future limit", () => {
  const now = Date.UTC(2026, 10, 13, 13, 5, 12);
  assert.equal(logic.publishedUtc("2026-11-13T13:15:12Z", now), "2026-11-13T13:15:12Z");
  assert.equal(logic.publishedUtc("2026-11-13T13:15:13Z", now), null);
  assert.equal(logic.publishedUtc("2026-11-13T13:15:13Z", new Date(now + 1000)), "2026-11-13T13:15:13Z");
  assert.equal(logic.publishedUtc("2026-11-13T13:15:12Z", new Date(now - 1)), null);
  assert.equal(logic.generatedAt(now + 999), "2026-11-13T13:05:12Z");
  assert.equal(logic.generatedAtDisplay(now), "2026-11-13 14:05");
  assert.throws(() => logic.publishedUtc("2026-11-13T13:15:12Z", "yesterday"), TypeError);
  assert.throws(() => logic.publishedUtc("2026-11-13T13:15:12Z", NaN), TypeError);
  assert.throws(() => logic.publishedUtc("2026-11-13T13:15:12Z", undefined), TypeError);
});

// ---- selection ---------------------------------------------------------------

const svt = sources.find((s) => s.id === "svt");
const sr = sources.find((s) => s.id === "sveriges-radio");
const SEL_NOW = "2026-11-13T13:05:12Z";

function rss(title, path, time, description = "") {
  return { title, link: "https://www.svt.se/nyheter/" + path, timeText: time, description };
}

test("selection: item shape, cleaning, filter, drops (R1.2, R1.4)", () => {
  const entries = [
    rss("<b>Riksdagen</b> &amp; regeringen", "a?x=1", "Fri, 13 Nov 2026 14:05:00 +0100", "ignored text"),
    rss("Vädret blir fint", "b", "Fri, 13 Nov 2026 12:00:00 +0100"),
    rss("Vädret", "c", "Fri, 13 Nov 2026 12:00:00 +0100", "Regeringen säger"),
    rss("   ", "d", "Fri, 13 Nov 2026 12:00:00 +0100"),
    { title: "Riksdagen: fel värd", link: "https://evil.example/x", timeText: "" },
    { title: "Riksdagen: javascript", link: "javascript:alert(1)", timeText: "" },
    { title: "Riksdagen: ingen länk" },
  ];
  const items = logic.selectItems(entries, svt, keywords, SEL_NOW);
  assert.equal(items.length, 2);
  assert.deepEqual(Object.keys(items[0]),
    ["id", "sourceId", "sourceName", "title", "url", "published", "publishedDisplay"]);
  assert.deepEqual(items[0], {
    id: logic.itemId("https://svt.se/nyheter/a"),
    sourceId: "svt", sourceName: "SVT",
    title: "Riksdagen & regeringen",
    url: "https://www.svt.se/nyheter/a?x=1",
    published: "2026-11-13T13:05:00Z",
    publishedDisplay: "2026-11-13 14:05",
  });
  assert.equal(items[1].title, "Vädret");
});

test("selection: Atom-shaped entries (Sveriges Radio), content never read", () => {
  const entries = [
    { title: "Riksdagen klubbar budgeten", summary: "kort", content: "lång text", published: "2026-11-13T12:00:00+01:00",
      updated: "2026-11-13T13:00:00+01:00", link: "https://www.sverigesradio.se/artikel/1" },
    { title: "Fotboll", summary: "Regeringen nämns", content: "x", published: "", updated: "2026-11-13T09:00:00+01:00",
      link: "https://sverigesradio.se/artikel/2" },
    { title: "Fotboll", summary: "", content: "Riksdagen står här", published: "2026-11-13T09:00:00+01:00",
      link: "https://sverigesradio.se/artikel/3" },
    { title: "Riksdag utan tid", link: "https://sverigesradio.se/artikel/4" },
    { title: "Riksdag fel host", link: "https://svt.se/artikel/5", published: "2026-11-13T09:00:00+01:00" },
  ];
  const items = logic.selectItems(entries, sr, keywords, SEL_NOW);
  assert.deepEqual(items.map((i) => i.url), [
    "https://www.sverigesradio.se/artikel/1",
    "https://sverigesradio.se/artikel/2",
    "https://sverigesradio.se/artikel/4",
  ]);
  assert.equal(items[1].published, "2026-11-13T08:00:00Z");
  assert.equal(items[2].published, null);
  assert.equal(items[2].publishedDisplay, "Tid saknas");
  for (const i of items) {
    assert.equal(i.sourceId, "sveriges-radio");
    assert.equal(Object.keys(i).length, 7);
  }
});

test("selection: duplicates by normalised URL, first in feed order wins (R5.3)", () => {
  const t = "Fri, 13 Nov 2026 12:00:00 +0100";
  const entries = [
    rss("Riksdagen ett", "x?a=1", t),
    rss("Riksdagen två", "x/?b=2#f", t),
    { title: "Riksdagen tre", link: "https://svt.se/nyheter/x", timeText: t },
    { title: "Riksdagen fyra", link: "HTTP://www.SVT.se/nyheter/x", timeText: t },
    rss("Riksdagen X", "X", t),
  ];
  const items = logic.selectItems(entries, svt, keywords, SEL_NOW);
  assert.deepEqual(items.map((i) => i.title), ["Riksdagen X", "Riksdagen ett", "Riksdagen fyra"]); // http and https differ
});

test("selection: age limit 7 days and future limit (R5.2, R2.6)", () => {
  const entries = [
    rss("Riksdagen exakt sju dagar", "a", "2026-11-06T13:05:12Z"),
    rss("Riksdagen en sekund för gammal", "b", "2026-11-06T13:05:11Z"),
    rss("Riksdagen om tio minuter", "c", "2026-11-13T13:15:12Z"),
    rss("Riksdagen om mer än tio minuter", "d", "2026-11-13T13:15:13Z"),
    rss("Riksdagen utan tid", "e", ""),
    rss("Riksdagen trasig tid", "f", "igår"),
  ];
  const items = logic.selectItems(entries, svt, keywords, SEL_NOW);
  assert.deepEqual(items.map((i) => i.title), [
    "Riksdagen om tio minuter",
    "Riksdagen exakt sju dagar",
    // the future time became null: these three have no time, by title
    "Riksdagen om mer än tio minuter",
    "Riksdagen trasig tid",
    "Riksdagen utan tid",
  ]);
});

test("selection: sorting, tie-break by title then feed order, cap of 20 (R5.1)", () => {
  const t = "2026-11-13T10:00:00Z";
  const entries = [
    rss("Riksdagen b", "1", t),
    rss("Riksdagen a", "2", t),
    rss("Riksdagen a", "3", t), // same time and title: feed order
    rss("Riksdagen nyast", "4", "2026-11-13T11:00:00Z"),
    rss("Riksdagen \u{1F600}", "5", t), // astral after BMP letters by code point
    rss("Riksdagen Ａ", "6", t),
  ];
  const items = logic.selectItems(entries, svt, keywords, SEL_NOW);
  assert.deepEqual(items.map((i) => i.url.split("/").pop()), ["4", "2", "3", "1", "6", "5"]);

  const many = [];
  for (let i = 0; i < 30; i++) {
    many.push(rss("Riksdagen " + i, "n" + i, `2026-11-13T${String(i % 10).padStart(2, "0")}:${String(i).padStart(2, "0")}:00Z`));
  }
  for (let i = 0; i < 5; i++) many.push(rss("Riksdagen utan tid " + i, "u" + i, ""));
  const out = logic.selectItems(many, svt, keywords, SEL_NOW);
  assert.equal(out.length, logic.MAX_ITEMS);
  assert.ok(out.every((i) => i.published !== null)); // 30 dated items fill the 20 places
  const times = out.map((i) => i.published);
  assert.deepEqual(times, [...times].sort().reverse());

  const few = [rss("Riksdagen ny", "p", t), rss("Riksdagen utan b", "q", ""), rss("Riksdagen utan a", "r", "")];
  assert.deepEqual(logic.selectItems(few, svt, keywords, SEL_NOW).map((i) => i.title),
    ["Riksdagen ny", "Riksdagen utan a", "Riksdagen utan b"]);
});

test("selection: errors for an unsupported method or a missing keyword list", () => {
  const src = (method) => ({ id: "x", name: "X", allowedHosts: ["svt.se"], "politics-sweden": { method } });
  assert.throws(() => logic.selectItems([], src("categoryFilter"), keywords, SEL_NOW), Error);
  assert.throws(() => logic.selectItems([], src("keywordFilter"), null, SEL_NOW), Error);
  const entries = [rss("Vädret", "a", "")];
  assert.equal(logic.selectItems(entries, src("feed"), null, SEL_NOW).length, 1);
  assert.deepEqual(logic.selectItems([], svt, keywords, SEL_NOW), []);
});

test("selection does not change its input", () => {
  const entries = [rss("Riksdagen a", "1", "2026-11-13T10:00:00Z")];
  const copy = structuredClone(entries);
  logic.selectItems(entries, svt, keywords, SEL_NOW);
  assert.deepEqual(entries, copy);
});

// ---- merge and sort ----------------------------------------------------------

const item = (sourceId, title, published) => ({
  id: sourceId + title, sourceId, sourceName: sourceId, title, url: "https://x.se/" + title,
  published, publishedDisplay: logic.displayTime(published),
});

test("merge: newest first, null last, ties by sourceId then title (R5.5)", () => {
  const a = [item("svt", "b", "2026-11-13T10:00:00Z"), item("svt", "a", "2026-11-13T09:00:00Z"), item("svt", "z", null)];
  const b = [item("sr", "c", "2026-11-13T10:00:00Z"), item("sr", "a", "2026-11-13T10:00:00Z"),
    item("sr", "a", null), item("sr", "m", "2026-11-13T11:00:00Z")];
  const merged = logic.mergeItems([a, b]);
  assert.deepEqual(merged.map((i) => i.sourceId + ":" + i.title + ":" + i.published), [
    "sr:m:2026-11-13T11:00:00Z",
    "sr:a:2026-11-13T10:00:00Z",
    "sr:c:2026-11-13T10:00:00Z",
    "svt:b:2026-11-13T10:00:00Z",
    "svt:a:2026-11-13T09:00:00Z",
    "sr:a:null",
    "svt:z:null",
  ]);
  assert.equal(a.length, 3);
  assert.equal(b.length, 4);
  assert.deepEqual(logic.mergeItems([b, a]), merged); // list order does not matter
  assert.deepEqual(logic.mergeItems([]), []);
  assert.deepEqual(logic.mergeItems([[], a]).length, 3);
});

test("merge: stable for fully equal keys, does not de-duplicate or mutate", () => {
  const x = { ...item("svt", "t", "2026-11-13T10:00:00Z"), id: "1" };
  const y = { ...item("svt", "t", "2026-11-13T10:00:00Z"), id: "2" };
  assert.deepEqual(logic.mergeItems([[x, y]]).map((i) => i.id), ["1", "2"]);
  assert.deepEqual(logic.mergeItems([[y], [x]]).map((i) => i.id), ["2", "1"]);
  assert.equal(logic.mergeItems([[x], [x]]).length, 2);
});

test("merge: selection of two sources end to end", () => {
  const t = "2026-11-13T10:00:00Z";
  const fromSvt = logic.selectItems([rss("Riksdagen svt", "1", t)], svt, keywords, SEL_NOW);
  const fromSr = logic.selectItems(
    [{ title: "Riksdagen sr", link: "https://sverigesradio.se/artikel/1", published: t }], sr, keywords, SEL_NOW);
  const merged = logic.mergeItems([fromSvt, fromSr]);
  assert.deepEqual(merged.map((i) => i.sourceId), ["sveriges-radio", "svt"]);
});

// ---- more checks of rules (each value verified against the Python code) ------

test("url: the host check refuses user info with a colon or on a subdomain", () => {
  assert.equal(logic.checkUrl("https://x:y@a.svt.se/", ["svt.se"]), null);
  assert.equal(logic.checkUrl("https://evil@x.svt.se/", ["svt.se"]), null);
  assert.equal(logic.parseUrl("https://x:y@a.svt.se/"), null);
});

test("keywords: adjacent and overlapping exclude phrases are all removed together (rule 4)", () => {
  const make = (include) => logic.validateKeywords({ version: 1, category: "politics-sweden",
    include: { words: include, caseSensitive: [] }, exclude: { words: [], phrases: ["a b", "b c"] } });
  const k = make(["c", "d"]);
  assert.equal(logic.matchesKeywords(k, "a b c"), false);   // "c" is removed with the phrase "b c"
  assert.equal(logic.matchesKeywords(k, "a b c d"), true);
  assert.equal(logic.matchesKeywords(k, "a b d"), true);
  assert.equal(logic.matchesKeywords(make(["b"]), "a b c"), false);
  const all = make(["a", "b", "c"]);
  assert.equal(logic.matchesKeywords(all, "a b c"), false);
  assert.equal(logic.matchesKeywords(all, "a b"), false);
  assert.equal(logic.matchesKeywords(all, "c b a"), true);  // no phrase in this order
});

test("keywords: caseSensitive terms are compared with the NFC form of the text", () => {
  const k = logic.validateKeywords({ version: 1, category: "politics-sweden",
    include: { words: ["zzz"], caseSensitive: ["\u00e9(S)", "\u00c5(S)"] }, exclude: { words: [], phrases: [] } });
  assert.equal(logic.matchesKeywords(k, "e\u0301(S)"), true);
  assert.equal(logic.matchesKeywords(k, "\u00e9(S)"), true);
  assert.equal(logic.matchesKeywords(k, "A\u030a(S)"), true);
  assert.equal(logic.matchesKeywords(k, "a\u030a(S)"), false); // case is kept
  // the description is cleaned and normalised the same way
  assert.equal(logic.matchesKeywords(k, "x", "e\u0301(S)"), true);
});

// ---- long inputs must be handled in linear time ------------------------------

function timed(fn) {
  const start = performance.now();
  const result = fn();
  return { result, ms: performance.now() - start };
}
const FAST_MS = 500;

test("long input: white space and slash runs around a URL (checkUrl, parseUrl)", () => {
  for (const n of [100000, 200000]) {
    const ws = " \t\n\u00a0".repeat(n / 4);
    const url = ws + "https://www.svt.se/a" + "/".repeat(n) + ws;
    const r = timed(() => logic.checkUrl(url, ["svt.se"]));
    assert.equal(r.result, "https://svt.se/a");
    assert.ok(r.ms < FAST_MS, "checkUrl took " + r.ms + " ms");
    const p = timed(() => logic.parseUrl(url));
    assert.equal(p.result.path, "/a" + "/".repeat(n));
    assert.ok(p.ms < FAST_MS, "parseUrl took " + p.ms + " ms");
    const only = timed(() => logic.parseUrl(ws));
    assert.equal(only.result, null);
    assert.ok(only.ms < FAST_MS);
    // a run that is NOT at the end (what makes a trim regular expression quadratic)
    const inner = timed(() => logic.checkUrl("https://svt.se/a" + "/".repeat(n) + "b", ["svt.se"]));
    assert.equal(inner.result, "https://svt.se/a" + "/".repeat(n) + "b");
    assert.ok(inner.ms < FAST_MS, "inner slash run took " + inner.ms + " ms");
    assert.equal(logic.parseUrl("x" + ws.slice(0, n) + "x"), null);
    const innerWs = timed(() => logic.parseUrl("https://svt.se/a" + " ".repeat(n) + "b"));
    assert.equal(innerWs.result, null);
    assert.ok(innerWs.ms < FAST_MS);
    const slashes = timed(() => logic.checkUrl("https://svt.se" + "/".repeat(n), ["svt.se"]));
    assert.equal(slashes.result, "https://svt.se");
    assert.ok(slashes.ms < FAST_MS);
  }
});

test("long input: white space around a time text (parseTime, publishedUtc)", () => {
  for (const n of [100000, 200000]) {
    const ws = " \t\n\r\f\v".repeat(n / 6);
    const r = timed(() => logic.publishedUtc(ws + "2026-11-13T12:00:00Z" + ws, NOW));
    assert.equal(r.result, "2026-11-13T12:00:00Z");
    assert.ok(r.ms < FAST_MS, "publishedUtc took " + r.ms + " ms");
    const only = timed(() => logic.parseTime(ws));
    assert.equal(only.result, null);
    assert.ok(only.ms < FAST_MS);
    const inner = timed(() => logic.parseTime("x" + " ".repeat(n) + "x"));
    assert.equal(inner.result, null);
    assert.ok(inner.ms < FAST_MS);
    const inner2 = timed(() => logic.parseTime(" ".repeat(n) + "x" + " ".repeat(n) + "x"));
    assert.equal(inner2.result, null);
    assert.ok(inner2.ms < FAST_MS);
    const junk = timed(() => logic.parseTime("2026-11-13T12:00:00Z" + ws + "x"));
    assert.equal(junk.result, null);
    assert.ok(junk.ms < FAST_MS);
  }
});

test("long input: selectItems with long link, time and title", () => {
  const n = 200000;
  const ws = " \t\n\u00a0".repeat(n / 4);
  const entries = [
    { title: ws + "Riksdagen" + ws, link: ws + "https://www.svt.se/nyheter/long" + "/".repeat(n) + ws,
      timeText: ws.replace(/\u00a0/g, " ") + "2026-11-13T12:00:00Z" + ws.replace(/\u00a0/g, " ") },
  ];
  const r = timed(() => logic.selectItems(entries, svt, keywords, SEL_NOW));
  assert.equal(r.result.length, 1);
  assert.equal(r.result[0].title, "Riksdagen");
  assert.equal(r.result[0].id, logic.itemId("https://svt.se/nyheter/long"));
  assert.equal(r.result[0].published, "2026-11-13T12:00:00Z");
  assert.equal(r.result[0].url, "https://www.svt.se/nyheter/long" + "/".repeat(n));
  assert.ok(r.ms < FAST_MS, "selectItems took " + r.ms + " ms");
});

// ---- a time before 1970 and Atom white space ---------------------------------

test("selection: a time that falls before 1970 is dropped as too old (explicit rule)", () => {
  // 1970-01-01T00:30:00+01:00 is 1969-12-31T23:30:00Z. The year check is made on
  // the text (1970 is allowed), so the time is usable and is the year 1969; the
  // item is then older than 7 days and is dropped.
  const entries = [rss("Riksdagen gammal", "old", "1970-01-01T00:30:00+01:00"),
    rss("Riksdagen ny", "new", "2026-11-13T10:00:00Z")];
  const items = logic.selectItems(entries, svt, keywords, SEL_NOW);
  assert.deepEqual(items.map((i) => i.title), ["Riksdagen ny"]);
  // publishedUtc itself still returns the 1969 text (the shared rule: only the year of the text is checked)
  assert.equal(logic.publishedUtc("1970-01-01T00:30:00+01:00", NOW), "1969-12-31T23:30:00Z");
  // with a "now" so early that 1969 is within 7 days the item is kept
  const early = logic.selectItems([rss("Riksdagen tidig", "e", "1970-01-01T00:30:00+01:00")], svt, keywords, "1970-01-02T00:00:00Z");
  assert.equal(early[0].published, "1969-12-31T23:30:00Z");
  assert.equal(early[0].publishedDisplay, "1970-01-01 00:30");
});

test("selection: an Atom published that is only white space falls back to updated", () => {
  const e = (published, updated) => ({ title: "Riksdagen", link: "https://sverigesradio.se/artikel/9", published, updated });
  const at = (entry) => logic.selectItems([entry], sr, keywords, SEL_NOW)[0].published;
  assert.equal(at(e("  \t\n", "2026-11-13T09:00:00Z")), "2026-11-13T09:00:00Z");
  assert.equal(at(e("", "2026-11-13T09:00:00Z")), "2026-11-13T09:00:00Z");
  assert.equal(at(e(undefined, "2026-11-13T09:00:00Z")), "2026-11-13T09:00:00Z");
  assert.equal(at(e("2026-11-13T08:00:00Z", "2026-11-13T09:00:00Z")), "2026-11-13T08:00:00Z");
  assert.equal(at(e("not a time", "2026-11-13T09:00:00Z")), null); // present but unusable: no fallback
  assert.equal(at(e("\u00a0", "2026-11-13T09:00:00Z")), null); // U+00A0 is not time white space, as in timeutil.py
});

// ---- loading as a classic script ---------------------------------------------

test("logic.js loads as a classic script and creates only the global NewsLogic", () => {
  const source = readFileSync(new URL("../logic.js", here), "utf-8");
  const context = vm.createContext({ TextEncoder });
  vm.runInContext(source, context, { filename: "logic.js" });
  assert.deepEqual(Object.keys(context).sort(), ["NewsLogic", "TextEncoder"]);
  const api = context.NewsLogic;
  assert.equal(typeof api.selectItems, "function");
  assert.equal(api.cleanHeadline("<b>a</b> &amp; b"), "a & b");
  assert.equal(api.itemId("https://svt.se/x"), "65197a66fb270320");
  assert.equal(api.displayTime("2026-07-01T10:00:00Z"), "2026-07-01 12:00");
  // the same functions as under Node
  assert.deepEqual(Object.keys(api).sort(), Object.keys(logic).sort());
});

test("logic.js does not use DOM, network, storage, clock, Intl, console or eval", () => {
  const source = readFileSync(new URL("../logic.js", here), "utf-8");
  const code = source.split("\n").filter((line) => !line.trim().startsWith("//")).join("\n");
  for (const name of ["document", "window", "fetch", "XMLHttpRequest", "localStorage", "sessionStorage",
    "indexedDB", "navigator", "location", "WebSocket", "Intl", "console", "eval", "Function", "setTimeout"]) {
    assert.ok(!new RegExp("\\b" + name + "\\b").test(code), name + " is used in logic.js");
  }
  assert.ok(!/Date\s*\.\s*now|new\s+Date\s*\(\s*\)|performance\.now|Math\.random/.test(code));
  assert.ok(!/\brequire\s*\(|\bimport\b/.test(code));
});

test("exports", () => {
  assert.equal(logic.version(), 1);
  assert.equal(logic.MAX_ITEMS, 20);
  assert.equal(logic.MISSING_DISPLAY, "Tid saknas");
});
