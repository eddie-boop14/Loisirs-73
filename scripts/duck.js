/* duck.js — Bleu canard édition easter egg 🦆  (v2)
   Drops ONE duck at a random spot on each page load (1-in-4 it peeks from an edge 👀).
   Click → quack IN THE PAGE LANGUAGE: fr "Coin coin", en "Quack quack", de "Quak quak",
   it "Qua qua", es "¡Cuac cuac!", nl "Kwak kwak" — + a tiny synthesized quack.
   v2 fixes: floats above maps/heroes (z-index) so it shows on hubs & indexes; localized call.
   Decorative, never blocks content, respects reduced-motion, self-disables on protected fiches. */
(function () {
  var BLOCK = ['/chez-nous-a-la-plage', '/chalet-du-tornet'];
  var path = location.pathname || '';
  for (var i = 0; i < BLOCK.length; i++) { if (path.indexOf(BLOCK[i]) !== -1) return; }
  if (window.__bcDuck) return; window.__bcDuck = 1;

  // language: <html lang> first, then URL prefix, default fr
  var lang = (document.documentElement.getAttribute('lang') || '').slice(0, 2).toLowerCase();
  if (!lang) { var m = path.match(/^\/(en|de|it|es|nl|pl|pt|cs|ar|he|ja)(\/|$)/); lang = m ? m[1] : 'fr'; }
  var QUACK = { fr: 'Coin coin\u00A0!', en: 'Quack quack!', de: 'Quak quak!',
                it: 'Qua qua!', es: '\u00A1Cuac cuac!', nl: 'Kwak kwak!',
                pl: 'Kwa kwa!', pt: 'Qu\u00E1 qu\u00E1!', cs: 'Kv\u00E1 kv\u00E1!',
                ar: '\u0643\u0648\u0627\u0643 \u0643\u0648\u0627\u0643!', he: '\u05D2\u05E2 \u05D2\u05E2!', ja: '\u30AC\u30FC\u30AC\u30FC\uFF01' };
  var SAY = QUACK[lang] || QUACK.fr;
  var rtl = (document.documentElement.getAttribute('dir') || '').toLowerCase() === 'rtl';

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', place);
  else place();

  function place() {
    if (document.getElementById('bc-duck')) return;
    var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    var d = document.createElement('button');
    d.id = 'bc-duck'; d.type = 'button';
    d.setAttribute('aria-label', SAY.replace(/[!\u00A1\u00A0]/g, ' ').trim());
    d.title = SAY; d.textContent = '\uD83E\uDD86';
    var s = d.style;
    s.position = 'fixed'; s.zIndex = '9998';   // above Leaflet maps (~400) and heroes
    s.border = '0'; s.background = 'transparent'; s.cursor = 'pointer';
    s.padding = '6px'; s.lineHeight = '1';
    s.fontSize = (18 + Math.random() * 10).toFixed(0) + 'px';
    s.opacity = '0'; s.transition = 'opacity .6s ease, transform .25s ease';
    s.filter = 'drop-shadow(0 1px 2px rgba(0,0,0,.25))';
    s.webkitTapHighlightColor = 'transparent';
    var top = 8 + Math.random() * 80, left = 4 + Math.random() * 88;
    if (Math.random() < 0.25) {
      var edge = Math.floor(Math.random() * 4);
      if (edge === 0) { s.top = '-6px'; s.left = left + '%'; }
      else if (edge === 1) { s.bottom = '-6px'; s.left = left + '%'; }
      else if (edge === 2) { s.left = '-6px'; s.top = top + '%'; }
      else { s.right = '-6px'; s.top = top + '%'; }
    } else { s.top = top + '%'; s.left = left + '%'; }
    d.addEventListener('click', quack);
    document.body.appendChild(d);
    requestAnimationFrame(function () { s.opacity = '0.9'; });

    function quack() {
      if (!reduce) { s.transform = 'rotate(-12deg) scale(1.25)';
        setTimeout(function () { s.transform = ''; }, 220); }
      bubble(SAY);
      try {
        var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
        var c = new AC(), o = c.createOscillator(), g = c.createGain();
        o.type = 'sawtooth';
        o.frequency.setValueAtTime(420, c.currentTime);
        o.frequency.exponentialRampToValueAtTime(180, c.currentTime + 0.18);
        g.gain.setValueAtTime(0.07, c.currentTime);
        g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + 0.2);
        o.connect(g); g.connect(c.destination);
        o.start(); o.stop(c.currentTime + 0.2);
      } catch (e) {}
    }
    function bubble(t) {
      var b = document.createElement('span'); b.textContent = t;
      var r = d.getBoundingClientRect(), bs = b.style;
      bs.position = 'fixed'; bs.zIndex = '9999';
      if (rtl) {           // mirror: anchor the bubble to the duck's right edge
        bs.right = Math.min(window.innerWidth - 90, Math.max(6, window.innerWidth - r.right)) + 'px';
        bs.direction = 'rtl';
      } else {
        bs.left = Math.min(window.innerWidth - 90, Math.max(6, r.left)) + 'px';
      }
      bs.top = Math.max(6, r.top - 26) + 'px';
      bs.background = '#1F6E78'; bs.color = '#fff';
      bs.font = '600 12px -apple-system,system-ui,Segoe UI,Roboto,sans-serif';
      bs.padding = '3px 8px'; bs.borderRadius = '10px'; bs.pointerEvents = 'none';
      bs.transition = 'opacity .8s ease, transform .8s ease';
      document.body.appendChild(b);
      requestAnimationFrame(function () { bs.opacity = '0'; bs.transform = 'translateY(-8px)'; });
      setTimeout(function () { b.remove(); }, 900);
    }
  }
})();
