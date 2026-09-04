<script>
/* Paper Repro Runner — 天气背景引擎 v3
   依据工程研究报告实现：五层景深(L0天空→L4效果)、视差比 速度1:0.55:0.25×尺寸2.3:1.6:1×α1:0.7:0.5、
   大气透视、离屏预渲染、批量绘制、dt 时间步进、DPR≤2、resize 防抖、切换 400ms 淡入、帧耗时自动降级。
   天气状态：kind = clear|cloudy|fog|rain|heavy_rain|storm|snow ; day ; wind(px/s)
*/
(function () {
  var parent = window.parent.document;
  var P = window.parent;
  if (parent.getElementById('pr-weather-canvas')) { return; }
  var canvas = document.createElement('canvas');
  canvas.id = 'pr-weather-canvas';
  canvas.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:0;';
  parent.body.appendChild(canvas);
  var ctx = canvas.getContext('2d');
  var CFG = __CFG__;
  var kind = CFG.kind || 'calm', day = !!CFG.day, wind = (CFG.wind || 0) * 0.5;

  var W = 0, H = 0, DPR = 1, resizeT = 0, skip = 1, _skipCount = 0, _raf = 0;
  function doResize() {
    W = P.innerWidth; H = P.innerHeight;
    var want = Math.min(window.devicePixelRatio || 1, 2);
    var cap = Math.sqrt(3900000 / Math.max(W * H, 1));
    DPR = Math.max(0.7, Math.min(want, cap));
    canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    buildStatic();
  }
  P.addEventListener('resize', function () { clearTimeout(resizeT); resizeT = setTimeout(doResize, 150); });
  var TAU = Math.PI * 2;
  function rnd(a, b) { return a + Math.random() * (b - a); }
  var i, j;

  /* ============ 工具：离屏画布 ============ */
  function off(w, h) { var c = document.createElement('canvas'); c.width = w; c.height = h; return c; }

  /* ============ L0 天空（按天气渐变，缓存） ============ */
  var skyCanvas = null, skyAlpha = 0;
  var SKY = {
    clear:  [['#0a1428', '#13264d', '#1e3a6e', '#2b5291'], ['#3a2c10', '#6b4f16', '#a3761d', '#d9a03a']],
    cloudy: [['#0d1526', '#16213c', '#22315a', '#31446f'], ['#24303c', '#38485c', '#4d6178', '#64788c']],
    fog:    [['#10161f', '#1a222e', '#273342', '#34404f'], ['#333c46', '#4a5560', '#5f6d79', '#72818e']],
    rain:   [['#0a0f1e', '#0e1628', '#16233d', '#1d2d4a'], ['#121d2e', '#1c2b42', '#28405c', '#33516f']],
    snow:   [['#0e1626', '#1a2438', '#2a3850', '#3a4a66'], ['#202e42', '#32445c', '#485d78', '#5c728e']]
  };
  function buildSky() {
    var pal = SKY[kind] || SKY.rain;
    var seq = day ? pal[1] : pal[0];
    skyCanvas = off(1, 4);
    var g = skyCanvas.getContext('2d');
    var lg = g.createLinearGradient(0, 0, 0, 4);
    lg.addColorStop(0, seq[0]); lg.addColorStop(0.55, seq[1]);
    lg.addColorStop(0.85, seq[2]); lg.addColorStop(1, seq[3]);
    g.fillStyle = lg; g.fillRect(0, 0, 1, 4);
    skyAlpha = 0;
  }
  function drawSky(dt) {
    skyAlpha = Math.min(1, skyAlpha + dt * 2.5);   // 切换 400ms 淡入
    ctx.globalAlpha = skyAlpha;
    ctx.drawImage(skyCanvas, 0, 0, 1, 4, 0, 0, W, H);
    ctx.globalAlpha = 1;
    // 地平线光带（夜里青-品微弱，白天暖）
    var hg = ctx.createLinearGradient(0, H * 0.62, 0, H);
    var c0 = day ? '255, 214, 150' : '120, 200, 255', c1 = day ? '255, 170, 120' : '255, 90, 180';
    hg.addColorStop(0, 'rgba(' + c0 + ',0)');
    hg.addColorStop(0.5, 'rgba(' + (day ? c0 : c1) + ',0.05)');
    hg.addColorStop(1, 'rgba(' + c1 + ',0)');
    ctx.fillStyle = hg; ctx.fillRect(0, H * 0.62, W, H * 0.38);
  }

  /* ============ 太阳 / 月亮（离屏 sprite + 光晕） ============ */
  var orb = null, orbGlow = null;
  function buildOrb() {
    if (day) {
      var r = Math.max(26, Math.min(56, H * 0.05));
      orb = off(Math.ceil(r * 2 + 4), Math.ceil(r * 2 + 4));
      var g = orb.getContext('2d');
      var x = r + 2, y = r + 2;
      var rg = g.createRadialGradient(x - r * 0.2, y - r * 0.2, r * 0.1, x, y, r);
      rg.addColorStop(0, '#fffbe8'); rg.addColorStop(0.6, '#ffe9a8'); rg.addColorStop(1, 'rgba(255,205,92,0.9)');
      g.fillStyle = rg; g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill();
      orbGlow = off(Math.ceil(r * 12), Math.ceil(r * 12));
      var gg = orbGlow.getContext('2d');
      var cx = orbGlow.width / 2, cy = orbGlow.height / 2;
      var gr = gg.createRadialGradient(cx, cy, r * 0.4, cx, cy, r * 6);
      gr.addColorStop(0, 'rgba(255,232,160,0.5)'); gr.addColorStop(0.35, 'rgba(255,225,150,0.18)'); gr.addColorStop(1, 'rgba(255,220,140,0)');
      gg.fillStyle = gr; gg.beginPath(); gg.arc(cx, cy, r * 6, 0, TAU); gg.fill();
      orb.r = r;
    } else {
      var mr = Math.max(18, Math.min(36, H * 0.035));
      orb = off(Math.ceil(mr * 3), Math.ceil(mr * 3));
      var g2 = orb.getContext('2d');
      var mx = mr * 1.5, my = mr * 1.5;
      var mg = g2.createRadialGradient(mx - mr * 0.15, my - mr * 0.15, mr * 0.1, mx, my, mr);
      mg.addColorStop(0, 'rgba(252,252,255,1)'); mg.addColorStop(1, 'rgba(215,228,252,0.9)');
      g2.fillStyle = mg; g2.beginPath(); g2.arc(mx, my, mr, 0, TAU); g2.fill();
      g2.globalCompositeOperation = 'destination-out';
      g2.beginPath(); g2.arc(mx + mr * 0.5, my - mr * 0.2, mr * 0.95, 0, TAU); g2.fill();
      orbGlow = off(Math.ceil(mr * 10), Math.ceil(mr * 10));
      var gg2 = orbGlow.getContext('2d');
      var cx2 = orbGlow.width / 2, cy2 = orbGlow.height / 2;
      var gr2 = gg2.createRadialGradient(cx2, cy2, mr * 0.3, cx2, cy2, mr * 5);
      gr2.addColorStop(0, 'rgba(210,226,255,0.35)'); gr2.addColorStop(1, 'rgba(210,226,255,0)');
      gg2.fillStyle = gr2; gg2.beginPath(); gg2.arc(cx2, cy2, mr * 5, 0, TAU); gg2.fill();
      orb.r = mr;
    }
  }

  /* ============ 星空（预生成固定种子 + 相位分组） ============ */
  var stars = null, starTex = null, starDyn = null;
  function buildStars() {
    stars = [];
    var n = Math.min(420, Math.round(W * H / 5000));
    for (i = 0; i < n; i++) {
      var kindIdx = Math.random();
      var bright = kindIdx > 0.95 ? 1 : (kindIdx > 0.7 ? 0.6 : 0.28);
      stars.push({ x: rnd(0, W), y: rnd(0, H * 0.85), r: bright > 0.7 ? rnd(0.9, 1.6) : rnd(0.4, 1),
                   base: bright, ph: rnd(0, 2), grp: (i % 4) * 1.5708, sp: rnd(0.5, 2.5) });
    }
    // 静态星层离屏纹理（P1-5）：每帧 1 次 blit 替代数百次 fillRect
    starTex = off(Math.ceil(W), Math.ceil(H * 0.9));
    var g = starTex.getContext('2d');
    for (i = 0; i < stars.length; i++) {
      var s = stars[i];
      if (s.base > 0.85) continue;   // 亮星进动态层（闪烁+十字光芒）
      var mid = s.base * 0.72;
      g.fillStyle = 'rgba(225,235,255,' + mid + ')';
      g.fillRect(s.x, s.y, s.r, s.r);
    }
    starDyn = [];
    for (i = 0; i < stars.length; i++) {
      if (stars[i].base > 0.85) starDyn.push(stars[i]);
    }
  }
  function drawStars(t, dt) {
    ctx.drawImage(starTex, 0, 0, starTex.width, starTex.height);
    for (i = 0; i < starDyn.length; i++) {
      var s = starDyn[i];
      var a = s.base * (0.55 + 0.45 * Math.sin(s.grp + t * 0.001 * s.sp + s.ph));
      ctx.fillStyle = 'rgba(225,235,255,' + a + ')';
      ctx.fillRect(s.x, s.y, s.r, s.r);
      ctx.strokeStyle = 'rgba(220,235,255,' + (a * 0.5) + ')';
      ctx.lineWidth = 0.6;
      ctx.beginPath();
      ctx.moveTo(s.x - s.r * 3, s.y); ctx.lineTo(s.x + s.r * 3, s.y);
      ctx.moveTo(s.x, s.y - s.r * 3); ctx.lineTo(s.x, s.y + s.r * 3);
      ctx.stroke();
    }
  }

  /* ============ 云（每朵离屏预渲染，平移绘制） ============ */
  var clouds = [], cloudCover = 1;
  function buildCloud(dark) {
    var rx = W * rnd(0.14, 0.3), ry = rx * 0.34;
    var pad = 8;
    var cv = off(Math.ceil(rx * 2.4 + pad * 2), Math.ceil(ry * 2.2 + pad * 2));
    var g = cv.getContext('2d');
    var cx = cv.width / 2, cy = ry + pad;
    var col = dark ? '128,146,190' : '205,222,240';
    var blobs = [];
    blobs.push({ dx: 0, dy: 0, rx: rx * 0.62, ry: ry * 0.8, a: 0.9 });
    var nb = 7 + (Math.random() * 4 | 0);
    for (i = 0; i < nb; i++) {
      blobs.push({ dx: rnd(-0.8, 0.8) * rx, dy: -Math.random() * ry * 0.8 + ry * 0.12,
                   rx: rx * rnd(0.22, 0.55), ry: ry * rnd(0.3, 0.7), a: rnd(0.7, 1) });
    }
    blobs.sort(function (a, b) { return a.dy - b.dy; });
    for (i = 0; i < blobs.length; i++) {
      var b = blobs[i];
      var grd = g.createRadialGradient(cx + b.dx, cy + b.dy, 1, cx + b.dx, cy + b.dy, b.rx * 1.2);
      grd.addColorStop(0, 'rgba(' + col + ',' + (0.24 * b.a * (dark ? 1.15 : 1)) + ')');
      grd.addColorStop(1, 'rgba(' + col + ',0)');
      g.fillStyle = grd;
      g.beginPath(); g.ellipse(cx + b.dx, cy + b.dy, b.rx, b.ry, 0, 0, TAU); g.fill();
    }
    return { cv: cv, w: cv.width, h: cv.height, speed: rnd(0.06, 0.2) * (dark ? 1.3 : 1), x: rnd(-cv.width, W), y: rnd(-10, H * 0.34), a: 1, dark: dark };
  }
  function buildClouds() {
    clouds = [];
    var n = kind === 'cloudy' ? 4 : 3;
    for (i = 0; i < n; i++) clouds.push(buildCloud(!day));
  }
  function drawClouds(dt) {
    for (i = 0; i < clouds.length; i++) {
      var c = clouds[i];
      c.x += c.speed * dt * 60;
      if (c.x > W + c.w * 0.5) { c.x = -c.w; c.y = rnd(-10, H * 0.34); }
      ctx.drawImage(c.cv, c.x - c.w / 2, c.y - c.h / 2, c.w, c.h);
    }
  }

  /* ============ 雨（三层视差批量绘制 + 底部雨雾 + 涟漪） ============ */
  var rainLayers = null, ripples = [];
  function buildRain(heavy) {
    var density = Math.max(110, Math.round(W * H / (heavy ? 3800 : 13000)));
    if (heavy) density = Math.round(density);
    var spec = [
      { p: 0.40, len: [4, 9], vy: [24, 52], w: 0.6, a: [0.14, 0.22], tilt: 0.10 },
      { p: 0.35, len: [10, 18], vy: [100, 200], w: 0.9, a: [0.24, 0.36], tilt: 0.20 },
      { p: 0.25, len: [20, 36], vy: [220, 380], w: 1.5, a: [0.44, 0.6], tilt: 0.28 }
    ];
    if (!heavy) { spec[0].vy = [12, 30]; spec[1].vy = [60, 110]; spec[2].vy = [130, 220]; }
    rainLayers = [];
    for (i = 0; i < 3; i++) {
      var s = spec[i];
      var arr = [];
      var n = Math.max(8, Math.round(density * s.p));
      for (j = 0; j < n; j++) arr.push(spawnDrop(s, true));
      rainLayers.push({ spec: s, drops: arr });
    }
  }
  function spawnDrop(s, any) {
    var m = 40;
    return { x: rnd(-m, W + m), y: any ? rnd(-40, H + 40) : rnd(-60, -10), vy: rnd(s.vy[0], s.vy[1]), len: rnd(s.len[0], s.len[1]), a: rnd(s.a[0], s.a[1]) };
  }
  function drawRain(dt) {
    var groundY = H * 0.965;
    // 底部雨雾渐变带
    var rg = ctx.createLinearGradient(0, H * 0.9, 0, H);
    rg.addColorStop(0, 'rgba(150,195,235,0)');
    rg.addColorStop(1, 'rgba(150,195,235,0.10)');
    ctx.fillStyle = rg; ctx.fillRect(0, H * 0.9, W, H * 0.1);
    var li;
    for (li = 0; li < 3; li++) {
      var L = rainLayers[li], s = L.spec;
      var windT = Math.tan(s.tilt + Math.abs(wind) * 0.004) * (wind < 0 ? -1 : 1);
      ctx.beginPath();
      for (i = 0; i < L.drops.length; i++) {
        var d = L.drops[i];
        d.y += d.vy * dt;
        d.x += windT * d.vy * 0.6 * dt;
        var lx = Math.sin(windT) * d.len, ly = Math.cos(windT) * d.len;
        ctx.moveTo(d.x, d.y);
        ctx.lineTo(d.x - lx * 1.6, d.y - ly);
        if (d.y > H + 20) { L.drops[i] = spawnDrop(s, false); }
        else if (li === 2 && d.y > groundY && Math.random() < 0.25 && ripples.length < 60) {
          ripples.push({ x: d.x, y: H * 0.985 + rnd(0, 6), r: 1.5, vr: rnd(16, 46), a: rnd(0.25, 0.4) });
          L.drops[i] = spawnDrop(s, false);
        }
      }
      ctx.strokeStyle = 'rgba(' + (day ? '190,215,250' : '150,210,250') + ',0.6)';
      ctx.lineWidth = s.w; ctx.lineCap = 'round';
      ctx.stroke();
    }
    // 涟漪（交换删除）
    for (i = ripples.length - 1; i >= 0; i--) {
      var r = ripples[i];
      r.r += r.vr * dt; r.a *= Math.pow(0.25, dt);
      if (r.a < 0.015 || r.r > 90) { ripples[i] = ripples[ripples.length - 1]; ripples.pop(); continue; }
      ctx.strokeStyle = 'rgba(185,225,255,' + r.a + ')';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.ellipse(r.x, r.y, r.r, r.r * 0.32, 0, 0, TAU); ctx.stroke();
      ctx.strokeStyle = 'rgba(220,240,255,' + r.a * 1.3 + ')';
      ctx.beginPath(); ctx.ellipse(r.x, r.y, r.r * 0.55, r.r * 0.18, 0, 0, TAU); ctx.stroke();
    }
  }

  /* ============ 雪（sprite 圆点 + 少量六角） ============ */
  var snowDots = null;
  function makeFlakeSprite(r) {
    var s = Math.ceil(r * 2 + 6);
    var cv = off(s, s);
    var g = cv.getContext('2d');
    var gr = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, r);
    gr.addColorStop(0, 'rgba(255,255,255,1)');
    gr.addColorStop(0.7, 'rgba(255,255,255,0.85)');
    gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr;
    g.beginPath(); g.arc(s / 2, s / 2, r, 0, TAU); g.fill();
    return { cv: cv, size: s, r: r };
  }
  function buildSnow() {
    var density = Math.max(100, Math.round(W * H / 6000));
    var sprites = [makeFlakeSprite(3), makeFlakeSprite(5), makeFlakeSprite(8)];
    snowDots = { spec: [{ p: 0.45, sp: 0, vy: [16, 45], sw: [6, 16], a: [0.4, 0.6] },
                        { p: 0.33, sp: 1, vy: [45, 90], sw: [12, 26], a: [0.55, 0.75] },
                        { p: 0.22, sp: 2, vy: [80, 160], sw: [22, 44], a: [0.75, 0.95] }], flakes: [], sprites: sprites };
    for (i = 0; i < density; i++) {
      var l = Math.random();
      var s = l < 0.45 ? snowDots.spec[0] : (l < 0.78 ? snowDots.spec[1] : snowDots.spec[2]);
      snowDots.flakes.push({ x: rnd(-10, W), y: rnd(-10, H), sp: s.sp, vy: rnd(s.vy[0], s.vy[1]), sw: rnd(s.sw[0], s.sw[1]), ph: rnd(0, TAU), a: rnd(s.a[0], s.a[1]) });
    }
  }
  function drawSnow(dt, t) {
    var fl, spr;
    for (i = 0; i < snowDots.flakes.length; i++) {
      fl = snowDots.flakes[i];
      fl.y += fl.vy * dt;
      fl.x += (wind + Math.sin(t * 0.001 + fl.ph) * fl.sw) * dt;
      if (fl.y > H + 10) { fl.y = -10; fl.x = rnd(-10, W); }
      if (fl.x < -10) fl.x = W + 10; if (fl.x > W + 10) fl.x = -10;
      spr = snowDots.sprites[fl.sp];
      ctx.globalAlpha = fl.a;
      ctx.drawImage(spr.cv, fl.x - spr.r, fl.y - spr.r, spr.r * 2, spr.r * 2);
    }
    ctx.globalAlpha = 1;
    var sg = ctx.createLinearGradient(0, H * 0.93, 0, H);
    sg.addColorStop(0, 'rgba(220,235,250,0)');
    sg.addColorStop(1, 'rgba(220,235,250,0.06)');
    ctx.fillStyle = sg; ctx.fillRect(0, H * 0.93, W, H * 0.07);
  }

  /* ============ 雾（预渲染模糊 sprite） ============ */
  var fogBands = null;
  function buildFog() {
    fogBands = [];
    for (i = 0; i < 4; i++) {
      var bw = Math.ceil(W * 1.6), bh = Math.ceil(H * rnd(0.14, 0.3));
      var cv = off(bw, bh);
      var g = cv.getContext('2d');
      var n = 2 + (Math.random() * 2 | 0);
      for (j = 0; j < n; j++) {
        var ex = bw * rnd(0.25, 0.75), ey = bh * rnd(0.4, 0.7), er = bh * rnd(0.5, 0.8);
        var gr = g.createRadialGradient(ex, ey, er * 0.1, ex, ey, er);
        gr.addColorStop(0, 'rgba(175,198,225,0.16)');
        gr.addColorStop(1, 'rgba(175,198,225,0)');
        g.fillStyle = gr;
        g.beginPath(); g.ellipse(ex, ey, er, er * 0.42, 0, 0, TAU); g.fill();
      }
      try { g.filter = 'blur(' + Math.round(bh * 0.08) + 'px)'; g.fillRect(0, 0, bw, bh); } catch (e) {}
      fogBands.push({ cv: cv, w: bw, h: bh, x: rnd(-bw * 0.4, 0), y: rnd(H * 0.1, H * 0.9), spd: rnd(4, 12) });
    }
  }
  function drawFog(dt) {
    for (i = 0; i < fogBands.length; i++) {
      var f = fogBands[i];
      f.x += f.spd * dt;
      if (f.x > W) f.x = -f.w;
      ctx.drawImage(f.cv, f.x, f.y - f.h / 2, f.w, f.h);
    }
  }

  /* ============ 闪电（调度 + 指数衰减） ============ */
  var boltList = [], flashA = 0, nextBolt = 3000;
  function genBolt() {
    var pts = [[rnd(W * 0.2, W * 0.8), 0]];
    var cx = pts[0][0], cy = 0, remain = 220 + Math.random() * 240;
    while (remain > 0 && cy < H * 0.7) {
      cx += rnd(-36, 36) + (wind < 0 ? -6 : 6);
      cy += rnd(14, 34);
      pts.push([cx, cy]);
      remain -= 20;
    }
    boltList.push({ pts: pts, life: 1 });
    flashA = Math.max(flashA, rnd(0.26, 0.4));
  }
  function drawBolts(dt) {
    if (flashA > 0.01) {
      ctx.fillStyle = 'rgba(215,225,255,' + flashA + ')';
      ctx.fillRect(0, 0, W, H);
      flashA *= Math.exp(-dt / 0.055);
    }
    for (i = boltList.length - 1; i >= 0; i--) {
      var b = boltList[i];
      b.life -= dt * 5;
      if (b.life <= 0) { boltList.splice(i, 1); continue; }
      var al = Math.min(1, b.life * 2);
      ctx.save();
      ctx.lineJoin = 'round';
      ctx.strokeStyle = 'rgba(150, 180, 255,' + (al * 0.16) + ')';
      ctx.lineWidth = 8;
      ctx.beginPath(); ctx.moveTo(b.pts[0][0], b.pts[0][1]);
      for (j = 1; j < b.pts.length; j++) ctx.lineTo(b.pts[j][0], b.pts[j][1]);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(200, 214, 255,' + al + ')';
      ctx.lineWidth = 2.6;
      ctx.stroke();
      ctx.strokeStyle = 'rgba(255,255,255,' + al + ')';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();;
    }
  }

  /* ============ 性能：降级与调度 ============ */
  var frameMS = [], scale = 1;
  var startT = performance.now();

  function buildAll() {
    buildSky();
    buildOrb();
    if (!day && (kind === 'clear' || kind === 'cloudy')) buildStars();
    if (kind === 'cloudy' || kind === 'fog' || kind === 'rain' || kind === 'heavy_rain' || kind === 'storm' || kind === 'snow') buildClouds();
    if (kind === 'rain' || kind === 'heavy_rain') buildRain(false);
    if (kind === 'storm') buildRain(true);
    if (kind === 'snow') buildSnow();
    if (kind === 'fog') buildFog();
  }
  function buildStatic() { buildAll(); }
  doResize();

  /* ============ 主循环 ============ */
  var last = performance.now();
  function tick(now) {
    if (_skipCount % skip !== 0) { _skipCount++; _raf = requestAnimationFrame(_loop); return; }
    _skipCount++;
    var dtRaw = (now - last) / 16.667;
    last = now;
    var dt = Math.min(Math.max(dtRaw, 0), 3);
    var t = now - startT;
    ctx.clearRect(0, 0, W, H);
    drawSky(dt);
    if (kind === 'cloudy' || kind === 'fog' || kind === 'rain' || kind === 'heavy_rain' || kind === 'storm' || kind === 'snow') drawClouds(dt);
    if (fogBands) drawFog(dt);
    if (stars && !day) drawStars(t, dt);
    if (rainLayers) drawRain(dt);
    if (snowDots) drawSnow(dt, t);
    // 太阳 / 月亮 + 光晕
    if (orb) {
      var ox = day ? W * 0.72 : W * 0.85, oy = day ? H * 0.12 : H * 0.11;
      if (orbGlow) ctx.drawImage(orbGlow, ox - orbGlow.width / 2, oy - orbGlow.height / 2, orbGlow.width, orbGlow.height);
      ctx.drawImage(orb, ox - orb.r - 2, oy - orb.r - 2, orb.r * 2 + 4, orb.r * 2 + 4);
    }
    if (kind === 'storm') {
      if (now - startT > nextBolt) { genBolt(); nextBolt = now - startT + rnd(2500, 11000); }
    }
    if (boltList.length || flashA > 0.01) drawBolts(dt);
    // 动态降级
    frameMS.push(dtRaw);
    if (frameMS.length > 120) {
      var avg = frameMS.reduce(function (a, b) { return a + b; }, 0) / frameMS.length;
      frameMS.length = 0;
      if (avg > 20 && skip < 3) skip += 1;
      else if (avg < 11 && skip > 1) skip -= 1;
    }
    _raf = requestAnimationFrame(_loop);
  }
  function _loop(now) { tick(now); }
  P.document.addEventListener('visibilitychange', function () {
    if (P.document.hidden || document.hidden) { cancelAnimationFrame(_raf); }
    else { last = performance.now(); _raf = requestAnimationFrame(_loop); }
  });
  _raf = requestAnimationFrame(_loop);
})();
</script>
