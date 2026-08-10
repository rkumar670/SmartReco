const authenticated = document.body.dataset.authenticated === "true";
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const queue = [];
const sessionId = sessionStorage.smartrecoSession || crypto.randomUUID();
sessionStorage.smartrecoSession = sessionId;

function track(eventType, values = {}) {
  if (!authenticated) return;
  queue.push({ event_id: crypto.randomUUID(), event_type: eventType, session_id: sessionId, ...values });
  if (queue.length >= 10) flush();
}

function flush() {
  if (!queue.length) return;
  const events = queue.splice(0, 100);
  fetch("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ events }),
    keepalive: true,
  }).catch(() => queue.unshift(...events));
}

document.querySelectorAll("[data-track]").forEach((element) => {
  element.addEventListener("click", () => {
    const values = {};
    if (element.dataset.productId) values.product_id = Number(element.dataset.productId);
    if (element.dataset.category) values.category = element.dataset.category;
    track(element.dataset.track, values);
    flush();
  });
});

const detail = document.querySelector("[data-product-id].product-detail");
if (detail) {
  const productId = Number(detail.dataset.productId);
  track("product_view", { product_id: productId, category: detail.dataset.category });
  const startedAt = Date.now();
  window.addEventListener("pagehide", () => {
    track("time_spent", {
      product_id: productId,
      category: detail.dataset.category,
      metadata: { seconds: Math.round((Date.now() - startedAt) / 1000) },
    });
    flush();
  });
}

const search = document.querySelector("[data-track-search]");
if (search) {
  search.addEventListener("submit", () => {
    const query = new FormData(search).get("q")?.trim();
    if (query) track("search", { search_query: query });
    flush();
  });
}

if (document.querySelector("[data-recommendation-id]")) {
  track("recommendation_impression");
}

const renderedRecommendation = document.querySelector("[data-recommendation-id]");
const renderedRecommendationId = Number(renderedRecommendation?.dataset.recommendationId || 0);
const isHomePage = window.location.pathname === "/";

if (authenticated && isHomePage) {
  setInterval(async () => {
    try {
      const response = await fetch("/api/recommendations/latest");
      if (!response.ok) return;
      const latest = await response.json();
      if (latest.id && latest.id !== renderedRecommendationId) window.location.reload();
    } catch (_) {
      // A later poll will retry transient failures.
    }
  }, 4000);
}

setInterval(flush, 5000);

