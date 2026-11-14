// node --test for site/atom.js (step S11). Hand-written, made-up feeds only; no
// network and no browser. The XML is read by a small stand-in for DOMParser
// (xml-fake.mjs); the real DOMParser is checked in a real browser by hand.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import atom from "../atom.js";
import logic from "../logic.js";
import { FakeDOMParser } from "./xml-fake.mjs";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const sourcesFile = JSON.parse(fs.readFileSync(path.join(ROOT, "sources.json"), "utf8"));
const SR = sourcesFile.sources.find((s) => s.id === "sveriges-radio");
const keywords = logic.validateKeywords(JSON.parse(fs.readFileSync(path.join(ROOT, "politics-keywords.json"), "utf8")));
const shared = JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "shared-cases.json"), "utf8"));
const NOW = Date.parse("2026-11-13T13:30:00Z");
const NS = "http://www.w3.org/2005/Atom";
const opts = { DOMParser: FakeDOMParser };

function esc(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// A feed in the shape of the Sveriges Radio one, with made-up content.
function entry(o = {}) {
  const e = {
    title: "Regeringen lägger fram budgeten",
    summary: "Kort sammanfattning.",
    link: "https://www.sverigesradio.se/artikel/900001",
    published: "2026-11-13T13:00:00+01:00",
    updated: "2026-11-13T13:10:00+01:00",
    content: "BRÖDTEXT-SKA-ALDRIG-LÄSAS",
    ...o,
  };
  const parts = ["<entry>", "<id>tag:example,2026:" + Math.abs(e.title.length) + "</id>"];
  if (e.title !== null) parts.push("<title>" + esc(e.title) + "</title>");
  if (e.summary !== null) parts.push("<summary>" + esc(e.summary) + "</summary>");
  if (e.link !== null) parts.push('<link rel="alternate" type="text/html" href="' + esc(e.link) + '"/>');
  if (e.published !== null) parts.push("<published>" + e.published + "</published>");
  if (e.updated !== null) parts.push("<updated>" + e.updated + "</updated>");
  if (e.content !== null) parts.push('<content type="html">' + esc(e.content) + "</content>");
  parts.push("<author><name>Någon</name></author><category term=\"Inrikes\"/>");
  parts.push("</entry>");
  return parts.join("");
}

function feed(entries, ns = NS) {
  return '<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="' + ns + '"><title>Ekot (test)</title>'
    + entries.join("") + "</feed>";
}

const select = (entries) => logic.selectItems(entries, {
  id: SR.id, name: SR.name, allowedHosts: SR.allowedHosts, "politics-sweden": SR["politics-sweden"],
}, keywords, NOW);

// ---------------------------------------------------------------- parsing

test("parseAtom: the plain entries have exactly title, summary, link, published, updated; content is never read", () => {
  const entries = atom.parseAtom(feed([entry()]), opts);
  assert.equal(entries.length, 1);
  assert.deepEqual(Object.keys(entries[0]).sort(), ["link", "published", "summary", "title", "updated"]);
  assert.deepEqual(entries[0], {
    title: "Regeringen lägger fram budgeten",
    summary: "Kort sammanfattning.",
    link: "https://www.sverigesradio.se/artikel/900001",
    published: "2026-11-13T13:00:00+01:00",
    updated: "2026-11-13T13:10:00+01:00",
  });
  assert.ok(!JSON.stringify(entries).includes("BRÖDTEXT"));
});

test("parseAtom: the items made from it have exactly the seven fields (R1.2) and never the summary or content", () => {
  const items = select(atom.parseAtom(feed([entry({ summary: "SAMMANFATTNING-HEMLIG riksdagen" })]), opts));
  assert.equal(items.length, 1);
  assert.deepEqual(Object.keys(items[0]).sort(),
    ["id", "published", "publishedDisplay", "sourceId", "sourceName", "title", "url"]);
  assert.equal(items[0].sourceName, "Sveriges Radio");
  assert.equal(items[0].published, "2026-11-13T12:00:00Z");
  assert.equal(items[0].publishedDisplay, "2026-11-13 13:00");
  const text = JSON.stringify(items);
  assert.ok(!text.includes("SAMMANFATTNING") && !text.includes("BRÖDTEXT"));
});

test("parseAtom: updated is used when published is missing or empty (R2.3)", () => {
  const items = select(atom.parseAtom(feed([
    entry({ title: "Riksdagen A", link: "https://www.sverigesradio.se/artikel/1", published: null }),
    entry({ title: "Riksdagen B", link: "https://www.sverigesradio.se/artikel/2", published: "  " }),
    entry({ title: "Riksdagen C", link: "https://www.sverigesradio.se/artikel/3", published: null, updated: null }),
  ]), opts));
  const byTitle = Object.fromEntries(items.map((i) => [i.title, i.published]));
  assert.equal(byTitle["Riksdagen A"], "2026-11-13T12:10:00Z");
  assert.equal(byTitle["Riksdagen B"], "2026-11-13T12:10:00Z");
  assert.equal(byTitle["Riksdagen C"], null);
});

test("parseAtom: of several links the first alternate (or without rel) with a href is used (R11.2)", () => {
  const xml = feed(["<entry><title>T</title>"
    + '<link rel="enclosure" href="https://www.sverigesradio.se/audio.mp3"/>'
    + '<link rel="alternate"/>'
    + '<link href="https://www.sverigesradio.se/artikel/5"/>'
    + '<link rel="alternate" href="https://www.sverigesradio.se/artikel/6"/>'
    + "</entry>"]);
  assert.equal(atom.parseAtom(xml, opts)[0].link, "https://www.sverigesradio.se/artikel/5");
  const none = feed(['<entry><title>T</title><link rel="enclosure" href="https://www.sverigesradio.se/a"/></entry>']);
  assert.equal(atom.parseAtom(none, opts)[0].link, "");
});

test("parseAtom: entities, CDATA, a prefixed namespace and comments", () => {
  const xml = '<?xml version="1.0"?><a:feed xmlns:a="' + NS + '"><!-- komm -->'
    + "<a:entry><a:title>Skatt &amp; avgift &#229;&#xE4;&#246; <![CDATA[<b>fet</b> & mer]]></a:title>"
    + '<a:summary><![CDATA[Riksdagen]]></a:summary><a:link href="https://www.sverigesradio.se/artikel/7"/></a:entry></a:feed>';
  const [e] = atom.parseAtom(xml, opts);
  assert.equal(e.title, "Skatt & avgift åäö <b>fet</b> & mer");
  assert.equal(e.summary, "Riksdagen");
  // The title is then cleaned by logic.js as any headline (R1.3): tags go, text stays.
  const items = select([e]);
  assert.equal(items[0].title, "Skatt & avgift åäö fet & mer");
});

test("parseAtom: missing fields give empty strings and are then dropped by logic.js (R1.4)", () => {
  const entries = atom.parseAtom(feed([
    "<entry/>",
    "<entry><title>Riksdagen utan länk</title></entry>",
    "<entry><link href=\"https://www.sverigesradio.se/artikel/8\"/></entry>",
    entry({ title: "Riksdagen med allt", link: "https://www.sverigesradio.se/artikel/9" }),
  ]), opts);
  assert.equal(entries.length, 4);
  assert.deepEqual(select(entries).map((i) => i.title), ["Riksdagen med allt"]);
});

test("parseAtom: elements outside the Atom namespace are ignored", () => {
  const xml = '<feed xmlns="' + NS + '" xmlns:x="urn:other"><x:entry><x:title>Riksdagen</x:title></x:entry>'
    + '<entry><x:title>Fel</x:title><title>Riksdagen rätt</title>'
    + '<link href="https://www.sverigesradio.se/artikel/1"/></entry></feed>';
  const entries = atom.parseAtom(xml, opts);
  assert.equal(entries.length, 1);
  assert.equal(entries[0].title, "Riksdagen rätt");
});

// ---------------------------------------------------------------- failures of parsing

function kindOf(fn) {
  try {
    fn();
  } catch (e) {
    assert.ok(e instanceof atom.AtomError, "only AtomError is thrown");
    assert.match(e.message, /^feed could not be read: [a-z-]+$/);
    return e.kind;
  }
  return null;
}

test("parseAtom: not a feed, wrong namespace, or an RSS document is refused (R11.2)", () => {
  assert.equal(kindOf(() => atom.parseAtom(feed([entry()], "urn:other"), opts)), "not-atom");
  assert.equal(kindOf(() => atom.parseAtom('<feed><entry><title>x</title></entry></feed>', opts)), "not-atom");
  assert.equal(kindOf(() => atom.parseAtom('<rss version="2.0"><channel><item><title>x</title></item></channel></rss>', opts)), "not-atom");
  assert.equal(kindOf(() => atom.parseAtom('<html xmlns="http://www.w3.org/1999/xhtml"></html>', opts)), "not-atom");
});

test("parseAtom: a parse error is refused", () => {
  for (const bad of ["", "not xml", "<feed", "<feed xmlns=\"" + NS + "\"><entry></feed>", feed([entry()]) + "<extra/>",
    '<feed xmlns="' + NS + '"><entry><title>&unknown;</title></entry></feed>',
    "<?xml version=\"1.0\"?>garbage<feed xmlns=\"" + NS + "\"/>"]) {
    assert.equal(kindOf(() => atom.parseAtom(bad, opts)), "parse", JSON.stringify(bad));
  }
  assert.equal(kindOf(() => atom.parseAtom(null, opts)), "parse");
  assert.equal(kindOf(() => atom.parseAtom(5, opts)), "parse");
  assert.equal(kindOf(() => atom.parseAtom(feed([entry()]), { DOMParser: null })), "parse");
  // A parser that throws, or returns nothing usable.
  class Throwing { parseFromString() { throw new Error("SECRET-DETAIL"); } }
  class Empty { parseFromString() { return {}; } }
  assert.equal(kindOf(() => atom.parseAtom(feed([entry()]), { DOMParser: Throwing })), "parse");
  assert.equal(kindOf(() => atom.parseAtom(feed([entry()]), { DOMParser: Empty })), "parse");
});

test("parseAtom: asks for application/xml and a parsererror in the document is a parse error", () => {
  const seen = [];
  class Spy {
    parseFromString(text, type) {
      seen.push(type);
      return { documentElement: { localName: "feed", namespaceURI: NS, children: [] },
        getElementsByTagName: (n) => (n === "parsererror" ? [{}] : []) };
    }
  }
  assert.equal(kindOf(() => atom.parseAtom(feed([entry()]), { DOMParser: Spy })), "parse");
  assert.deepEqual(seen, ["application/xml"]);
});

test("parseAtom: a DOCTYPE or an entity declaration is refused before parsing (billion laughs, external entities)", () => {
  let parsed = 0;
  class Count extends FakeDOMParser { parseFromString(...a) { parsed++; return super.parseFromString(...a); } }
  const laughs = '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
    + '<feed xmlns="' + NS + '"><entry><title>&lol2;</title></entry></feed>';
  const external = '<?xml version="1.0"?><!DOCTYPE feed SYSTEM "http://127.0.0.1:1/x.dtd">' + feed([entry()]);
  const lower = feed([entry()]).replace("<feed", "<!doctype feed><feed");
  const spaced = feed([entry()]).replace("<feed", "<! ENTITY x 'y'><feed");
  for (const bad of [laughs, external, lower, spaced]) {
    assert.equal(kindOf(() => atom.parseAtom(bad, { DOMParser: Count })), "dtd");
  }
  assert.equal(parsed, 0, "the parser never saw them");
});

test("parseAtom: a text over the size limit is refused before parsing; the entry count is limited", () => {
  let parsed = 0;
  class Count extends FakeDOMParser { parseFromString(...a) { parsed++; return super.parseFromString(...a); } }
  assert.equal(kindOf(() => atom.parseAtom("x".repeat(atom.MAX_BYTES + 1), { DOMParser: Count })), "too-large");
  assert.equal(parsed, 0);
  const many = [];
  for (let i = 0; i < 250; i++) many.push("<entry><title>Riksdagen " + i + "</title></entry>");
  assert.equal(atom.parseAtom(feed(many), opts).length, atom.MAX_ENTRIES);
});

test("parseAtom: a title over the limit is not cut: the entry has no headline and is dropped; the summary is only a match aid", () => {
  const long = "Riksdagen ".repeat(600); // 6000 characters
  const entries = atom.parseAtom(feed([
    entry({ title: long, link: "https://www.sverigesradio.se/artikel/1" }),
    entry({ title: "Rubrik utan träff", summary: "x".repeat(30000) + " riksdagen", link: "https://www.sverigesradio.se/artikel/2" }),
    entry({ title: "Regeringen " + "ord ".repeat(1000), link: "https://www.sverigesradio.se/artikel/3" }),
  ]), opts);
  assert.equal(entries[0].title, "");
  assert.equal(entries[1].summary, "", "an over-long summary is ignored, never cut and matched");
  assert.equal(select(entries).length, 1);
  assert.ok(select(entries)[0].title.endsWith("ord"), "a long headline under the limit is kept whole");
  const hugeLink = entry({ link: "https://www.sverigesradio.se/artikel/" + "1".repeat(3000) });
  assert.equal(atom.parseAtom(feed([hugeLink]), opts)[0].link, "");
});

// ---------------------------------------------------------------- hostile input through the same rules

test("hostile entries: bad links are dropped by logic.js (R9.1), markup in a headline becomes text", () => {
  const links = ["javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://www.sverigesradio.se/a",
    "https://evil.example/artikel/1", "https://sverigesradio.se.evil.example/artikel/1",
    "https://evil.example/?u=https://www.sverigesradio.se/artikel/1", "//www.sverigesradio.se/artikel/1",
    "/artikel/1", "https://user:pw@www.sverigesradio.se/artikel/1", "https://www.sverigesradio.se/a b", ""];
  const entries = atom.parseAtom(feed(links.map((l, i) => entry({ title: "Riksdagen " + i, link: l }))), opts);
  assert.deepEqual(select(entries).map((i) => i.url), []);
  const good = select(atom.parseAtom(feed([
    entry({ title: "&lt;img src=x onerror=alert(1)&gt; Riksdagen &lt;script&gt;x&lt;/script&gt;" }),
  ]).replace(/&amp;lt;/g, "&lt;").replace(/&amp;gt;/g, "&gt;"), opts));
  assert.equal(good.length, 1);
  assert.ok(!/[<>]/.test(good[0].title));
  assert.equal(good[0].title, "Riksdagen x"); // tags go, the text between them stays (R1.3)
});

test("hostile entries: duplicate links are removed, far-future and old times are handled by logic.js", () => {
  const items = select(atom.parseAtom(feed([
    entry({ title: "Riksdagen först", link: "https://www.sverigesradio.se/artikel/1?x=1" }),
    entry({ title: "Riksdagen igen", link: "https://sverigesradio.se/artikel/1/" }),
    entry({ title: "Riksdagen framtid", link: "https://www.sverigesradio.se/artikel/2", published: "2099-01-01T00:00:00Z", updated: null }),
    entry({ title: "Riksdagen gammal", link: "https://www.sverigesradio.se/artikel/3", published: "2020-01-01T00:00:00Z", updated: null }),
  ]), opts));
  assert.deepEqual(items.map((i) => i.title), ["Riksdagen först", "Riksdagen framtid"]);
  assert.equal(items[1].published, null);
});

test("keyword selection is the same as the shared cases (R4.5), also through XML", () => {
  let n = 0;
  for (const c of shared.keywords) {
    const headline = c.input.headline;
    if (logic.cleanHeadline(headline) === "") continue;
    const description = c.input.description;
    const xml = feed([entry({
      title: headline,
      summary: description === undefined || description === null ? null : description,
      link: "https://www.sverigesradio.se/artikel/" + (1000 + n),
    })]);
    const items = select(atom.parseAtom(xml, opts));
    assert.equal(items.length === 1, c.expected.match, c.id);
    n++;
  }
  assert.ok(n > 100);
});

// ---------------------------------------------------------------- reading the response

const encoder = new TextEncoder();

function streamOf(chunks, extra = {}) {
  let i = 0;
  let cancelled = false;
  const reader = {
    read: async () => (i < chunks.length ? { done: false, value: chunks[i++] } : { done: true }),
    cancel: async () => { cancelled = true; },
  };
  return {
    status: 200,
    headers: { get: (k) => (extra.headers || {})[k.toLowerCase()] ?? null },
    body: { getReader: () => reader },
    get cancelled() { return cancelled; },
    get chunksRead() { return i; },
  };
}

test("readLimited: a stream over the limit is cancelled and refused while it is read", async () => {
  const response = streamOf([new Uint8Array(600), new Uint8Array(600), new Uint8Array(600), new Uint8Array(600)]);
  await assert.rejects(atom.readLimited(response, 1000), (e) => e.kind === "too-large");
  assert.equal(response.cancelled, true);
  assert.equal(response.chunksRead, 2, "the rest of the body was not read");
});

test("readLimited: the announced length is checked first, without touching the body", async () => {
  let touched = false;
  const response = { headers: { get: (k) => (k === "content-length" ? "999999" : null) },
    get body() { touched = true; return null; }, text: async () => { touched = true; return ""; } };
  await assert.rejects(atom.readLimited(response, 1000), (e) => e.kind === "too-large");
  assert.equal(touched, false);
});

test("readLimited: a simple response without a stream is checked after reading; a real Response works", async () => {
  await assert.rejects(atom.readLimited({ text: async () => "x".repeat(1001), headers: { get: () => null } }, 1000),
    (e) => e.kind === "too-large");
  assert.equal(await atom.readLimited({ text: async () => "abc", headers: { get: () => null } }, 1000), "abc");
  assert.equal(await atom.readLimited({ text: async () => "abc" }, 1000), "abc");
  assert.equal(await atom.readLimited(new Response("Ärlig rubrik åäö"), 1000), "Ärlig rubrik åäö");
  await assert.rejects(atom.readLimited(new Response("x".repeat(5000)), 1000), (e) => e.kind === "too-large");
  await assert.rejects(atom.readLimited({ text: async () => 5, headers: { get: () => null } }, 1000),
    (e) => e.kind === "parse");
});

test("readLimited: the charset of the response is used (ISO-8859-1), an unknown one means UTF-8", async () => {
  const latin = Uint8Array.from([0x52, 0xe5, 0x64, 0x20, 0xe4, 0xf6]); // "Råd äö" in ISO-8859-1
  const r1 = streamOf([latin], { headers: { "content-type": "application/atom+xml; charset=ISO-8859-1" } });
  assert.equal(await atom.readLimited(r1, 1000), "Råd äö");
  const r2 = streamOf([encoder.encode("Råd äö")], { headers: { "content-type": "application/atom+xml; charset=nonsense-9" } });
  assert.equal(await atom.readLimited(r2, 1000), "Råd äö");
  const r3 = streamOf([encoder.encode("Råd äö")]);
  assert.equal(await atom.readLimited(r3, 1000), "Råd äö");
  // A multi-byte character split between two chunks is decoded whole.
  const bytes = encoder.encode("å");
  const r4 = streamOf([bytes.slice(0, 1), bytes.slice(1)]);
  assert.equal(await atom.readLimited(r4, 1000), "å");
});

// ---------------------------------------------------------------- the request

function okResponse(text, headers = {}) {
  return new Response(text, { status: 200, headers });
}

test("fetchAtom: the request has credentials omit and cache no-store, and the entries come back (R7.1)", async () => {
  const seen = [];
  const controller = new AbortController();
  const fetchFn = async (url, init) => { seen.push([url, init]); return okResponse(feed([entry()])); };
  const entries = await atom.fetchAtom(fetchFn, "https://feed.example/x", { signal: controller.signal, DOMParser: FakeDOMParser });
  assert.equal(entries.length, 1);
  assert.equal(seen.length, 1);
  assert.equal(seen[0][0], "https://feed.example/x");
  assert.deepEqual(seen[0][1], { credentials: "omit", cache: "no-store", signal: controller.signal });
  await atom.fetchAtom(fetchFn, "https://feed.example/x", { DOMParser: FakeDOMParser });
  assert.deepEqual(seen[1][1], { credentials: "omit", cache: "no-store" });
});

test("fetchAtom: every failure is an AtomError with a fixed message that holds nothing from the feed or the error", async () => {
  const secret = "GEHEIM-INNEHÅLL-riksdagen";
  const cases = [
    ["network", () => { throw new TypeError("Failed to fetch " + secret); }],
    ["status", async () => new Response(secret, { status: 500 })],
    ["status", async () => new Response(secret, { status: 404 })],
    ["status", async () => new Response(null, { status: 204 })],
    ["status", async () => undefined],
    ["parse", async () => okResponse("<feed>" + secret)],
    ["parse", async () => okResponse(secret)],
    ["not-atom", async () => okResponse('<rss version="2.0"><channel>' + secret + "</channel></rss>")],
    ["dtd", async () => okResponse('<!DOCTYPE x [<!ENTITY a "' + secret + '">]><feed/>')],
    ["too-large", async () => okResponse("x".repeat(atom.MAX_BYTES + 10))],
    ["too-large", async () => okResponse("x", { "content-length": String(atom.MAX_BYTES + 1) })],
    ["network", async () => ({ status: 200, headers: { get: () => null }, text: async () => { throw new Error(secret); } })],
  ];
  for (const [kind, fetchFn] of cases) {
    await assert.rejects(atom.fetchAtom(fetchFn, "https://feed.example/x", { DOMParser: FakeDOMParser }), (e) => {
      assert.ok(e instanceof atom.AtomError);
      assert.equal(e.kind, kind);
      assert.equal(e.message, "feed could not be read: " + kind);
      assert.ok(!String(e.stack).includes("GEHEIM") && !JSON.stringify(e).includes("GEHEIM"));
      assert.ok(!e.cause);
      return true;
    }, kind);
  }
});

test("fetchAtom: an aborted request (the timeout) is the kind timeout", async () => {
  const controller = new AbortController();
  const fetchFn = (url, init) => new Promise((resolve, reject) => {
    init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  });
  const run = atom.fetchAtom(fetchFn, "https://feed.example/x", { signal: controller.signal, DOMParser: FakeDOMParser });
  controller.abort();
  await assert.rejects(run, (e) => e.kind === "timeout");
  // Aborted while the body is read.
  const c2 = new AbortController();
  const slow = async () => ({ status: 200, headers: { get: () => null },
    text: () => new Promise((resolve, reject) => c2.signal.addEventListener("abort", () => reject(new Error("x")))) });
  const run2 = atom.fetchAtom(slow, "https://feed.example/x", { signal: c2.signal, DOMParser: FakeDOMParser });
  await new Promise((r) => setImmediate(r));
  c2.abort();
  await assert.rejects(run2, (e) => e.kind === "timeout");
});

test("atom.js loads as a classic script and creates only the global NewsAtom", async () => {
  const vm = await import("node:vm");
  const source = fs.readFileSync(new URL("../atom.js", import.meta.url), "utf-8");
  const context = vm.createContext({ TextDecoder, Uint8Array });
  vm.runInContext(source, context, { filename: "atom.js" });
  assert.deepEqual(Object.keys(context).sort(), ["NewsAtom", "TextDecoder", "Uint8Array"]);
  assert.deepEqual(Object.keys(context.NewsAtom).sort(), Object.keys(atom).sort());
});
