/* ============================================================
   moteur de tri
   météo (cadre) → catégorie (groupe) → lieu (ordre)
   Couche horaires : CÂBLÉE MAIS DORMANTE.
   Une fiche sans `horaires` ne montre aucun badge ouvert/fermé.
   Une fiche AVEC `horaires` l'active automatiquement. Zéro refonte.
   ============================================================ */
(function (global) {
  'use strict';

  // ---- catégorie → type météo (écrit une fois) ----------------
  var TYPE = {
    lac:'out', plage:'out', cascade:'out', 'point-de-vue':'out',
    'voie-verte':'out', sentier:'out', telecabine:'out', 'base-de-loisirs':'out', domaine:'out', parc:'out',
    escape:'in', laser:'in', bowling:'in', patinoire:'in', aquatique:'in',
    spa:'in', trampoline:'in', 'soft-play':'in', science:'in', musee:'in', casino:'in',
    chateau:'mix', attraction:'mix', divers:'mix',
    karting:'mix' // certains indoor, certains plein air → flag par fiche `outdoor:true`
  };

  // ---- 4 zones (bounding boxes) -------------------------------
  var ZONES = [
    { id:'annecy',    nom:'Bassin annécien',  lat:[45.75,45.95], lng:[6.05,6.30] },
    { id:'chablais',  nom:'Chablais / Léman',  lat:[46.30,46.45], lng:[6.30,6.80] },
    { id:'montblanc', nom:'Mont-Blanc / Arve', lat:[45.85,46.05], lng:[6.60,7.05] },
    { id:'genevois',  nom:'Genevois',          lat:[46.05,46.25], lng:[6.05,6.45] }
  ];

  function zoneOf(lat, lng) {
    for (var i = 0; i < ZONES.length; i++) {
      var z = ZONES[i];
      if (lat >= z.lat[0] && lat <= z.lat[1] && lng >= z.lng[0] && lng <= z.lng[1]) return z;
    }
    // fallback : zone dont le centre est le plus proche
    var best = null, bd = Infinity;
    for (var j = 0; j < ZONES.length; j++) {
      var c = ZONES[j], cl = (c.lat[0]+c.lat[1])/2, cg = (c.lng[0]+c.lng[1])/2;
      var d = (lat-cl)*(lat-cl) + (lng-cg)*(lng-cg);
      if (d < bd) { bd = d; best = c; }
    }
    return best;
  }

  function typeOf(fiche) {
    var cats = fiche.categories || [];
    // karting plein air explicite
    if (cats.indexOf('karting') !== -1 && fiche.outdoor === true) return 'out';
    for (var i = 0; i < cats.length; i++) {
      var t = TYPE[cats[i]];
      if (t === 'in') return 'in';
      if (t === 'out') return 'out';
    }
    return 'mix';
  }

  // ---- distance (Haversine, km) -------------------------------
  function distKm(a1, o1, a2, o2) {
    var R = 6371, dLa = (a2-a1)*Math.PI/180, dLo = (o2-o1)*Math.PI/180;
    var s = Math.sin(dLa/2)*Math.sin(dLa/2) +
            Math.cos(a1*Math.PI/180)*Math.cos(a2*Math.PI/180)*Math.sin(dLo/2)*Math.sin(dLo/2);
    return Math.round(R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1-s)));
  }

  // ---- COUCHE HORAIRES (dormante tant que `horaires` absent) --
  // format attendu :
  //   horaires: { lun:[["10:00","19:00"]], mar:[...], ... , dim:[...] }
  //   jour absent ou [] = fermé ce jour
  var JOURS = ['dim','lun','mar','mer','jeu','ven','sam']; // getDay() 0=dim
  function statutHoraire(fiche, now) {
    if (!fiche.horaires) return null;           // <-- dormant : aucune donnée, aucun badge
    if (fiche.saisonnier === true && fiche.horaires.__hors_saison === true) {
      return { ouvert:false, texte:'saisonnier' };
    }
    now = now || new Date();
    var creneaux = fiche.horaires[JOURS[now.getDay()]];
    if (!creneaux || !creneaux.length) return { ouvert:false, texte:'fermé aujourd\u2019hui' };
    var mins = now.getHours()*60 + now.getMinutes();
    for (var i = 0; i < creneaux.length; i++) {
      var o = hhmm(creneaux[i][0]), f = hhmm(creneaux[i][1]);
      if (mins >= o && mins < f) {
        var reste = f - mins;
        return { ouvert:true, texte: reste <= 60 ? 'ferme bientôt' : 'ferme à ' + creneaux[i][1] };
      }
      if (mins < o) return { ouvert:false, texte:'ouvre à ' + creneaux[i][0] };
    }
    return { ouvert:false, texte:'fermé' };
  }
  function hhmm(s){ var p = s.split(':'); return (+p[0])*60 + (+p[1]); }

  // ---- TRI PRINCIPAL ------------------------------------------
  // opts : { weather:0..1, origin:{lat,lng}|null, now:Date|null }
  function trier(fiches, opts) {
    opts = opts || {};
    var w = opts.weather == null ? 0 : opts.weather;
    var origin = opts.origin || null;
    var now = opts.now || new Date();
    var veutIndoor = w >= 0.5;

    var enrichies = fiches.map(function (f) {
      var ty = typeOf(f);
      var z  = (f.lat != null && f.lng != null) ? zoneOf(f.lat, f.lng) : null;
      var d  = (origin && f.lat != null) ? distKm(origin.lat, origin.lng, f.lat, f.lng) : null;
      var st = statutHoraire(f, now);   // null = couche dormante
      return {
        fiche: f, type: ty,
        zone: z ? z.id : null, zoneNom: z ? z.nom : null,
        distance: d, statut: st,
        // pertinence météo : indoor demandé → indoor d'abord ; sinon outdoor d'abord ; mix toujours ok
        pertinent: ty === 'mix' || (veutIndoor ? ty === 'in' : ty === 'out')
      };
    });

    enrichies.sort(function (a, b) {
      // 1. pertinence météo
      if (a.pertinent !== b.pertinent) return a.pertinent ? -1 : 1;
      // 2. ouvert avant fermé (seulement si la donnée existe des deux côtés)
      var ao = a.statut ? (a.statut.ouvert ? 0 : 1) : 0.5;
      var bo = b.statut ? (b.statut.ouvert ? 0 : 1) : 0.5;
      if (ao !== bo) return ao - bo;
      // 3. proximité si géoloc
      if (a.distance != null && b.distance != null && a.distance !== b.distance)
        return a.distance - b.distance;
      // 4. sinon ordre stable d'origine
      return 0;
    });

    return enrichies;
  }

  // ---- regroupement par catégorie (pour les carrousels) -------
  function grouper(enrichies, ordreCategories) {
    var buckets = {};
    enrichies.forEach(function (e) {
      (e.fiche.categories || ['divers']).forEach(function (c) {
        (buckets[c] = buckets[c] || []).push(e);
      });
    });
    if (!ordreCategories) return buckets;
    var out = [];
    ordreCategories.forEach(function (c) { if (buckets[c]) out.push({ categorie:c, lieux:buckets[c] }); });
    return out;
  }

  global.L74 = { trier:trier, grouper:grouper, zoneOf:zoneOf, typeOf:typeOf, distKm:distKm, statutHoraire:statutHoraire, ZONES:ZONES };
})(window);
