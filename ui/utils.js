/* Kali Linux Windows Substitute - Shared UI Utilities
 * DOM helpers, toast messages and the API client
 */
"use strict";

/* --- DOM Helpers -------------------------------------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// Durations in ms, shown as "350 ms" or "2.4 s".
function formatDuration(ms) {
  if (!ms) return "—";
  return ms < 1000 ? Math.round(ms) + " ms" : (ms / 1000).toFixed(1) + " s";
}

// Server timestamps are UTC, stored as "YYYY-MM-DD HH:MM:SS" (or ISO); a missing zone is treated as UTC.
function formatWhen(text) {
  if (!text) return "—";
  let s = String(text).trim().replace(" ", "T");
  if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(s)) s += "Z";
  const d = new Date(s);
  return isNaN(d) ? String(text) : d.toLocaleString();
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

let toastTimer = null;
function toast(message, isError) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("error", !!isError);
  el.classList.remove("hidden");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.add("hidden");
    toastTimer = null;
  }, 4500);
}

/* --- API Helper --------------------------------------------------------- */
// Per-request configuration
const API_CONFIG = {
  timeout: 10000,
  retries: 2,
  retryDelay: 1000,
};

function getApiBase() {
  // Use the same origin as the page (backend serves on loopback)
  return window.location.origin;
}

// Always resolves with { ok, status, data }. HTTP errors carry the server's status
// and body; network failures use status 0 and timeouts use 408, both with data.error.
// Callers can check `ok` / `data.error` and never need a try/catch.
async function api(method, path, body, options = {}) {
  // Default 10 s so quick calls never hang. Long operations (tool runs, installs)
  // pass { timeout: <ms> } or { timeout: 0 } for no limit and use a Stop button.
  const timeoutMs = options.timeout !== undefined ? options.timeout : API_CONFIG.timeout;
  const controller = new AbortController();
  const timeoutId = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;
  // Only idempotent reads are retried: replaying a POST could run a scan twice.
  const maxRetries = method === "GET" ? API_CONFIG.retries : 0;

  // If the caller also supplies a signal (e.g. a Stop button), abort on either.
  const callerSignal = options.signal;
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort(callerSignal.reason);
    else callerSignal.addEventListener("abort", () => controller.abort(callerSignal.reason), { once: true });
  }

  const opts = {
    method,
    credentials: 'include',
    headers: {},
    signal: controller.signal
  };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (method !== "GET") opts.headers["X-KWS-CSRF"] = csrf();

  // Build full URL - resolve relative paths against current origin
  const url = path.startsWith("http") ? path : getApiBase() + path;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const resp = await fetch(url, opts);
      clearTimeout(timeoutId);

      const text = await resp.text();
      let data;
      try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { raw: text }; }
      if (!resp.ok && !data.error) data.error = "request failed (" + resp.status + ")";
      return { ok: resp.ok, status: resp.status, data, attempt };
    } catch (err) {
      clearTimeout(timeoutId);

      if (err.name === "AbortError") {
        // Distinguish our timeout from a caller-initiated cancellation.
        if (callerSignal && callerSignal.aborted) {
          return { ok: false, status: 0, data: { error: "Request cancelled" }, attempt };
        }
        return { ok: false, status: 408, data: { error: "Request timeout (" + timeoutMs + "ms)" }, attempt };
      }

      // Network error - retry if we have attempts left
      if (attempt < maxRetries && navigator.onLine) {
        await new Promise(r => setTimeout(r, API_CONFIG.retryDelay * (attempt + 1)));
        continue;
      }
      return { ok: false, status: 0, data: { error: "Network error: " + err.message }, attempt };
    }
  }
}

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)(kws_csrf(?:_\d+)?)=([^;]+)/);
  return m ? decodeURIComponent(m[2]) : "";
}

/* --- Export utilities --------------------------------------------------- */
/* Global exports for script tags */
if (typeof window !== "undefined") {
  window.$ = $;
  window.$$ = $$;
  window.esc = esc;
  window.formatDuration = formatDuration;
  window.formatWhen = formatWhen;
  window.toast = toast;
  window.api = api;
  window.csrf = csrf;
}
