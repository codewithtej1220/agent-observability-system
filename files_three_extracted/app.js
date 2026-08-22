import * as THREE from 'three';

/* ============================================================
   CONFIG — swap these for real API calls when you wire up
   a backend. Every function below that says "MOCK" is the
   seam to replace.
   ============================================================ */
const COLORS = {
  papaya: 0xff7a1a,
  signal: 0x5b8cff,
  mint: 0x2ee6a6,
};

/* ============================================================
   1. MOCK DATA LAYER  (replace with fetch() to your API)
   ============================================================ */
function generateMockTraces(count = 24) {
  const descriptions = [
    'Testing PostgreSQL migration', 'Validating auth token refresh',
    'Summarizing customer ticket', 'Running vector search query',
    'Retrying failed webhook delivery', 'Parsing uploaded CSV batch',
    'Calling third-party pricing API', 'Generating embeddings for doc set',
    'Executing scheduled cron job', 'Reconciling ledger entries',
  ];
  const actions = ['continue', 'retry', 'halt', 'escalate'];
  const traces = [];
  const now = Date.now();

  for (let i = 0; i < count; i++) {
    const anomalous = Math.random() < 0.22;
    const score = anomalous
      ? 42 + Math.random() * 55
      : Math.random() * 30;
    traces.push({
      id: cryptoRandomId(),
      desc: descriptions[Math.floor(Math.random() * descriptions.length)],
      anomalous,
      score,
      action: anomalous ? actions[Math.floor(Math.random() * actions.length)] : 'continue',
      ts: new Date(now - Math.floor(Math.random() * 3600_000)),
    });
  }
  return traces.sort((a, b) => b.ts - a.ts);
}

function cryptoRandomId() {
  const hex = () => Math.floor(Math.random() * 0xffffffff).toString(16).padStart(8, '0');
  return `${hex().slice(0,8)}-${hex().slice(0,4)}-${hex().slice(0,4)}-${hex().slice(0,4)}-${hex()}${hex().slice(0,4)}`;
}

function generateSeries(range) {
  const points = range === '1H' ? 12 : range === '24H' ? 24 : 7;
  const labels = [];
  const data = [];
  for (let i = 0; i < points; i++) {
    if (range === '1H') labels.push(`${i * 5}m`);
    else if (range === '24H') labels.push(`${i}:00`);
    else labels.push(`Day ${i + 1}`);
    const base = 15 + Math.sin(i / 2) * 10 + Math.random() * 18;
    data.push(Math.max(0, Math.min(60, base)));
  }
  // guarantee at least one visible spike, echoing the "T1 anomaly" moment
  data[Math.floor(points * 0.6)] = 49.5;
  return { labels, data };
}

/* ============================================================
   2. STAT COUNTERS  (GSAP-driven count-up)
   ============================================================ */
function animateCount(el, target, decimals = 0, suffix = '') {
  const obj = { val: 0 };
  gsap.to(obj, {
    val: target,
    duration: 1.4,
    ease: 'power2.out',
    onUpdate: () => {
      el.textContent = obj.val.toFixed(decimals) + suffix;
    },
  });
}

function initHeaderCounters() {
  document.querySelectorAll('[data-count]').forEach((el) => {
    const target = parseFloat(el.getAttribute('data-count'));
    const decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
    const suffix = el.getAttribute('data-suffix') || '';
    animateCount(el, target, decimals, suffix);
  });
}

/* ============================================================
   3. SUMMARY STATS + CHART + TRACE LIST
   ============================================================ */
let allTraces = [];
let scoreChart = null;

function renderSummary(traces) {
  const total = traces.length;
  const anomalies = traces.filter(t => t.anomalous).length;
  const healthy = total - anomalies;
  const avgScore = total ? traces.reduce((s, t) => s + t.score, 0) / total : 0;

  animateCount(document.getElementById('totalTraces'), total, 0);
  animateCount(document.getElementById('anomalyCount'), anomalies, 0);
  animateCount(document.getElementById('healthyCount'), healthy, 0);
  animateCount(document.getElementById('avgScore'), avgScore, 1, '%');

  const anomalyPct = total ? (anomalies / total) * 100 : 0;
  const healthyPct = total ? (healthy / total) * 100 : 0;
  document.getElementById('anomalyPct').textContent = anomalyPct.toFixed(1) + '%';
  document.getElementById('healthyPct').textContent = healthyPct.toFixed(1) + '%';

  requestAnimationFrame(() => {
    document.getElementById('anomalyBar').style.width = anomalyPct + '%';
    document.getElementById('healthyBar').style.width = healthyPct + '%';
  });

  const badge = document.getElementById('alertBadge');
  badge.textContent = anomalies;
  badge.dataset.zero = anomalies === 0 ? 'true' : 'false';

  const trendPct = (Math.random() * 20 - 10).toFixed(0);
  const trendEl = document.getElementById('trendLabel');
  trendEl.textContent = `${trendPct < 0 ? '↓' : '↑'} ${Math.abs(trendPct)}% from last hour`;
  trendEl.className = 'trend ' + (trendPct < 0 ? 'trend-down' : 'trend-up');
}

function renderTraceList(traces) {
  const list = document.getElementById('traceList');
  document.getElementById('traceListCount').textContent = traces.length;
  list.innerHTML = '';

  traces.slice(0, 12).forEach((t) => {
    const row = document.createElement('div');
    row.className = 'trace-row' + (t.anomalous ? ' anomalous' : '');
    row.innerHTML = `
      <div class="trace-main">
        <span class="trace-desc">${escapeHtml(t.desc)}…</span>
        <span class="trace-id mono">ID: ${t.id}</span>
      </div>
      <div class="trace-meta">
        <span>Anomaly Score: <b>${t.score.toFixed(1)}%</b></span>
        <span>Action: <b>${t.action}</b></span>
        <span>Timestamp: <b>${t.ts.toLocaleTimeString()}</b></span>
      </div>
      <span class="status-chip ${t.anomalous ? 'anomalous' : 'healthy'}">
        ${t.anomalous
          ? '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3L2 20h20L12 3z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg> ANOMALOUS'
          : '<svg viewBox="0 0 24 24" fill="none"><path d="M4 12l5 5L20 6" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg> HEALTHY'}
      </span>
    `;
    list.appendChild(row);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function initChart(range = '1H') {
  const ctx = document.getElementById('scoreChart');
  const { labels, data } = generateSeries(range);

  const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, 'rgba(91,140,255,0.35)');
  gradient.addColorStop(1, 'rgba(91,140,255,0)');

  if (scoreChart) scoreChart.destroy();
  scoreChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Anomaly Score (%)',
        data,
        borderColor: '#5b8cff',
        backgroundColor: gradient,
        pointBackgroundColor: (c) => c.raw > 40 ? '#ff7a1a' : '#5b8cff',
        pointBorderColor: '#05070c',
        pointRadius: (c) => c.raw > 40 ? 5 : 3,
        pointHoverRadius: 7,
        borderWidth: 2.5,
        fill: true,
        tension: 0.35,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 900, easing: 'easeOutCubic' },
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#131a26',
          borderColor: 'rgba(255,255,255,0.12)',
          borderWidth: 1,
          titleColor: '#8b93a7',
          titleFont: { family: 'JetBrains Mono', size: 11 },
          bodyColor: '#f2f5fb',
          bodyFont: { family: 'JetBrains Mono', size: 13, weight: '600' },
          padding: 12,
          cornerRadius: 8,
          callbacks: {
            label: (c) => `Anomaly Score (%): ${c.raw.toFixed(1)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.05)', drawTicks: false },
          ticks: { color: '#545c6e', font: { family: 'JetBrains Mono', size: 10 } },
        },
        y: {
          min: 0, max: 60,
          grid: { color: 'rgba(255,255,255,0.05)', drawTicks: false, borderDash: [4, 4] },
          ticks: { color: '#545c6e', font: { family: 'JetBrains Mono', size: 10 }, stepSize: 15 },
        },
      },
    },
  });
}

/* ============================================================
   4. THREE.JS — RADAR TRACE VISUALIZATION
   ============================================================ */
function initTraceViz() {
  const frame = document.querySelector('.viz-frame');
  const canvas = document.getElementById('traceCanvas');

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x05070c, 0.045);

  const camera = new THREE.PerspectiveCamera(50, frame.clientWidth / frame.clientHeight, 0.1, 200);
  camera.position.set(0, 6, 22);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(frame.clientWidth, frame.clientHeight);

  // ---- soft radial glow texture, used for node sprites ----
  function makeGlowTexture(hex) {
    const size = 128;
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const g = c.getContext('2d');
    const color = new THREE.Color(hex);
    const r = Math.floor(color.r * 255), gr = Math.floor(color.g * 255), b = Math.floor(color.b * 255);
    const grad = g.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
    grad.addColorStop(0, `rgba(${r},${gr},${b},1)`);
    grad.addColorStop(0.35, `rgba(${r},${gr},${b},0.55)`);
    grad.addColorStop(1, `rgba(${r},${gr},${b},0)`);
    g.fillStyle = grad;
    g.fillRect(0, 0, size, size);
    return new THREE.CanvasTexture(c);
  }

  const blueGlow = makeGlowTexture(COLORS.signal);
  const papayaGlow = makeGlowTexture(COLORS.papaya);

  // ---- group everything so we can orbit as one unit ----
  const rig = new THREE.Group();
  scene.add(rig);

  // ---- floor grid, matching the reference screenshot ----
  const grid = new THREE.GridHelper(34, 22, 0x2a3550, 0x161d2c);
  grid.position.y = -6;
  rig.add(grid);

  // ---- generate trace nodes ----
  const NODE_COUNT = 42;
  const nodes = [];
  const nodeGroup = new THREE.Group();
  rig.add(nodeGroup);

  for (let i = 0; i < NODE_COUNT; i++) {
    const anomalous = Math.random() < 0.12;
    const radius = 4 + Math.random() * 9;
    const theta = Math.random() * Math.PI * 2;
    const y = (Math.random() - 0.3) * 8;

    const pos = new THREE.Vector3(
      Math.cos(theta) * radius,
      y,
      Math.sin(theta) * radius
    );

    const material = new THREE.SpriteMaterial({
      map: anomalous ? papayaGlow : blueGlow,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const sprite = new THREE.Sprite(material);
    const scale = anomalous ? 1.6 : 0.9 + Math.random() * 0.5;
    sprite.scale.set(scale, scale, 1);
    sprite.position.copy(pos);
    nodeGroup.add(sprite);

    nodes.push({ sprite, anomalous, basePos: pos.clone(), phase: Math.random() * Math.PI * 2 });
  }

  // ---- connective lines between nearby nodes ----
  const lineGeom = new THREE.BufferGeometry();
  const linePositions = [];
  const lineColors = [];
  const tmpColorBlue = new THREE.Color(COLORS.signal);
  const tmpColorPapaya = new THREE.Color(COLORS.papaya);

  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const d = nodes[i].basePos.distanceTo(nodes[j].basePos);
      if (d < 5.5 && Math.random() < 0.5) {
        linePositions.push(
          nodes[i].basePos.x, nodes[i].basePos.y, nodes[i].basePos.z,
          nodes[j].basePos.x, nodes[j].basePos.y, nodes[j].basePos.z
        );
        const c = (nodes[i].anomalous || nodes[j].anomalous) ? tmpColorPapaya : tmpColorBlue;
        lineColors.push(c.r, c.g, c.b, c.r, c.g, c.b);
      }
    }
  }
  lineGeom.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
  lineGeom.setAttribute('color', new THREE.Float32BufferAttribute(lineColors, 3));
  const lineMat = new THREE.LineBasicMaterial({
    vertexColors: true, transparent: true, opacity: 0.16, blending: THREE.AdditiveBlending,
  });
  const lines = new THREE.LineSegments(lineGeom, lineMat);
  rig.add(lines);

  // ---- expanding "detection pulse" rings for anomalous nodes ----
  const pulseRings = nodes.filter(n => n.anomalous).map((n) => {
    const geom = new THREE.RingGeometry(1, 1.05, 32);
    const mat = new THREE.MeshBasicMaterial({
      color: COLORS.papaya, transparent: true, opacity: 0.6,
      side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
    });
    const ring = new THREE.Mesh(geom, mat);
    ring.position.copy(n.basePos);
    ring.lookAt(camera.position);
    rig.add(ring);
    return { ring, node: n, t: Math.random() };
  });

  // ---- HUD readouts ----
  document.getElementById('hudNodes').textContent = NODE_COUNT;
  document.getElementById('hudAnomaly').textContent = nodes.filter(n => n.anomalous).length;

  // ---- interaction: drag to orbit, button to toggle auto-rotate ----
  let autoRotate = true;
  let isDragging = false;
  let lastX = 0, lastY = 0;
  let azimuth = 0, elevation = 0.22;

  const rotateBtn = document.getElementById('rotateBtn');
  const rotateIcon = document.getElementById('rotateIcon');
  const rotateLabel = document.getElementById('rotateLabel');

  rotateBtn.addEventListener('click', () => {
    autoRotate = !autoRotate;
    rotateBtn.dataset.active = String(autoRotate);
    rotateLabel.textContent = autoRotate ? 'Rotate' : 'Paused';
    rotateIcon.innerHTML = autoRotate
      ? '<path d="M8 5v14l11-7z" fill="currentColor"/>'
      : '<rect x="6" y="5" width="4" height="14" fill="currentColor"/><rect x="14" y="5" width="4" height="14" fill="currentColor"/>';
  });

  canvas.addEventListener('pointerdown', (e) => {
    isDragging = true; lastX = e.clientX; lastY = e.clientY;
  });
  window.addEventListener('pointerup', () => { isDragging = false; });
  window.addEventListener('pointermove', (e) => {
    if (!isDragging) return;
    const dx = e.clientX - lastX, dy = e.clientY - lastY;
    azimuth += dx * 0.005;
    elevation = Math.max(-0.6, Math.min(0.9, elevation + dy * 0.003));
    lastX = e.clientX; lastY = e.clientY;
  });

  // ---- resize handling ----
  function onResize() {
    const w = frame.clientWidth, h = frame.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  window.addEventListener('resize', onResize);

  // ---- scan clock ----
  const clock = new THREE.Clock();
  const scanEl = document.getElementById('hudScan');

  function formatClock(sec) {
    const h = String(Math.floor(sec / 3600)).padStart(2, '0');
    const m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
    const s = String(Math.floor(sec % 60)).padStart(2, '0');
    return `${h}:${m}:${s}`;
  }

  function animate() {
    requestAnimationFrame(animate);
    const t = clock.getElapsedTime();

    if (autoRotate) azimuth += 0.0026;

    camera.position.x = Math.sin(azimuth) * 22 * Math.cos(elevation);
    camera.position.z = Math.cos(azimuth) * 22 * Math.cos(elevation);
    camera.position.y = 6 + elevation * 14;
    camera.lookAt(0, -1, 0);

    // pulse anomalous nodes
    nodes.forEach((n) => {
      if (!n.anomalous) return;
      const s = 1.6 + Math.sin(t * 2.4 + n.phase) * 0.35;
      n.sprite.scale.set(s, s, 1);
    });

    // expanding detection rings
    pulseRings.forEach((p) => {
      p.t += 0.012;
      if (p.t > 1) p.t = 0;
      const scale = 1 + p.t * 3.2;
      p.ring.scale.set(scale, scale, scale);
      p.ring.material.opacity = 0.55 * (1 - p.t);
      p.ring.lookAt(camera.position);
    });

    scanEl.textContent = formatClock(t);

    renderer.render(scene, camera);
  }
  animate();
}

/* ============================================================
   5. WIRING
   ============================================================ */
function initToolbar() {
  document.getElementById('searchInput').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    const filtered = allTraces.filter(
      t => t.desc.toLowerCase().includes(q) || t.id.toLowerCase().includes(q)
    );
    renderTraceList(filtered);
  });

  document.getElementById('exportBtn').addEventListener('click', () => {
    const rows = [['id', 'description', 'anomalous', 'score', 'action', 'timestamp']];
    allTraces.forEach(t => rows.push([t.id, t.desc, t.anomalous, t.score.toFixed(1), t.action, t.ts.toISOString()]));
    const csv = rows.map(r => r.map(v => `"${v}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'traces.csv'; a.click();
    URL.revokeObjectURL(url);
  });

  document.getElementById('refreshBtn').addEventListener('click', () => {
    const icon = document.getElementById('refreshIcon');
    gsap.to(icon, { rotation: '+=360', duration: 0.6, ease: 'power2.inOut', transformOrigin: '50% 50%' });
    allTraces = generateMockTraces();
    renderSummary(allTraces);
    renderTraceList(allTraces);
  });

  document.getElementById('rangeToggle').addEventListener('click', (e) => {
    const btn = e.target.closest('.seg-btn');
    if (!btn) return;
    document.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    initChart(btn.dataset.range);
  });
}

function revealPanels() {
  gsap.to('[data-reveal]', {
    opacity: 1, y: 0, duration: 0.7, ease: 'power3.out', stagger: 0.1,
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderCounters();
  revealPanels();

  allTraces = generateMockTraces();
  renderSummary(allTraces);
  renderTraceList(allTraces);
  initChart('1H');
  initToolbar();
  initTraceViz();
});
