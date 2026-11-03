/* Eleven procedural 3D scenes for vertical Shorts.
   Deterministic frame renderer: update(t) produces the same scene at any timestamp. */
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
  function smoothPop(x) { x = clamp01(x); return 1 - Math.pow(1 - x, 3); }

  function pal(i, out, shift) {
    var f = frac(i);
    var h = frac(P.hue0 + P.span * f + (shift || 0));
    return out.setHSL(h, Math.min(1, P.sat), Math.max(0.48, Math.min(0.82,
      P.light + 0.065 * Math.sin(f * TAU * 2))));
  }

  function geo(shape, size) {
    switch (shape) {
      case 'cube': return new THREE.BoxGeometry(size, size, size);
      case 'sphere': return new THREE.SphereGeometry(size * 0.55, 32, 24);
      case 'cylinder': return new THREE.CylinderGeometry(size * 0.42, size * 0.42, size, 32, 1);
      case 'cone': return new THREE.ConeGeometry(size * 0.5, size, 32, 1);
      case 'torus': return new THREE.TorusGeometry(size * 0.40, size * 0.13, 16, 36);
      case 'octahedron': return new THREE.OctahedronGeometry(size * 0.62, 1);
      case 'icosahedron': return new THREE.IcosahedronGeometry(size * 0.58, 1);
      default: return new THREE.DodecahedronGeometry(size * 0.56, 1);
    }
  }

  function mat(kind) {
    var opts = {
      color: 0xffffff, roughness: 0.2, metalness: 0.32,
      emissive: 0x111111, emissiveIntensity: 0.16
    };
    if (kind === 'ceramic') { opts.roughness = 0.3; opts.metalness = 0.08; opts.clearcoat = 0.7; }
    if (kind === 'chrome' || kind === 'liquid-metal') {
      opts.roughness = 0.11; opts.metalness = 0.92; opts.clearcoat = 1;
      opts.clearcoatRoughness = 0.08;
    }
    if (kind === 'prism' || kind === 'pearl') {
      opts.roughness = 0.13; opts.metalness = 0.55; opts.clearcoat = 1;
      opts.clearcoatRoughness = 0.06; opts.emissiveIntensity = 0.24;
    }
    if (kind === 'glass') {
      opts.roughness = 0.08; opts.metalness = 0.18; opts.clearcoat = 1;
      opts.transparent = true; opts.opacity = 0.88; opts.depthWrite = false;
    }
    if (kind === 'neon') {
      opts.roughness = 0.24; opts.metalness = 0.15; opts.emissive = 0xffffff;
      opts.emissiveIntensity = 0.42;
    }
    if (kind === 'candy') {
      opts.roughness = 0.12; opts.metalness = 0.16; opts.clearcoat = 1;
      opts.clearcoatRoughness = 0.1;
    }
    return new THREE.MeshPhysicalMaterial(opts);
  }

  function inst(n, shape, size, material) {
    var m = new THREE.InstancedMesh(geo(shape, size), material || mat(P.material), n);
    m.frustumCulled = false;
    S.scene.add(m);
    return m;
  }

  function fit(halfH, halfW) {
    var t = Math.tan(S.cam.fov * Math.PI / 360);
    return Math.max(halfH / t, halfW / (S.cam.aspect * t));
  }

  function addRing(radius, tube, color, rotation) {
    var mesh = new THREE.Mesh(
      new THREE.TorusGeometry(radius, tube, 16, 160),
      new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.84 })
    );
    if (rotation) mesh.rotation.set(rotation[0], rotation[1], rotation[2]);
    S.scene.add(mesh);
    return mesh;
  }

  function addStars() {
    var vertices = [], rng = mulberry((P.seed ^ 0x5f3759df) >>> 0);
    for (var i = 0; i < 360; i++) {
      vertices.push((rng() - 0.5) * 19, (rng() - 0.5) * 31,
        -9 + rng() * 23);
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    var p = new THREE.Points(g, new THREE.PointsMaterial({
      color: 0x9ebaff, size: 0.026, transparent: true, opacity: 0.52,
      depthWrite: false, sizeAttenuation: true
    }));
    S.scene.add(p);
  }

  function addPayoff() {
    var colors = [0xffffff, 0x6ffcff, 0xff62dc];
    var rings = [];
    for (var i = 0; i < 3; i++) {
      var ring = new THREE.Mesh(
        new THREE.TorusGeometry(1.35 + i * 0.25, 0.022, 12, 120),
        new THREE.MeshBasicMaterial({ color: colors[i], transparent: true,
          opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending })
      );
      ring.rotation.set(i * 0.88, i * 0.61, i * 0.42);
      ring.position.y = S.focusY || 0;
      S.scene.add(ring);
      rings.push(ring);
    }
    var core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.34, 2),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true,
        opacity: 0, blending: THREE.AdditiveBlending }));
    core.position.y = S.focusY || 0;
    S.scene.add(core);
    S.payoff = function (t) {
      var q = ease((t - (P.duration - 2.35)) / 0.62);
      var pulse = 1 + 0.10 * Math.sin(t * 15);
      for (var j = 0; j < rings.length; j++) {
        rings[j].material.opacity = 0.78 * q;
        rings[j].rotation.x += 0; // deterministic orientation is set below
        rings[j].rotation.y = j * 0.61 + t * (0.32 + j * 0.12);
        rings[j].rotation.z = j * 0.42 - t * (0.24 + j * 0.1);
        rings[j].scale.setScalar((0.22 + 0.78 * q) * pulse);
      }
      core.material.opacity = 0.92 * q;
      core.rotation.set(t * 1.7, t * 2.1, t * 1.2);
      core.scale.setScalar((0.35 + 0.65 * q) * pulse);
    };
  }

  function camera(t, dist, height, look, front) {
    var u = t / P.duration, a, c = S.cam, mode = P.camera;
    if (front && (mode === 'orbit' || mode === 'low' || mode === 'top')) mode = 'sweep';
    switch (mode) {
      case 'low':
        a = TAU * u * 0.72;
        c.position.set(Math.sin(a) * dist * 0.72, height * 0.43 + dist * 0.07, Math.cos(a) * dist);
        break;
      case 'top':
        a = TAU * u * 0.55;
        c.position.set(Math.sin(a) * dist * 0.16, dist * 0.96, Math.cos(a) * dist * 0.34);
        break;
      case 'dolly':
        c.position.set(Math.sin(TAU * u) * dist * 0.10, height,
          dist * (1.10 - 0.15 * Math.sin(Math.PI * u)));
        break;
      case 'sweep':
        a = Math.sin(TAU * u * 0.72) * 0.44;
        c.position.set(Math.sin(a) * dist, height + Math.sin(TAU * u) * 0.12, Math.cos(a) * dist);
        break;
      default:
        a = TAU * u * 0.62;
        c.position.set(Math.sin(a) * dist * 0.58, height, Math.cos(a) * dist);
    }
    c.lookAt(0, look, 0);
  }

  function beats(kind) {
    var nb = Math.floor(P.duration / P.beat);
    for (var b = 0; b < nb; b++) {
      S.events.push({ t: b * P.beat, kind: kind || 'beat', pitch: b });
    }
  }

  /* 1 — A dense glossy field makes a travelling concentric wave. */
  builders.ripple = function () {
    var cols = [13, 15, 17, 19][P.density], rows = Math.round(cols * 1.8);
    var count = cols * rows, m = inst(count, P.shape, 0.72);
    var dm = new THREE.Object3D(), col = new THREE.Color(), points = [];
    var hc = (cols - 1) / 2, hr = (rows - 1) / 2, maxD = Math.hypot(hc, hr);
    for (var x = 0; x < cols; x++) for (var z = 0; z < rows; z++) {
      var px = (x - hc) * 0.88, pz = (z - hr) * 0.88;
      points.push({ x: px, z: pz, d: Math.hypot(px, pz) });
    }
    beats('beat');
    var dist = fit(hr * 0.79 + 1.8, hc * 0.88 + 1.9) * 1.08;
    S.focusY = 0;
    S.update = function (t) {
      var phase = t * 2.1, pulse = 1 + 0.10 * Math.sin(t * 7);
      for (var i = 0; i < count; i++) {
        var q = points[i], wave = Math.sin(q.d * 1.10 - phase);
        var crown = Math.exp(-Math.pow((q.d - (1.0 + frac(t / 7) * maxD * 0.75)), 2) * 0.18);
        var y = wave * 0.46 + crown * 0.78;
        dm.position.set(q.x, y, q.z);
        dm.rotation.set(y * 0.28, phase * 0.10 + q.d * 0.14, y * 0.14);
        var s = (0.66 + 0.20 * (wave * 0.5 + 0.5) + crown * 0.28) * pulse;
        dm.scale.set(s, s * (P.shape === 'cube' ? 1.18 : 1), s);
        dm.updateMatrix(); m.setMatrixAt(i, dm.matrix);
        m.setColorAt(i, pal(q.d / maxD * 0.88 + t * 0.07, col));
      }
      m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true;
      camera(t, dist, dist * 0.56, 0, true);
    };
  };

  /* 2 — A continuous spiral domino chain reaction, timed to the beat. */
  builders.domino = function () {
    var n = [100, 140, 180, 220][P.density], w = 0.62, h = 1.18, th = 0.22;
    var g = new THREE.BoxGeometry(w, h, th); g.translate(0, h / 2, 0);
    var m = new THREE.InstancedMesh(g, mat(P.material), n);
    m.frustumCulled = false; S.scene.add(m);
    var theta = 1.6, b = 0.16, spacing = 0.56, items = [];
    var col = new THREE.Color(), dm = new THREE.Object3D(), maxR = 0;
    var gap = Math.min(P.beat * 0.52, (P.duration - 4.4) / n);
    for (var i = 0; i < n; i++) {
      var r = b * theta, x = r * Math.cos(theta), z = r * Math.sin(theta);
      var dx = b * Math.cos(theta) - r * Math.sin(theta);
      var dz = b * Math.sin(theta) + r * Math.cos(theta);
      dm.position.set(x, 0, z); dm.rotation.set(0, Math.atan2(dx, dz), 0);
      dm.updateMatrix(); items.push({ base: dm.matrix.clone(), start: 0.22 + i * gap });
      m.setColorAt(i, pal(i / n, col));
      S.events.push({ t: 0.25 + i * gap, kind: 'tick', pitch: i });
      maxR = Math.max(maxR, r);
      theta += spacing / Math.sqrt(r * r + b * b);
    }
    m.instanceColor.needsUpdate = true;
    var ringA = addRing(maxR + 0.8, 0.025, 0x48eaff, [Math.PI / 2, 0, 0]);
    ringA.position.y = 0.02;
    var a = new THREE.Matrix4(), b0 = new THREE.Matrix4(), c = new THREE.Matrix4();
    var local = new THREE.Matrix4(), final = new THREE.Matrix4();
    var dist = fit(maxR * 0.8 + 1.2, maxR + 1.2) * 1.05;
    S.focusY = 0;
    S.update = function (t) {
      for (var j = 0; j < n; j++) {
        var q = clamp01((t - items[j].start) / 0.38), ang = 1.25 * q * q;
        a.makeTranslation(0, 0, th / 2); b0.makeRotationX(ang); c.makeTranslation(0, 0, -th / 2);
        local.multiplyMatrices(a, b0).multiply(c);
        final.multiplyMatrices(items[j].base, local);
        m.setMatrixAt(j, final);
      }
      m.instanceMatrix.needsUpdate = true;
      ringA.rotation.z = t * 0.16;
      camera(t, dist, dist * 0.62, 0.25, false);
    };
  };

  /* 3 — A transparent vessel fills with a perfectly ordered cascade of spheres. */
  builders.jar = function () {
    var n = [84, 124, 176, 232][P.density], R = 1.75, spacing = 0.48, rr = R - 0.34;
    var base = [], i, j, k;
    for (j = -8; j <= 8; j++) for (i = -8; i <= 8; i++) {
      var x = (i + (j & 1) * 0.5) * spacing, z = j * spacing * 0.866;
      if (Math.hypot(x, z) <= rr) base.push([x, z]);
    }
    var per = base.length, layers = Math.ceil(n / per), H = Math.max(6.4, layers * 0.43 + 1.1);
    var m = inst(n, 'sphere', 0.58), dm = new THREE.Object3D(), col = new THREE.Color(), balls = [];
    var y0 = H + 4.1, gravity = 33, gap = Math.min(P.beat / 2.8, (P.duration - 4.2) / n);
    var orders = [];
    for (k = 0; k < layers; k++) {
      var ids = [];
      for (i = 0; i < per; i++) ids.push(i);
      for (i = per - 1; i > 0; i--) {
        j = Math.floor(S.rand() * (i + 1));
        var tmp = ids[i]; ids[i] = ids[j]; ids[j] = tmp;
      }
      orders.push({ ids: ids, angle: k * 0.38 });
    }
    for (i = 0; i < n; i++) {
      k = Math.floor(i / per);
      var layer = orders[k], p = base[layer.ids[i % per]];
      var ca = Math.cos(layer.angle), sa = Math.sin(layer.angle);
      var fx = p[0] * ca - p[1] * sa, fz = p[0] * sa + p[1] * ca;
      var fy = 0.34 + k * 0.43, fd = Math.sqrt(2 * (y0 - fy) / gravity);
      var ti = 0.30 + i * gap;
      balls.push({ x: fx, z: fz, y: fy, fall: fd, start: ti });
      m.setColorAt(i, pal(i / n, col));
      S.events.push({ t: ti + fd, kind: 'plink', pitch: i });
    }
    m.instanceColor.needsUpdate = true;
    var glass = new THREE.Mesh(new THREE.CylinderGeometry(R, R, H, 72, 1, true),
      new THREE.MeshPhysicalMaterial({ color: 0x9edfff, roughness: 0.05, metalness: 0.12,
        transparent: true, opacity: 0.17, side: THREE.DoubleSide, depthWrite: false,
        clearcoat: 1, clearcoatRoughness: 0.02 }));
    glass.position.y = H / 2; S.scene.add(glass);
    var rim = addRing(R, 0.055, 0x8cfbff, [Math.PI / 2, 0, 0]); rim.position.y = H;
    var foot = addRing(R * 0.98, 0.07, 0xff5de2, [Math.PI / 2, 0, 0]); foot.position.y = 0.06;
    var dist = fit(H * 0.54, R + 0.38) * 1.08;
    S.focusY = H * 0.44;
    S.update = function (t) {
      for (var j = 0; j < n; j++) {
        var q = balls[j], tau = t - q.start, y, scale = 1;
        if (tau < 0) { y = y0; scale = 0.0001; }
        else if (tau < q.fall) y = y0 - 0.5 * gravity * tau * tau;
        else {
          var settle = tau - q.fall;
          y = q.y + 0.055 * Math.exp(-settle * 8) * Math.sin(settle * 18);
        }
        dm.position.set(q.x, y, q.z);
        dm.rotation.set(Math.max(0, tau) * 1.7, Math.max(0, tau) * 1.2, 0);
        dm.scale.setScalar(scale); dm.updateMatrix(); m.setMatrixAt(j, dm.matrix);
      }
      m.instanceMatrix.needsUpdate = true;
      camera(t, dist, H * 0.62, H * 0.43, false);
    };
  };

  /* 4 — Repeating rings and gem fragments rush through a black prism tunnel. */
  builders.tunnel = function () {
    var rings = [27, 33, 39, 45][P.density], sides = [16, 18, 20, 22][P.density];
    var count = rings * sides, spacing = 1.42, length = rings * spacing, radius = 3.15;
    var m = inst(count, P.shape, 0.47), dm = new THREE.Object3D(), col = new THREE.Color();
    var rails = [];
    for (var r = 0; r < 4; r++) {
      var rail = addRing(radius + r * 0.12, 0.018, [0x39eaff, 0xff48d7, 0x9b70ff, 0xffffff][r],
        [0, 0, 0]);
      rail.position.z = -r * 5;
      rails.push(rail);
    }
    beats('beat');
    S.focusY = 0;
    S.update = function (t) {
      var idx = 0;
      for (var ri = 0; ri < rings; ri++) {
        var z = -frac((ri * spacing + t * 3.3) / length) * length;
        var depth = 0.72 + 0.28 * Math.cos(ri / rings * Math.PI);
        var rot = ri * 0.23 + t * (ri % 2 ? 0.55 : -0.48);
        for (var k0 = 0; k0 < sides; k0++) {
          var a = rot + k0 / sides * TAU;
          var rr0 = radius * (1 + 0.07 * Math.sin(ri * 0.45 - t * 2.3));
          dm.position.set(Math.cos(a) * rr0, Math.sin(a) * rr0, z);
          dm.rotation.set(a + t * 0.8, t * 0.7 + ri * 0.12, a * 0.5);
          var s = (0.56 + 0.16 * Math.sin(ri * 0.6 + t * 3)) * depth;
          dm.scale.setScalar(s); dm.updateMatrix(); m.setMatrixAt(idx, dm.matrix);
          m.setColorAt(idx, pal(ri / rings + k0 / sides * 0.16 + t * 0.025, col));
          idx++;
        }
      }
      m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true;
      rails.forEach(function (rail, j) {
        rail.position.z = -frac(t * 2.4 + j * 0.24) * 18;
        rail.rotation.z = t * (0.11 + j * 0.035);
      });
      S.cam.position.set(Math.sin(t * 0.45) * 0.20, Math.cos(t * 0.5) * 0.17, 2.6);
      S.cam.lookAt(0, 0, -13);
    };
  };

  /* 5 — Bubbles burst in a travelling wave, then snap back into a perfect grid. */
  builders.bubbles = function () {
    var cols = [10, 12, 14, 16][P.density], rows = [17, 20, 23, 26][P.density];
    var count = cols * rows, gap = 0.52, items = [], order, m = inst(count, 'sphere', 0.48);
    var dm = new THREE.Object3D(), col = new THREE.Color();
    for (var r = 0; r < rows; r++) for (var c = 0; c < cols; c++) {
      var x = (c - (cols - 1) / 2) * gap, y = (r - (rows - 1) / 2) * gap;
      items.push({ x: x, y: y, z: -0.35 * Math.cos(x * 0.7) });
    }
    var cx = (S.rand() - 0.5) * 2.2, cy = (S.rand() - 0.5) * 3.2;
    order = items.map(function (q, i) {
      return { i: i, d: Math.hypot(q.x - cx, q.y - cy) + S.rand() * 0.35 };
    }).sort(function (a, b) { return a.d - b.d; });
    var popGap = Math.min(P.beat / 3, P.duration * 0.51 / count);
    var rebuild = 1.0 + count * popGap + 0.85;
    order.forEach(function (q, i) {
      items[q.i].popAt = 0.24 + i * popGap;
      items[q.i].backAt = rebuild + i * popGap * 0.28;
      S.events.push({ t: items[q.i].popAt, kind: 'pop', pitch: i });
    });
    for (var i = 0; i < count; i++) m.setColorAt(i,
      pal(frac(items[i].y / (rows * gap) + 0.5 + items[i].x * 0.035), col));
    m.instanceColor.needsUpdate = true;
    var dist = fit(rows * gap / 2 + 1, cols * gap / 2 + 1) * 1.08;
    S.focusY = 0;
    S.update = function (t) {
      for (var j = 0; j < count; j++) {
        var q = items[j], tau = t - q.popAt, s, z = q.z, dx = 0, dy = 0;
        if (tau < 0) s = 0.94 + 0.055 * Math.sin(t * 2.8 + j);
        else if (tau < 0.16) {
          s = 1 + 0.34 * Math.sin(Math.PI * tau / 0.16);
          z += Math.sin(tau * 18) * 0.18;
        } else {
          var back = ease((t - q.backAt) / 0.42);
          var pulse = Math.exp(-Math.max(0, tau - 0.16) * 2.5);
          s = 0.0001 + back * (0.97 + 0.06 * Math.sin(t * 3 + j));
          dx = (q.x > cx ? 1 : -1) * (1 - back) * 0.36;
          dy = (q.y > cy ? 1 : -1) * (1 - back) * 0.32;
          z += pulse * 0.3 * Math.sin(t * 4 + j);
        }
        dm.position.set(q.x + dx, q.y + dy, z);
        dm.rotation.set(t * 0.25 + j * 0.01, t * 0.32, 0);
        dm.scale.setScalar(s); dm.updateMatrix(); m.setMatrixAt(j, dm.matrix);
      }
      m.instanceMatrix.needsUpdate = true;
      camera(t, dist, 0.45, 0, true);
    };
  };

  /* 6 — Multiple colorful strands braid around one another. */
  builders.helix = function () {
    var strands = [3, 3, 4, 5][P.density], per = [46, 58, 70, 82][P.density];
    var count = strands * per, m = inst(count, P.shape, 0.48);
    var dm = new THREE.Object3D(), col = new THREE.Color(), dy = 0.205;
    var dist = fit(per * dy / 2 + 1.0, 4.3) * 1.10;
    beats('beat'); S.focusY = 0;
    S.update = function (t) {
      var idx = 0, spin = t * 0.62, wave = t * 2.4;
      for (var s = 0; s < strands; s++) for (var i = 0; i < per; i++) {
        var a = i * 0.31 + s / strands * TAU + spin;
        var w = 0.5 + 0.5 * Math.sin(i / per * TAU * 2 - wave + s * 0.6);
        var r = 2.15 + w * 0.75, scale = 0.43 + w * 0.38;
        dm.position.set(Math.cos(a) * r, (i - (per - 1) / 2) * dy, Math.sin(a) * r);
        dm.rotation.set(a, i * 0.18 + t * 0.45, w * 0.55);
        dm.scale.setScalar(scale); dm.updateMatrix(); m.setMatrixAt(idx, dm.matrix);
        m.setColorAt(idx, pal(i / per + s * 0.13 + t * 0.035, col));
        idx++;
      }
      m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true;
      camera(t, dist, dist * 0.18, 0, false);
    };
  };

  /* 7 — Concentric orbital machinery with a glowing central core. */
  builders.orbit = function () {
    var levels = [3, 4, 5, 6][P.density], per = 72, count = levels * per;
    var m = inst(count, 'icosahedron', 0.58), dm = new THREE.Object3D();
    var col = new THREE.Color(), rings = [], center = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.78, 2),
      new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.08, metalness: 0.48,
        emissive: 0x5b21ff, emissiveIntensity: 0.55, clearcoat: 1 }));
    S.scene.add(center);
    for (var l = 0; l < levels; l++) {
      var rr = 1.25 + l * 0.55;
      var ring = addRing(rr, 0.025, [0x35eaff, 0xff42d5, 0x8e72ff, 0x7effa8, 0xffd65c, 0xffffff][l]);
      ring.rotation.set(0.42 + l * 0.39, l * 0.24, l * 0.51);
      rings.push(ring);
    }
    var dist = fit(4.7, 4.5) * 1.18;
    S.focusY = 0; beats('plink');
    S.update = function (t) {
      var idx = 0;
      for (var q = 0; q < levels; q++) for (var j = 0; j < per; j++) {
        var a = j / per * TAU + t * (0.42 + q * 0.12) * (q % 2 ? -1 : 1);
        var rr0 = 1.25 + q * 0.55;
        var tilt = 0.45 + q * 0.22;
        var y = Math.sin(a * 1.8 + q * 0.7) * 0.42;
        dm.position.set(Math.cos(a) * rr0, y, Math.sin(a) * rr0 * Math.cos(tilt));
        dm.rotation.set(a, -a * 0.7, t * 0.55 + j * 0.025);
        var scale = 0.64 + 0.20 * Math.sin(t * 3 + j * 0.22 + q);
        dm.scale.setScalar(scale); dm.updateMatrix(); m.setMatrixAt(idx, dm.matrix);
        m.setColorAt(idx, pal(j / per + q / levels * 0.3 + t * 0.018, col)); idx++;
      }
      m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true;
      center.rotation.set(t * 0.42, t * 0.72, t * 0.31);
      center.scale.setScalar(1 + 0.08 * Math.sin(t * 4));
      rings.forEach(function (ring, i) {
        ring.rotation.y = i * 0.24 + t * (0.16 + i * 0.04);
        ring.rotation.z = i * 0.51 - t * 0.11;
      });
      camera(t, dist, 0.4, 0, false);
    };
  };

  /* 8 — A rotating crystal cluster locks into a brilliant symmetric formation. */
  builders.crystal = function () {
    var count = [64, 88, 112, 144][P.density], m = inst(count, 'icosahedron', 1.0);
    var dm = new THREE.Object3D(), col = new THREE.Color(), points = [];
    var golden = Math.PI * (3 - Math.sqrt(5));
    for (var i = 0; i < count; i++) {
      var y = 1 - (i / Math.max(1, count - 1)) * 2;
      var radius = Math.sqrt(1 - y * y), a = golden * i;
      var shell = 1.55 + 0.62 * (0.5 + 0.5 * Math.sin(i * 2.399));
      points.push({ x: Math.cos(a) * radius * shell, y: y * 4.9,
        z: Math.sin(a) * radius * shell, phase: a });
      m.setColorAt(i, pal(i / count, col));
    }
    m.instanceColor.needsUpdate = true;
    var halo1 = addRing(2.75, 0.035, 0x41eaff, [0.8, 0.1, 0.2]);
    var halo2 = addRing(3.15, 0.03, 0xff4bdd, [1.1, 0.8, 0.5]);
    var dist = fit(6.5, 3.9) * 1.14;
    S.focusY = 0; beats('plink');
    S.update = function (t) {
      var turn = t * 0.28;
      for (var j = 0; j < count; j++) {
        var q = points[j], c = Math.cos(turn), s = Math.sin(turn);
        var x = q.x * c - q.z * s, z = q.x * s + q.z * c;
        var pulse = 1 + 0.10 * Math.sin(t * 3.1 + q.phase);
        dm.position.set(x, q.y + 0.12 * Math.sin(t * 1.8 + q.phase), z);
        dm.rotation.set(t * 0.22 + q.phase, t * 0.35 + q.phase, t * 0.17);
        dm.scale.setScalar((0.52 + 0.13 * Math.sin(t * 2.6 + q.phase)) * pulse);
        dm.updateMatrix(); m.setMatrixAt(j, dm.matrix);
      }
      m.instanceMatrix.needsUpdate = true;
      halo1.rotation.y = t * 0.22; halo2.rotation.x = 1.1 + t * 0.19;
      halo2.rotation.z = t * -0.14;
      camera(t, dist, dist * 0.12, 0, false);
    };
  };

  /* 9 — Six arms of particles spiral inward and bloom outward in waves. */
  builders.vortex = function () {
    var arms = [4, 5, 6, 7][P.density], per = [62, 72, 82, 92][P.density];
    var count = arms * per, m = inst(count, P.shape, 0.43), dm = new THREE.Object3D();
    var col = new THREE.Color(), coords = [];
    for (var a = 0; a < arms; a++) for (var i = 0; i < per; i++) {
      coords.push({ arm: a, u: i / per, phase: S.rand() * TAU });
      m.setColorAt(a * per + i, pal(i / per + a / arms * 0.22, col));
    }
    m.instanceColor.needsUpdate = true;
    var dist = fit(5.1, 4.7) * 1.16;
    var core = new THREE.Mesh(new THREE.SphereGeometry(0.55, 36, 28),
      new THREE.MeshBasicMaterial({ color: 0xffffff }));
    S.scene.add(core);
    var halo = addRing(1.0, 0.045, 0x5ffaff, [Math.PI / 2, 0, 0]);
    S.focusY = 0; beats('beat');
    S.update = function (t) {
      for (var j = 0; j < count; j++) {
        var q = coords[j], a = q.arm / arms * TAU + q.u * TAU * 2.7 + t * 0.52;
        var pulse = 0.5 + 0.5 * Math.sin(t * 2.2 - q.u * 8 + q.phase);
        var rr = 0.42 + q.u * 3.5 + 0.22 * pulse;
        var y = (q.u - 0.5) * 8 + 0.42 * Math.sin(a * 1.2 + t);
        dm.position.set(Math.cos(a) * rr, y, Math.sin(a) * rr);
        dm.rotation.set(a, t + q.phase, a * 0.38);
        dm.scale.setScalar(0.26 + 0.24 * pulse);
        dm.updateMatrix(); m.setMatrixAt(j, dm.matrix);
      }
      m.instanceMatrix.needsUpdate = true;
      core.scale.setScalar(0.78 + 0.16 * Math.sin(t * 3.2));
      core.rotation.set(t * 0.6, t * 0.9, 0);
      halo.rotation.z = t * 0.42;
      camera(t, dist, 0.25, 0, false);
    };
  };

  /* 10 — A high-density 3D surface wave with synchronized traveling crests. */
  builders.wave = function () {
    var cols = [17, 20, 23, 26][P.density], rows = [27, 31, 35, 39][P.density];
    var count = cols * rows, m = inst(count, P.shape, 0.40), dm = new THREE.Object3D();
    var col = new THREE.Color(), points = [], cx = (cols - 1) / 2, cy = (rows - 1) / 2;
    for (var y = 0; y < rows; y++) for (var x = 0; x < cols; x++) {
      points.push({ x: (x - cx) * 0.39, y: (y - cy) * 0.39,
        d: Math.hypot(x - cx, y - cy) });
    }
    beats('beat');
    var dist = fit(rows * 0.39 / 2 + 1.5, cols * 0.39 / 2 + 1.2) * 1.12;
    S.focusY = 0;
    S.update = function (t) {
      for (var i = 0; i < count; i++) {
        var q = points[i], ph = t * 2.2;
        var h = Math.sin(q.x * 1.05 + ph) * 0.82 +
          Math.sin(q.y * 1.35 - ph * 1.18) * 0.42 +
          Math.sin(q.d * 0.72 - ph * 1.4) * 0.22;
        var scale = 0.55 + 0.32 * (0.5 + 0.5 * Math.sin(h * 2 + t));
        dm.position.set(q.x, q.y, h);
        dm.rotation.set(h * 0.12, ph * 0.08, h * 0.16);
        dm.scale.setScalar(scale); dm.updateMatrix(); m.setMatrixAt(i, dm.matrix);
        m.setColorAt(i, pal(frac((q.x + q.y) * 0.055 + h * 0.045 + t * 0.025), col));
      }
      m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true;
      camera(t, dist, 0.1, 0, true);
    };
  };

  /* 11 — A tall golden-ratio spiral assembles into a smooth rotating sculpture. */
  builders.spiral = function () {
    var count = [220, 280, 340, 420][P.density], m = inst(count, P.shape, 0.52);
    var dm = new THREE.Object3D(), col = new THREE.Color(), pts = [];
    var golden = Math.PI * (3 - Math.sqrt(5));
    for (var i = 0; i < count; i++) {
      var u = i / Math.max(1, count - 1), a = i * golden;
      pts.push({ u: u, a: a, radius: 0.8 + 2.15 * u,
        y: (u - 0.5) * 11.8 });
      m.setColorAt(i, pal(u, col));
    }
    m.instanceColor.needsUpdate = true;
    var dist = fit(6.8, 3.9) * 1.13;
    var baseRing = addRing(2.8, 0.028, 0x65f8ff, [Math.PI / 2, 0, 0]);
    baseRing.position.y = -5.6;
    var topRing = addRing(1.0, 0.025, 0xff4ed8, [Math.PI / 2, 0, 0]);
    topRing.position.y = 5.5;
    S.focusY = 0; beats('plink');
    S.update = function (t) {
      var turn = t * 0.38;
      for (var j = 0; j < count; j++) {
        var q = pts[j], a = q.a + turn;
        var wave = Math.sin(t * 2.4 - q.u * 13);
        var r = q.radius + 0.24 * wave;
        dm.position.set(Math.cos(a) * r, q.y + 0.12 * Math.sin(t * 1.8 + q.a),
          Math.sin(a) * r);
        dm.rotation.set(a, t * 0.4 + q.a, t * 0.25);
        dm.scale.setScalar(0.42 + 0.13 * (0.5 + 0.5 * wave));
        dm.updateMatrix(); m.setMatrixAt(j, dm.matrix);
      }
      m.instanceMatrix.needsUpdate = true;
      baseRing.rotation.y = t * 0.18; topRing.rotation.y = -t * 0.24;
      camera(t, dist, dist * 0.08, 0, false);
    };
  };

  /* 12 — Rotating gap-run game: the glass sphere clears the opening and multiplies. */
  builders.gaprun = function () {
    var radius = 2.62, gapCenter = Math.PI * 0.5, gapHalf = 0.29;
    var gapStart = gapCenter - gapHalf, gapEnd = gapCenter + gapHalf;
    var angularSpeed = 1.30, startAngle = gapStart - 0.88;
    var col = new THREE.Color();

    function arcMesh(r, tube, start, end, hex, glow) {
      var pts = [], segments = Math.max(32, Math.ceil((end - start) * 56));
      for (var i = 0; i <= segments; i++) {
        var a = start + (end - start) * i / segments;
        pts.push(new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0));
      }
      var curve = new THREE.CatmullRomCurve3(pts);
      var material = new THREE.MeshPhysicalMaterial({
        color: hex, emissive: hex, emissiveIntensity: glow,
        roughness: 0.14, metalness: 0.72, clearcoat: 1,
        clearcoatRoughness: 0.04
      });
      var mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, segments, tube, 12, false), material);
      S.scene.add(mesh);
      return mesh;
    }

    arcMesh(radius, 0.105, gapEnd, gapStart + TAU, 0x9afaff, 0.56);
    arcMesh(radius + 0.17, 0.034, gapEnd, gapStart + TAU, 0x27dfff, 0.9);
    arcMesh(radius - 0.17, 0.028, gapEnd, gapStart + TAU, 0xff4fd8, 0.82);
    arcMesh(radius - 0.34, 0.012, gapEnd, gapStart + TAU, 0xffffff, 0.5);

    var gateGeometry = new THREE.SphereGeometry(0.115, 24, 18);
    var gateColors = [0x45f5ff, 0xff4fd8];
    [gapStart, gapEnd].forEach(function (a, i) {
      var gate = new THREE.Mesh(gateGeometry, new THREE.MeshPhysicalMaterial({
        color: gateColors[i], emissive: gateColors[i], emissiveIntensity: 1.1,
        roughness: 0.1, metalness: 0.35, clearcoat: 1
      }));
      gate.position.set(Math.cos(a) * radius, Math.sin(a) * radius, 0.08);
      S.scene.add(gate);
    });

    var markerGeo = new THREE.OctahedronGeometry(0.105, 1);
    for (var k = 0; k < 8; k++) {
      var a0 = k / 8 * TAU;
      if (a0 > gapStart && a0 < gapEnd) continue;
      var marker = new THREE.Mesh(markerGeo, new THREE.MeshPhysicalMaterial({
        color: pal(k / 8, col), emissive: pal(k / 8, col), emissiveIntensity: 0.48,
        roughness: 0.17, metalness: 0.52, clearcoat: 1
      }));
      marker.position.set(Math.cos(a0) * (radius + 0.31), Math.sin(a0) * (radius + 0.31), 0.03);
      S.scene.add(marker);
    }

    arcMesh(radius * 0.43, 0.012, 0, TAU, 0x315b9e, 0.24);
    var core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.43, 2),
      new THREE.MeshPhysicalMaterial({
        color: 0x9b7bff, emissive: 0x5428ff, emissiveIntensity: 0.9,
        roughness: 0.12, metalness: 0.42, clearcoat: 1
      }));
    S.scene.add(core);

    function pointAt(unwrappedAngle) {
      var local = gapStart + (((unwrappedAngle - gapStart) % TAU) + TAU) % TAU;
      if (local >= gapStart && local <= gapEnd) {
        var u = clamp01((local - gapStart) / (gapEnd - gapStart));
        var one = 1 - u;
        var x0 = Math.cos(gapStart) * radius, y0 = Math.sin(gapStart) * radius;
        var x2 = Math.cos(gapEnd) * radius, y2 = Math.sin(gapEnd) * radius;
        var x1 = Math.cos(gapCenter) * radius * 0.35;
        var y1 = Math.sin(gapCenter) * radius * 0.35;
        return new THREE.Vector3(
          one * one * x0 + 2 * one * u * x1 + u * u * x2,
          one * one * y0 + 2 * one * u * y1 + u * u * y2,
          0.24
        );
      }
      return new THREE.Vector3(Math.cos(local) * radius, Math.sin(local) * radius, 0.24);
    }

    var shortcutPoints = [];
    for (var q = 0; q <= 30; q++) shortcutPoints.push(pointAt(gapStart + (gapEnd - gapStart) * q / 30));
    var shortcut = new THREE.Mesh(
      new THREE.TubeGeometry(new THREE.CatmullRomCurve3(shortcutPoints), 40, 0.022, 8, false),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.86,
        blending: THREE.AdditiveBlending, depthWrite: false })
    );
    S.scene.add(shortcut);

    var balls = [], ballGeometry = new THREE.SphereGeometry(0.235, 40, 28);
    for (var bi = 0; bi < 8; bi++) {
      var ballMaterial = mat(P.material || 'glass');
      ballMaterial.color.setHSL(frac(P.hue0 + bi * 0.105), 0.82, 0.66);
      ballMaterial.emissive.setHSL(frac(P.hue0 + bi * 0.105), 0.9, 0.28);
      ballMaterial.emissiveIntensity = 0.5;
      var ball = new THREE.Mesh(ballGeometry, ballMaterial);
      ball.visible = bi === 0;
      S.scene.add(ball);
      balls.push(ball);
    }
    var glow = new THREE.PointLight(0x5df5ff, 3.2, 5.5);
    balls[0].add(glow);

    var trailCount = 54, trailPositions = new Float32Array(trailCount * 3);
    var trailGeometry = new THREE.BufferGeometry();
    trailGeometry.setAttribute('position', new THREE.BufferAttribute(trailPositions, 3));
    var trail = new THREE.Line(trailGeometry, new THREE.LineBasicMaterial({
      color: 0x8bfaff, transparent: true, opacity: 0.88,
      blending: THREE.AdditiveBlending, depthWrite: false
    }));
    S.scene.add(trail);

    var burst = new THREE.Mesh(new THREE.TorusGeometry(0.46, 0.026, 10, 72),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0,
        blending: THREE.AdditiveBlending, depthWrite: false }));
    S.scene.add(burst);

    var dist = fit(3.55, 3.55) * 1.17;
    S.focusY = 0;
    beats('plink');
    var firstGapClear = (gapEnd - startAngle) / angularSpeed;
    for (var pass = 0; pass < 5; pass++) {
      S.events.push({ t: firstGapClear + pass * TAU / angularSpeed, kind: 'pop', pitch: pass });
    }

    S.update = function (t) {
      var angle = startAngle + t * angularSpeed;
      var cleared = Math.max(0, Math.floor((angle - gapEnd) / TAU) + 1);
      var stage = Math.min(3, cleared);
      var multiplier = [1, 2, 4, 8][stage];
      for (var b = 0; b < 8; b++) {
        var active = b < multiplier;
        balls[b].visible = active;
        if (!active) continue;
        var ballAngle = angle - b * (0.055 + stage * 0.012);
        var position = pointAt(ballAngle);
        balls[b].position.copy(position);
        balls[b].rotation.set(t * 3.6 + b, t * 4.2 + b * 0.4, t * 2.8);
        balls[b].scale.setScalar(1 + 0.075 * Math.sin(t * 8 - b * 0.7));
      }

      for (var tr = 0; tr < trailCount; tr++) {
        var sample = pointAt(angle - tr * 0.018);
        trailPositions[tr * 3] = sample.x;
        trailPositions[tr * 3 + 1] = sample.y;
        trailPositions[tr * 3 + 2] = 0.19 - tr * 0.0014;
      }
      trailGeometry.attributes.position.needsUpdate = true;
      trailGeometry.computeBoundingSphere();

      var age = ((((angle - gapEnd) % TAU) + TAU) % TAU) / angularSpeed;
      var flash = Math.exp(-age * 2.4);
      burst.position.set(0, 0, 0.22);
      burst.material.opacity = flash * 0.86;
      burst.scale.setScalar(0.3 + flash * 2.15);
      burst.rotation.z = t * 0.42;
      core.rotation.set(t * 0.34, t * 0.57, t * 0.26);
      core.scale.setScalar(1 + 0.11 * Math.sin(t * 3.2));

      S.cam.position.set(Math.sin(t * 0.20) * 0.72, Math.sin(t * 0.17) * 0.42, dist);
      S.cam.lookAt(0, 0, 0);
    };
  };

  window.initScene = function (params) {
    P = params;
    var W = window.innerWidth, H = window.innerHeight;
    document.body.style.background = '#000000';
    var renderer = new THREE.WebGLRenderer({
      canvas: document.getElementById('c'), antialias: true, alpha: false,
      preserveDrawingBuffer: true, powerPreference: 'high-performance'
    });
    renderer.setPixelRatio(1);
    renderer.setSize(W, H, false);
    renderer.setClearColor(0x000000, 1);
    if (THREE.ACESFilmicToneMapping !== undefined) {
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.34;
    }
    if (THREE.sRGBEncoding !== undefined) renderer.outputEncoding = THREE.sRGBEncoding;
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);
    scene.fog = new THREE.FogExp2(0x000000, 0.008);
    var cam = new THREE.PerspectiveCamera(39, W / H, 0.1, 220);
    scene.add(new THREE.HemisphereLight(0xc9e8ff, 0x26104d, 1.32));
    var key = new THREE.DirectionalLight(0xffffff, 1.8);
    key.position.set(7, 11, 9); scene.add(key);
    var rim = new THREE.DirectionalLight(0x4b7bff, 1.25);
    rim.position.set(-8, 5, -7); scene.add(rim);
    var pink = new THREE.PointLight(0xff38cc, 42, 24);
    pink.position.set(-4, 4, 5); scene.add(pink);
    var cyan = new THREE.PointLight(0x36eaff, 38, 24);
    cyan.position.set(4, -3, 4); scene.add(cyan);
    S = { r: renderer, scene: scene, cam: cam, rand: mulberry(P.seed),
      events: [], update: null, payoff: null, focusY: 0 };
    window.__renderer = renderer;
    addStars();
    if (!builders[P.scene]) throw new Error('Unknown 3D scene: ' + P.scene);
    builders[P.scene]();
    addPayoff();
    S.events.sort(function (a, b) { return a.t - b.t; });
    return { events: S.events };
  };

  window.renderAt = function (t) {
    S.update(t);
    if (S.payoff) S.payoff(t);
    S.r.render(S.scene, S.cam);
    return true;
  };
})();
