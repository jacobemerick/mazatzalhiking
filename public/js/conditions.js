/* Condition observations: the one renderer every surface uses (#19).
 *
 * Observations are dated, first-person notes about a segment, node or feature
 * (schema/observations.schema.json). This module groups them by target, orders
 * them newest first, and renders them so the builder, the popups and the trail
 * pages cannot drift into showing conditions differently.
 *
 * Rules it enforces, in one place:
 *   - newest first, ties in file order
 *   - the date is always visible next to the text
 *   - the empty case says there is no observation; it never implies the trail is clear
 *   - text is plain; blank lines are paragraph breaks and nothing else is markup
 *
 * Global, no build step: window.Conditions. */
(function () {
  'use strict';

  var LABELS = {
    'brush': 'Brush', 'deadfall': 'Deadfall', 'tread': 'Tread',
    'route-finding': 'Route finding', 'water': 'Water', 'access': 'Access'
  };

  function index(doc) {
    /* observations.json -> { 'segment:0C': [obs, ...], ... } newest first */
    var by = {};
    (doc && doc.observations || []).forEach(function (o, i) {
      (by[o.target] = by[o.target] || []).push({ o: o, i: i });
    });
    Object.keys(by).forEach(function (k) {
      by[k].sort(function (a, b) {
        return a.o.date < b.o.date ? 1 : a.o.date > b.o.date ? -1 : a.i - b.i;
      });
      by[k] = by[k].map(function (x) { return x.o; });
    });
    return by;
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function fmtDate(iso) {
    var d = new Date(iso + 'T12:00:00');
    return isNaN(d) ? iso : d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function renderOne(o) {
    var art = el('article', 'obs obs-' + o.category);
    var head = el('header', 'obs-head');
    head.appendChild(el('span', 'obs-cat', LABELS[o.category] || o.category));
    var t = el('time', 'obs-date', fmtDate(o.date));
    t.setAttribute('datetime', o.date);
    head.appendChild(t);
    art.appendChild(head);
    String(o.text).split(/\n\s*\n/).forEach(function (para) {
      if (para.trim()) art.appendChild(el('p', 'obs-text', para.trim()));
    });
    if (o.photos && o.photos.length) {
      var ul = el('ul', 'obs-photos');
      o.photos.forEach(function (p) {
        var li = el('li', null, p.caption ? p.caption : p.file);
        li.setAttribute('data-file', p.file);
        ul.appendChild(li);
      });
      art.appendChild(ul);
    }
    return art;
  }

  /* render(list, {compact}) -> element. list is already newest-first from index(). */
  function render(list, opts) {
    opts = opts || {};
    var wrap = el('div', 'obs-list' + (opts.compact ? ' obs-compact' : ''));
    if (!list || !list.length) {
      wrap.appendChild(el('p', 'obs-empty', 'No recorded observation for this leg.'));
      return wrap;
    }
    list.forEach(function (o) { wrap.appendChild(renderOne(o)); });
    return wrap;
  }

  /* One-line summary for tooltips and export text: "brush, 23 May 2026" or null. */
  function summary(list) {
    if (!list || !list.length) return null;
    var o = list[0];
    return (LABELS[o.category] || o.category) + ', ' + fmtDate(o.date)
      + (list.length > 1 ? ' (+' + (list.length - 1) + ' older)' : '');
  }

  /* Plain text for GPX/KML descriptions. Same ordering, date first on every line. */
  function plain(list) {
    if (!list || !list.length) return '';
    return list.map(function (o) {
      return '[' + o.date + ', ' + (LABELS[o.category] || o.category) + '] ' + o.text.replace(/\s*\n\s*\n\s*/g, ' / ');
    }).join('\n');
  }

  window.Conditions = { index: index, render: render, summary: summary, plain: plain, labels: LABELS, fmtDate: fmtDate };
})();
