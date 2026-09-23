// Landing page map: pick the trail nearest the pointer instead of relying on hitting
// a 1.6px line. On a phone the map is ~340px wide and three in four points on a line
// have another trail within a thumb's width.
//
// Pointing at the map (mouse) previews the nearest trail; a click or tap selects it,
// which lights it up and names it in the bar under the map. Only that bar's
// "Open trail" link leaves the page. Without this script every trail is a plain link.
(function () {
  var svg = document.querySelector('.net');
  var pick = document.getElementById('net-pick');
  if (!svg || !pick || !svg.createSVGPoint) return;
  var hint = pick.innerHTML;
  var reach = { mouse: 12, touch: 26, pen: 18 };  // CSS px from the line that still counts

  var trails = Array.prototype.map.call(svg.querySelectorAll('a'), function (a) {
    var lines = Array.prototype.map.call(a.querySelectorAll('polyline'), function (pl) {
      return pl.getAttribute('points').trim().split(/\s+/).map(function (p) {
        var xy = p.split(','); return [+xy[0], +xy[1]];
      });
    });
    return { a: a, lines: lines };
  });

  function segDist2(px, py, ax, ay, bx, by) {
    var dx = bx - ax, dy = by - ay, l = dx * dx + dy * dy;
    var t = l ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l)) : 0;
    var x = ax + t * dx - px, y = ay + t * dy - py;
    return x * x + y * y;
  }

  function nearest(e, kind) {
    var ctm = svg.getScreenCTM(); if (!ctm) return null;
    var pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    var p = pt.matrixTransform(ctm.inverse());
    var max = (reach[kind] || reach.touch) / ctm.a;  // CSS px to SVG units
    var best = null, bestD = max * max;
    trails.forEach(function (t) {
      t.lines.forEach(function (ln) {
        for (var i = 1; i < ln.length; i++) {
          var d = segDist2(p.x, p.y, ln[i - 1][0], ln[i - 1][1], ln[i][0], ln[i][1]);
          if (d < bestD) { bestD = d; best = t.a; }
        }
      });
    });
    return best;
  }

  // What shows is the hovered trail if there is one, else the selected one.
  var selected = null, hovered = null, shown = null;
  function render() {
    var a = hovered || selected;
    if (a === shown) return;
    if (shown) shown.classList.remove('on');
    shown = a;
    if (!a) { pick.innerHTML = hint; return; }
    a.classList.add('on');
    a.parentNode.appendChild(a);  // draw it on top of its neighbours
    pick.innerHTML = '';
    var name = document.createElement('b'); name.textContent = a.dataset.name;
    var miles = document.createElement('span'); miles.textContent = a.dataset.miles + ' mi';
    var open = document.createElement('a'); open.href = a.getAttribute('href'); open.textContent = 'Open trail →';
    pick.append(name, miles, open);
  }

  var kind = 'mouse';
  svg.addEventListener('pointerdown', function (e) { kind = e.pointerType || 'mouse'; });
  svg.addEventListener('mousedown', function (e) { e.preventDefault(); });  // no focus ring on click
  svg.addEventListener('pointermove', function (e) {
    if (e.pointerType !== 'mouse') return;
    hovered = nearest(e, 'mouse');
    svg.style.cursor = hovered ? 'pointer' : '';
    render();
  });
  svg.addEventListener('pointerleave', function () { hovered = null; svg.style.cursor = ''; render(); });
  svg.addEventListener('click', function (e) {
    if (e.detail === 0) return;                       // keyboard: the focused link opens as usual
    if (e.metaKey || e.ctrlKey || e.shiftKey) return; // new tab or window: leave it to the browser
    e.preventDefault();
    selected = nearest(e, kind);                      // empty ground clears the selection
    render();
  });
  svg.addEventListener('focusin', function (e) { var a = e.target.closest('a'); if (a) { selected = a; render(); } });
})();
