// A small stand-in for the browser's DOMParser, for the tests that run under Node
// (Node has none). It reads well-formed XML into elements with `localName`,
// `namespaceURI`, `children`, `textContent` and `getAttribute`, resolves
// namespaces, entities (the five predefined and numeric ones) and CDATA, and
// reports any error the way a browser does: a document that holds a <parsererror>
// element. It is only as strict as these tests need. The real DOMParser is checked
// in a real browser by hand (README, "Checks by hand").

const XHTML = "http://www.w3.org/1999/xhtml";
const PREDEFINED = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

class XmlError extends Error {}

function decode(text) {
  return text.replace(/&(#x[0-9A-Fa-f]+|#[0-9]+|[A-Za-z][A-Za-z0-9]*);/g, (whole, body) => {
    if (body[0] === "#") {
      const code = body[1] === "x" ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
      if (!Number.isInteger(code) || code < 1 || code > 0x10ffff) throw new XmlError("bad reference");
      return String.fromCodePoint(code);
    }
    if (!(body in PREDEFINED)) throw new XmlError("undefined entity");
    return PREDEFINED[body];
  });
}

class Element {
  constructor(qname, namespaceURI, attrs) {
    this.qname = qname;
    this.localName = qname.includes(":") ? qname.split(":")[1] : qname;
    this.namespaceURI = namespaceURI;
    this.attrs = attrs;
    this.children = [];
    this.parts = []; // text and elements in order
  }
  get textContent() {
    return this.parts.map((p) => (typeof p === "string" ? p : p.textContent)).join("");
  }
  getAttribute(name) {
    return name in this.attrs ? this.attrs[name] : null;
  }
}

function lookup(scopes, prefix) {
  for (let i = scopes.length - 1; i >= 0; i--) if (prefix in scopes[i]) return scopes[i][prefix];
  return prefix === "" ? "" : null;
}

function parseDocument(text) {
  let i = 0;
  const stack = [];
  const scopes = [{}];
  let root = null;
  const fail = () => { throw new XmlError("not well-formed"); };
  if (text.charCodeAt(0) === 0xfeff) i = 1;
  while (i < text.length) {
    if (text.startsWith("<?", i)) {
      const end = text.indexOf("?>", i);
      if (end < 0) fail();
      i = end + 2;
    } else if (text.startsWith("<!--", i)) {
      const end = text.indexOf("-->", i + 4);
      if (end < 0) fail();
      i = end + 3;
    } else if (text.startsWith("<![CDATA[", i)) {
      const end = text.indexOf("]]>", i);
      if (end < 0 || stack.length === 0) fail();
      stack[stack.length - 1].parts.push(text.slice(i + 9, end));
      i = end + 3;
    } else if (text.startsWith("<!", i)) {
      fail(); // a DOCTYPE is not handled here (atom.js refuses it before parsing)
    } else if (text.startsWith("</", i)) {
      const m = /^<\/([A-Za-z_][\w.:-]*)\s*>/.exec(text.slice(i, i + 300));
      if (!m || stack.length === 0 || stack[stack.length - 1].qname !== m[1]) fail();
      stack.pop();
      scopes.pop();
      i += m[0].length;
    } else if (text[i] === "<") {
      const head = /^<([A-Za-z_][\w.:-]*)/.exec(text.slice(i, i + 300));
      if (!head) fail();
      i += head[0].length;
      const attrs = {};
      for (;;) {
        const ws = /^\s+/.exec(text.slice(i, i + 20));
        if (ws) i += ws[0].length;
        if (text.startsWith("/>", i) || text[i] === ">") break;
        const a = /^([A-Za-z_][\w.:-]*)\s*=\s*(?:"([^"<]*)"|'([^'<]*)')/.exec(text.slice(i, i + 20000));
        if (!a || !ws || a[1] in attrs) fail();
        attrs[a[1]] = decode(a[2] !== undefined ? a[2] : a[3]);
        i += a[0].length;
      }
      const scope = {};
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "xmlns") scope[""] = v;
        else if (k.startsWith("xmlns:")) scope[k.slice(6)] = v;
      }
      scopes.push(scope);
      const prefix = head[1].includes(":") ? head[1].split(":")[0] : "";
      const ns = lookup(scopes, prefix);
      if (ns === null) fail();
      const el = new Element(head[1], ns === "" ? null : ns, attrs);
      if (stack.length > 0) {
        stack[stack.length - 1].children.push(el);
        stack[stack.length - 1].parts.push(el);
      } else {
        if (root) fail();
        root = el;
      }
      if (text.startsWith("/>", i)) {
        scopes.pop();
        i += 2;
      } else {
        stack.push(el);
        i += 1;
      }
    } else {
      const end = text.indexOf("<", i);
      const raw = text.slice(i, end < 0 ? text.length : end);
      if (stack.length === 0) {
        if (raw.trim() !== "") fail();
      } else {
        stack[stack.length - 1].parts.push(decode(raw));
      }
      i += raw.length;
    }
  }
  if (!root || stack.length > 0) fail();
  return root;
}

export class FakeDOMParser {
  parseFromString(text, type) {
    if (type !== "application/xml") throw new Error("the page must ask for application/xml");
    try {
      const root = parseDocument(String(text));
      return { documentElement: root, getElementsByTagName: () => [] };
    } catch (e) {
      if (!(e instanceof XmlError)) throw e;
      const bad = new Element("parsererror", XHTML, {});
      return { documentElement: bad, getElementsByTagName: (n) => (n === "parsererror" ? [bad] : []) };
    }
  }
}
