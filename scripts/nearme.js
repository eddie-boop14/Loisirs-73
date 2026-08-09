/* nearme.js — sitewide "◎ Près de moi" proximity finder.
 *
 * One shared component for every page type. The button lives top-right in the
 * site header; on allow it fetches /api/lieux.json, haversine-ranks the whole
 * guide, and renders the nearest lieux into the .near-results mount. On
 * deny / unavailable / timeout it shows an HONEST "off" state — it never fakes
 * a location (the old homepage code silently substituted Annecy).
 *
 * Localised labels are read from data-* attributes on the button, so no inline
 * strings are needed per page. Self-contained, no deps.
 */
(function () {
  "use strict";
  var btn = document.getElementById("nearMe");
  if (!btn) return;

  // self-inject styles once (var fallbacks → works on every page type)
  if (!document.getElementById("nearme-css")) {
    var st = document.createElement("style");
    st.id = "nearme-css";
    st.textContent =
      ".near-me{font:600 .8rem var(--sans,system-ui,sans-serif);display:inline-flex;align-items:center;gap:.3rem;background:transparent;color:var(--ink-mute,#6a727d);border:1px solid var(--line,#e3e3dc);border-radius:999px;padding:.4rem .8rem;cursor:pointer;white-space:nowrap;transition:color .15s,border-color .15s,background .15s}" +
      ".near-me:hover{color:var(--ink,#0b0d10);border-color:var(--ink-mute,#6a727d)}" +
      ".near-me.on{background:var(--accent,#0a5a3a);color:#fff;border-color:var(--accent,#0a5a3a)}" +
      ".near-results{padding:1.1rem 0 .25rem;border-bottom:1px solid var(--line,#e3e3dc)}" +
      ".near-results .wrap{max-width:64rem;margin-inline:auto;padding-inline:clamp(1rem,3vw,2rem)}" +
      ".near-results-head{margin-bottom:1rem}" +
      ".near-results-head h2{font:600 1.1rem var(--sans,system-ui,sans-serif);margin:0;color:var(--ink,#0b0d10)}" +
      ".near-results-head p{font:400 .8rem var(--sans,system-ui,sans-serif);margin:.15rem 0 0;color:var(--ink-mute,#6a727d)}" +
      ".near-results-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.75rem}" +
      ".near-card{display:flex;flex-direction:column;background:var(--surface,#fff);border:1px solid var(--line,#e3e3dc);border-radius:10px;overflow:hidden;text-decoration:none;color:inherit;transition:transform .15s,box-shadow .15s}" +
      ".near-card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.08)}" +
      ".near-card img{width:100%;height:110px;object-fit:cover;display:block}" +
      ".near-card-noimg{height:54px;background:var(--surface-2,#f3f3ee)}" +
      ".near-card-body{padding:.6rem .7rem .75rem;display:flex;flex-direction:column;gap:.2rem}" +
      ".near-card-body strong{font:600 .85rem var(--sans,system-ui,sans-serif);color:var(--ink,#0b0d10);line-height:1.25}" +
      ".near-meta{font:400 .7rem var(--sans,system-ui,sans-serif);color:var(--ink-mute,#6a727d)}" +
      ".near-cta{font:600 .68rem var(--sans,system-ui,sans-serif);color:var(--accent,#0a5a3a);margin-top:.15rem;text-transform:uppercase;letter-spacing:.06em}";
    document.head.appendChild(st);
  }

  var L = {
    def: btn.getAttribute("data-default") || "◎ Près de moi",
    loading: btn.getAttribute("data-loading") || "…",
    on: btn.getAttribute("data-on") || "◎ À proximité",
    off: btn.getAttribute("data-off") || "Localisation indisponible",
    title: btn.getAttribute("data-results-title") || "À proximité",
    sub: btn.getAttribute("data-results-sub") || "",
    cta: btn.getAttribute("data-cta") || "Voir",
    km: btn.getAttribute("data-km") || "km",
    empty: btn.getAttribute("data-empty") || "—",
  };
  var TOP = 12;
  var origin = null;
  var DATA = null;

  function mount() {
    var m = document.getElementById("nearResults");
    if (m) return m;
    m = document.createElement("section");
    m.id = "nearResults";
    m.className = "near-results";
    m.setAttribute("aria-live", "polite");
    var hdr = document.querySelector("header.site");
    if (hdr && hdr.parentNode) hdr.parentNode.insertBefore(m, hdr.nextSibling);
    else document.body.insertBefore(m, document.body.firstChild);
    return m;
  }

  function distKm(la1, lo1, la2, lo2) {
    var R = 6371, p = Math.PI / 180;
    var dLa = (la2 - la1) * p, dLo = (lo2 - lo1) * p;
    var a = Math.sin(dLa / 2) * Math.sin(dLa / 2) +
            Math.cos(la1 * p) * Math.cos(la2 * p) * Math.sin(dLo / 2) * Math.sin(dLo / 2);
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  function lat(r) { return r.latitude != null ? r.latitude : r.lat; }
  function lng(r) { return r.longitude != null ? r.longitude : (r.lng != null ? r.lng : r.lon); }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function langPrefix() {
    var m = location.pathname.match(/^\/(en|de|it|es|nl)\//);
    return m ? "/" + m[1] : "";
  }

  function render() {
    var box = mount();
    if (!origin || !DATA) { box.innerHTML = ""; return; }
    var pre = langPrefix();
    var ranked = DATA
      .filter(function (r) { return lat(r) != null && lng(r) != null; })
      .map(function (r) { return { r: r, d: distKm(origin.lat, origin.lng, lat(r), lng(r)) }; })
      .sort(function (a, b) { return a.d - b.d; })
      .slice(0, TOP);
    var cards = ranked.map(function (x) {
      var r = x.r, d = x.d;
      var dist = d < 1 ? Math.round(d * 1000) + " m" : d.toFixed(1) + " " + L.km;
      var href = "__SITE_ORIGIN__" + pre + "/" + r.slug;
      var photo = r.photo
        ? '<img src="' + esc(r.photo) + '" alt="" loading="lazy" decoding="async">'
        : '<div class="near-card-noimg"></div>';
      return '<a class="near-card" href="' + esc(href) + '">' + photo +
        '<div class="near-card-body"><strong>' + esc(r.name || r.slug) + "</strong>" +
        '<span class="near-meta">' + esc(r.commune || "") + " · " + dist + "</span>" +
        '<span class="near-cta">' + esc(L.cta) + " →</span></div></a>";
    }).join("");
    box.innerHTML =
      '<div class="wrap"><div class="near-results-head"><h2>' + esc(L.title) + "</h2>" +
      (L.sub ? "<p>" + esc(L.sub) + "</p>" : "") + "</div>" +
      '<div class="near-results-grid">' + (cards || esc(L.empty)) + "</div></div>";
  }

  function load(cb) {
    if (DATA) { cb(); return; }
    fetch("/api/lieux.json").then(function (r) { return r.json(); }).then(function (j) {
      DATA = Array.isArray(j) ? j : (j && j.lieux) || [];
      cb();
    }).catch(function () { DATA = []; cb(); });
  }

  function reset() {
    origin = null;
    btn.classList.remove("on");
    btn.textContent = L.def;
    var m = document.getElementById("nearResults");
    if (m) m.innerHTML = "";
  }

  function off() {
    origin = null;
    btn.classList.remove("on");
    btn.textContent = L.off;        // HONEST: no fake location, no results
    var m = document.getElementById("nearResults");
    if (m) m.innerHTML = "";
  }

  btn.addEventListener("click", function () {
    if (origin) { reset(); return; }
    if (!navigator.geolocation) { off(); return; }
    btn.textContent = L.loading;
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        origin = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        btn.classList.add("on");
        btn.textContent = L.on;
        load(render);
      },
      function () { off(); },           // deny / unavailable / timeout → honest off
      { timeout: 8000, maximumAge: 60000 }
    );
  });
})();
