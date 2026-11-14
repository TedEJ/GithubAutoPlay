// The Atom side of the live fetch (step S11, requirements R7.1, R7.3, R11.2):
// fetch a feed from a `fetchedBy: browser` source and turn the Atom text into
// plain entries. Nothing else.
//
// What is here: the request (credentials omitted, no HTTP cache, a size limit
// that is enforced while the body is read), the parsing with the browser's
// DOMParser, and the mapping of Atom entries to plain objects. What is not here:
// no rendering, no timers, no call limits (app.js), no keyword matching, cleaning,
// link check or time handling (logic.js), and no storage of any kind. The
// entries live only in the caller's variables (R7.3).
//
// Errors carry a fixed kind (see AtomError) and a fixed message. They never carry
// text from the feed or from the original error, so nothing from the feed can
// reach a log or an error report.
//
// Loading: a classic script (global `NewsAtom`) or Node (`require`). The parsing
// needs a DOMParser; the browser has one, and the tests pass their own.
(function (root) {
  "use strict";

  // The XML namespace of Atom (RFC 4287). It names a namespace, it is not
  // an address that is ever requested.
  const ATOM_NS = "http://www.w3.org/2005/Atom";

  // Limits (hostile or broken feeds). The feed is about 20 entries.
  const MAX_BYTES = 2 * 1024 * 1024; // as the build's limit for RSS (R9.4)
  const MAX_ENTRIES = 100; // entries looked at; logic.selectItems keeps 20
  const MAX_TITLE = 5000;
  const MAX_SUMMARY = 20000; // only used for the keyword match, then dropped
  const MAX_LINK = 2000;
  const MAX_TIME = 100;

  const KINDS = ["network", "timeout", "status", "too-large", "dtd", "parse", "not-atom"];

  class AtomError extends Error {
    constructor(kind) {
      super("feed could not be read: " + kind);
      this.name = "AtomError";
      this.kind = kind;
    }
  }

  // A document type declaration (and so any entity declaration) has no place in
  // an Atom feed. It is refused before parsing, so no entity expansion trick can
  // reach the parser. The browser's parser does not load external entities
  // either (R9.4).
  const DTD = /<!\s*(?:DOCTYPE|ENTITY)/i;

  // ------------------------------------------------------------------------
  // Reading the response with a size limit

  function charsetOf(response) {
    let type = "";
    try {
      type = response.headers && typeof response.headers.get === "function"
        ? String(response.headers.get("content-type") || "") : "";
    } catch (e) {
      type = "";
    }
    const m = /;\s*charset\s*=\s*"?([A-Za-z0-9._:-]{1,40})"?/i.exec(type);
    return m ? m[1] : "utf-8";
  }

  function decoderFor(label) {
    try {
      return new TextDecoder(label);
    } catch (e) {
      return new TextDecoder("utf-8");
    }
  }

  // The body of a response as text, refusing more than `max` bytes. The limit is
  // checked against the announced length first, then while the body is read, so
  // a huge body is never read to the end.
  async function readLimited(response, max) {
    const limit = typeof max === "number" ? max : MAX_BYTES;
    let announced = NaN;
    try {
      announced = Number(response.headers.get("content-length"));
    } catch (e) {
      announced = NaN;
    }
    if (Number.isFinite(announced) && announced > limit) throw new AtomError("too-large");

    const body = response.body;
    if (body && typeof body.getReader === "function") {
      const reader = body.getReader();
      const chunks = [];
      let total = 0;
      for (;;) {
        const step = await reader.read();
        if (step.done) break;
        total += step.value.length;
        if (total > limit) {
          try { await reader.cancel(); } catch (e) { /* nothing to do */ }
          throw new AtomError("too-large");
        }
        chunks.push(step.value);
      }
      const bytes = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.length;
      }
      return decoderFor(charsetOf(response)).decode(bytes);
    }
    // No stream (a simple response object): the text is read and then checked.
    const text = await response.text();
    if (typeof text !== "string") throw new AtomError("parse");
    if (text.length > limit) throw new AtomError("too-large");
    return text;
  }

  // ------------------------------------------------------------------------
  // Atom text -> plain entries (R11.2)

  function isAtom(node, name) {
    return node && node.namespaceURI === ATOM_NS && node.localName === name;
  }

  function firstChild(entry, name) {
    for (const child of Array.from(entry.children || [])) {
      if (isAtom(child, name)) return child;
    }
    return null;
  }

  function textOf(entry, name, max) {
    const child = firstChild(entry, name);
    if (!child) return "";
    const text = child.textContent;
    return typeof text === "string" && text.length <= max ? text : "";
  }

  // The first link with rel="alternate" or without rel (R11.2) that has a href.
  function linkOf(entry) {
    for (const child of Array.from(entry.children || [])) {
      if (!isAtom(child, "link")) continue;
      const rel = child.getAttribute("rel");
      if (rel !== null && rel !== "alternate") continue;
      const href = child.getAttribute("href");
      if (typeof href === "string" && href !== "" && href.length <= MAX_LINK) return href;
    }
    return "";
  }

  // The Atom text -> an array of plain entries with exactly these fields: title,
  // summary, link, published, updated (strings, "" when missing). `summary` is
  // there only for the keyword match and must be dropped after it. `content`,
  // `author`, `id` and `category` are never read. A title over the limit is
  // given as "" (the entry is then dropped as one without a headline), because a
  // headline is never cut. Throws AtomError: "too-large", "dtd", "parse",
  // "not-atom".
  //
  // `options.DOMParser`: the parser class (default: the global one).
  function parseAtom(text, options) {
    if (typeof text !== "string") throw new AtomError("parse");
    if (text.length > MAX_BYTES) throw new AtomError("too-large");
    if (DTD.test(text)) throw new AtomError("dtd");
    const Parser = (options && options.DOMParser) || root.DOMParser;
    if (typeof Parser !== "function") throw new AtomError("parse");
    let doc;
    try {
      doc = new Parser().parseFromString(text, "application/xml");
    } catch (e) {
      throw new AtomError("parse");
    }
    if (!doc || !doc.documentElement) throw new AtomError("parse");
    // A browser reports a parse error as a document with a <parsererror> element.
    if (doc.getElementsByTagName("parsererror").length > 0) throw new AtomError("parse");
    const feed = doc.documentElement;
    if (!isAtom(feed, "feed")) throw new AtomError("not-atom");

    const entries = [];
    for (const child of Array.from(feed.children || [])) {
      if (!isAtom(child, "entry")) continue;
      if (entries.length >= MAX_ENTRIES) break;
      entries.push({
        title: textOf(child, "title", MAX_TITLE),
        summary: textOf(child, "summary", MAX_SUMMARY),
        link: linkOf(child),
        published: textOf(child, "published", MAX_TIME),
        updated: textOf(child, "updated", MAX_TIME),
      });
    }
    return entries;
  }

  // ------------------------------------------------------------------------
  // The request (R7.1)

  // Fetch `url` and return the plain entries. `fetchFn` is fetch (or a fake),
  // `options.signal` an AbortSignal for the timeout (app.js sets it up),
  // `options.DOMParser` as for parseAtom. Throws AtomError only, with a kind
  // from KINDS.
  async function fetchAtom(fetchFn, url, options) {
    const opts = options || {};
    const init = { credentials: "omit", cache: "no-store" };
    if (opts.signal) init.signal = opts.signal;
    const timedOut = () => Boolean(opts.signal && opts.signal.aborted);
    let text;
    try {
      let response;
      try {
        response = await fetchFn(url, init);
      } catch (e) {
        throw new AtomError(timedOut() ? "timeout" : "network");
      }
      if (!response || response.status !== 200) throw new AtomError("status");
      try {
        text = await readLimited(response, opts.maxBytes);
      } catch (e) {
        if (e instanceof AtomError) throw e;
        throw new AtomError(timedOut() ? "timeout" : "network");
      }
    } catch (e) {
      throw e instanceof AtomError ? e : new AtomError("network");
    }
    return parseAtom(text, { DOMParser: opts.DOMParser });
  }

  const api = {
    ATOM_NS,
    MAX_BYTES,
    MAX_ENTRIES,
    KINDS,
    AtomError,
    readLimited,
    parseAtom,
    fetchAtom,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.NewsAtom = api;
  }
})(typeof self !== "undefined" ? self : globalThis);
