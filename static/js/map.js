/* ── Laborsuche DACH – map.js ──────────────────────────────────────────────
   Single-file vanilla JS. No framework needed.
   Depends on: Leaflet, Leaflet.markercluster (loaded via CDN in index.html)
─────────────────────────────────────────────────────────────────────────── */

"use strict";

// ── Constants ─────────────────────────────────────────────────────────────
const API_BASE = "/api/v1";

const COLORS = {
  dexa:      "#3b82f6",
  blood_lab: "#ef4444",
  both:      "#8b5cf6",
};

const ICONS = {
  dexa:      "🔬",
  blood_lab: "🩸",
  both:      "⚕️",
};

const SERVICE_LABELS = {
  body_composition:   "Body Composition",
  bone_density:       "Knochendichte",
  blood_test_self_pay:"Bluttest (Selbstzahler)",
};

const CATEGORY_LABELS = {
  dexa:      "DEXA Body Scan",
  blood_lab: "Blutlabor",
  both:      "DEXA + Blutlabor",
};

// ── State ─────────────────────────────────────────────────────────────────
let allProviders  = [];
let activeMarkers = {};   // id → L.Marker
let clusterGroup  = null;
let map           = null;

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initMap();
  bindUI();
  fetchAndRender();
});

function initMap() {
  map = L.map("map", {
    center: [51.1657, 10.4515],   // geographic centre of Germany
    zoom: 6,
    zoomControl: true,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map);

  clusterGroup = L.markerClusterGroup({
    maxClusterRadius: 50,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
    zoomToBoundsOnClick: true,
  });
  map.addLayer(clusterGroup);
}

// ── Data fetching ─────────────────────────────────────────────────────────
async function fetchAndRender() {
  const params = buildQueryParams();
  try {
    const [provRes, statsRes] = await Promise.all([
      fetch(`${API_BASE}/providers?${params}`),
      fetch(`${API_BASE}/stats`),
    ]);
    const { providers } = await provRes.json();
    const stats         = await statsRes.json();

    allProviders = providers;
    renderStats(stats, providers.length);
    renderMarkers(providers);
    renderList(providers);
  } catch (err) {
    console.error("Fetch error:", err);
    document.getElementById("resultsList").innerHTML =
      `<div class="empty-state">⚠️ Fehler beim Laden der Daten.</div>`;
  }
}

function buildQueryParams() {
  const p = new URLSearchParams();

  const category = document.querySelector('input[name="category"]:checked')?.value;
  if (category && category !== "all") p.set("category", category);

  const countries = [...document.querySelectorAll('input[name="country"]:checked')]
    .map(el => el.value);
  // API doesn't support multi-country in one call, so we filter client-side
  // (keeping country param for single selection UX if needed)

  if (document.getElementById("verifiedOnly").checked) p.set("verified", "true");

  const q = document.getElementById("searchInput").value.trim();
  if (q) p.set("q", q);

  return p.toString();
}

// ── Markers ───────────────────────────────────────────────────────────────
function renderMarkers(providers) {
  clusterGroup.clearLayers();
  activeMarkers = {};

  // Apply client-side service & country filters
  const filtered = applyClientFilters(providers);

  filtered.forEach(p => {
    if (!p.coordinates?.lat || !p.coordinates?.lng) return;

    const icon = makeIcon(p.category);
    const marker = L.marker([p.coordinates.lat, p.coordinates.lng], { icon })
      .on("click", () => openDetail(p));

    marker.bindTooltip(`<strong>${p.name}</strong><br>${p.address.city}`, {
      direction: "top",
      offset: [0, -30],
    });

    activeMarkers[p.id] = marker;
    clusterGroup.addLayer(marker);
  });
}

function makeIcon(category) {
  const color = COLORS[category] || COLORS.dexa;
  const emoji = ICONS[category]  || "📍";
  const html  = `
    <div class="marker-icon marker-icon--${category}">
      <span>${emoji}</span>
    </div>`;
  return L.divIcon({
    html,
    className: "",
    iconSize:  [32, 32],
    iconAnchor:[16, 32],
    popupAnchor:[0, -34],
  });
}

// ── Results list ──────────────────────────────────────────────────────────
function renderList(providers) {
  const filtered = applyClientFilters(providers);
  const el       = document.getElementById("resultsList");

  if (filtered.length === 0) {
    el.innerHTML = `<div class="empty-state">Keine Anbieter gefunden.<br>Filter anpassen?</div>`;
    return;
  }

  el.innerHTML = filtered.map(p => `
    <div class="result-item" data-id="${p.id}">
      <div class="result-item__name">${escHtml(p.name)}</div>
      <div class="result-item__meta">
        <span class="badge badge--${p.category}">${CATEGORY_LABELS[p.category]}</span>
        <span>${escHtml(p.address.city)} &middot; ${p.address.country}</span>
        ${p.verified ? `<span class="badge badge--verified">✓</span>` : ""}
      </div>
    </div>
  `).join("");

  el.querySelectorAll(".result-item").forEach(item => {
    item.addEventListener("click", () => {
      const provider = filtered.find(p => p.id === item.dataset.id);
      if (!provider) return;
      openDetail(provider);
      flyTo(provider);
    });
  });
}

// ── Stats ─────────────────────────────────────────────────────────────────
function renderStats(stats, shownCount) {
  document.getElementById("statsBar").innerHTML =
    `${shownCount} von ${stats.total} Anbietern &middot; ` +
    `${stats.dexa} DEXA &middot; ${stats.blood_lab} Labor &middot; ` +
    `${stats.verified} verifiziert`;
}

// ── Client-side filters ───────────────────────────────────────────────────
function applyClientFilters(providers) {
  const selectedCountries = [...document.querySelectorAll('input[name="country"]:checked')]
    .map(el => el.value);

  const selectedServices = [...document.querySelectorAll('input[name="service"]:checked')]
    .map(el => el.value);

  return providers.filter(p => {
    if (!selectedCountries.includes(p.address.country)) return false;
    if (selectedServices.length > 0) {
      const hasAll = selectedServices.every(s => p.services.includes(s));
      if (!hasAll) return false;
    }
    return true;
  });
}

// ── Detail Panel ──────────────────────────────────────────────────────────
function openDetail(provider) {
  const panel   = document.getElementById("detailPanel");
  const overlay = document.getElementById("detailOverlay");
  const content = document.getElementById("detailContent");

  content.innerHTML = buildDetailHTML(provider);
  panel.classList.add("is-open");
  overlay.classList.add("is-open");

  flyTo(provider);
}

function closeDetail() {
  document.getElementById("detailPanel").classList.remove("is-open");
  document.getElementById("detailOverlay").classList.remove("is-open");
}

function buildDetailHTML(p) {
  const prices = p.prices || {};
  const hasPrices = Object.values(prices).some(v => v);

  const priceRows = [
    ["DEXA Body Composition", prices.dexa_body_composition],
    ["Knochendichte",         prices.bone_density],
    ["Bluttest",              prices.blood_test],
  ]
    .filter(([, v]) => v)
    .map(([k, v]) => `<tr><td>${k}</td><td><strong>${escHtml(v)}</strong></td></tr>`)
    .join("");

  const serviceTags = (p.services || [])
    .map(s => `<span class="service-tag">${SERVICE_LABELS[s] || s}</span>`)
    .join("");

  return `
    <div class="detail__category-badge">
      <span class="badge badge--${p.category}">${CATEGORY_LABELS[p.category]}</span>
      ${p.verified ? `<span class="badge badge--verified" style="margin-left:6px">✓ Verifiziert</span>` : ""}
    </div>

    <h2 class="detail__name">${escHtml(p.name)}</h2>
    <p class="detail__address">
      ${escHtml(p.address.street)}<br>
      ${escHtml(p.address.zip)} ${escHtml(p.address.city)}, ${p.address.country}
    </p>

    ${serviceTags ? `
    <div class="detail__section">
      <div class="detail__section-title">Leistungen</div>
      ${serviceTags}
    </div>` : ""}

    ${hasPrices ? `
    <div class="detail__section">
      <div class="detail__section-title">Preise</div>
      <table class="price-table">${priceRows}</table>
    </div>` : ""}

    <div class="detail__section detail__contact">
      <div class="detail__section-title">Kontakt</div>
      ${p.contact.phone ? `<p>📞 <a href="tel:${p.contact.phone}">${escHtml(p.contact.phone)}</a></p>` : ""}
      ${p.contact.email ? `<p>✉️ <a href="mailto:${p.contact.email}">${escHtml(p.contact.email)}</a></p>` : ""}
      ${p.contact.website
        ? `<p>🌐 <a href="${p.contact.website}" target="_blank" rel="noopener">${escHtml(p.contact.website.replace(/^https?:\/\//, ""))}</a></p>`
        : ""}
    </div>

    ${p.notes ? `
    <div class="detail__section">
      <div class="detail__section-title">Hinweise</div>
      <div class="detail__notes">${escHtml(p.notes)}</div>
    </div>` : ""}

    ${p.verified ? `
    <div class="detail__verified">
      ✅ Zuletzt verifiziert: ${p.last_verified || "–"}
      ${p.source ? ` &middot; Quelle: ${escHtml(p.source)}` : ""}
    </div>` : ""}
  `;
}

function flyTo(provider) {
  if (!provider.coordinates?.lat) return;
  map.flyTo([provider.coordinates.lat, provider.coordinates.lng], 14, {
    animate: true,
    duration: 0.8,
  });
  const marker = activeMarkers[provider.id];
  if (marker) {
    setTimeout(() => {
      if (!clusterGroup.hasLayer(marker)) {
        clusterGroup.zoomToShowLayer(marker, () => marker.openTooltip());
      } else {
        marker.openTooltip();
      }
    }, 900);
  }
}

// ── UI Bindings ───────────────────────────────────────────────────────────
function bindUI() {
  // Filter changes → re-fetch + re-render
  document.querySelectorAll('input[name="category"]').forEach(el => {
    el.addEventListener("change", fetchAndRender);
  });
  document.querySelectorAll('input[name="country"]').forEach(el => {
    el.addEventListener("change", () => {
      renderMarkers(allProviders);
      renderList(allProviders);
    });
  });
  document.querySelectorAll('input[name="service"]').forEach(el => {
    el.addEventListener("change", () => {
      renderMarkers(allProviders);
      renderList(allProviders);
    });
  });
  document.getElementById("verifiedOnly").addEventListener("change", fetchAndRender);

  // Search (debounced)
  let searchTimer;
  document.getElementById("searchInput").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fetchAndRender, 350);
  });

  // Reset
  document.getElementById("resetFilters").addEventListener("click", () => {
    document.querySelector('input[name="category"][value="all"]').checked = true;
    document.querySelectorAll('input[name="country"]').forEach(el => el.checked = true);
    document.querySelectorAll('input[name="service"]').forEach(el => el.checked = false);
    document.getElementById("verifiedOnly").checked = false;
    document.getElementById("searchInput").value = "";
    fetchAndRender();
  });

  // Detail panel close
  document.getElementById("closeDetail").addEventListener("click", closeDetail);
  document.getElementById("detailOverlay").addEventListener("click", closeDetail);

  // Mobile sidebar toggle
  document.getElementById("sidebarToggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("is-open");
  });
}

// ── Util ──────────────────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
