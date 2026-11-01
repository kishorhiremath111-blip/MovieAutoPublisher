/* Six satisfying 3D scenes. Har scene deterministic hai: renderAt(t) hamesha
   same frame deta hai, isliye Python frame-by-frame screenshot le sakta hai.
   Har scene S.events me (time, kind, pitch) bharta hai, jisse audio banti hai. */
(function () {
  'use strict';
  var TAU = Math.PI * 2;
  var P, S, builders = {};

  function mulberry(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function ease(x) { x = clamp01(x); return x * x * (3 - 2 * x); }
  function frac(x) { return x - Math.floor(x); }

  function pal(i, out) {
    var f = frac(i);
    var h = P.hue0 + P.span * f;
    h = h - Math.floor(h);
    return out.setHSL(h, P.sat, Math.min(0.85, P.light + 0.06 * Math.sin(f * TAU * 2)));
  }

  function geo(shape, size) {
    switch (shape) {
      case 'cube': return new THREE.BoxGeometry(size, size, size);
      case 'sphere': return new THREE.SphereGeometry(size * 0.55, 24, 16);
      case 'cylinder': return new THREE.CylinderGeometry(size * 0.45, size * 0.45, size, 24);
      case 'cone': return new THREE.ConeGeometry(size * 0.5, size, 24);
      case 'torus': return new THREE.TorusGeometry(size * 0.4, size * 0.15, 12, 24);
      case 'octahedron': return new THREE.OctahedronGeometry(size * 0.6);
      case 'icosahedron': return new THREE.IcosahedronGeometry(size * 0.58);
      default: return new THREE.DodecahedronGeometry(size * 0.55);
    }
  }

  function mat(kind) {
    switch (kind) {
      case 'clay': return new THREE.MeshStandardMaterial({ roughness: 0.92, metalness: 0 });
      case 'metal': return new THREE.MeshStandardMaterial({ roughness: 0.3, metalness: 0.65 });
      case 'pearl': return new THREE.MeshStandardMaterial({ roughness: 0.22, metalness: 0.15, emissive: 0x333333 });
      case 'neon': return new THREE.MeshBasicMaterial({});
      case 'glass': return new THREE.MeshStandardMaterial({ roughness: 0.05, metalness: 0.1, transparent: true, opacity: 0.78 });
      default: return new THREE.MeshStandardMaterial({ roughness: 0.18, metalness: 0 });
    }
  }

  function inst(n, shape, size) {
    var m = new THREE.InstancedMesh(geo(shape, size), mat(P.material), n);
    m.frustumCulled = false;
    S.scene.add(m);
    return m;
  }

  function fit(halfH, halfW) {
    var t = Math.tan(S.cam.fov * Math.PI / 360);
    return Math.max(halfH / t, halfW / (S.cam.aspect * t));
  }

  function ground(r, y) {
    var g = new THREE.Mesh(new THREE.CircleGeometry(r, 64),
      new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.14, roughness: 0.6 }));
    g.rotation.x = -Math.PI / 2;
    g.position.y = y;
    S.scene.add(g);
  }

  function beats(kind) {
    var nb = Math.floor(P.duration / P.beat);
    for (var b = 0; b < nb; b++) S.events.push({ t: b * P.beat, kind: kind || 'beat', pitch: b });
  }

  /* front=true: scene ka ek hi saamne wala side hai, isliye camera sirf halka hilta hai */
  function camera(t, dist, height, look, front) {
    var u = t / P.duration, a, c = S.cam, mode = P.camera;
    if (front) mode = (mode === 'orbit' || mode === 'low') ? 'sway' : (mode === 'top' ? 'dolly' : mode);
    switch (mode) {
      case 'low':
        a = TAU * u;
        c.position.set(Math.sin(a) * dist * 0.92, height * 0.35 + dist * 0.1, Math.cos(a) * dist * 0.92);
        break;
      case 'top':
        a = TAU * u;
        c.position.set(Math.sin(a) * dist * 0.28, dist * 0.95, Math.cos(a) * dist * 0.45);
        break;
      case 'dolly':
        c.position.set(Math.sin(TAU * u) * dist * 0.14, height, dist * (1.04 - 0.16 * Math.sin(Math.PI * u)));
        break;
      case 'sway':
        a = Math.sin(TAU * u) * 0.8;
        c.position.set(Math.sin(a) * dist, height, Math.cos(a) * dist);
        break;
      default:
        a = TAU * u;
        c.position.set(Math.sin(a) * dist, height, Math.cos(a) * dist);
    }
    c.lookAt(0, look, 0);
  }

  /* ---------- 1. ripple wave ---------- */
  builders.ripple = function () {
    var cols = [9, 11, 13, 15][P.density], rows = Math.round(cols * 1.8), cnt = cols * rows;
    var m = inst(cnt, P.shape, 0.82), dm = new THREE.Object3D(), col = new THREE.Color(), pos = [];
    var hc = (cols - 1) / 2, hr = (rows - 1) / 2, maxD = Math.hypot(hc, hr);
    for (var ix = 0; ix < cols; ix++) for (var iz = 0; iz < rows; iz++) {
      var x = ix - hc, z = iz - hr;
      pos.push({ x: x, z: z, d: Math.hypot(x, z) });
    }
    beats('beat');
    var dist = fit(hr * 0.78 + 2, hc + 2.2) * 1.12;
    S.update = function (t) {
      var ph = t / (P.beat * 4) * TAU, bounce = Math.exp(-(t % P.beat) * 7) * 0.2;
      for (var i = 0; i < cnt; i++) {
        var q = pos[i], w = Math.sin(q.d * 0.62 - ph), k = w * 0.5 + 0.5;
        dm.position.set(q.x, w * 1.1, q.z);
        dm.rotation.set(0, ph * 0.25 + q.d * 0.12, 0);
        var s = 0.7 + 0.28 * k + bounce;
        dm.scale.set(s, s * (P.shape === 'cube' ? 1 + k * 0.9 : 1), s);
        dm.updateMatrix();
        m.setMatrixAt(i, dm.matrix);
        m.setColorAt(i, pal(q.d / maxD * 0.9 + t * 0.04, col));
      }
      m.instanceMatrix.needsUpdate = true;
      m.instanceColor.needsUpdate = true;
      camera(t, dist, dist * 0.62, 0, true);
    };
  };

  /* ---------- 2. domino spiral ---------- */
  builders.domino = function () {
    var n = [60, 90, 120, 160][P.density], w = 0.9, h = 1.5, th = 0.28;
    var g = new THREE.BoxGeometry(w, h, th);
    g.translate(0, h / 2, 0);
    var m = new THREE.InstancedMesh(g, mat(P.material), n);
    m.frustumCulled = false;
    S.scene.add(m);
    var b = 0.5, theta = 2.0, spacing = 0.75, items = [], col = new THREE.Color(), dm = new THREE.Object3D();
    var dtF = Math.min(P.beat * 0.6, (P.duration - 0.9 - 2.4) / n), fallDur = 0.38, maxA = 1.25;
    var maxR = 1;
    for (var i = 0; i < n; i++) {
      var r = b * theta, x = r * Math.cos(theta), z = r * Math.sin(theta);
      var dx = b * Math.cos(theta) - r * Math.sin(theta), dz = b * Math.sin(theta) + r * Math.cos(theta);
      dm.position.set(x, 0, z);
      dm.rotation.set(0, Math.atan2(dx, dz), 0);
      dm.scale.set(1, 1, 1);
      dm.updateMatrix();
      items.push({ m0: dm.matrix.clone(), ti: 0.9 + i * dtF });
      m.setColorAt(i, pal(i / n, col));
      S.events.push({ t: 0.9 + i * dtF + 0.06, kind: 'tick', pitch: i });
      maxR = r;
      theta += spacing / Math.sqrt(r * r + b * b);
    }
    m.instanceColor.needsUpdate = true;
    ground(maxR + 2, -0.02);
    var tA = new THREE.Matrix4(), tB = new THREE.Matrix4(), tC = new THREE.Matrix4(),
        loc = new THREE.Matrix4(), fin = new THREE.Matrix4();
    var dist = fit(maxR * 0.7 + 1.5, maxR + 1.5) * 1.1;
    S.update = function (t) {
      for (var i = 0; i < n; i++) {
        var q = clamp01((t - items[i].ti) / fallDur), ang = maxA * q * q;
        tA.makeTranslation(0, 0, th / 2);
        tB.makeRotationX(ang);
        tC.makeTranslation(0, 0, -th / 2);
        loc.multiplyMatrices(tA, tB).multiply(tC);
        fin.multiplyMatrices(items[i].m0, loc);
        m.setMatrixAt(i, fin);
      }
      m.instanceMatrix.needsUpdate = true;
      camera(t, dist, dist * 0.6, 0.3, false);
    };
  };

  /* ---------- 3. jar fill ---------- */
  builders.jar = function () {
    var n = [70, 110, 160, 230][P.density], R = 1.9, sp = 0.62, rr = R - 0.36;
    var base = [], i, j, k;
    for (j = -8; j <= 8; j++) for (i = -8; i <= 8; i++) {
      var x = (i + (j & 1) * 0.5) * sp, z = j * sp * 0.866;
      if (Math.hypot(x, z) <= rr) base.push([x, z]);
    }
    var per = base.length, layers = Math.ceil(n / per), H = Math.max(6, layers * 0.5 + 1.5);
    var m = inst(n, P.shape, 0.6), dm = new THREE.Object3D(), col = new THREE.Color(), balls = [];
    var g = 34, y0 = H + 4, gap = Math.min(P.beat / 2, (P.duration - 3.5) / n);
    var layerOrder = [];
    for (k = 0; k < layers; k++) {
      var idxs = [], ca = Math.cos(k * 0.6), sa = Math.sin(k * 0.6);
      for (i = 0; i < per; i++) idxs.push(i);
      for (i = per - 1; i > 0; i--) { j = Math.floor(S.rand() * (i + 1)); var tmp = idxs[i]; idxs[i] = idxs[j]; idxs[j] = tmp; }
      layerOrder.push({ idxs: idxs, ca: ca, sa: sa });
    }
    for (i = 0; i < n; i++) {
      k = Math.floor(i / per);
      var lo = layerOrder[k], p = base[lo.idxs[i % per]];
      var fx = p[0] * lo.ca - p[1] * lo.sa, fz = p[0] * lo.sa + p[1] * lo.ca, fy = 0.38 + k * 0.5;
      var fd = Math.sqrt(2 * (y0 - fy) / g), ti = 0.6 + i * gap;
      balls.push({ x: fx, z: fz, y: fy, fd: fd, ti: ti });
      m.setColorAt(i, pal(i / n, col));
      S.events.push({ t: ti + fd, kind: 'plink', pitch: i });
    }
    m.instanceColor.needsUpdate = true;
    var jar = new THREE.Mesh(new THREE.CylinderGeometry(R + 0.12, R + 0.12, H, 48, 1, true),
      new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.16, roughness: 0.05,
        side: THREE.DoubleSide, depthWrite: false }));
    jar.position.y = H / 2;
    S.scene.add(jar);
    ground(R * 2.4, -0.02);
    var dist = fit((H + 1) / 2 * 1.15, R * 1.7 + 0.5);
    S.update = function (t) {
      for (var i = 0; i < n; i++) {
        var b = balls[i], tau = t - b.ti, y, sc = 1;
        if (tau < 0) { sc = 0.0001; y = y0; }
        else if (tau < b.fd) y = y0 - 0.5 * g * tau * tau;
        else { var bt = tau - b.fd; y = b.y + 0.25 * Math.exp(-bt * 9) * Math.abs(Math.sin(bt * 14)); }
        var spin = tau < 0 ? 0 : Math.min(tau, b.fd);
        dm.position.set(b.x, y, b.z);
        dm.rotation.set(spin * 2.1, spin * 1.7, 0);
        dm.scale.set(sc, sc, sc);
        dm.updateMatrix();
        m.setMatrixAt(i, dm.matrix);
      }
      m.instanceMatrix.needsUpdate = true;
      camera(t, dist, H * 0.55, H * 0.42, false);
    };
  };

  /* ---------- 4. endless tunnel ---------- */
  builders.tunnel = function () {
    var rings = [28, 36, 44, 52][P.density], K = [12, 14, 16, 18][P.density], sp = 1.4, L = rings * sp, rad = 3.2;
    var cnt = rings * K, m = inst(cnt, P.shape, 0.6), dm = new THREE.Object3D(), col = new THREE.Color();
    var v = sp / P.beat;
    beats('beat');
    S.update = function (t) {
      var idx = 0;
      for (var r = 0; r < rings; r++) {
        var z = -(((r * sp - v * t) % L) + L) % L;
        var near = ease((-z - 0.6) / 2), far = ease((L + z) / 8), f = near * far;
        var rot = r * 0.25 + t * 0.4 * (r % 2 ? 1 : -1);
        var rr = rad * (1 + 0.12 * Math.sin(r * 0.5 - t * 3));
        pal(frac(r / rings + t * 0.08), col);
        for (var k = 0; k < K; k++) {
          var a = rot + k / K * TAU, s = (0.8 + 0.25 * Math.sin(r * 0.7 + t * 4)) * f + 0.0001;
          dm.position.set(Math.cos(a) * rr, Math.sin(a) * rr, z);
          dm.rotation.set(a, t * 0.8 + r * 0.3, 0);
          dm.scale.set(s, s, s);
          dm.updateMatrix();
          m.setMatrixAt(idx, dm.matrix);
          m.setColorAt(idx, col);
          idx++;
        }
      }
      m.instanceMatrix.needsUpdate = true;
      m.instanceColor.needsUpdate = true;
      var u = t / P.duration, c = S.cam;
      c.up.set(Math.sin(TAU * u * 2) * 0.22, 1, 0);
      c.position.set(Math.sin(TAU * u * 2) * 0.4, Math.cos(TAU * u * 2) * 0.3, 2);
      c.lookAt(0, 0, -12);
    };
  };

  /* ---------- 5. bubble pop wall ---------- */
  builders.bubbles = function () {
    var cols = [8, 10, 12, 14][P.density], rows = [14, 18, 22, 25][P.density], cnt = cols * rows, sp = 7.6 / cols;
    var m = inst(cnt, P.shape, sp * 0.92), dm = new THREE.Object3D(), col = new THREE.Color(), items = [];
    var cx = (S.rand() - 0.5) * cols * sp * 0.6, cy = (S.rand() - 0.5) * rows * sp * 0.6, i;
    for (var r = 0; r < rows; r++) for (var c = 0; c < cols; c++) {
      var x = (c - (cols - 1) / 2) * sp, y = (r - (rows - 1) / 2) * sp;
      items.push({ x: x, y: y, z: -x * x * 0.02, key: Math.hypot(x - cx, y - cy) + S.rand() * 0.9, ph: S.rand() * TAU });
    }
    var order = items.map(function (_, ix) { return ix; }).sort(function (a, b) { return items[a].key - items[b].key; });
    var gapP = Math.min(P.beat / 3, P.duration * 0.6 / cnt);
    var tr = 1 + cnt * gapP + 0.8, gapR = gapP * 0.5;
    for (i = 0; i < cnt; i++) {
      var it = items[order[i]];
      it.tp = 1 + i * gapP;
      it.tg = tr + i * gapR;
      S.events.push({ t: it.tp, kind: 'pop', pitch: i });
    }
    for (i = 0; i < cnt; i++) m.setColorAt(i, pal(frac(items[i].y / (rows * sp) + 0.5 + items[i].x * 0.02), col));
    m.instanceColor.needsUpdate = true;
    var dist = fit(rows * sp / 2 + 1.2, 4.8);
    S.update = function (t) {
      for (var i = 0; i < cnt; i++) {
        var it = items[i], s, tau = t - it.tp;
        if (tau < 0) s = 1 + 0.03 * Math.sin(t * 2.5 + it.ph);
        else if (tau < 0.05) s = 1 + 0.3 * tau / 0.05;
        else if (tau < 0.12) s = 1.3 * (1 - (tau - 0.05) / 0.07);
        else s = 0;
        var tg = t - it.tg;
        if (tau >= 0.12 && tg > 0) { var q = tg / 0.5; s = 1 - Math.exp(-6 * q) * Math.cos(14 * q); }
        dm.position.set(it.x, it.y, it.z);
        dm.rotation.set(t * 0.3 + it.ph, t * 0.4, 0);
        dm.scale.set(Math.max(s, 0.0001), Math.max(s, 0.0001), Math.max(s, 0.0001));
        dm.updateMatrix();
        m.setMatrixAt(i, dm.matrix);
      }
      m.instanceMatrix.needsUpdate = true;
      camera(t, dist, 0.6, 0, true);
    };
  };

  /* ---------- 6. helix dance ---------- */
  builders.helix = function () {
    var strands = [2, 3, 3, 4][P.density], per = [34, 44, 58, 72][P.density], cnt = strands * per;
    var m = inst(cnt, P.shape, 0.5), dm = new THREE.Object3D(), col = new THREE.Color(), dy = 0.24;
    beats('beat');
    var dist = fit(per * dy / 2 + 1.5, 4.4) * 1.05;
    S.update = function (t) {
      var idx = 0, spin = t * TAU / (P.beat * 16), wph = t * TAU / (P.beat * 4);
      for (var s = 0; s < strands; s++) for (var i = 0; i < per; i++) {
        var a = i * 0.32 + s / strands * TAU + spin;
        var w = Math.max(0, Math.sin(i / per * TAU * 2 - wph));
        var r = 2.4 + w * 0.9, sc = 0.55 + w * 0.5;
        dm.position.set(Math.cos(a) * r, (i - per / 2) * dy, Math.sin(a) * r);
        dm.rotation.set(a, i * 0.2 + t, 0);
        dm.scale.set(sc, sc, sc);
        dm.updateMatrix();
        m.setMatrixAt(idx, dm.matrix);
        m.setColorAt(idx, pal(i / per + s * 0.1 + t * 0.03, col));
        idx++;
      }
      m.instanceMatrix.needsUpdate = true;
      m.instanceColor.needsUpdate = true;
      camera(t, dist, dist * 0.18, 0, false);
    };
  };

  /* ---------- public API ---------- */
  window.initScene = function (params) {
    P = params;
    var W = window.innerWidth, H = window.innerHeight;
    document.body.style.background = 'linear-gradient(170deg,' + P.bg[0] + ',' + P.bg[1] + ')';
    var r = new THREE.WebGLRenderer({ canvas: document.getElementById('c'), antialias: true, alpha: true,
      preserveDrawingBuffer: true });
    r.setPixelRatio(1);
    r.setSize(W, H, false);
    r.setClearColor(0x000000, 0);
    var scene = new THREE.Scene();
    var cam = new THREE.PerspectiveCamera(40, W / H, 0.1, 300);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8878c8, 1.0));
    var d1 = new THREE.DirectionalLight(0xffffff, 0.9); d1.position.set(6, 12, 8); scene.add(d1);
    var d2 = new THREE.DirectionalLight(0xffd6f0, 0.35); d2.position.set(-8, 4, -6); scene.add(d2);
    S = { r: r, scene: scene, cam: cam, rand: mulberry(P.seed), events: [], update: null };
    builders[P.scene]();
    S.events.sort(function (a, b) { return a.t - b.t; });
    return { events: S.events };
  };

  window.renderAt = function (t) {
    S.update(t);
    S.r.render(S.scene, S.cam);
    return true;
  };
})();
