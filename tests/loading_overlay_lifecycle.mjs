/**
 * Lifecycle checks for the Happy Solar loading overlay.
 * Slow and failed requests are simulated in this test only.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "api", "loading_overlay.js"), "utf8");

if (typeof globalThis.requestAnimationFrame !== "function") {
  globalThis.requestAnimationFrame = (fn) => setTimeout(() => fn(Date.now()), 0);
  globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function makeElement(tag) {
  const listeners = {};
  const el = {
    tagName: String(tag || "div").toUpperCase(),
    id: "",
    className: "",
    hidden: false,
    tabIndex: 0,
    inert: false,
    isConnected: false,
    style: {},
    textContent: "",
    attributes: {},
    _html: "",
    _buttons: [],
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name === "id") this.id = String(value);
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
    },
    hasAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name);
    },
    addEventListener(type, fn) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(fn);
    },
    dispatch(type, event) {
      (listeners[type] || []).forEach((fn) => fn(event));
    },
    focus() {
      document.activeElement = this;
    },
    contains(node) {
      return node === this || this._buttons.indexOf(node) >= 0;
    },
    closest() {
      return null;
    },
    querySelector(sel) {
      if (sel === "button") return this._buttons[0] || null;
      if (sel === "#loadingRetry") return this._buttons.find((button) => button.id === "loadingRetry") || null;
      if (sel === "#loadingBack") return this._buttons.find((button) => button.id === "loadingBack") || null;
      return null;
    },
    querySelectorAll(sel) {
      if (sel === "button") return this._buttons.slice();
      return [];
    },
    appendChild(child) {
      child.isConnected = true;
      return child;
    },
  };
  el.classList = {
    add() {},
    remove() {},
    contains(name) {
      return el.className.split(/\s+/).indexOf(name) >= 0;
    },
  };
  Object.defineProperty(el, "innerHTML", {
    get() {
      return el._html;
    },
    set(value) {
      el._html = String(value);
      el._buttons = [];
      const re = /<button\b([^>]*)>([\s\S]*?)<\/button>/g;
      let match;
      while ((match = re.exec(el._html))) {
        const attrs = match[1];
        const button = makeElement("button");
        button.isConnected = true;
        const id = /id="([^"]+)"/.exec(attrs);
        button.id = id ? id[1] : "";
        button.textContent = match[2].replace(/<[^>]+>/g, "");
        button.className = (/class="([^"]+)"/.exec(attrs) || [])[1] || "";
        button._click = [];
        button.addEventListener = (type, fn) => {
          if (type === "click") button._click.push(fn);
        };
        button.dispatch = (type) => {
          if (type === "click") button._click.forEach((fn) => fn({}));
        };
        el._buttons.push(button);
      }
    },
  });
  return el;
}

const surfaces = ["workspace", "sidebar", "overlay"].map((name) => {
  const el = makeElement("div");
  el.id = name === "workspace" ? "" : name;
  el.className = name === "workspace" ? "workspace" : "";
  el.isConnected = true;
  return el;
});
const main = makeElement("main");
main.id = "main";
main.isConnected = true;
const heading = makeElement("h2");
heading.isConnected = true;
const body = makeElement("body");
body.isConnected = true;
const bodyClasses = new Set();
body.classList = {
  add(name) {
    bodyClasses.add(name);
  },
  remove(name) {
    bodyClasses.delete(name);
  },
  contains(name) {
    return bodyClasses.has(name);
  },
};
body.appendChild = (child) => {
  child.isConnected = true;
  if (child.id === "hsFreshness") globalThis.__freshness = child;
  return child;
};
const docListeners = {};
globalThis.document = {
  body,
  documentElement: { style: {} },
  activeElement: body,
  createElement: makeElement,
  getElementById(id) {
    if (id === "main") return main;
    if (id === "hsFreshness") return globalThis.__freshness || null;
    return null;
  },
  querySelector(sel) {
    if (sel === "main") return main;
    if (String(sel).includes("h2")) return heading;
    return null;
  },
  querySelectorAll(sel) {
    if (String(sel).includes(".workspace")) return surfaces;
    return [];
  },
  addEventListener(type, fn) {
    docListeners[type] = docListeners[type] || [];
    docListeners[type].push(fn);
  },
  dispatch(type, event) {
    (docListeners[type] || []).forEach((fn) => fn(event));
  },
};
globalThis.window = globalThis;
globalThis.location = {
  href: "https://database-migration-chi.vercel.app/api/company_overview",
  origin: "https://database-migration-chi.vercel.app",
  reloadCount: 0,
  reload() {
    this.reloadCount += 1;
  },
};

new Function(source)();
const loading = globalThis.HappySolarLoading;
const layer = () => loading.layer;
let failures = 0;

function assert(condition, message) {
  if (!condition) {
    failures += 1;
    console.error("FAIL:", message);
  }
}

function http(ok, body, status) {
  return {
    ok,
    status: status || (ok ? 200 : 500),
    json() {
      return Promise.resolve(body);
    },
    text() {
      return Promise.resolve(JSON.stringify(body));
    },
  };
}

function laterFetch(delay, result) {
  return (_input, init) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve(result), delay);
      const signal = init && init.signal;
      const abort = () => {
        clearTimeout(timer);
        const error = new Error("The operation was aborted.");
        error.name = "AbortError";
        reject(error);
      };
      if (signal) {
        if (signal.aborted) abort();
        else signal.addEventListener("abort", abort);
      }
    });
}

async function mainTest() {
  assert(loading, "HappySolarLoading is installed");
  assert(!/Preview loading/.test(source), "production script has no Preview loading control");
  assert(!/previewDashboardLoading/.test(source), "production script does not start a timed preview");
  assert(!/(^|[^0-9])5000([^0-9]|$)/.test(source), "production script has no five-second timer");

  const starter = makeElement("button");
  starter.isConnected = true;
  starter.focus();
  loading.begin("view");
  await loading.fetch(laterFetch(0, http(false, { error: "database unavailable" }, 503)), "/api/metrics/company_snapshot?initial=1");
  await wait(30);
  assert(!layer().hidden, "initial failure shows the error card");
  assert(layer()._html.includes("We couldn’t load this view. Try again."), "initial-load error copy");
  assert(!layer()._html.includes("previous view is still available"), "initial failure does not claim a previous view");
  assert(!layer()._html.includes("503") && !layer()._html.includes("database unavailable"), "server details stay off the card");
  assert(String(loading.lastDiagnostic).includes("503"), "diagnostic is retained off the card");
  const retry = layer().querySelector("#loadingRetry");
  const back = layer().querySelector("#loadingBack");
  assert(retry && retry.textContent === "Try again", "Try again button");
  assert(back && back.textContent === "Back to dashboard", "Back to dashboard button");
  assert(document.activeElement === retry, "failure focuses Try again");
  document.activeElement = back;
  let wrapped = false;
  layer().dispatch("keydown", {
    key: "Tab",
    shiftKey: false,
    preventDefault() {
      wrapped = true;
    },
    stopPropagation() {},
  });
  assert(wrapped && document.activeElement === retry, "Tab stays inside the error actions");
  back.dispatch("click", {});
  assert(layer().hidden, "Back to dashboard closes the error card");
  assert(document.activeElement === starter, "focus returns to the initiating control");
  assert(main.getAttribute("aria-busy") === "false", "busy state cleared on exit");

  loading.begin("view");
  const fast = loading.fetch(laterFetch(20, http(true, { value: 4 })), "/api/metrics/company_snapshot?fast=1");
  await wait(40);
  assert(layer().hidden, "overlay is still hidden while a fast request is in flight under 150ms");
  await fast;
  await wait(40);
  assert(layer().hidden, "request faster than 150ms does not flash the overlay");
  assert(loading.committed, "fast success commits after render");

  const focusBeforeSlow = makeElement("button");
  focusBeforeSlow.isConnected = true;
  focusBeforeSlow.focus();
  loading.begin("view");
  let releaseSlow;
  const slow = loading.fetch(
    (_input, init) =>
      new Promise((resolve, reject) => {
        releaseSlow = () => resolve(http(true, { value: 8 }));
        const signal = init && init.signal;
        if (signal) {
          signal.addEventListener("abort", () => {
            const error = new Error("The operation was aborted.");
            error.name = "AbortError";
            reject(error);
          });
        }
      }),
    "/api/metrics/company_snapshot?slow=1"
  );
  await wait(180);
  assert(!layer().hidden, "slow request shows the overlay after 150ms");
  assert(layer()._html.includes("LOADING REQUESTED DATA"), "loading footer copy");
  assert(layer()._html.includes("A CLEARER VIEW IS ON ITS WAY"), "eyebrow copy");
  assert(layer()._html.includes("Updating your dashboard"), "title copy");
  assert(layer()._html.includes("Bringing your numbers into focus."), "body copy");
  assert(layer()._html.includes("HAPPY SOLAR"), "brand copy");
  assert((layer()._html.match(/rotate\(/g) || []).length === 12, "twelve solar rays");
  assert(layer().getAttribute("role") === "dialog", "dialog role");
  assert(layer().getAttribute("aria-modal") === "true", "aria-modal");
  assert(layer().getAttribute("aria-labelledby") === "loadingTitle", "aria-labelledby");
  assert(layer()._html.includes('role="status"'), "polite loading status");
  assert(main.getAttribute("aria-busy") === "true", "dashboard aria-busy while loading");
  assert(body.classList.contains("loading-open"), "scroll lock class");
  assert(body.style.overflow === "hidden", "background scroll locked");
  assert(surfaces.every((el) => el.inert === true), "workspace, sidebar, and modal are inert");
  assert(document.activeElement === layer(), "focus moves to the dialog while loading");
  let escapeBlocked = false;
  layer().dispatch("keydown", {
    key: "Escape",
    preventDefault() {
      escapeBlocked = true;
    },
    stopPropagation() {},
  });
  assert(escapeBlocked && !layer().hidden, "Escape does not dismiss a live request");
  let tabBlocked = false;
  layer().dispatch("keydown", {
    key: "Tab",
    shiftKey: false,
    preventDefault() {
      tabBlocked = true;
    },
    stopPropagation() {},
  });
  assert(tabBlocked, "Tab is trapped when loading has no buttons");
  releaseSlow();
  await slow;
  await wait(40);
  assert(layer().hidden, "overlay hides after the slow request renders");
  assert(document.activeElement === focusBeforeSlow, "focus returns after a successful load");
  assert(surfaces.every((el) => el.inert === false), "inert state restored");
  assert(!body.classList.contains("loading-open"), "scroll lock released");

  loading.begin("view");
  await loading.fetch(laterFetch(0, http(true, { value: 20 })), "/api/metrics/company_snapshot?ok=1");
  await wait(40);
  let visibleValue = 20;
  loading.begin("view");
  await loading.fetch(laterFetch(0, http(false, { error: "nope" }, 500)), "/api/metrics/company_snapshot?fail=1");
  await wait(30);
  if (!layer()._html.includes("previous view")) visibleValue = 0;
  assert(visibleValue === 20, "refresh failure does not replace the previous view with zero");
  assert(layer()._html.includes("Your previous view is still available."), "refresh error keeps the previous-view copy");
  assert(layer()._html.includes("Try refreshing the data again."), "refresh guidance");
  let retried = 0;
  globalThis.hsOpsReload = () => {
    retried += 1;
    loading.begin("view");
    return loading.fetch(laterFetch(0, http(true, { value: 21 })), "/api/metrics/company_snapshot?retry=1");
  };
  layer().querySelector("#loadingRetry").dispatch("click", {});
  await wait(50);
  assert(retried === 1, "Try again runs the page reload for the current scope");
  assert(layer().hidden, "successful retry hides the overlay");

  const commits = [];
  function loadView(label, delay) {
    loading.begin("filter");
    const generation = loading.currentId;
    return loading
      .fetch(laterFetch(delay, http(true, { value: label })), "/api/metrics/company_snapshot?" + label)
      .then(async (res) => {
        const data = await res.json();
        if (loading.currentId !== generation) return;
        commits.push(data.value);
      })
      .catch((error) => {
        if (error && error.name === "AbortError") return;
        throw error;
      });
  }
  const first = loadView("stale", 250);
  const second = loadView("current", 10);
  await wait(80);
  await second;
  await wait(200);
  await first;
  assert(commits.length === 1 && commits[0] === "current", "rapid filter changes cannot commit a stale response");
  assert(!String(layer()._html).includes("couldn’t"), "a superseded abort does not show an obsolete error");

  let sawOpenDashboard = false;
  await loading.background(async () => {
    sawOpenDashboard = layer().hidden === true;
  });
  const chip = document.getElementById("hsFreshness");
  assert(sawOpenDashboard, "background refresh leaves the dashboard usable");
  assert(layer().hidden, "background refresh does not show the blocking overlay");
  assert(chip && chip.textContent === "Updated" && chip.hidden === false, "background refresh shows a quiet freshness indicator");

  loading.begin("view");
  let releaseBlock;
  const pending = loading.fetch(
    () =>
      new Promise((resolve) => {
        releaseBlock = () => resolve(http(true, { value: 1 }));
      }),
    "/api/metrics/company_snapshot?block=1"
  );
  await wait(180);
  assert(!layer().hidden, "the current view request is showing");
  await loading.fetch(laterFetch(0, http(true, { value: 1 })), "/api/metrics/company_trends?oc_raw=1", { hsBackground: true });
  assert(!layer().hidden, "a background request does not dismiss the newer loading state");
  releaseBlock();
  await pending;
  await wait(40);
  assert(layer().hidden, "the current request hides only after it renders");

  const tab = makeElement("button");
  tab.textContent = "Overview";
  tab.closest = () => null;
  document.dispatch("click", { target: tab });
  await loading.fetch(laterFetch(30, http(true, { cached: true })), "/api/metrics/company_snapshot?cached=1");
  await wait(40);
  assert(layer().hidden, "a tab switch over already-loaded data does not block");

  if (failures) {
    console.error(failures + " assertion(s) failed");
    process.exit(1);
  }
  console.log("loading overlay lifecycle checks passed");
}

mainTest().catch((error) => {
  console.error(error);
  process.exit(1);
});
