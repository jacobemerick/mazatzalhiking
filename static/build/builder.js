/* Route builder v1 (#21).
 *
 * A route is an ordered list of legs, each a segment walked in one direction.
 * The only rule: a leg must start where the previous one ended. Nothing is
 * pathfound; the shape of the route is whatever gets clicked.
 *
 * Data comes from public/data/, emitted by tools/build_site.py:
 *   graph.json        topology and per-leg stats, loaded once
 *   display.json      simplified lines for drawing, loaded once
 *   observations.json dated condition notes, loaded once
 *   geometry/<id>     full-resolution line, fetched per leg only at export
 *
 * The route lives in the URL as ?r=<leg>.<leg>.<leg>, where each leg is a
 * segment id optionally prefixed with '-' when walked to -> from. Flags are
 * optional on input (direction is inferred from connectivity, so a trail page
 * can link with bare ids) and always written on output. */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var M2FT = 3.28084;

  var G = null;          // { trails, nodes, segments } as id -> object, plus raw
  var OBS = {};          // Conditions.index(observations.json)
  var LINES = {};        // segment id -> L.Polyline (visible)
  var HITS = {};         // segment id -> L.Polyline (wide, invisible, takes the click)
  var NODE_MARKS = {};   // node id -> L.CircleMarker
  var route = [];        // [{ id, rev }]
  var map, geomCache = {};

  /* ---------------------------------------------------------------- data */

  function load() {
    return Promise.all([
      fetch('/data/graph.json').then(function (r) { return r.json(); }),
      fetch('/data/display.json').then(function (r) { return r.json(); }),
      fetch('/data/observations.json').then(function (r) { return r.json(); })
    ]).then(function (res) {
      var g = res[0];
      G = { raw: g, trails: {}, nodes: {}, segments: {}, retired: {}, display: res[1].segments, touching: {} };
      g.trails.forEach(function (t) { G.trails[t.id] = t; });
      g.nodes.forEach(function (n) { G.nodes[n.id] = n; });
      g.segments.forEach(function (s) {
        G.segments[s.id] = s;
        (G.touching[s.from] = G.touching[s.from] || []).push(s.id);
        if (s.to !== s.from) (G.touching[s.to] = G.touching[s.to] || []).push(s.id);
      });
      (g.retired || []).forEach(function (r) { G.retired[r.id] = r; });
      OBS = Conditions.index(res[2]);
    });
  }

  /* ---------------------------------------------------------------- route model */

  function legStart(leg) { var s = G.segments[leg.id]; return leg.rev ? s.to : s.from; }
  function legEnd(leg) { var s = G.segments[leg.id]; return leg.rev ? s.from : s.to; }
  function legGain(leg) { var s = G.segments[leg.id]; return leg.rev ? s.loss_ft : s.gain_ft; }
  function legLoss(leg) { var s = G.segments[leg.id]; return leg.rev ? s.gain_ft : s.loss_ft; }
  function tail() { return route.length ? legEnd(route[route.length - 1]) : null; }

  /* Which segments may be clicked next. Empty route: any. One leg: anything touching
   * either end, because the first leg's direction is not fixed until the second
   * click. Otherwise: anything touching the tail, including the leg just walked
   * (that is how an out-and-back is built). */
  function candidates() {
    if (!route.length) return null;                       // null = all
    var set = {};
    if (route.length === 1) {
      var s = G.segments[route[0].id];
      (G.touching[s.from] || []).concat(G.touching[s.to] || []).forEach(function (id) { set[id] = true; });
    } else {
      (G.touching[tail()] || []).forEach(function (id) { set[id] = true; });
    }
    return set;
  }

  function directionFrom(node, id) {
    var s = G.segments[id];
    return s.from === node ? false : s.to === node ? true : null;
  }

  function add(id) {
    var s = G.segments[id];
    if (!s) return false;
    if (!route.length) { route.push({ id: id, rev: false }); return true; }
    if (route.length === 1) {
      var first = G.segments[route[0].id];
      // prefer continuing from the first leg's `to`; otherwise flip the first leg
      var d = directionFrom(first.to, id);
      if (d === null) {
        d = directionFrom(first.from, id);
        if (d === null) return false;
        route[0].rev = true;
      }
      route.push({ id: id, rev: d });
      return true;
    }
    var dir = directionFrom(tail(), id);
    if (dir === null) return false;
    route.push({ id: id, rev: dir });
    return true;
  }

  function totals() {
    var mi = 0, gain = 0, loss = 0;
    route.forEach(function (l) { mi += G.segments[l.id].miles; gain += legGain(l); loss += legLoss(l); });
    return { miles: mi, gain: gain, loss: loss };
  }

  /* ---------------------------------------------------------------- url */

  function encode() {
    return route.map(function (l) { return (l.rev ? '-' : '') + l.id; }).join('.');
  }

  /* Returns { legs, problem }. Direction flags are honoured when present and
   * inferred from connectivity when absent; the first leg without a flag is
   * oriented to meet the second. Stops at the first leg that cannot connect. */
  function decode(str) {
    var out = [], problem = null;
    var toks = (str || '').split('.').filter(Boolean);
    for (var i = 0; i < toks.length; i++) {
      var flagged = toks[i][0] === '-', id = flagged ? toks[i].slice(1) : toks[i];
      var s = G.segments[id];
      if (!s) {
        var r = G.retired[id];
        problem = r ? 'Leg ' + (i + 1) + ' of the shared route (' + id + ') was split into ' + (r.superseded_by || []).join(' and ') + ' on ' + r.on + ' (' + r.reason + '). The route is loaded up to that point.'
                    : 'Leg ' + (i + 1) + ' of the shared route (' + id + ') does not exist. The route is loaded up to that point.';
        break;
      }
      if (!out.length) { out.push({ id: id, rev: flagged }); continue; }
      var prevEnd = legEnd(out[out.length - 1]);
      var dir = flagged ? true : directionFrom(prevEnd, id);
      if (out.length === 1 && !toks[0].startsWith('-')) {
        // first leg may still flip to meet this one
        if (dir === null || (flagged && s.to !== prevEnd)) {
          var otherEnd = legStart(out[0]);
          var d2 = flagged ? (s.to === otherEnd ? true : null) : directionFrom(otherEnd, id);
          if (d2 !== null) { out[0].rev = !out[0].rev; dir = d2; }
        }
      }
      if (dir === null || (flagged && s.to !== legEnd(out[out.length - 1]))) {
        problem = 'Leg ' + (i + 1) + ' of the shared route (' + id + ') does not connect to leg ' + i + '. The route is loaded up to that point.';
        break;
      }
      out.push({ id: id, rev: dir });
    }
    return { legs: out, problem: problem };
  }

  function syncUrl() {
    var u = new URL(location.href);
    if (route.length) u.searchParams.set('r', encode()); else u.searchParams.delete('r');
    history.replaceState(null, '', u);
  }

  /* ---------------------------------------------------------------- map */

  var STYLE = {
    base:      { color: '#17150f', weight: 2.5, opacity: .55 },
    candidate: { color: '#d9a441', weight: 5,   opacity: .95 },
    route:     { color: '#c8703f', weight: 6,   opacity: 1 },
    hover:     { weight: 7 }
  };

  function buildMap() {
    map = L.map('map', { zoomControl: true, preferCanvas: false });
    L.tileLayer('https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 16, attribution: 'Basemap: <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map">USGS The National Map</a>'
    }).addTo(map);
    L.control.scale({ imperial: true, metric: false }).addTo(map);

    var all = [];
    Object.keys(G.display).forEach(function (id) {
      var pts = G.display[id];
      all = all.concat(pts);
      LINES[id] = L.polyline(pts, Object.assign({ interactive: false }, STYLE.base)).addTo(map);
      var hit = L.polyline(pts, { color: '#000', weight: 18, opacity: 0.001, interactive: true, bubblingMouseEvents: false }).addTo(map);
      hit.segId = id;
      hit.on('mouseover', function () { LINES[id].setStyle(STYLE.hover); });
      hit.on('mouseout', function () { restyle(); });
      hit.on('click', function (e) { onSegmentClick(id, e.latlng); });
      hit.bindTooltip(function () { return tipHtml(id); }, { sticky: true, className: 'seg-tip', direction: 'top', offset: [0, -8] });
      HITS[id] = hit;
    });
    G.raw.nodes.forEach(function (n) {
      var th = n.kind === 'trailhead';
      var m = L.circleMarker([n.lat, n.lon], {
        radius: th ? 6 : 3.5, color: '#17150f', weight: th ? 2 : 1.5, fillColor: th ? '#faf6ef' : '#17150f', fillOpacity: 1, interactive: true
      }).addTo(map);
      m.bindTooltip(n.name, { className: 'node-tip', direction: 'top', offset: [0, -6], permanent: false });
      m.on('click', function () { showNodePopup(n); });
      NODE_MARKS[n.id] = m;
    });
    map.fitBounds(L.latLngBounds(all).pad(0.04));
  }

  function restyle() {
    var cand = candidates();
    var onRoute = {};
    route.forEach(function (l) { onRoute[l.id] = true; });
    Object.keys(LINES).forEach(function (id) {
      var st = onRoute[id] ? STYLE.route : (cand === null || cand[id]) ? STYLE.candidate : STYLE.base;
      LINES[id].setStyle(st);
      if (onRoute[id]) LINES[id].bringToFront();
    });
    Object.keys(HITS).forEach(function (id) { HITS[id].bringToFront(); });
    var t = tail();
    Object.keys(NODE_MARKS).forEach(function (id) {
      var n = G.nodes[id], th = n.kind === 'trailhead';
      NODE_MARKS[id].setStyle(id === t ? { fillColor: '#d9a441', radius: 8, color: '#17150f', weight: 2 }
                                       : { fillColor: th ? '#faf6ef' : '#17150f', radius: th ? 6 : 3.5, weight: th ? 2 : 1.5 });
      NODE_MARKS[id].bringToFront();
    });
  }

  function legName(id, rev) {
    var s = G.segments[id];
    return { trail: s.trails.map(function (t) { return G.trails[t].name; }).join(' / '),
             from: G.nodes[rev ? s.to : s.from].name, to: G.nodes[rev ? s.from : s.to].name };
  }

  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function tipHtml(id) {
    var s = G.segments[id], cand = candidates(), n = legName(id, false);
    var ok = cand === null || cand[id];
    var c = Conditions.summary(OBS['segment:' + id]);
    return '<b>' + esc(n.trail) + '</b><small>' + esc(n.from) + ' to ' + esc(n.to) + ' &middot; ' + s.miles.toFixed(2) + ' mi</small>'
      + (c ? '<span class="tip-cond">' + esc(c) + '</span>' : '')
      + (ok ? '<span class="tip-add">Click to add</span>' : '<small>Does not connect to the route</small>');
  }

  function onSegmentClick(id, latlng) {
    var cand = candidates();
    if (cand === null || cand[id]) {
      if (add(id)) { render(); return; }
    }
    showSegmentPopup(id, latlng);
  }

  function showSegmentPopup(id, latlng) {
    var s = G.segments[id], n = legName(id, false);
    var div = document.createElement('div'); div.className = 'pop';
    div.innerHTML = '<h3>' + esc(n.trail) + '</h3><div class="leg-ends">' + esc(n.from) + ' to ' + esc(n.to) + '</div>'
      + '<div class="leg-stats"><b>' + s.miles.toFixed(2) + '</b> mi &middot; +<b>' + Math.round(s.gain_ft) + '</b> / &minus;<b>' + Math.round(s.loss_ft) + '</b> ft</div>'
      + (s.sources && s.sources.length ? '<div class="leg-src">' + esc(s.sources.map(function (x) { return x.date; }).join(', ')) + '</div>' : '');
    div.appendChild(Conditions.render(OBS['segment:' + id], { compact: true }));
    var why = document.createElement('p'); why.className = 'why';
    why.textContent = 'This leg does not connect to the end of your route.';
    div.appendChild(why);
    var b = document.createElement('button'); b.textContent = 'Start a new route here';
    b.onclick = function () { route = []; add(id); map.closePopup(); render(); };
    div.appendChild(b);
    L.popup({ maxWidth: 320 }).setLatLng(latlng).setContent(div).openOn(map);
  }

  function showNodePopup(n) {
    var div = document.createElement('div'); div.className = 'pop';
    div.innerHTML = '<h3>' + esc(n.name) + '</h3><div class="leg-ends">' + (n.kind === 'trailhead' ? 'Trailhead' : 'Junction')
      + (n.ele_ft != null ? ' &middot; ' + Math.round(n.ele_ft) + ' ft' : '') + '</div>';
    div.appendChild(Conditions.render(OBS['node:' + n.id], { compact: true }));
    L.popup({ maxWidth: 320 }).setLatLng([n.lat, n.lon]).setContent(div).openOn(map);
  }

  /* ---------------------------------------------------------------- panel */

  function render() {
    var t = totals();
    $('st-miles').textContent = t.miles.toFixed(1);
    $('st-gain').textContent = Math.round(t.gain).toLocaleString();
    $('st-loss').textContent = Math.round(t.loss).toLocaleString();
    $('st-legs').textContent = route.length;

    var hint = $('hint');
    if (!route.length) hint.textContent = 'Click any trail segment to start. Then keep clicking segments that connect to the end of your route; they are shown in gold.';
    else if (route.length === 1) hint.textContent = 'Click a segment that touches either end of this leg. The route will run that way.';
    else hint.textContent = 'Segments that connect to the end of your route are shown in gold. Clicking the leg you just walked turns back along it.';

    var ol = $('legs'); ol.innerHTML = '';
    route.forEach(function (l, i) {
      var s = G.segments[l.id], n = legName(l.id, l.rev);
      var li = document.createElement('li'); li.className = 'leg' + (i === route.length - 1 ? ' leg-tail' : ''); li.setAttribute('data-n', i + 1);
      li.innerHTML = '<div class="leg-trail">' + esc(n.trail) + '</div><div class="leg-ends">' + esc(n.from) + ' to ' + esc(n.to) + '</div>'
        + '<div class="leg-stats"><b>' + s.miles.toFixed(2) + '</b> mi &middot; +<b>' + Math.round(legGain(l)) + '</b> / &minus;<b>' + Math.round(legLoss(l)) + '</b> ft</div>'
        + (s.sources && s.sources.length ? '<div class="leg-src">' + esc(s.sources.map(function (x) { return x.date; }).join(', ')) + '</div>' : '');
      li.appendChild(Conditions.render(OBS['segment:' + l.id], { compact: true }));
      li.addEventListener('mouseenter', function () { LINES[l.id].setStyle(STYLE.hover); });
      li.addEventListener('mouseleave', restyle);
      li.addEventListener('click', function () { map.fitBounds(LINES[l.id].getBounds().pad(0.3)); });
      ol.appendChild(li);
    });

    var some = route.length > 0;
    ['undo', 'clear', 'link', 'gpx', 'kml'].forEach(function (id) { $(id).disabled = !some; });
    restyle();
    syncUrl();
  }

  function notice(msg) {
    var n = $('notice');
    if (!msg) { n.hidden = true; n.textContent = ''; return; }
    n.textContent = msg; n.hidden = false;
  }

  /* ---------------------------------------------------------------- export */

  function geometry(id) {
    if (geomCache[id]) return Promise.resolve(geomCache[id]);
    return fetch('/data/' + G.segments[id].geometry).then(function (r) { return r.json(); }).then(function (g) { geomCache[id] = g; return g; });
  }

  function isOutAndBack() {
    var n = route.length;
    if (n < 2 || n % 2) return false;
    for (var i = 0; i < n / 2; i++) {
      var a = route[i], b = route[n - 1 - i];
      if (a.id !== b.id || a.rev === b.rev) return false;
    }
    return true;
  }

  function routeName() {
    var a = G.nodes[legStart(route[0])].name, b = G.nodes[tail()].name;
    if (isOutAndBack()) return 'Out and back from ' + a;
    return a === b ? 'Loop from ' + a : a + ' to ' + b;
  }

  /* Points for every leg in walking order, joined; plus the waypoints:
   * every node passed (with its observations), and, for each leg that has
   * observations, one waypoint at the leg's midpoint carrying them. */
  function assemble() {
    return Promise.all(route.map(function (l) { return geometry(l.id); })).then(function (geoms) {
      var pts = [], wpts = [], seen = {}, condDone = {};
      function nodeWpt(nid) {
        var n = G.nodes[nid];
        wpts.push({ lat: n.lat, lon: n.lon, ele: n.ele_ft != null ? n.ele_ft / M2FT : null, name: n.name,
                    desc: (n.kind === 'trailhead' ? 'Trailhead' : 'Junction') + (OBS['node:' + nid] ? '\n' + Conditions.plain(OBS['node:' + nid]) : '') });
      }
      route.forEach(function (l, i) {
        var g = geoms[i], c = g.coordinates.slice();
        if (l.rev) c.reverse();
        if (pts.length) c = c.slice(1);
        pts = pts.concat(c.map(function (p) { return { lon: p[0], lat: p[1], ele: p[2] }; }));
        var start = legStart(l), end = legEnd(l);
        if (!seen[start]) { seen[start] = true; nodeWpt(start); }
        if (!seen[end]) { seen[end] = true; nodeWpt(end); }
        var obs = OBS['segment:' + l.id];
        if (obs && obs.length && !condDone[l.id]) {
          condDone[l.id] = true;
          var cum = g.cum_m, half = cum[cum.length - 1] / 2, k = 0;
          while (k < cum.length - 1 && cum[k + 1] < half) k++;
          var mid = g.coordinates[k], n = legName(l.id, l.rev);
          wpts.push({ lat: mid[1], lon: mid[0], ele: mid[2], name: 'Conditions: ' + n.trail + ', ' + n.from + ' to ' + n.to, desc: Conditions.plain(obs) });
        }
      });
      var t = totals();
      var desc = route.map(function (l, i) {
        var s = G.segments[l.id], n = legName(l.id, l.rev), obs = OBS['segment:' + l.id];
        return (i + 1) + '. ' + n.trail + ': ' + n.from + ' to ' + n.to + ' (' + s.miles.toFixed(2) + ' mi, +' + Math.round(legGain(l)) + '/-' + Math.round(legLoss(l)) + ' ft)'
          + (obs && obs.length ? '\n   ' + Conditions.plain(obs).replace(/\n/g, '\n   ') : '');
      }).join('\n');
      desc = t.miles.toFixed(1) + ' mi, +' + Math.round(t.gain) + ' / -' + Math.round(t.loss) + ' ft. Built at ' + location.href + '\n'
        + 'Every leg is a GPS track that was walked and recorded; condition notes carry the date observed. A leg with no note has no observation, which is not the same as clear.\n\n' + desc;
      return { name: routeName(), desc: desc, pts: pts, wpts: wpts, legs: route.map(function (l, i) {
        var c = geoms[i].coordinates.slice(); if (l.rev) c.reverse(); return c; }) };
    });
  }

  function xml(t) { return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function num(v, d) { return v == null ? null : Number(v).toFixed(d); }

  function toGpx(r) {
    var out = ['<?xml version="1.0" encoding="UTF-8"?>',
      '<gpx version="1.1" creator="mazatzalhiking.com" xmlns="http://www.topografix.com/GPX/1/1">',
      '<metadata><name>' + xml(r.name) + '</name><desc>' + xml(r.desc) + '</desc><link href="' + xml(location.href) + '"><text>Mazatzal Hiking route builder</text></link><time>' + new Date().toISOString() + '</time></metadata>'];
    r.wpts.forEach(function (w) {
      out.push('<wpt lat="' + num(w.lat, 6) + '" lon="' + num(w.lon, 6) + '">' + (w.ele != null ? '<ele>' + num(w.ele, 1) + '</ele>' : '') + '<name>' + xml(w.name) + '</name><desc>' + xml(w.desc) + '</desc></wpt>');
    });
    out.push('<trk><name>' + xml(r.name) + '</name><desc>' + xml(r.desc) + '</desc>');
    r.legs.forEach(function (c) {
      out.push('<trkseg>');
      c.forEach(function (p) { out.push('<trkpt lat="' + num(p[1], 6) + '" lon="' + num(p[0], 6) + '">' + (p[2] != null ? '<ele>' + num(p[2], 1) + '</ele>' : '') + '</trkpt>'); });
      out.push('</trkseg>');
    });
    out.push('</trk></gpx>');
    return out.join('\n');
  }

  function toKml(r) {
    var coords = r.pts.map(function (p) { return num(p.lon, 6) + ',' + num(p.lat, 6) + ',' + (p.ele != null ? num(p.ele, 1) : '0'); }).join(' ');
    var out = ['<?xml version="1.0" encoding="UTF-8"?>',
      '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
      '<name>' + xml(r.name) + '</name><description><![CDATA[' + xml(r.desc).replace(/\n/g, '<br>') + ']]></description>',
      '<Style id="route"><LineStyle><color>ff3f70c8</color><width>4</width></LineStyle></Style>',
      '<Placemark><name>' + xml(r.name) + '</name><styleUrl>#route</styleUrl><LineString><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode><coordinates>' + coords + '</coordinates></LineString></Placemark>'];
    r.wpts.forEach(function (w) {
      out.push('<Placemark><name>' + xml(w.name) + '</name><description><![CDATA[' + xml(w.desc).replace(/\n/g, '<br>') + ']]></description><Point><coordinates>' + num(w.lon, 6) + ',' + num(w.lat, 6) + ',' + (w.ele != null ? num(w.ele, 1) : '0') + '</coordinates></Point></Placemark>');
    });
    out.push('</Document></kml>');
    return out.join('\n');
  }

  function download(text, ext, mime) {
    var slug = routeName().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60);
    var blob = new Blob([text], { type: mime });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'mazatzal-' + slug + '.' + ext;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
  }

  function exportAs(kind) {
    var btn = $(kind); btn.disabled = true; btn.textContent = 'Preparing…';
    assemble().then(function (r) {
      if (kind === 'gpx') download(toGpx(r), 'gpx', 'application/gpx+xml');
      else download(toKml(r), 'kml', 'application/vnd.google-earth.kml+xml');
    }).catch(function (e) { notice('Export failed: ' + e.message); })
      .then(function () { btn.disabled = !route.length; btn.textContent = kind === 'gpx' ? 'Download GPX' : 'Download KML'; });
  }

  /* ---------------------------------------------------------------- boot */

  function wire() {
    $('undo').onclick = function () { route.pop(); notice(null); render(); };
    $('clear').onclick = function () { route = []; notice(null); render(); };
    $('gpx').onclick = function () { exportAs('gpx'); };
    $('kml').onclick = function () { exportAs('kml'); };
    $('link').onclick = function () {
      var b = $('link');
      (navigator.clipboard ? navigator.clipboard.writeText(location.href) : Promise.reject()).then(function () {
        b.textContent = 'Link copied'; setTimeout(function () { b.textContent = 'Copy link'; }, 1600);
      }, function () { prompt('Copy this link:', location.href); });
    };
    window.addEventListener('keydown', function (e) {
      if ((e.key === 'z' || e.key === 'Z') && (e.metaKey || e.ctrlKey) && route.length) { e.preventDefault(); route.pop(); render(); }
    });
  }

  load().then(function () {
    buildMap();
    wire();
    var r = new URL(location.href).searchParams.get('r');
    if (r) {
      var d = decode(r);
      route = d.legs;
      if (d.problem) notice(d.problem);
      if (route.length) {
        var b = null;
        route.forEach(function (l) { b = b ? b.extend(LINES[l.id].getBounds()) : L.latLngBounds(LINES[l.id].getBounds()); });
        map.fitBounds(b.pad(0.15));
      }
    }
    render();
  }).catch(function (e) {
    $('hint').textContent = 'The trail data could not be loaded (' + e.message + '). Try reloading.';
  });

  // exposed for tests and for the console
  window.Builder = { encode: encode, decode: decode, add: add, get route() { return route; }, set route(v) { route = v; render(); }, totals: totals, assemble: assemble, toGpx: toGpx, toKml: toKml };
})();
