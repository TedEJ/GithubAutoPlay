// The news reader page: SVT headlines from news.json, the reader's choice of
// sources, an offline copy, notices (step S10), and the live fetch of the sources
// that the page reads itself, today Sveriges Radio (step S11).
//
// This is a thin layer. The rules (URL check, time display, sorting, the call
// limits of the live fetch) live in logic.js; the request and the Atom parsing
// live in atom.js. All text is built with createElement and textContent, never by
// parsing markup. The pure parts (validation of what is read from the network and
// from localStorage, the choice of notices, the rows of "Källor") are exported
// so that `node --test` can test them without a browser.
//
// Live items (Sveriges Radio) are kept in `state.live`, a variable, and nowhere
// else (R7.3): they are never given to the code that writes to storage, they are
// never logged and no error message holds any of their text. The saved copy
// (KEY_LAST_NEWS) is made from the validated news.json only.
(function (root) {
  "use strict";

  const logic = typeof module !== "undefined" && module.exports
    ? require("./logic.js")
    : root.NewsLogic;
  const atom = typeof module !== "undefined" && module.exports
    ? require("./atom.js")
    : root.NewsAtom;

  const KEY_SELECTED = "newsReader.selectedSources";
  const KEY_LAST_NEWS = "newsReader.lastNews";

  const REFRESH_MS = 10 * 60 * 1000; // R8.1
  const STALE_MS = 3 * 60 * 60 * 1000; // R8.3
  const FETCH_TIMEOUT_MS = 15 * 1000;

  // Limits for everything that is read from a file or from storage.
  const MAX_TEXT_CHARS = 2000000;
  const MAX_SOURCES = 50;
  const MAX_ITEMS = 500;
  const MAX_TITLE = 2000;
  const MAX_URL = 2000;
  const MAX_NAME = 100;
  const MAX_MESSAGE = 200;

  const STATUSES = ["ok", "error", "blocked-by-robots"];

  // The texts of the page (Swedish).
  const TEXT = {
    fetchFailed: "Kunde inte hämta nyheter. Försök igen senare.",
    empty: "Inga nyheter från valda källor.",
    loading: "Laddar nyheter …",
    keywordNote: "Urval med nyckelord – ungefärligt",
    noTime: "Tid saknas",
  };

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isText(value, max) {
    return typeof value === "string" && value.length > 0 && value.length <= max;
  }

  // ------------------------------------------------------------------------
  // sources.json

  // The parsed sources.json -> the enabled sources with only the fields the
  // page uses, or null when nothing usable is in it.
  function validateSources(data) {
    if (!isObject(data) || data.version !== 1 || !Array.isArray(data.sources)) return null;
    const result = [];
    const seen = new Set();
    for (const raw of data.sources.slice(0, MAX_SOURCES)) {
      if (!isObject(raw) || raw.enabled !== true) continue;
      if (!isText(raw.id, MAX_NAME) || !isText(raw.name, MAX_NAME) || seen.has(raw.id)) continue;
      if (raw.fetchedBy !== "build" && raw.fetchedBy !== "browser") continue;
      const hosts = raw.allowedHosts;
      if (!Array.isArray(hosts) || hosts.length === 0 || !hosts.every((h) => isText(h, 253))) continue;
      const category = raw["politics-sweden"];
      const method = isObject(category) && typeof category.method === "string" ? category.method : "";
      seen.add(raw.id);
      const source = {
        id: raw.id,
        name: raw.name,
        fetchedBy: raw.fetchedBy,
        allowedHosts: hosts.slice(),
        method,
      };
      // The address of a feed that the page fetches itself (R7.1): from
      // sources.json, never written in this script. Only https is accepted.
      if (raw.fetchedBy === "browser") {
        const url = isObject(category) ? category.url : "";
        source.url = isText(url, MAX_URL) && /^https:\/\/[^\s]+$/.test(url) ? url : "";
      }
      result.push(source);
    }
    return result.length > 0 ? result : null;
  }

  // "SVT", "SVT och Sveriges Radio", "A, B och C".
  function joinNames(names) {
    if (names.length <= 1) return names.join("");
    return names.slice(0, -1).join(", ") + " och " + names[names.length - 1];
  }

  function bottomLine(sources) {
    return "Rubriker och länkar från " + joinNames(sources.map((s) => s.name)) +
      ". Klicka för att läsa hos källan.";
  }

  // ------------------------------------------------------------------------
  // news.json (and the saved copy of it)

  // The parsed news.json -> a clean copy in the same shape, or null when the
  // file cannot be used. Only the named fields are read (N1). Items of other
  // than enabled build sources are dropped (Sveriges Radio items are never
  // shown from a file, N10), as are items without a headline or with a link
  // that logic.checkUrl does not accept (R9.1). The source name comes from
  // sources.json, the time text is recomputed by logic.js, and the id is
  // recomputed from the link. Idempotent: a clean copy validates to itself.
  function validateNews(data, sources, nowMs) {
    if (!isObject(data) || data.version !== 1) return null;
    if (typeof data.generatedAt !== "string") return null;
    const generatedSeconds = logic.parseTime(data.generatedAt);
    if (generatedSeconds === null) return null;
    if (!Array.isArray(data.items)) return null;
    const generatedAt = logic.formatUtc(generatedSeconds);

    const bySource = new Map();
    for (const s of sources) if (s.fetchedBy === "build") bySource.set(s.id, s);

    const items = [];
    const seen = new Set();
    for (const raw of data.items.slice(0, MAX_ITEMS)) {
      if (!isObject(raw)) continue;
      const source = typeof raw.sourceId === "string" ? bySource.get(raw.sourceId) : undefined;
      if (!source) continue;
      if (!isText(raw.title, MAX_TITLE) || raw.title.trim() === "") continue;
      if (!isText(raw.url, MAX_URL)) continue;
      const normalised = logic.checkUrl(raw.url, source.allowedHosts);
      if (normalised === null) continue;
      const id = logic.itemId(normalised);
      if (seen.has(id)) continue;
      seen.add(id);
      const published = logic.publishedUtc(raw.published, nowMs);
      items.push({
        id,
        sourceId: source.id,
        sourceName: source.name,
        title: raw.title,
        url: raw.url.trim(),
        published,
        publishedDisplay: logic.displayTime(published),
      });
    }

    const statuses = [];
    if (Array.isArray(data.sources)) {
      for (const raw of data.sources.slice(0, MAX_SOURCES)) {
        if (!isObject(raw) || typeof raw.id !== "string" || !bySource.has(raw.id)) continue;
        if (!STATUSES.includes(raw.status)) continue;
        const count = Number.isInteger(raw.itemCount) && raw.itemCount >= 0 && raw.itemCount <= MAX_ITEMS
          ? raw.itemCount : 0;
        let lastSuccess = null;
        if (typeof raw.lastSuccess === "string") {
          const seconds = logic.parseTime(raw.lastSuccess);
          if (seconds !== null) lastSuccess = logic.formatUtc(seconds);
        }
        const entry = {
          id: raw.id,
          name: bySource.get(raw.id).name,
          status: raw.status,
          lastSuccess,
          itemCount: count,
        };
        if (raw.status !== "ok" && isText(raw.message, MAX_MESSAGE)) entry.message = raw.message;
        statuses.push(entry);
      }
    }

    return {
      version: 1,
      generatedAt,
      generatedAtDisplay: logic.displayTime(generatedAt),
      category: "politics-sweden",
      sources: statuses,
      items,
    };
  }

  // Text from storage -> a clean news object, or null.
  function parseSavedNews(text, sources, nowMs) {
    if (typeof text !== "string" || text.length === 0 || text.length > MAX_TEXT_CHARS) return null;
    let data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      return null;
    }
    return validateNews(data, sources, nowMs);
  }

  // ------------------------------------------------------------------------
  // The reader's choice of sources (R3.3, R3.5)

  // Saved text -> the chosen source ids. No saved choice, or one that cannot
  // be read: all enabled sources (R3.3). Saved ids that are not (or no longer)
  // approved and enabled are ignored; a source that is not in the saved list
  // is not chosen (R3.5). An empty saved list is a valid choice.
  function parseSelected(text, sources) {
    const all = sources.map((s) => s.id);
    if (typeof text !== "string" || text.length === 0 || text.length > 10000) return all;
    let data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      return all;
    }
    if (!Array.isArray(data) || data.length > MAX_SOURCES * 2 || !data.every((v) => typeof v === "string")) {
      return all;
    }
    return all.filter((id) => data.includes(id));
  }

  // ------------------------------------------------------------------------
  // What the page shows

  // The list: the chosen sources' items, merged and sorted by logic.js (R5.5).
  // `liveItems` (optional): a Map from the id of a source that the page fetches
  // itself to its items in memory.
  function visibleItems(news, selected, liveItems) {
    const lists = selected.map((id) => {
      const fromFile = news ? news.items.filter((item) => item.sourceId === id) : [];
      const live = liveItems && liveItems.get(id);
      return live ? fromFile.concat(live) : fromFile;
    });
    return logic.mergeItems(lists);
  }

  // The notices above the list (R8.2, R8.3). `fromSaved` is true when the
  // list comes from the saved copy because loading failed.
  function decideNotices(news, fromSaved, nowMs) {
    if (!news) return [{ kind: "error", text: TEXT.fetchFailed }];
    const notices = [];
    if (fromSaved) {
      notices.push({
        kind: "offline",
        text: "Offline – visar sparade SVT-nyheter från " + news.generatedAtDisplay,
      });
    }
    const generated = logic.parseTime(news.generatedAt);
    if (generated !== null && nowMs - generated * 1000 > STALE_MS) {
      notices.push({
        kind: "stale",
        text: "SVT-nyheterna kan vara gamla – senast uppdaterade " + news.generatedAtDisplay,
      });
    }
    return notices;
  }

  function countText(n) {
    return n === 1 ? "1 rubrik" : n + " rubriker";
  }

  // "14:07" in Europe/Stockholm, from epoch milliseconds.
  function clockTime(ms) {
    return logic.displayTime(logic.formatUtc(Math.floor(ms / 1000))).slice(11);
  }

  // The status text of a source that the page fetches itself (R7.6). `live` is
  // its state ({status: "idle" | "loading" | "ok" | "error", fetchedAt, items})
  // or undefined. The text of a failure holds the source name only.
  function browserStatus(source, live) {
    if (!live || live.status === "idle") return "Inte hämtad ännu";
    if (live.status === "error") return source.name + " kunde inte hämtas just nu";
    if (live.status === "loading") return "Hämtar …";
    return "Hämtad " + clockTime(live.fetchedAt) + ", " + countText(live.items.length);
  }

  function buildStatus(source, news) {
    if (!news) return "Status okänd";
    const entry = news.sources.find((s) => s.id === source.id);
    if (!entry) return "Status okänd";
    if (entry.status === "ok") return "Hämtad, " + countText(entry.itemCount);
    if (entry.status === "blocked-by-robots") return "Blockerad enligt källans robots.txt";
    if (entry.lastSuccess === null) return "Kunde inte hämtas";
    return "Kunde inte hämtas sedan " + logic.displayTime(entry.lastSuccess);
  }

  // The rows of "Källor" (R4.6): name, note and status of each enabled source.
  function sourceRows(sources, news, selected, live) {
    return sources.map((source) => ({
      id: source.id,
      name: source.name,
      checked: selected.includes(source.id),
      note: source.method === "keywordFilter" ? TEXT.keywordNote : "",
      status: source.fetchedBy === "browser"
        ? browserStatus(source, live && live.get(source.id))
        : buildStatus(source, news),
    }));
  }

  // ------------------------------------------------------------------------
  // Storage (every access can throw, R3.3)

  function getStorage(win) {
    try {
      return win && win.localStorage ? win.localStorage : null;
    } catch (e) {
      return null;
    }
  }

  function readKey(storage, key) {
    try {
      return storage ? storage.getItem(key) : null;
    } catch (e) {
      return null;
    }
  }

  function writeKey(storage, key, value) {
    try {
      if (storage) storage.setItem(key, value);
    } catch (e) {
      // Blocked or full: the page works without it.
    }
  }

  // ------------------------------------------------------------------------
  // The page (DOM, timers, fetch)

  // env: document, window (for localStorage), fetch, now (ms), setInterval,
  // setTimeout, clearTimeout, AbortController, DOMParser (for the live fetch).
  function createApp(env) {
    const doc = env.document;
    const storage = getStorage(env.window);
    const el = {};
    for (const id of ["updated", "refresh", "notices", "headlines", "empty", "sources", "sources-section",
      "bottom-line"]) {
      el[id] = doc.getElementById(id);
    }

    const state = {
      sources: null,
      news: null,
      fromSaved: false,
      selected: [],
      loading: false,
      lastLoad: 0,
      // Sveriges Radio and any other source the page fetches itself. Memory
      // only (R7.3): source id -> {last, inFlight, status, fetchedAt, items}.
      live: new Map(),
      keywords: null,
    };
    const pendingLive = new Set();
    const sourceEls = new Map();
    let sourcesBuilt = "";
    // What is on the screen now. A part is only rewritten when its key changes,
    // so that the keyboard focus stays where it is and a screen reader does not
    // read the same notice again after every reload.
    let noticesKey = null;
    let listKey = null;
    const linkById = new Map();

    function makeText(tag, className, text) {
      const node = doc.createElement(tag);
      if (className) node.className = className;
      node.textContent = text;
      return node;
    }

    function renderNotices() {
      const notices = decideNotices(state.news, state.fromSaved, env.now());
      const key = JSON.stringify(notices);
      if (key === noticesKey) return;
      noticesKey = key;
      el.notices.replaceChildren();
      for (const notice of notices) {
        el.notices.appendChild(makeText("p", "notice notice-" + notice.kind, notice.text));
      }
    }

    function liveItems() {
      const map = new Map();
      for (const [id, live] of state.live) map.set(id, live.items);
      return map;
    }

    function renderList() {
      const items = visibleItems(state.news, state.selected, liveItems());
      // R8.4: only when news were loaded, nothing is left to show and no chosen
      // source is still being fetched.
      const waiting = state.selected.some((id) => {
        const live = state.live.get(id);
        return live !== undefined && live.status === "loading";
      });
      const showEmpty = state.news !== null && items.length === 0 && !waiting;
      const key = JSON.stringify([state.news !== null, showEmpty, items]);
      if (key === listKey) return;
      listKey = key;
      // Keep the focus on a headline link that is still in the list.
      let focusedId = null;
      for (const [id, link] of linkById) {
        if (doc.activeElement === link) focusedId = id;
      }
      linkById.clear();
      el.headlines.replaceChildren();
      for (const item of items) {
        const li = doc.createElement("li");
        li.className = "item";
        const link = makeText("a", "headline", item.title);
        link.setAttribute("href", item.url);
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
        linkById.set(item.id, link);
        li.appendChild(link);
        const meta = doc.createElement("p");
        meta.className = "meta";
        meta.appendChild(makeText("span", "source", item.sourceName));
        meta.appendChild(makeText("span", "sep", " · "));
        if (item.published !== null) {
          const time = makeText("time", "time", item.publishedDisplay);
          time.setAttribute("datetime", item.published);
          meta.appendChild(time);
        } else {
          meta.appendChild(makeText("span", "time", TEXT.noTime));
        }
        li.appendChild(meta);
        el.headlines.appendChild(li);
      }
      el.empty.textContent = TEXT.empty;
      el.empty.hidden = !showEmpty;
      if (focusedId !== null && linkById.has(focusedId)) linkById.get(focusedId).focus();
    }

    function renderHeader() {
      const news = state.news;
      const parts = [];
      if (news && state.sources) {
        const names = state.sources.filter((s) => s.fetchedBy === "build").map((s) => s.name);
        parts.push(joinNames(names) + " uppdaterad " + news.generatedAtDisplay);
      }
      if (state.sources) {
        for (const source of state.sources) {
          const live = state.live.get(source.id);
          if (source.fetchedBy === "browser" && live && live.status === "ok") {
            parts.push(source.name + " hämtad " + clockTime(live.fetchedAt));
          }
        }
      }
      el.updated.textContent = parts.join(" · ");
    }

    // Built once per list of sources, so that a checkbox keeps its focus when
    // the data is reloaded; later calls only update the texts.
    function renderSources() {
      el["sources-section"].hidden = !state.sources;
      if (!state.sources) return;
      const rows = sourceRows(state.sources, state.news, state.selected, state.live);
      const signature = rows.map((r) => r.id).join("|");
      if (signature !== sourcesBuilt) {
        sourcesBuilt = signature;
        sourceEls.clear();
        el.sources.replaceChildren();
        rows.forEach((row, index) => {
          const li = doc.createElement("li");
          li.className = "source-row";
          // Element ids use the position, not the source id, so that they are
          // always valid and cannot collide.
          const boxId = "src-cb-" + index;
          const infoId = "src-info-" + index;
          const input = doc.createElement("input");
          input.setAttribute("type", "checkbox");
          input.setAttribute("id", boxId);
          input.setAttribute("aria-describedby", infoId);
          input.addEventListener("change", onChoice);
          const label = makeText("label", "source-name", row.name);
          label.setAttribute("for", boxId);
          const info = doc.createElement("span");
          info.setAttribute("id", infoId);
          info.className = "source-info";
          const note = makeText("span", "source-note", "");
          const status = makeText("span", "source-status", "");
          info.appendChild(note);
          info.appendChild(status);
          li.appendChild(input);
          li.appendChild(label);
          li.appendChild(info);
          el.sources.appendChild(li);
          sourceEls.set(row.id, { input, note, status });
        });
      }
      for (const row of rows) {
        const parts = sourceEls.get(row.id);
        parts.input.checked = row.checked;
        parts.note.textContent = row.note;
        parts.note.hidden = row.note === "";
        parts.status.textContent = row.status;
      }
    }

    function renderBottom() {
      el["bottom-line"].textContent = state.sources ? bottomLine(state.sources) : "";
    }

    function renderAll() {
      renderNotices();
      renderHeader();
      renderList();
      renderSources();
      renderBottom();
    }

    function onChoice() {
      // The ids of the ticked boxes, in the order of sources.json. Ids that are
      // no longer approved are not in it, so they are dropped here (R3.5).
      state.selected = state.sources
        .filter((s) => sourceEls.get(s.id).input.checked)
        .map((s) => s.id);
      writeKey(storage, KEY_SELECTED, JSON.stringify(state.selected));
      renderList();
      renderSources();
    }

    async function fetchJson(url) {
      const controller = typeof env.AbortController === "function" ? new env.AbortController() : null;
      const timer = controller ? env.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS) : null;
      try {
        const options = { cache: "no-store", credentials: "same-origin" };
        if (controller) options.signal = controller.signal;
        const response = await env.fetch(url, options);
        if (!response.ok) throw new Error("status " + response.status);
        const text = await response.text();
        if (text.length > MAX_TEXT_CHARS) throw new Error("too large");
        return JSON.parse(text);
      } finally {
        if (timer !== null) env.clearTimeout(timer);
      }
    }

    // ---- the live fetch (R7.1 to R7.6) ----

    function liveOf(id) {
      let live = state.live.get(id);
      if (!live) {
        live = { last: null, inFlight: false, status: "idle", fetchedAt: null, items: [] };
        state.live.set(id, live);
      }
      return live;
    }

    // One request to one source, then its items in memory. Every failure ends
    // in the same status; nothing about the failure is kept or logged, and no
    // text from the feed leaves this function except as the items.
    async function fetchLive(source, live) {
      let controller = null;
      let timer = null;
      try {
        if (!state.keywords) {
          state.keywords = logic.validateKeywords(await fetchJson("politics-keywords.json"));
        }
        if (typeof env.AbortController === "function") {
          controller = new env.AbortController();
          timer = env.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
        }
        const entries = await atom.fetchAtom(env.fetch, source.url, {
          signal: controller ? controller.signal : undefined,
          DOMParser: env.DOMParser,
        });
        const items = logic.selectItems(entries, {
          id: source.id,
          name: source.name,
          allowedHosts: source.allowedHosts,
          "politics-sweden": { method: source.method },
        }, state.keywords, env.now());
        live.items = items;
        live.fetchedAt = env.now();
        live.status = "ok";
      } catch (e) {
        // Nothing from the error is used: not its message, not its type.
        live.items = [];
        live.status = "error";
      } finally {
        if (timer !== null) env.clearTimeout(timer);
        live.inFlight = false;
        // While an SVT load runs, it draws everything when it ends. Drawing
        // before that would show "Kunde inte hämta nyheter" for a moment.
        if (!state.loading) renderAll();
      }
    }

    // Starts the requests that the call limits allow for this trigger ("open",
    // "timer", "visible" or "refresh", see logic.liveFetchAllowed). The time of
    // a request is recorded before anything is awaited, so two triggers at the
    // same moment, or a request that is still running, cannot make two requests.
    // The returned promise ends when the requests started now have ended; the
    // page does not wait for it (an SVT load never waits for Sveriges Radio).
    function startLive(trigger) {
      if (!state.sources) return Promise.resolve();
      const jobs = [];
      for (const source of state.sources) {
        if (source.fetchedBy !== "browser") continue;
        const live = liveOf(source.id);
        if (live.inFlight) continue;
        const now = env.now();
        if (!logic.liveFetchAllowed(trigger, live.last, now, doc.hidden === true)) continue;
        live.last = now;
        live.inFlight = true;
        if (live.status !== "ok") live.status = "loading";
        const job = fetchLive(source, live);
        pendingLive.add(job);
        job.then(() => pendingLive.delete(job));
        jobs.push(job);
      }
      return Promise.all(jobs).then(() => undefined);
    }

    async function load(trigger) {
      if (state.loading) return;
      state.loading = true;
      // aria-busy, not the disabled attribute: a disabled button loses the focus.
      el.refresh.setAttribute("aria-busy", "true");
      state.lastLoad = env.now();
      try {
        if (!state.sources) {
          const sources = validateSources(await fetchJson("sources.json"));
          if (!sources) throw new Error("no usable sources");
          state.sources = sources;
          state.selected = parseSelected(readKey(storage, KEY_SELECTED), sources);
        }
        startLive(trigger || "refresh");
        const fresh = validateNews(await fetchJson("news.json"), state.sources, env.now());
        if (!fresh) throw new Error("news.json not usable");
        state.news = fresh;
        state.fromSaved = false;
        writeKey(storage, KEY_LAST_NEWS, JSON.stringify(fresh));
      } catch (e) {
        // A failed load changes nothing that is shown (R8.1); without anything
        // to show, the saved copy is used (R8.2).
        if (state.sources && !state.news) {
          state.news = parseSavedNews(readKey(storage, KEY_LAST_NEWS), state.sources, env.now());
        }
        state.fromSaved = state.news !== null;
      } finally {
        state.loading = false;
        el.refresh.setAttribute("aria-busy", "false");
      }
      renderAll();
    }

    function start() {
      const html = doc.documentElement;
      html.className = html.className ? html.className + " js" : "js";
      el["sources-section"].hidden = true;
      el.empty.hidden = true;
      noticesKey = "loading";
      el.notices.replaceChildren();
      el.notices.appendChild(makeText("p", "notice", TEXT.loading));
      el.refresh.addEventListener("click", () => {
        load("refresh");
        startLive("refresh");
      });
      env.setInterval(() => {
        if (doc.hidden) return;
        load("timer");
        startLive("timer");
      }, REFRESH_MS);
      doc.addEventListener("visibilitychange", () => {
        if (doc.hidden) return;
        if (env.now() - state.lastLoad >= REFRESH_MS) load("visible");
        startLive("visible");
      });
      // The first load starts the first live request once sources.json is read
      // (if the tab is hidden it waits until the tab is visible). The promise
      // ends when the requests started by then have ended.
      return load("open").then(() => Promise.all(Array.from(pendingLive)).then(() => undefined));
    }

    return { start, load, state };
  }

  const api = {
    KEY_SELECTED,
    KEY_LAST_NEWS,
    REFRESH_MS,
    STALE_MS,
    TEXT,
    validateSources,
    validateNews,
    parseSavedNews,
    parseSelected,
    visibleItems,
    decideNotices,
    sourceRows,
    browserStatus,
    bottomLine,
    joinNames,
    createApp,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.NewsApp = api;
    if (typeof document !== "undefined" && document.getElementById("headlines")) {
      createApp({
        document,
        window: root,
        fetch: root.fetch.bind(root),
        now: () => Date.now(),
        setInterval: root.setInterval.bind(root),
        setTimeout: root.setTimeout.bind(root),
        clearTimeout: root.clearTimeout.bind(root),
        AbortController: root.AbortController,
        DOMParser: root.DOMParser,
      }).start();
    }
  }
})(typeof self !== "undefined" ? self : globalThis);
