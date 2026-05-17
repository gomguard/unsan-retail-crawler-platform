(() => {
  const captured = [];
  const matchUrl = (url) =>
    /lowes\.com|lowescdn\.com|digital-bff|LowesSearchServices|getpartialproductlist|getshowmoreproductlist|getdepartmentproductlist|productData|productSpecData|search/i.test(
      String(url || "")
    );
  const bodyToString = (body) => {
    if (body == null) return "";
    if (typeof body === "string") return body;
    try {
      return JSON.stringify(body);
    } catch {
      return String(body);
    }
  };
  const push = (row) => {
    captured.push({
      captured_at: new Date().toISOString(),
      ...row,
    });
    console.log("[LOWES_CAPTURE]", row.method || "", row.status || "", row.url);
  };

  if (!window.__LOWES_CAPTURE_ORIGINAL_FETCH__) {
    window.__LOWES_CAPTURE_ORIGINAL_FETCH__ = window.fetch;
    window.fetch = async function lowesCapturedFetch(input, init = {}) {
      const url = typeof input === "string" ? input : input && input.url;
      const method = init.method || (input && input.method) || "GET";
      const requestBody = bodyToString(init.body || (input && input.body));
      const started = performance.now();
      try {
        const response = await window.__LOWES_CAPTURE_ORIGINAL_FETCH__.apply(this, arguments);
        if (matchUrl(url)) {
          let text = "";
          try {
            text = await response.clone().text();
          } catch {
            text = "";
          }
          push({
            type: "fetch",
            url,
            method,
            status: response.status,
            elapsed_ms: Math.round(performance.now() - started),
            request_body: requestBody,
            response_bytes: text.length,
            response_head: text.slice(0, 1200),
            content_type: response.headers && response.headers.get("content-type"),
          });
        }
        return response;
      } catch (error) {
        if (matchUrl(url)) {
          push({
            type: "fetch",
            url,
            method,
            elapsed_ms: Math.round(performance.now() - started),
            request_body: requestBody,
            error: String(error),
          });
        }
        throw error;
      }
    };
  }

  if (!window.__LOWES_CAPTURE_ORIGINAL_XHR_OPEN__) {
    window.__LOWES_CAPTURE_ORIGINAL_XHR_OPEN__ = XMLHttpRequest.prototype.open;
    window.__LOWES_CAPTURE_ORIGINAL_XHR_SEND__ = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function lowesCapturedOpen(method, url) {
      this.__lowes_capture = { method, url, started: 0, request_body: "" };
      return window.__LOWES_CAPTURE_ORIGINAL_XHR_OPEN__.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function lowesCapturedSend(body) {
      if (this.__lowes_capture) {
        this.__lowes_capture.started = performance.now();
        this.__lowes_capture.request_body = bodyToString(body);
        this.addEventListener("loadend", () => {
          const info = this.__lowes_capture || {};
          if (!matchUrl(info.url)) return;
          const text = typeof this.responseText === "string" ? this.responseText : "";
          push({
            type: "xhr",
            url: info.url,
            method: info.method || "GET",
            status: this.status,
            elapsed_ms: Math.round(performance.now() - info.started),
            request_body: info.request_body,
            response_bytes: text.length,
            response_head: text.slice(0, 1200),
            content_type: this.getResponseHeader("content-type"),
          });
        });
      }
      return window.__LOWES_CAPTURE_ORIGINAL_XHR_SEND__.apply(this, arguments);
    };
  }

  window.__LOWES_CAPTURED__ = captured;
  window.copyLowesCaptured = async () => {
    const text = JSON.stringify(window.__LOWES_CAPTURED__ || [], null, 2);
    await navigator.clipboard.writeText(text);
    console.log(`[LOWES_CAPTURE] copied ${window.__LOWES_CAPTURED__.length} requests`);
  };
  window.downloadLowesCaptured = () => {
    const text = JSON.stringify(window.__LOWES_CAPTURED__ || [], null, 2);
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lowes_network_capture_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  console.log(
    "[LOWES_CAPTURE] ready. Interact with the page, then run copyLowesCaptured() or downloadLowesCaptured()."
  );
})();
