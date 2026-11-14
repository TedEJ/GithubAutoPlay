// The pure logic of the page: the JavaScript twin of the Python build logic
// (newsreader/select.py, keywords.py, timeutil.py). It gives the same answers as
// Python for every case in tests/shared-cases.json (checked by site/tests).
//
// No DOM, no network, no storage, no clock: "now" is always a parameter
// (a Date, or epoch milliseconds, or UTC text like 2026-11-13T13:05:12Z).
// No dependencies. Time zone rules are written out (no Intl), SHA-256 is
// implemented here, so Node and every browser give the same results.
//
// Loading: a classic script (`<script src="logic.js">` gives the global
// `NewsLogic`) or Node (`require`, or `import logic from "./logic.js"`).
// It is not an ES module: do not add `"type": "module"` to a package.json
// above this folder.
(function (root) {
  "use strict";

  // ------------------------------------------------------------------------
  // Headline cleaning (R1.3)

  // White space: space, tab, LF, CR, FF, VT and U+00A0. Not trim(), not \s.
  const WS_CLASS = " \\t\\n\\r\\f\\v\\u00a0";
  const WS_RUN = new RegExp("[" + WS_CLASS + "]+", "g");
  const WS_CHARS = " \t\n\r\f\v\u00a0";
  const TIME_WS_CHARS = " \t\n\r\f\v";

  // Remove leading and trailing characters of `chars`. Two linear scans (a
  // regular expression like /^[ ]+|[ ]+$/ is quadratic on long runs).
  function trimChars(text, chars) {
    let start = 0;
    let end = text.length;
    while (start < end && chars.indexOf(text.charAt(start)) !== -1) start++;
    while (end > start && chars.indexOf(text.charAt(end - 1)) !== -1) end--;
    return text.slice(start, end);
  }

  function stripWs(text) {
    return trimChars(text, WS_CHARS);
  }

  const TAG = /<\/?[A-Za-z][^<>]*>|<!--[\s\S]*?-->/g;

  const NAMED_ENTITIES = new Map(Object.entries({
    amp: "&", lt: "<", gt: ">", quot: '"', apos: "'",
    nbsp: "\u00a0", laquo: "«", raquo: "»",
    ndash: "–", mdash: "—", hellip: "…",
    lsquo: "‘", rsquo: "’", ldquo: "“", rdquo: "”",
    auml: "ä", ouml: "ö", aring: "å",
    Auml: "Ä", Ouml: "Ö", Aring: "Å",
    eacute: "é", Eacute: "É", euro: "€", copy: "©",
  }));

  const ENTITY = /&(?:#([0-9]+)|#[xX]([0-9A-Fa-f]+)|([A-Za-z][A-Za-z0-9]*));/g;

  function decodeEntity(whole, dec, hex, name) {
    if (name !== undefined) {
      return NAMED_ENTITIES.has(name) ? NAMED_ENTITIES.get(name) : whole;
    }
    const code = dec !== undefined ? parseInt(dec, 10) : parseInt(hex, 16);
    // Valid code points only: not 0, not a surrogate, not above U+10FFFF.
    if (!(code > 0) || (code >= 0xd800 && code <= 0xdfff) || code > 0x10ffff) {
      return whole;
    }
    return String.fromCodePoint(code);
  }

  function cleanHeadline(text) {
    text = String(text).replace(TAG, "");
    text = text.replace(ENTITY, decodeEntity);
    text = text.replace(WS_RUN, " ");
    return stripWs(text);
  }

  // ------------------------------------------------------------------------
  // Keywords (R4.3, R4.4, design 7.2)

  class KeywordsError extends Error {
    constructor(message) {
      super(message);
      this.name = "KeywordsError";
    }
  }

  const WORD = /[\p{L}\p{Nd}]+/gu;

  // Words of the text (NFC first, case kept).
  function splitWords(text) {
    return text.normalize("NFC").match(WORD) || [];
  }

  // Python's str.strip() white space (str.isspace), for validating the file.
  const PY_SPACE_CHARS = (function () {
    let chars = "\t\n\v\f\r \x85\xa0\u1680\u2028\u2029\u202f\u205f\u3000";
    for (let c = 0x1c; c <= 0x1f; c++) chars += String.fromCharCode(c);
    for (let c = 0x2000; c <= 0x200a; c++) chars += String.fromCharCode(c);
    return chars;
  })();

  function stringList(value, where, lowercase) {
    if (!Array.isArray(value)) throw new KeywordsError(where + " must be a list");
    const result = [];
    for (let item of value) {
      if (typeof item !== "string") throw new KeywordsError(where + " must hold only strings");
      if (item === "" || item !== trimChars(item, PY_SPACE_CHARS)) {
        throw new KeywordsError(where + ": empty term or term with surrounding white space: " + JSON.stringify(item));
      }
      const nfc = item.normalize("NFC");
      if (lowercase) item = nfc.toLowerCase();
      else if (nfc !== item) throw new KeywordsError(where + ": term is not NFC-normalised: " + JSON.stringify(item));
      result.push(item);
    }
    if (new Set(result).size !== result.length) {
      throw new KeywordsError(where + ": duplicate term (after lowercasing)");
    }
    return result;
  }

  function checkKeys(obj, allowed, where) {
    if (obj === null || typeof obj !== "object" || Array.isArray(obj)) {
      throw new KeywordsError(where + " must be an object");
    }
    const keys = Object.keys(obj).sort();
    if (keys.length !== allowed.length || keys.some((k, i) => k !== [...allowed].sort()[i])) {
      throw new KeywordsError(where + " must have exactly the keys " + allowed.join(", "));
    }
  }

  function singleWord(term, where) {
    const body = term.endsWith("*") ? term.slice(0, -1) : term;
    const words = body === "" ? [] : splitWords(body);
    if (body === "" || words.length !== 1 || words[0] !== body) {
      throw new KeywordsError(where + ": not a single word (letters and digits, optional trailing *): " + JSON.stringify(term));
    }
    return body;
  }

  // The parsed politics-keywords.json -> a validated keyword object, with the
  // same rules and the same normalisation as newsreader/keywords.py. (A
  // duplicate key inside a JSON object cannot be seen after JSON.parse; the
  // Python side rejects it and the file is shared.)
  function validateKeywords(data) {
    checkKeys(data, ["version", "category", "include", "exclude"], "file");
    if (data.version !== 1) throw new KeywordsError("version must be 1");
    if (data.category !== "politics-sweden") throw new KeywordsError("category must be 'politics-sweden'");
    const inc = data.include;
    const exc = data.exclude;
    checkKeys(inc, ["words", "caseSensitive"], "include");
    checkKeys(exc, ["words", "phrases"], "exclude");

    const incWords = stringList(inc.words, "include.words", true);
    const caseTerms = stringList(inc.caseSensitive, "include.caseSensitive", false);
    const excWords = stringList(exc.words, "exclude.words", true);
    const excPhrases = stringList(exc.phrases, "exclude.phrases", true);
    if (incWords.length === 0 && caseTerms.length === 0) {
      throw new KeywordsError("the include lists are both empty");
    }

    const exact = [];
    const prefixes = [];
    for (const term of incWords) {
      const body = singleWord(term, "include.words");
      (term.endsWith("*") ? prefixes : exact).push(body);
    }
    for (const term of excWords) {
      if (term.endsWith("*")) throw new KeywordsError("exclude.words: no wildcard allowed: " + JSON.stringify(term));
      singleWord(term, "exclude.words");
    }
    const phrases = [];
    for (const phrase of excPhrases) {
      const words = splitWords(phrase);
      if (words.length < 2 || words.join(" ") !== phrase) {
        throw new KeywordsError("exclude.phrases: two or more words separated by single spaces, no other characters: " + JSON.stringify(phrase));
      }
      phrases.push(words);
    }
    for (const term of caseTerms) {
      if (term === term.toLowerCase() && term === term.toUpperCase()) {
        throw new KeywordsError("include.caseSensitive: term has no letters, use words: " + JSON.stringify(term));
      }
    }
    return {
      includeExact: new Set(exact),
      includePrefixes: prefixes,
      caseSensitive: caseTerms,
      excludeWords: new Set(excWords),
      excludePhrases: phrases,
    };
  }

  // Rule 6 and rules 2 to 5 of keywords.py for one cleaned text.
  function hasHit(keywords, text) {
    text = text.normalize("NFC");
    for (const term of keywords.caseSensitive) {
      if (text.includes(term)) return true;
    }
    const words = splitWords(text).map((w) => w.toLowerCase());
    const removed = new Array(words.length).fill(false);
    for (const phrase of keywords.excludePhrases) {
      const n = phrase.length;
      for (let i = 0; i + n <= words.length; i++) {
        let same = true;
        for (let j = 0; j < n; j++) {
          if (words[i + j] !== phrase[j]) { same = false; break; }
        }
        if (same) for (let j = i; j < i + n; j++) removed[j] = true;
      }
    }
    for (let i = 0; i < words.length; i++) {
      const word = words[i];
      if (removed[i] || keywords.excludeWords.has(word)) continue;
      if (keywords.includeExact.has(word)) return true;
      for (const prefix of keywords.includePrefixes) {
        if (word.startsWith(prefix)) return true;
      }
    }
    return false;
  }

  // True if the item is about Swedish politics (R4.4). Both texts are cleaned
  // first; a missing or empty description is ignored.
  function matchesKeywords(keywords, headline, description) {
    for (const text of [headline, description]) {
      if (text === undefined || text === null || text === "") continue;
      if (hasHit(keywords, cleanHeadline(text))) return true;
    }
    return false;
  }

  // ------------------------------------------------------------------------
  // URL check and normalisation (R9.1, R5.3) and id (R5.4)

  const URL_RE = /^([A-Za-z][A-Za-z0-9+.-]*):\/\/([^/?#]*)([^?#]*)(?:\?[^#]*)?(?:#.*)?$/;
  const HOST_RE = /^[a-z0-9-]+(?:\.[a-z0-9-]+)*$/;
  const PRINTABLE_ASCII = /^[\x21-\x7E]+$/;

  // `{scheme, host, path}` or null; same rules as parse_url in select.py.
  function parseUrl(url) {
    if (typeof url !== "string") return null;
    url = stripWs(url);
    if (!PRINTABLE_ASCII.test(url) || url.includes("\\")) return null;
    const m = URL_RE.exec(url);
    if (!m) return null;
    const scheme = m[1].toLowerCase();
    const host = m[2].toLowerCase();
    if (scheme !== "http" && scheme !== "https") return null;
    if (!HOST_RE.test(host)) return null;
    return { scheme, host, path: m[3] };
  }

  function onAllowedHost(host, allowedHosts) {
    return allowedHosts.some((a) => host === a || host.endsWith("." + a));
  }

  function stripTrailingSlashes(path) {
    let end = path.length;
    while (end > 0 && path.charCodeAt(end - 1) === 47) end--;
    return path.slice(0, end);
  }

  // The normalised URL if usable for a source with these allowedHosts, else null.
  function checkUrl(url, allowedHosts) {
    const parsed = parseUrl(url);
    if (parsed === null) return null;
    let host = parsed.host;
    if (!onAllowedHost(host, allowedHosts)) return null;
    if (host.startsWith("www.")) host = host.slice(4);
    return parsed.scheme + "://" + host + stripTrailingSlashes(parsed.path);
  }

  const SHA_K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]);

  function utf8Bytes(text) {
    return new TextEncoder().encode(text);
  }

  // SHA-256 of a string (UTF-8) as 64 lower-case hex characters. Synchronous.
  function sha256Hex(text) {
    const data = utf8Bytes(text);
    const bitLen = data.length * 8;
    const total = (((data.length + 9 + 63) >> 6) << 6);
    const buf = new Uint8Array(total);
    buf.set(data);
    buf[data.length] = 0x80;
    const view = new DataView(buf.buffer);
    view.setUint32(total - 8, Math.floor(bitLen / 0x100000000));
    view.setUint32(total - 4, bitLen >>> 0);
    const h = new Uint32Array([
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ]);
    const w = new Uint32Array(64);
    const rotr = (x, n) => (x >>> n) | (x << (32 - n));
    for (let off = 0; off < total; off += 64) {
      for (let i = 0; i < 16; i++) w[i] = view.getUint32(off + i * 4);
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, hh] = h;
      for (let i = 0; i < 64; i++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const ch = (e & f) ^ (~e & g);
        const t1 = (hh + S1 + ch + SHA_K[i] + w[i]) >>> 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const maj = (a & b) ^ (a & c) ^ (b & c);
        const t2 = (S0 + maj) >>> 0;
        hh = g; g = f; f = e; e = (d + t1) >>> 0;
        d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      h[0] += a; h[1] += b; h[2] += c; h[3] += d;
      h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
    }
    return Array.from(h, (x) => x.toString(16).padStart(8, "0")).join("");
  }

  // `id` (R5.4): the first 16 hex characters of the SHA-256 of the normalised URL.
  function itemId(normalisedUrl) {
    return sha256Hex(normalisedUrl).slice(0, 16);
  }

  // ------------------------------------------------------------------------
  // Time (R2): the rules of newsreader/timeutil.py, with Europe/Stockholm
  // written out. Times are whole seconds since 1970-01-01T00:00:00Z in the
  // helpers below ("naive" local times are counted the same way).

  const MIN_YEAR = 1970;
  const MAX_YEAR = 9998;
  const MISSING_DISPLAY = "Tid saknas";
  const FUTURE_LIMIT_MS = 10 * 60 * 1000;
  const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
  const MAX_ITEMS = 20;
  const HOUR = 3600;

  const MONTHS = { Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6, Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12 };
  const ZONE_NAMES = {
    UT: 0, UTC: 0, GMT: 0, Z: 0,
    EST: -300, EDT: -240, CST: -360, CDT: -300,
    MST: -420, MDT: -360, PST: -480, PDT: -420,
  };

  const RFC822 = /^(?:[A-Za-z]{3},[ ]+)?([0-9]{1,2})[ ]+([A-Za-z]{3})[ ]+([0-9]{4})[ ]+([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?(?:[ ]+([A-Za-z]+|[+-][0-9]{4}))?$/;
  const ISO = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?(?:\.[0-9]+)?(Z|z|[+-][0-9]{2}(?::?[0-9]{2})?)?$/;
  const UTC_TEXT = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$/;

  // Days since 1970-01-01 of a proleptic Gregorian date (month 1-12).
  function daysFromCivil(y, m, d) {
    y -= m <= 2 ? 1 : 0;
    const era = Math.floor(y / 400);
    const yoe = y - era * 400;
    const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
    const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
    return era * 146097 + doe - 719468;
  }

  function civilFromDays(z) {
    z += 719468;
    const era = Math.floor(z / 146097);
    const doe = z - era * 146097;
    const yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365);
    const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
    const mp = Math.floor((5 * doy + 2) / 153);
    const d = doy - Math.floor((153 * mp + 2) / 5) + 1;
    const m = mp < 10 ? mp + 3 : mp - 9;
    return [era * 400 + yoe + (m <= 2 ? 1 : 0), m, d];
  }

  function isLeap(y) {
    return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
  }

  function daysInMonth(y, m) {
    return [31, isLeap(y) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
  }

  // Last Sunday of the month, as days since 1970-01-01.
  function lastSunday(y, m) {
    const last = daysFromCivil(y, m, daysInMonth(y, m));
    const weekday = (((last + 4) % 7) + 7) % 7; // 1970-01-01 was a Thursday; 0 = Sunday
    return last - weekday;
  }

  // Summer time of Europe/Stockholm in a year, as [start, end) in UTC seconds,
  // or null when the year has none. From the time zone database:
  // 1970-1979 none; 1980 from 6 April; from 1981 the last Sunday of March;
  // ends the last Sunday of September until 1995 and of October from 1996;
  // changes at 01:00 UTC. This is also the EU rule for all later years.
  function summerWindow(year) {
    if (year < 1980) return null;
    const startDay = year === 1980 ? daysFromCivil(1980, 4, 6) : lastSunday(year, 3);
    const endDay = lastSunday(year, year <= 1995 ? 9 : 10);
    return [startDay * 86400 + HOUR, endDay * 86400 + HOUR];
  }

  function inSummer(utcSeconds) {
    const year = civilFromDays(Math.floor(utcSeconds / 86400))[0];
    const w = summerWindow(year);
    return w !== null && utcSeconds >= w[0] && utcSeconds < w[1];
  }

  // Stockholm wall-clock time (counted as seconds, fold 0) -> UTC seconds.
  // A time in the skipped hour is read with +01:00; a time in the repeated
  // hour is the first occurrence (+02:00).
  function stockholmToUtc(naive, year) {
    const w = summerWindow(year);
    if (w !== null) {
      const asSummer = naive - 2 * HOUR;
      if (asSummer >= w[0] && asSummer < w[1]) return asSummer;
    }
    return naive - HOUR;
  }

  // '+0100', '+01:00', '+01' -> offset in seconds, or null.
  function offsetSeconds(text) {
    const sign = text[0] === "-" ? -1 : 1;
    const digits = text.slice(1).replace(":", "");
    const hours = parseInt(digits.slice(0, 2), 10);
    const minutes = digits.length > 2 ? parseInt(digits.slice(2, 4), 10) : 0;
    if (hours > 23 || minutes > 59) return null;
    return sign * (hours * 3600 + minutes * 60);
  }

  // Fields plus an offset in seconds or null (Stockholm) -> UTC seconds or null.
  function buildTime(year, month, day, hour, minute, second, offset) {
    if (year < MIN_YEAR || year > MAX_YEAR) return null;
    if (second > 59 || hour > 23 || minute > 59) return null;
    if (month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)) return null;
    const naive = daysFromCivil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second;
    return offset === null ? stockholmToUtc(naive, year) : naive - offset;
  }

  // Time text -> UTC seconds since 1970-01-01, or null when missing or unusable.
  // Accepts RFC 822/2822 and ISO 8601; see timeutil.py for the rules.
  function parseTime(text) {
    if (typeof text !== "string") return null;
    // The trimming set of timeutil.py: the cleaning set without U+00A0.
    text = trimChars(text, TIME_WS_CHARS);
    let m = RFC822.exec(text);
    if (m) {
      const monthName = m[2].charAt(0).toUpperCase() + m[2].slice(1).toLowerCase();
      if (!Object.prototype.hasOwnProperty.call(MONTHS, monthName)) return null;
      const month = MONTHS[monthName];
      let offset;
      const zone = m[7];
      if (zone === undefined) offset = null;
      else if (zone[0] === "+" || zone[0] === "-") {
        offset = offsetSeconds(zone);
        if (offset === null) return null;
      } else if (Object.prototype.hasOwnProperty.call(ZONE_NAMES, zone.toUpperCase())) {
        offset = ZONE_NAMES[zone.toUpperCase()] * 60;
      } else return null;
      return buildTime(+m[3], month, +m[1], +m[4], +m[5], m[6] === undefined ? 0 : +m[6], offset);
    }
    m = ISO.exec(text);
    if (m) {
      let offset;
      const zone = m[7];
      if (zone === undefined) offset = null;
      else if (zone === "Z" || zone === "z") offset = 0;
      else {
        offset = offsetSeconds(zone);
        if (offset === null) return null;
      }
      return buildTime(+m[1], +m[2], +m[3], +m[4], +m[5], m[6] === undefined ? 0 : +m[6], offset);
    }
    return null;
  }

  function pad(n, width) {
    return String(n).padStart(width, "0");
  }

  // UTC seconds -> `YYYY-MM-DDTHH:MM:SSZ`.
  function formatUtc(seconds) {
    const days = Math.floor(seconds / 86400);
    const rest = seconds - days * 86400;
    const [y, mo, d] = civilFromDays(days);
    return pad(y, 4) + "-" + pad(mo, 2) + "-" + pad(d, 2) + "T" + pad(Math.floor(rest / 3600), 2) + ":" +
      pad(Math.floor((rest % 3600) / 60), 2) + ":" + pad(rest % 60, 2) + "Z";
  }

  // `now` (Date, epoch milliseconds, or UTC text) -> epoch milliseconds.
  function toMillis(now) {
    if (now instanceof Date) {
      if (Number.isNaN(now.getTime())) throw new TypeError("now is an invalid Date");
      return now.getTime();
    }
    if (typeof now === "number" && Number.isFinite(now)) return now;
    if (typeof now === "string") {
      const m = UTC_TEXT.exec(now);
      // Any valid UTC time of years 1 to 9999 (not limited to 1970-9998).
      if (m) {
        const [y, mo, d, h, mi, sec] = m.slice(1).map(Number);
        if (y >= 1 && mo >= 1 && mo <= 12 && d >= 1 && d <= daysInMonth(y, mo) && h < 24 && mi < 60 && sec < 60) {
          return (daysFromCivil(y, mo, d) * 86400 + h * 3600 + mi * 60 + sec) * 1000;
        }
      }
    }
    throw new TypeError("now must be a Date, epoch milliseconds or UTC text like 2026-11-13T13:05:12Z");
  }

  // Time text -> `published` (R2.1, R2.6): UTC text, or null. A time more than
  // 10 minutes after `now` is null; exactly 10 minutes ahead is kept.
  function publishedUtc(text, now) {
    const nowMs = toMillis(now);
    const seconds = parseTime(text);
    if (seconds === null) return null;
    if (seconds * 1000 > nowMs + FUTURE_LIMIT_MS) return null;
    return formatUtc(seconds);
  }

  // `published` (UTC text or null) -> `publishedDisplay` (R2.4, R2.5): Stockholm
  // time as `YYYY-MM-DD HH:MM`. Throws Error for text that is not a UTC time.
  // Times before 1970 are shown with +01:00 (CET), enough for the 1969 times
  // that a +hh:mm offset on 1970-01-01 can give.
  function displayTime(published) {
    if (published === null || published === undefined) return MISSING_DISPLAY;
    const m = typeof published === "string" ? UTC_TEXT.exec(published) : null;
    if (!m) throw new Error("not a UTC time: " + JSON.stringify(published));
    const [year, month, day, hour, minute, second] = m.slice(1).map(Number);
    if (year < 1 || month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month) ||
        hour > 23 || minute > 59 || second > 59) {
      throw new Error("not a usable UTC time: " + JSON.stringify(published));
    }
    const utc = daysFromCivil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second;
    const local = utc + (inSummer(utc) ? 2 * HOUR : HOUR);
    const [y, mo, d] = civilFromDays(Math.floor(local / 86400));
    if (y > 9999) throw new Error("not a usable UTC time: " + JSON.stringify(published));
    const rest = local - Math.floor(local / 86400) * 86400;
    return pad(y, 4) + "-" + pad(mo, 2) + "-" + pad(d, 2) + " " + pad(Math.floor(rest / 3600), 2) + ":" +
      pad(Math.floor((rest % 3600) / 60), 2);
  }

  // `generatedAt`-style helpers for `now`, whole seconds.
  function generatedAt(now) {
    return formatUtc(Math.floor(toMillis(now) / 1000));
  }

  function generatedAtDisplay(now) {
    return displayTime(generatedAt(now));
  }

  // ------------------------------------------------------------------------
  // Selection (R1.4, R5.1 to R5.4), merge and sort (R5.5)

  // Compare strings by Unicode code point (not by UTF-16 unit).
  function compareCodePoints(a, b) {
    const x = Array.from(a);
    const y = Array.from(b);
    const n = Math.min(x.length, y.length);
    for (let i = 0; i < n; i++) {
      const p = x[i].codePointAt(0);
      const q = y[i].codePointAt(0);
      if (p !== q) return p < q ? -1 : 1;
    }
    return x.length < y.length ? -1 : x.length > y.length ? 1 : 0;
  }

  function text(value) {
    return typeof value === "string" ? value : "";
  }

  // The fields of a plain entry. Accepted names: `title`, `link`, and the time
  // text as `timeText` (Python RawEntry shape) or `published`, falling back to
  // `updated` (Atom, R2.3; the fallback is used when the first is missing, empty or
  // only white space); the description as `description` or `summary`. `content` is never
  // read.
  function entryFields(entry) {
    const timeText = [entry.timeText, entry.published, entry.updated].map(text).find((t) => trimChars(t, TIME_WS_CHARS) !== "") || "";
    const description = text(entry.description) !== "" ? entry.description : text(entry.summary);
    return { title: text(entry.title), link: entry.link, timeText, description };
  }

  // Raw entries of one source -> the items to show (same steps as select_items):
  // clean, drop empty titles, keyword filter, URL check, de-duplicate by
  // normalised URL (first wins), drop times in the future (R2.6) and items
  // older than 7 days, sort newest first (equal times by title, then feed
  // order; no time last, by title), keep 20. `source` is an entry of
  // sources.json, `keywords` the result of validateKeywords, `now` as above.
  function selectItems(entries, source, keywords, now) {
    const nowMs = toMillis(now);
    const method = source["politics-sweden"].method;
    let useKeywords;
    if (method === "keywordFilter") useKeywords = true;
    else if (method === "feed") useKeywords = false;
    else throw new Error("unsupported politics method " + JSON.stringify(method) + " for source " + JSON.stringify(source.id));
    if (useKeywords && !keywords) throw new Error("source " + JSON.stringify(source.id) + " needs a keyword list");
    const cutoffMs = nowMs - MAX_AGE_MS;

    const seen = new Set();
    const items = [];
    for (const entry of entries) {
      const raw = entryFields(entry);
      const title = cleanHeadline(raw.title);
      if (title === "") continue;
      if (useKeywords && !matchesKeywords(keywords, raw.title, raw.description)) continue;
      const normalised = checkUrl(raw.link, source.allowedHosts);
      if (normalised === null || seen.has(normalised)) continue;
      seen.add(normalised);
      // Time: unusable or more than 10 minutes ahead -> no time (null). A time
      // before the cutoff is dropped; this includes a time before 1970 (a
      // `+hh:mm` offset on 1970-01-01 can give 1969), which is simply old.
      const seconds = parseTime(raw.timeText);
      let published = null;
      if (seconds !== null) {
        if (seconds * 1000 < cutoffMs) continue;
        if (seconds * 1000 <= nowMs + FUTURE_LIMIT_MS) published = formatUtc(seconds);
      }
      items.push({
        id: itemId(normalised),
        sourceId: source.id,
        sourceName: source.name,
        title,
        url: stripWs(raw.link),
        published,
        publishedDisplay: displayTime(published),
      });
    }
    return sortItems(items, false).slice(0, MAX_ITEMS);
  }

  // Newest first by `published` (fixed-width UTC text), `null` last. Ties: by
  // `sourceId` first when `bySource` is true (R5.5), then by title (code
  // points), then the input order (the sort is stable). Returns a new array.
  function sortItems(items, bySource) {
    return items.slice().sort((a, b) => {
      if (a.published !== b.published) {
        if (a.published === null) return 1;
        if (b.published === null) return -1;
        return a.published < b.published ? 1 : -1;
      }
      if (bySource) {
        const s = compareCodePoints(a.sourceId, b.sourceId);
        if (s !== 0) return s;
      }
      return compareCodePoints(a.title, b.title);
    });
  }

  // Item lists of several sources -> one list, newest first (R5.5): by
  // `published` descending, `null` last, equal times by `sourceId`, then by
  // `title`, then the order given. Nothing is dropped or de-duplicated here and
  // the input lists are not changed.
  function mergeItems(lists) {
    return sortItems([].concat(...lists), true);
  }

  // ------------------------------------------------------------------------
  // Call limits of the live fetch (R7.2)

  const LIVE_SCHEDULED_MS = 10 * 60 * 1000; // timer and "tab visible again"
  const LIVE_MIN_GAP_MS = 5 * 60 * 1000; // never two requests closer than this
  const CLOCK_RESET_MS = 60 * 60 * 1000;

  // May a request to a source that the page fetches itself be sent now?
  // `trigger`: "open" (the page was opened), "timer" or "visible" (scheduled:
  // at most one request every 10 minutes), "refresh" (the button "Uppdatera":
  // at least 5 minutes since the last request). `lastMs`: when the last request
  // to this source was started (epoch ms), or null when there was none.
  // `nowMs`: now. `hidden`: the tab is hidden: nothing is sent then. A clock
  // that has been set back by up to an hour counts as "not long enough ago"; a
  // bigger step back is taken as a reset and allows the request.
  function liveFetchAllowed(trigger, lastMs, nowMs, hidden) {
    if (hidden) return false;
    if (lastMs === null) return true;
    const elapsed = nowMs - lastMs;
    if (elapsed < -CLOCK_RESET_MS) return true;
    if (trigger === "timer" || trigger === "visible") return elapsed >= LIVE_SCHEDULED_MS;
    return elapsed >= LIVE_MIN_GAP_MS;
  }

  const api = {
    version() { return 1; },
    MAX_ITEMS,
    MISSING_DISPLAY,
    KeywordsError,
    cleanHeadline,
    splitWords,
    validateKeywords,
    matchesKeywords,
    parseUrl,
    checkUrl,
    sha256Hex,
    itemId,
    parseTime,
    publishedUtc,
    displayTime,
    formatUtc,
    generatedAt,
    generatedAtDisplay,
    selectItems,
    sortItems,
    mergeItems,
    liveFetchAllowed,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.NewsLogic = api;
  }
})(typeof self !== "undefined" ? self : globalThis);
