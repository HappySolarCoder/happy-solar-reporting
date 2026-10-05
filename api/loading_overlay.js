/* Happy Solar loading overlay. Visual markup matches the approved prototype.
   Lifecycle: 150ms show delay, request generations, cancellation, no minimum display time. */
(function (root) {
  var SHOW_DELAY_MS = 150;
  var REQUEST_TIMEOUT_MS = 25000;
  var layer = null;
  var freshness = null;
  var current = null;
  var seq = 0;
  var blocked = [];
  var savedOverflow = null;
  var focusReturn = null;
  var committed = false;
  var sideAbort = null;
  var lastDiagnostic = "";

  function ensureSideAbort() {
    if (!sideAbort) sideAbort = new AbortController();
    return sideAbort;
  }

  function requestUrl(input) {
    if (typeof input === "string") return input;
    if (input && typeof input.url === "string") return input.url;
    return "";
  }

  function pathnameOf(input) {
    try {
      return new URL(requestUrl(input), root.location.href).pathname;
    } catch (error) {
      return "";
    }
  }

  function shouldTrack(input) {
    var path = pathnameOf(input);
    if (!path || path.indexOf("/api/") !== 0) return false;
    if (path === "/api/warm_cache") return false;
    if (path.indexOf("/api/copilot") === 0) return false;
    try {
      var url = new URL(requestUrl(input), root.location.href);
      if (url.origin !== root.location.origin) return false;
    } catch (error) {
      return false;
    }
    return true;
  }

  function isOptionalPath(input) {
    var path = pathnameOf(input);
    return path.indexOf("/api/metrics/bloom_goals") === 0 || path.indexOf("/api/metrics/company_trends") === 0;
  }

  function solarMark() {
    var rays = "";
    for (var i = 0; i < 12; i += 1) {
      rays += '<path d="M90 55v-8" transform="rotate(' + i * 30 + ' 90 90)"/>';
    }
    return '<div class="solar-loader" aria-hidden="true"><div class="solar-halo"></div><svg viewBox="0 0 180 180"><circle class="solar-orbit-track" cx="90" cy="90" r="75"/><g class="solar-orbit"><circle cx="90" cy="90" r="75" class="solar-arc"/><circle cx="90" cy="15" r="4" class="solar-satellite"/></g><circle class="solar-inner" cx="90" cy="90" r="57"/><g class="solar-rays">' + rays + '</g><circle class="solar-core" cx="90" cy="90" r="22"/><path class="solar-pulse" d="M72 92h10l6-10 8 18 6-8h7"/></svg><span class="solar-coordinate coordinate-a"></span><span class="solar-coordinate coordinate-b"></span></div>';
  }

  function loadingMarkup() {
    return '<div class="loading-grid" aria-hidden="true"></div><div class="loading-card"><div class="loading-brand">HAPPY SOLAR <span>/</span> OPERATIONS CONTROL</div>' + solarMark() + '<div class="loading-message" role="status" aria-live="polite"><div class="loading-eyebrow">A CLEARER VIEW IS ON ITS WAY</div><h2 id="loadingTitle">Updating your dashboard<span class="loading-dots" aria-hidden="true"><i></i><i></i><i></i></span></h2><p>Bringing your numbers into focus.</p></div><div class="loading-flow" aria-hidden="true"><i></i></div><div class="loading-footer"><span class="loading-status-dot"></span>LOADING REQUESTED DATA</div></div>';
  }

  function errorMarkup() {
    var support = committed
      ? "Your previous view is still available.<br>Try refreshing the data again."
      : "We couldn’t load this view. Try again.";
    return '<div class="loading-card"><div class="loading-brand">HAPPY SOLAR <span>/</span> OPERATIONS CONTROL</div><div class="loading-error-icon" aria-hidden="true">!</div><h2 id="loadingTitle">We couldn’t refresh this view</h2><p id="loadingErrorStatus" role="status" aria-live="polite">' + support + '</p><div class="loading-error-actions"><button type="button" class="primary" id="loadingRetry">Try again</button><button type="button" id="loadingBack">Back to dashboard</button></div></div>';
  }

  function ensureLayer() {
    if (layer && layer.isConnected) return layer;
    layer = document.createElement("div");
    layer.id = "dashboardLoading";
    layer.className = "dashboard-loading";
    layer.hidden = true;
    layer.setAttribute("role", "dialog");
    layer.setAttribute("aria-modal", "true");
    layer.setAttribute("aria-labelledby", "loadingTitle");
    layer.tabIndex = -1;
    layer.addEventListener("keydown", onLayerKeydown);
    document.body.appendChild(layer);
    return layer;
  }

  function mainEl() {
    return document.getElementById("main") || document.querySelector("main");
  }

  function setBlocked(value) {
    var node = ensureLayer();
    if (value) {
      if (blocked.length) return;
      blocked = Array.prototype.map.call(
        document.querySelectorAll(".workspace, #sidebar, #overlay, .wrap, .goose-open, .goose-panel"),
        function (el) {
          return { el: el, inert: el.inert };
        }
      );
      blocked.forEach(function (item) {
        item.el.inert = true;
      });
      savedOverflow = {
        body: document.body.style.overflow,
        html: document.documentElement.style.overflow,
      };
      document.body.classList.add("loading-open");
      document.body.style.overflow = "hidden";
      document.documentElement.style.overflow = "hidden";
      var busy = mainEl();
      if (busy) busy.setAttribute("aria-busy", "true");
      node.setAttribute("aria-modal", "true");
    } else {
      blocked.forEach(function (item) {
        item.el.inert = item.inert;
      });
      blocked = [];
      document.body.classList.remove("loading-open");
      if (savedOverflow) {
        document.body.style.overflow = savedOverflow.body;
        document.documentElement.style.overflow = savedOverflow.html;
        savedOverflow = null;
      }
      var idle = mainEl();
      if (idle) idle.setAttribute("aria-busy", "false");
    }
  }

  function rememberFocus() {
    var active = document.activeElement;
    if (active && active !== document.body && layer && !layer.contains(active)) focusReturn = active;
  }

  function focusHeading() {
    var heading = document.querySelector(".crumb strong, main h1, #main h1, main h2, #main h2");
    if (heading && heading.focus) {
      if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
      heading.focus();
    }
  }

  function restoreFocus() {
    var back = focusReturn;
    focusReturn = null;
    if (back && back.isConnected && typeof back.focus === "function") back.focus();
    else focusHeading();
  }

  function showLoading() {
    var node = ensureLayer();
    rememberFocus();
    if (node.hidden) setBlocked(true);
    node.className = "dashboard-loading";
    node.hidden = false;
    node.innerHTML = loadingMarkup();
    node.focus();
  }

  function hideOverlay(options) {
    var restore = !options || options.restoreFocus !== false;
    if (!layer) return;
    setBlocked(false);
    if (restore) restoreFocus();
    layer.hidden = true;
    layer.className = "dashboard-loading";
    layer.innerHTML = "";
  }

  function showError() {
    var node = ensureLayer();
    rememberFocus();
    if (node.hidden) setBlocked(true);
    node.className = "dashboard-loading loading-error";
    node.hidden = false;
    node.innerHTML = errorMarkup();
    var retry = node.querySelector("#loadingRetry");
    var back = node.querySelector("#loadingBack");
    if (retry) {
      retry.addEventListener("click", function () {
        retryLoading();
      });
    }
    if (back) {
      back.addEventListener("click", function () {
        backToDashboard();
      });
    }
    if (retry) retry.focus();
    else node.focus();
  }

  function clearShowTimer(gen) {
    if (gen && gen.showTimer) {
      clearTimeout(gen.showTimer);
      gen.showTimer = null;
    }
  }

  function armShow(gen) {
    if (!gen || gen.showTimer || gen.shown || gen.settled) return;
    gen.showTimer = setTimeout(function () {
      gen.showTimer = null;
      if (gen !== current || gen.stale || gen.settled || gen.failed) return;
      if (gen.inFlight <= 0) return;
      showLoading();
      gen.shown = true;
    }, SHOW_DELAY_MS);
  }

  function finishGeneration(gen) {
    gen.settleQueued = false;
    if (gen !== current || gen.stale) return;
    if (gen.inFlight > 0) return;
    clearShowTimer(gen);
    gen.settled = true;
    if (gen.failed) {
      showError();
      return;
    }
    if (gen.saw) committed = true;
    if (gen.shown || (layer && !layer.hidden)) hideOverlay();
  }

  function scheduleSettle(gen) {
    if (!gen || gen.settleQueued || gen.settled || gen.stale) return;
    gen.settleQueued = true;
    if (gen.failed) {
      setTimeout(function () {
        finishGeneration(gen);
      }, 0);
      return;
    }
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        finishGeneration(gen);
      });
    });
  }

  function begin(reason) {
    var previous = current;
    if (
      previous &&
      !previous.settled &&
      !previous.stale &&
      !previous.failed &&
      previous.inFlight === 0 &&
      !previous.saw
    ) {
      previous.reason = reason || previous.reason;
      return previous;
    }
    if (previous && !previous.settled) {
      previous.stale = true;
      clearShowTimer(previous);
      try {
        previous.controller.abort();
      } catch (error) {
        /* already aborted */
      }
    }
    try {
      if (sideAbort) sideAbort.abort();
    } catch (error) {
      /* already aborted */
    }
    sideAbort = new AbortController();
    if (previous && previous.settled && layer && !layer.hidden) hideOverlay({ restoreFocus: false });
    var keepVisible = layer && !layer.hidden && !layer.classList.contains("loading-error");
    var gen = {
      id: ++seq,
      reason: reason || "view",
      controller: new AbortController(),
      inFlight: 0,
      saw: false,
      failed: false,
      stale: false,
      settled: false,
      shown: !!keepVisible,
      showTimer: null,
      settleQueued: false,
    };
    current = gen;
    return gen;
  }

  function mergeSignal(gen, init, timeoutSignal) {
    var signals = [gen.controller.signal, timeoutSignal];
    if (init.signal) signals.push(init.signal);
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.any === "function") {
      return AbortSignal.any(signals);
    }
    return gen.controller.signal;
  }

  function guardBody(response, gen) {
    ["json", "text"].forEach(function (method) {
      if (typeof response[method] !== "function") return;
      var original = response[method].bind(response);
      response[method] = function () {
        if (gen.stale || gen !== current) {
          throw new DOMException("The operation was aborted.", "AbortError");
        }
        return Promise.resolve(original()).then(function (body) {
          if (gen.stale || gen !== current) {
            throw new DOMException("The operation was aborted.", "AbortError");
          }
          return body;
        });
      };
    });
    return response;
  }

  function noteEnd(gen, optional, failed) {
    if (gen.stale) return;
    if (failed && !optional) gen.failed = true;
    gen.inFlight = Math.max(0, gen.inFlight - 1);
    if (gen.inFlight === 0) scheduleSettle(gen);
  }

  function track(originalFetch, input, init, optional) {
    var gen = current;
    var timeoutSignal = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
    var nextInit = Object.assign({}, init, { signal: mergeSignal(gen, init, timeoutSignal) });
    gen.inFlight += 1;
    gen.saw = true;
    if (layer && !layer.hidden && !layer.classList.contains("loading-error")) gen.shown = true;
    armShow(gen);
    return Promise.resolve()
      .then(function () {
        return originalFetch(input, nextInit);
      })
      .then(function (response) {
        if (!gen.stale && !optional && response && response.ok === false) {
          gen.failed = true;
          lastDiagnostic = (response.status || "error") + " " + requestUrl(input);
        }
        return guardBody(response, gen);
      })
      .catch(function (error) {
        var aborted = gen.stale || (gen.controller && gen.controller.signal.aborted);
        var timedOut = timeoutSignal.aborted || (error && error.name === "TimeoutError");
        if (!aborted && timedOut && !optional) {
          gen.failed = true;
          lastDiagnostic = "timeout " + requestUrl(input);
        } else if (!aborted && !(error && error.name === "AbortError") && !optional) {
          gen.failed = true;
          lastDiagnostic = (error && error.name ? error.name : "error") + " " + requestUrl(input);
        }
        throw error;
      })
      .finally(function () {
        noteEnd(gen, optional, false);
      });
  }

  function stripFlags(init) {
    var next = Object.assign({}, init || {});
    var flags = {
      optional: !!next.hsOptional,
      background: !!next.hsBackground,
      quiet: !!next.hsQuiet,
    };
    delete next.hsOptional;
    delete next.hsBackground;
    delete next.hsQuiet;
    return { init: next, flags: flags };
  }

  function ensureFreshness() {
    if (freshness && freshness.isConnected) return freshness;
    freshness = document.createElement("p");
    freshness.id = "hsFreshness";
    freshness.className = "hs-freshness";
    freshness.hidden = true;
    freshness.setAttribute("role", "status");
    freshness.setAttribute("aria-live", "polite");
    document.body.appendChild(freshness);
    return freshness;
  }

  function runBackground(originalFetch, input, init) {
    var chip = ensureFreshness();
    chip.hidden = false;
    chip.textContent = "Updating";
    return Promise.resolve()
      .then(function () {
        return originalFetch(input, init);
      })
      .finally(function () {
        if (!freshness) return;
        freshness.hidden = false;
        freshness.textContent = "Updated";
      });
  }

  function trackedFetch(originalFetch, input, init) {
    var parsed = stripFlags(init);
    if (parsed.flags.background) return runBackground(originalFetch, input, parsed.init);
    if (parsed.flags.quiet || !shouldTrack(input)) return originalFetch(input, parsed.init);
    if (!current || current.settled || current.stale) {
      var quietInit = parsed.init;
      var side = ensureSideAbort();
      if (side.signal && typeof AbortSignal !== "undefined" && AbortSignal.any) {
        quietInit = Object.assign({}, quietInit, {
          signal: quietInit.signal ? AbortSignal.any([side.signal, quietInit.signal]) : side.signal,
        });
      }
      return originalFetch(input, quietInit);
    }
    return track(originalFetch, input, parsed.init, parsed.flags.optional || isOptionalPath(input));
  }

  function retryLoading() {
    hideOverlay({ restoreFocus: false });
    begin("retry");
    var reload = root.hsOpsReload;
    if (typeof reload === "function") {
      try {
        var result = reload();
        if (result && typeof result.catch === "function") result.catch(function () {});
      } catch (error) {
        /* the generation records the failure */
      }
      return;
    }
    root.location.reload();
  }

  function backToDashboard() {
    if (current && !current.settled) return;
    hideOverlay();
  }

  function buttonsInLayer() {
    if (!layer) return [];
    return Array.prototype.slice.call(layer.querySelectorAll("button"));
  }

  function onLayerKeydown(event) {
    if (!layer || layer.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (event.key !== "Tab") {
      event.stopPropagation();
      return;
    }
    var buttons = buttonsInLayer();
    if (!buttons.length) {
      event.preventDefault();
      event.stopPropagation();
      layer.focus();
      return;
    }
    var first = buttons[0];
    var last = buttons[buttons.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === layer)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === layer)) {
      event.preventDefault();
      first.focus();
    }
    event.stopPropagation();
  }

  function isIgnoredSurface(node) {
    return !!(node && node.closest && node.closest("#dashboardLoading, #overlay, .modal, .goose-panel"));
  }

  function onChange(event) {
    var target = event.target;
    if (!target || isIgnoredSurface(target)) return;
    var tag = target.tagName;
    if (tag === "SELECT") {
      begin("filter");
      return;
    }
    if (tag === "INPUT") {
      var type = (target.getAttribute("type") || "").toLowerCase();
      if (type === "date" || type === "month" || type === "week") begin("filter");
    }
  }

  function onClick(event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var button = target.closest("button");
    if (!button || isIgnoredSurface(button)) return;
    if (button.classList.contains("filter-reset")) {
      begin("refresh");
      return;
    }
    if (button.closest(".global-filterbar, .filter-controls, .filter-chips")) {
      begin("refresh");
      return;
    }
    var text = (button.textContent || "").replace(/\s+/g, " ").trim();
    if (/^refresh\b/i.test(text) || button.id === "refreshAll") begin("refresh");
  }

  function install() {
    ensureLayer();
    ensureSideAbort();
    begin("initial");
    document.addEventListener("change", onChange, true);
    document.addEventListener("click", onClick, true);
    if (typeof root.addEventListener === "function") root.addEventListener("pagehide", function () {
      if (current && !current.settled) {
        current.stale = true;
        clearShowTimer(current);
        try {
          current.controller.abort();
        } catch (error) {
          /* ignore */
        }
      }
      hideOverlay({ restoreFocus: false });
    });
    setTimeout(function () {
      if (current && !current.saw && current.inFlight === 0 && !current.settled && !current.stale) {
        current.settled = true;
      }
    }, 0);
  }

  function background(task) {
    var chip = ensureFreshness();
    chip.hidden = false;
    chip.textContent = "Updating";
    return Promise.resolve()
      .then(task)
      .finally(function () {
        chip.hidden = false;
        chip.textContent = "Updated";
      });
  }

  root.HappySolarLoading = {
    begin: begin,
    fetch: trackedFetch,
    background: background,
    install: install,
    shouldTrack: shouldTrack,
    get committed() {
      return committed;
    },
    get currentId() {
      return current ? current.id : 0;
    },
    get currentGeneration() {
      return current;
    },
    get lastDiagnostic() {
      return lastDiagnostic;
    },
    get layer() {
      return layer;
    },
    SHOW_DELAY_MS: SHOW_DELAY_MS,
    REQUEST_TIMEOUT_MS: REQUEST_TIMEOUT_MS,
  };

  if (document.body) install();
  else document.addEventListener("DOMContentLoaded", install);
})(typeof window !== "undefined" ? window : globalThis);
