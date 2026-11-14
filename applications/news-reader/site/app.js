// The news reader page: headlines from news.json (the build sources), the reader's
// choice of topic (Ämnen, step F7) and of sources, an offline copy, notices (step
// S10), and the live fetch of the sources that the page reads itself, today
// Sveriges Radio (step S11) with all the topics of one response (step F8).
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
  const KEY_TOPIC = "newsReader.selectedTopic"; // R18.3: one topic id, nothing else

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
    topicsHeading: "Ämnen",
  };

  // The line that must follow the credit text of Riksdagen (R16.5, D38). One
  // constant, so that the owner can change it in one line (the Riksdag's terms do not
  // let the service use the name Sveriges riksdag apart from the credit; the
  // alternative is "Sidan har inget samband med riksdagen.").
  const DISCLAIMER_RIKSDAGEN = "Sidan har inget samband med Sveriges riksdag.";
  const DISCLAIMERS = { riksdagen: DISCLAIMER_RIKSDAGEN };

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
    if (!isObject(data) || data.version !== 2 || !Array.isArray(data.sources)) return null;
    const result = [];
    const seen = new Set();
    for (const raw of data.sources.slice(0, MAX_SOURCES)) {
      if (!isObject(raw) || raw.enabled !== true) continue;
      if (!isText(raw.id, MAX_NAME) || !isText(raw.name, MAX_NAME) || seen.has(raw.id)) continue;
      if (raw.fetchedBy !== "build" && raw.fetchedBy !== "browser") continue;
      const hosts = raw.allowedHosts;
      if (!Array.isArray(hosts) || hosts.length === 0 || !hosts.every((h) => isText(h, 253))) continue;
      // Version 2 (R14.7): the feed entries of the source; `linkHosts` is accepted and
      // ignored here.
      const feedList = Array.isArray(raw.feeds) ? raw.feeds.filter((f) => isObject(f) && typeof f.method === "string") : [];
      seen.add(raw.id);
      const source = {
        id: raw.id,
        name: raw.name,
        fetchedBy: raw.fetchedBy,
        allowedHosts: hosts.slice(),
        // The topics the source offers, each with its method (R18.5, R13.7) and, for
        // a title-only keyword match, `matchOn` (R14.2). The address stays in the file.
        feeds: TOPICS.filter((t) => feedList.some((f) => f.topic === t)).map((t) => {
          const feed = feedList.find((f) => f.topic === t);
          const entry = { topic: t, method: feed.method };
          if (feed.matchOn === "title") entry.matchOn = "title";
          return entry;
        }),
      };
      // The credit text that the page must show with the items (R16.5).
      if (isText(raw.credit, MAX_NAME)) source.credit = raw.credit;
      // The address of a feed that the page fetches itself (R7.1): from
      // sources.json, never written in this script. Only https is accepted. The page
      // makes one request per fetch round (R15.3), so all the feed entries of the
      // source must use one and the same address; with none or several the address is
      // empty and the source shows the failure status (D42).
      if (raw.fetchedBy === "browser") {
        const urls = new Set(feedList.map((f) => f.url));
        const url = urls.size === 1 ? Array.from(urls)[0] : "";
        source.url = isText(url, MAX_URL) && /^https:\/\/[^\s]+$/.test(url) ? url : "";
      }
      result.push(source);
    }
    return result.length > 0 ? result : null;
  }

  // The parsed sources.json -> the topics in the order of R13.1 as [{id, label}],
  // from the `topics` list of the file (only known ids with a text label).
  function readTopicList(data) {
    if (!isObject(data) || !Array.isArray(data.topics)) return [];
    const result = [];
    for (const id of TOPICS) {
      const raw = data.topics.slice(0, TOPICS.length * 4).find((t) => isObject(t) && t.id === id);
      if (raw && isText(raw.label, MAX_NAME)) {
        const entry = { id, label: raw.label };
        // The keyword file of the topic (R14.1): only a name of the form
        // <id>-keywords.json is accepted, so it cannot hold a path.
        if (typeof raw.keywords === "string" && raw.keywords === id + "-keywords.json") entry.keywords = raw.keywords;
        result.push(entry);
      }
    }
    return result;
  }

  // "SVT", "SVT och Sveriges Radio", "A, B och C".
  function joinNames(names) {
    if (names.length <= 1) return names.join("");
    return names.slice(0, -1).join(", ") + " och " + names[names.length - 1];
  }

  // R8.7, R18.7: every enabled source, then the credit text of each source that has
  // an item in the list (R16.5), with the line that must follow it. `items` is the
  // list on the screen; without it no credit is shown.
  function bottomLine(sources, items) {
    let text = "Rubriker och länkar från " + joinNames(sources.map((s) => s.name)) +
      ". Klicka för att läsa hos källan.";
    for (const source of sources) {
      if (!source.credit || !(items || []).some((i) => i.sourceId === source.id)) continue;
      text += " " + source.credit + ".";
      if (DISCLAIMERS[source.id]) text += " " + DISCLAIMERS[source.id];
    }
    return text;
  }

  // ------------------------------------------------------------------------
  // news.json (and the saved copy of it)

  // The topics of news.json and the topics that a version 1 file stands for (R18.4:
  // its items were politics headlines). Order and ids are those of R13.1.
  const TOPICS = logic.TOPIC_ORDER;
  const V1_TOPICS = ["all-news", "politics"];

  // A list of topic ids -> the known ones in the order of R13.1 without duplicates, or
  // null when the value is not a list or no known id is left (R1.5, R19.2).
  function readTopics(value) {
    if (!Array.isArray(value) || value.length > TOPICS.length * 4) return null;
    const known = TOPICS.filter((t) => value.includes(t));
    return known.length > 0 ? known : null;
  }

  // The parsed news.json (version 1 or 2, R19.8) -> a clean copy in the shape of
  // version 2, or null when the file cannot be used. Only the named fields are read
  // (N1). Items of other than enabled build sources are dropped (Sveriges Radio items
  // are never shown from a file, N10), as are items without a headline or with a link
  // that logic.checkUrl does not accept (R9.1). The source name comes from
  // sources.json, the time text is recomputed by logic.js, and the id is recomputed
  // from the link. Every item has `topics`: a version 1 item gets ["all-news",
  // "politics"] (R18.4); a version 2 item with a missing or unusable list is dropped
  // (R1.5). The status of each feed is kept when present (R19.3); a version 1 file has
  // none. Idempotent: a clean copy validates to itself.
  function validateNews(data, sources, nowMs) {
    if (!isObject(data) || (data.version !== 1 && data.version !== 2)) return null;
    const version2 = data.version === 2;
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
      const topics = version2 ? readTopics(raw.topics) : V1_TOPICS.slice();
      if (topics === null) continue;
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
        topics,
      });
    }

    const statuses = [];
    if (Array.isArray(data.sources)) {
      for (const raw of data.sources.slice(0, MAX_SOURCES)) {
        if (!isObject(raw) || typeof raw.id !== "string" || !bySource.has(raw.id)) continue;
        if (!STATUSES.includes(raw.status)) continue;
        const entry = {
          id: raw.id,
          name: bySource.get(raw.id).name,
          status: raw.status,
          lastSuccess: readLastSuccess(raw.lastSuccess),
          itemCount: readCount(raw.itemCount),
        };
        if (raw.status !== "ok" && isText(raw.message, MAX_MESSAGE)) entry.message = raw.message;
        if (version2 && Array.isArray(raw.feeds)) {
          entry.feeds = [];
          for (const feed of raw.feeds.slice(0, TOPICS.length)) {
            if (!isObject(feed) || !TOPICS.includes(feed.topic) || !STATUSES.includes(feed.status)) continue;
            const clean = {
              topic: feed.topic,
              status: feed.status,
              lastSuccess: readLastSuccess(feed.lastSuccess),
              itemCount: readCount(feed.itemCount),
            };
            if (feed.status !== "ok" && isText(feed.message, MAX_MESSAGE)) clean.message = feed.message;
            entry.feeds.push(clean);
          }
        }
        statuses.push(entry);
      }
    }

    // The topics that exist (R19.1): from a version 2 file the known ids in order; a
    // version 1 file stands for Alla nyheter and Politik.
    const topics = version2 ? readTopics(data.topics) : V1_TOPICS.slice();
    return {
      version: 2,
      generatedAt,
      generatedAtDisplay: logic.displayTime(generatedAt),
      topics: topics === null ? [] : topics,
      sources: statuses,
      items,
    };
  }

  function readCount(value) {
    return Number.isInteger(value) && value >= 0 && value <= MAX_ITEMS ? value : 0;
  }

  function readLastSuccess(value) {
    if (typeof value !== "string") return null;
    const seconds = logic.parseTime(value);
    return seconds === null ? null : logic.formatUtc(seconds);
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

  // The list: the chosen sources' items that belong to the chosen topic (R18.2),
  // merged and sorted by logic.js (R5.5). `liveItems` (optional): a Map from the id of
  // a source that the page fetches itself to its items in memory, each with its
  // `topics` (F8): they are filtered by the topic like the others.
  function visibleItems(news, selected, liveItems, topic) {
    const chosen = topic === undefined ? logic.DEFAULT_TOPIC : topic;
    const lists = selected.map((id) => {
      const fromFile = news
        ? logic.filterByTopic(news.items.filter((item) => item.sourceId === id), chosen)
        : [];
      const live = liveItems ? liveItems.get(id) : undefined;
      return live ? fromFile.concat(logic.filterByTopic(live, chosen)) : fromFile;
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
        text: "Offline – visar sparade nyheter från " + news.generatedAtDisplay,
      });
    }
    const generated = logic.parseTime(news.generatedAt);
    if (generated !== null && nowMs - generated * 1000 > STALE_MS) {
      notices.push({
        kind: "stale",
        text: "Nyheterna kan vara gamla – senast uppdaterade " + news.generatedAtDisplay,
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
  // or undefined; `chosen` is false when the reader has unticked the source (then
  // nothing is requested). The text of a failure holds the source name only.
  // One request serves all topics (R15.3), so there is one status, not one per topic;
  // the count is that of the chosen topic `topic` (all items without it).
  function browserStatus(source, live, chosen, topic) {
    if (chosen === false) return "Inte vald – ingen hämtning";
    if (!live || live.status === "idle") return "Inte hämtad ännu";
    if (live.status === "error") return source.name + " kunde inte hämtas just nu";
    if (live.status === "loading") return "Hämtar …";
    const shown = topic === undefined ? live.items : logic.filterByTopic(live.items, topic);
    return "Hämtad " + clockTime(live.fetchedAt) + " (en hämtning för alla ämnen), " + countText(shown.length);
  }

  // The status of a build source for the chosen topic (R18.5): the status of the
  // feed of that topic in news.json, or the source-level fields when the file has no
  // feeds (a version 1 file). The count is the number of items of the source that
  // are shown for the topic (F7), so it equals what the reader sees.
  function buildStatus(source, news, topic) {
    if (!news) return "Status okänd";
    const entry = news.sources.find((s) => s.id === source.id);
    if (!entry) return "Status okänd";
    const chosen = topic === undefined ? logic.DEFAULT_TOPIC : topic;
    const feed = Array.isArray(entry.feeds) ? entry.feeds.find((f) => f.topic === chosen) : undefined;
    const shown = feed || entry;
    if (shown.status === "ok") {
      const count = logic.filterByTopic(news.items.filter((i) => i.sourceId === source.id), chosen).length;
      return "Hämtad, " + countText(count);
    }
    if (shown.status === "blocked-by-robots") return "Blockerad enligt källans robots.txt";
    if (shown.lastSuccess === null) return "Kunde inte hämtas";
    return "Kunde inte hämtas sedan " + logic.displayTime(shown.lastSuccess);
  }

  // The rows of "Källor" (R4.6, R18.5): name, the topics the source offers, the note
  // for a keyword selection, the credit and the status for the chosen topic.
  // `topics`: [{id, label}] of the page (for the labels); `topic`: the chosen id.
  function sourceRows(sources, news, selected, live, topic, topics) {
    const chosen = topic === undefined ? logic.DEFAULT_TOPIC : topic;
    const labels = new Map((topics || []).map((t) => [t.id, t.label]));
    const labelOf = (id) => labels.get(id) || id;
    return sources.map((source) => {
      const feed = source.feeds.find((f) => f.topic === chosen);
      const isChosen = selected.includes(source.id);
      let status;
      if (!feed) {
        status = "Erbjuder inte ämnet " + labelOf(chosen);
      } else if (source.fetchedBy === "browser") {
        const state = live && live.get(source.id);
        status = browserStatus(source, state, isChosen, chosen);
        // A keyword list that could not be read (D42): the items count under Alla
        // nyheter only for those topics, and the row says so. Labels only, no content.
        if (isChosen && state && state.status === "ok" && state.missing && state.missing.length > 0) {
          status += ". Nyckelord saknas för " + joinNames(state.missing.map(labelOf)) +
            ": de rubrikerna visas bara under Alla nyheter";
        }
      } else {
        status = buildStatus(source, news, chosen);
      }
      return {
        id: source.id,
        name: source.name,
        checked: isChosen,
        topics: labels.size > 0 ? "Ämnen: " + source.feeds.map((f) => labelOf(f.topic)).join(", ") : "",
        note: feed && feed.method === "keywordFilter" ? TEXT.keywordNote : "",
        credit: source.credit || "",
        status,
      };
    });
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
      "topics", "topics-section", "bottom-line"]) {
      el[id] = doc.getElementById(id);
    }

    const state = {
      sources: null,
      news: null,
      fromSaved: false,
      selected: [],
      // The topics the page lists ([{id, label}], R18.1) and the chosen one (R18.3).
      topics: [],
      topic: logic.DEFAULT_TOPIC,
      loading: false,
      lastLoad: 0,
      // Sveriges Radio and any other source the page fetches itself. Memory
      // only (R7.3): source id -> {last, inFlight, status, fetchedAt, items}.
      live: new Map(),
      // Validated keyword lists by topic id, and the file names (from sources.json).
      keywords: new Map(),
    };
    const pendingLive = new Set();
    const sourceEls = new Map();
    let sourcesBuilt = "";
    let topicsBuilt = "";
    const topicEls = new Map();
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

    function topicLabel() {
      const found = state.topics.find((t) => t.id === state.topic);
      return found ? found.label : state.topic;
    }

    function currentItems() {
      return visibleItems(state.news, state.selected, liveItems(), state.topic);
    }

    function renderList() {
      const items = currentItems();
      // R8.4: only when news were loaded, nothing is left to show and no chosen
      // source is still being fetched.
      // A chosen live source that offers the topic and is still being fetched is
      // waited for.
      const waiting = state.selected.some((id) => {
        const live = state.live.get(id);
        const source = (state.sources || []).find((s) => s.id === id);
        return live !== undefined && live.status === "loading" && source !== undefined &&
          logic.offersTopic(source, state.topic);
      });
      const showEmpty = state.news !== null && items.length === 0 && !waiting;
      const emptyText = logic.emptyNoticeText(
        (state.sources || []).filter((s) => state.selected.includes(s.id)), state.topic, topicLabel());
      const key = JSON.stringify([state.news !== null, showEmpty, emptyText, items]);
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
      el.empty.textContent = emptyText;
      el.empty.hidden = !showEmpty;
      if (focusedId !== null && linkById.has(focusedId)) linkById.get(focusedId).focus();
    }

    function renderHeader() {
      const news = state.news;
      const parts = [];
      if (news && state.sources) {
        parts.push("Nyheter uppdaterade " + news.generatedAtDisplay); // R18.8
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
      const rows = sourceRows(state.sources, state.news, state.selected, state.live, state.topic, state.topics);
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
          const topics = makeText("span", "source-topics", "");
          const note = makeText("span", "source-note", "");
          const credit = makeText("span", "source-credit", "");
          const status = makeText("span", "source-status", "");
          info.appendChild(topics);
          info.appendChild(note);
          info.appendChild(credit);
          info.appendChild(status);
          li.appendChild(input);
          li.appendChild(label);
          li.appendChild(info);
          el.sources.appendChild(li);
          sourceEls.set(row.id, { input, topics, note, credit, status });
        });
      }
      for (const row of rows) {
        const parts = sourceEls.get(row.id);
        parts.input.checked = row.checked;
        parts.topics.textContent = row.topics;
        parts.topics.hidden = row.topics === "";
        parts.note.textContent = row.note;
        parts.note.hidden = row.note === "";
        parts.credit.textContent = row.credit;
        parts.credit.hidden = row.credit === "";
        parts.status.textContent = row.status;
      }
    }

    function renderBottom() {
      el["bottom-line"].textContent = state.sources ? bottomLine(state.sources, currentItems()) : "";
    }

    // "Ämnen" (R18.1): one radio button per topic, built once per list of topics so
    // that the focus stays where it is; later calls only set which one is chosen.
    function renderTopics() {
      el["topics-section"].hidden = !state.sources || state.topics.length === 0;
      if (!state.sources) return;
      const signature = state.topics.map((t) => t.id + "=" + t.label).join("|");
      if (signature !== topicsBuilt) {
        topicsBuilt = signature;
        topicEls.clear();
        el.topics.replaceChildren();
        state.topics.forEach((topic, index) => {
          const row = doc.createElement("div");
          row.className = "topic-row";
          const id = "topic-rb-" + index;
          const input = doc.createElement("input");
          input.setAttribute("type", "radio");
          input.setAttribute("name", "topic");
          input.setAttribute("id", id);
          input.addEventListener("change", () => {
            if (input.checked) onTopic(topic.id);
          });
          const label = makeText("label", "topic-name", topic.label);
          label.setAttribute("for", id);
          row.appendChild(input);
          row.appendChild(label);
          el.topics.appendChild(row);
          topicEls.set(topic.id, input);
        });
      }
      for (const [id, input] of topicEls) input.checked = id === state.topic;
    }

    function renderAll() {
      renderNotices();
      renderHeader();
      renderTopics();
      renderList();
      renderSources();
      renderBottom();
    }

    // A new topic: saved (the id only, R18.3) and shown at once. No request is made
    // (R18.2, R15.3).
    function onTopic(id) {
      if (id === state.topic || !state.topics.some((t) => t.id === id)) return;
      state.topic = id;
      writeKey(storage, KEY_TOPIC, id);
      renderList();
      renderTopics();
      renderSources();
      renderBottom();
    }

    function onChoice() {
      // The ids of the ticked boxes, in the order of sources.json. Ids that are
      // no longer approved are not in it, so they are dropped here (R3.5).
      const before = state.selected;
      state.selected = state.sources
        .filter((s) => sourceEls.get(s.id).input.checked)
        .map((s) => s.id);
      const ticked = state.selected.filter((id) => !before.includes(id));
      writeKey(storage, KEY_SELECTED, JSON.stringify(state.selected));
      // The topic is saved with the choice, so that the one-time migration of R18.4
      // (which runs only without a saved topic) never adds a source the reader has
      // unticked since.
      writeKey(storage, KEY_TOPIC, state.topic);
      // An unticked live source keeps nothing in memory. Its time of last request
      // stays, so the call limits hold across unticking and ticking.
      for (const source of state.sources) {
        const live = state.live.get(source.id);
        if (source.fetchedBy === "browser" && live && !state.selected.includes(source.id)) {
          live.items = [];
          live.missing = [];
          if (!live.inFlight) live.status = "idle";
        }
      }
      // Ticking a source fetches it if the limits allow (the first request of the
      // page at once, later ones only 5 minutes after the last).
      if (ticked.length > 0) startLive("choose", ticked);
      renderList();
      renderSources();
      renderBottom();
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
        live = { last: null, inFlight: false, status: "idle", fetchedAt: null, items: [], missing: [] };
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
        // The lists of the topics this source filters by keywords, fetched from the
        // build folder under the names in sources.json, once per page; only a source
        // that is chosen gets here (R15.3). A list that cannot be read or is invalid
        // leaves its topic out for this round (D42); it is tried again next time.
        const wanted = [];
        for (const feed of source.feeds) {
          if (feed.method === "keywordFilter" && !wanted.includes(feed.topic)) wanted.push(feed.topic);
        }
        const missing = [];
        await Promise.all(wanted.map(async (topic) => {
          if (state.keywords.has(topic)) return;
          try {
            const entry = state.topics.find((t) => t.id === topic);
            if (!entry || !entry.keywords) throw new Error("no keyword file");
            state.keywords.set(topic, logic.validateKeywords(await fetchJson(entry.keywords), topic));
          } catch (e) {
            missing.push(topic);
          }
        }));
        // The reader may have unticked the source while the keyword files were fetched:
        // then no request goes to the source (R15.3).
        if (!state.selected.includes(source.id)) {
          live.items = [];
          live.missing = [];
          live.status = "idle";
          return;
        }
        if (typeof env.AbortController === "function") {
          controller = new env.AbortController();
          timer = env.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
        }
        const entries = await atom.fetchAtom(env.fetch, source.url, {
          signal: controller ? controller.signal : undefined,
          DOMParser: env.DOMParser,
        });
        // One response, all topics (R15.3, R7.4): a feed whose keyword list is missing
        // is left out, so its topic is simply not given to any item. "all-news" is a
        // `feed` entry and is always given.
        const items = logic.selectTopicItems(entries, {
          id: source.id,
          name: source.name,
          allowedHosts: source.allowedHosts,
          feeds: source.feeds.filter((f) => f.method !== "keywordFilter" || !missing.includes(f.topic)),
        }, state.keywords, env.now());
        if (state.selected.includes(source.id)) {
          live.items = items;
          live.missing = missing;
          live.fetchedAt = env.now();
          live.status = "ok";
        } else {
          // Unticked while the request ran: nothing is kept.
          live.items = [];
          live.missing = [];
          live.status = "idle";
        }
      } catch (e) {
        // Nothing from the error is used: not its message, not its type.
        live.items = [];
        live.missing = [];
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
    function startLive(trigger, only) {
      if (!state.sources) return Promise.resolve();
      const jobs = [];
      for (const source of state.sources) {
        if (source.fetchedBy !== "browser") continue;
        if (only && !only.includes(source.id)) continue;
        const live = liveOf(source.id);
        if (live.inFlight) continue;
        // An unticked source is not requested at all (the reader asked not to see it).
        if (!state.selected.includes(source.id)) continue;
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
          const file = await fetchJson("sources.json");
          const sources = validateSources(file);
          if (!sources) throw new Error("no usable sources");
          state.sources = sources;
          state.topics = logic.offeredTopics(readTopicList(file), sources);
          // The one-time addition of Riksdagen to a saved choice (R18.4, R16.9).
          const migrated = logic.migrateSavedChoice(readKey(storage, KEY_SELECTED), readKey(storage, KEY_TOPIC), sources);
          if (migrated) {
            writeKey(storage, KEY_SELECTED, JSON.stringify(migrated.selected));
            writeKey(storage, KEY_TOPIC, migrated.topic);
          }
          state.selected = parseSelected(readKey(storage, KEY_SELECTED), sources);
          state.topic = logic.readSavedTopic(readKey(storage, KEY_TOPIC), state.topics.map((t) => t.id)) ||
            logic.DEFAULT_TOPIC;
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
      el["topics-section"].hidden = true;
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
    KEY_TOPIC,
    DISCLAIMER_RIKSDAGEN,
    REFRESH_MS,
    STALE_MS,
    TEXT,
    validateSources,
    readTopicList,
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
