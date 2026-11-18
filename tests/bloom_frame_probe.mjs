/**
 * Run a rendered Data Center script against a fake frame.
 * Stdin: { html, mode, scenario }.
 * mode is "empower" (requests on load) or "copilot" (requests when Goose opens).
 */
import vm from "node:vm";

const raw = await new Promise((resolve, reject) => {
  const chunks = [];
  process.stdin.on("data", (chunk) => chunks.push(chunk));
  process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
  process.stdin.on("error", reject);
});

const input = JSON.parse(raw);
const scenario = input.scenario || {};
const mode = input.mode;

function lastScript(html) {
  const end = html.lastIndexOf("</script>");
  const start = html.lastIndexOf("<script>", end);
  if (start < 0 || end < start) {
    throw new Error("missing script");
  }
  return html.slice(start + "<script>".length, end);
}

function makeEl(id) {
  const listeners = {};
  return {
    id: id || "",
    hidden: true,
    textContent: "",
    className: "",
    dataset: {},
    style: {},
    innerHTML: "",
    value: "",
    classList: {
      add() {},
      remove() {},
      toggle() {},
      contains() {
        return false;
      },
    },
    getAttribute(name) {
      if (name === "data-default") return "Open";
      return null;
    },
    setAttribute() {},
    addEventListener(type, fn) {
      (listeners[type] || (listeners[type] = [])).push(fn);
    },
    removeEventListener(type, fn) {
      const list = listeners[type] || [];
      const idx = list.indexOf(fn);
      if (idx >= 0) list.splice(idx, 1);
    },
    querySelectorAll() {
      return [];
    },
    appendChild(child) {
      return child;
    },
    click() {
      (listeners.click || []).forEach((fn) => fn({ preventDefault() {}, target: this }));
    },
  };
}

const elements = new Map();
function getElementById(id) {
  if (!elements.has(id)) elements.set(id, makeEl(id));
  return elements.get(id);
}

const posts = [];
const fetches = [];
const timeouts = [];
const windowListeners = {};

const windowObj = {
  setTimeout(fn, ms) {
    timeouts.push(ms);
    return timeouts.length;
  },
  clearTimeout() {},
  addEventListener(type, fn) {
    (windowListeners[type] || (windowListeners[type] = [])).push(fn);
  },
  removeEventListener(type, fn) {
    const list = windowListeners[type] || [];
    const idx = list.indexOf(fn);
    if (idx >= 0) list.splice(idx, 1);
  },
};

const parent = {
  postMessage(data, origin) {
    posts.push({ data, origin });
  },
};
windowObj.parent = scenario.topLevel ? windowObj : parent;

const documentObj = {
  referrer: scenario.referrer || "",
  documentElement: makeEl("documentElement"),
  getElementById,
  createElement() {
    return makeEl("");
  },
  addEventListener() {},
};

const locationObj = {
  ancestorOrigins: scenario.ancestorOrigins || [],
};
windowObj.document = documentObj;
windowObj.location = locationObj;

function fetchImpl(url, options) {
  const headers = (options && options.headers) || {};
  fetches.push({
    url: String(url),
    authorization: headers.Authorization || headers.authorization || "",
  });
  return Promise.resolve({
    ok: true,
    json() {
      return Promise.resolve({
        ok: true,
        metrics: {},
        filters: {},
        enrollments: [],
        changes: [],
        stages: [],
        waiting: [],
        history: [],
      });
    },
  });
}

const sandbox = {
  window: windowObj,
  document: documentObj,
  location: locationObj,
  fetch: fetchImpl,
  console,
  setTimeout: windowObj.setTimeout,
  clearTimeout: windowObj.clearTimeout,
};

function deliver(messages) {
  (messages || []).forEach((message) => {
    const event = { origin: message.origin, data: message.data };
    (windowListeners.message || []).forEach((fn) => fn(event));
  });
}

function snapshot() {
  const locked = elements.get("locked");
  const dashboard = elements.get("dashboard");
  return {
    posts,
    fetches,
    timeouts,
    locked: locked ? { hidden: Boolean(locked.hidden), text: locked.textContent } : null,
    dashboardHidden: dashboard ? Boolean(dashboard.hidden) : null,
  };
}

const context = vm.createContext(sandbox);
try {
  vm.runInContext(lastScript(input.html), context, { timeout: 1000 });
  if (mode === "copilot") {
    getElementById("gooseOpen").click();
  }
} catch (err) {
  process.stderr.write(String(err && err.stack ? err.stack : err));
  process.exit(1);
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

await flush();
try {
  deliver(scenario.messages || []);
} catch (err) {
  process.stderr.write(String(err && err.stack ? err.stack : err));
  process.exit(1);
}
await flush();
process.stdout.write(JSON.stringify(snapshot()));
