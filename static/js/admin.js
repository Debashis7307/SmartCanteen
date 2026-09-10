/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — Admin Analytics Dashboard (admin.js)
   ───────────────────────────────────────────────────────────────
   Day 8 (theory): turning MongoDB aggregation JSON (Day 13–15) into
   Chart.js canvases + a custom CSS-grid heatmap.

   Every chart uses animated gradients, entrance animations, and
   rich tooltips so the admin dashboard feels alive and readable.
   ═══════════════════════════════════════════════════════════════ */

let period = 'week';
let charts = {};
const PALETTE = ['#7c3aed', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#a855f7', '#ef4444', '#3b82f6'];

async function adminInit() {
  if (!Auth.isLoggedIn()) { location.href = '/login'; return; }
  if (!Auth.isAdmin()) {
    document.body.innerHTML = `<div class="container"><div class="empty" style="margin-top:60px"><div class="emoji">🚫</div><p>Admin access only.</p><a href="/" class="btn btn-ghost mt">Home</a></div></div>`;
    return;
  }
  initAdminTabs();
  bindPeriod();
  await loadAll();
  await loadMenuList();  // pre-load menu management list
}

/* ── Admin tabs ─────────────────────────────────────────────── */
function initAdminTabs() {
  document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.admin-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panelId = 'tab-' + tab.dataset.tab;
      const panel = document.getElementById(panelId);
      if (panel) panel.classList.add('active');
    });
  });
}

function bindPeriod() {
  document.querySelectorAll('.period-btn').forEach(b =>
    b.onclick = () => {
      period = b.dataset.period;
      document.querySelectorAll('.period-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      loadAll();
    });
}

async function loadAll() {
  await Promise.all([loadSummary(), loadRevenue(), loadPopular(), loadPeak(),
                     loadWaste(), loadTopStudents(), loadCategory()]);
}

/* ── KPI summary with animated count-up ─────────────────────── */
async function loadSummary() {
  try {
    const r = await API.get(`/api/analytics/summary?period=${period}`);
    const d = r.data;
    countUp('kpi-revenue', d.revenue, v => '₹' + Math.round(v).toLocaleString('en-IN'));
    countUp('kpi-orders', d.orders);
    countUp('kpi-avg', d.avg_order, v => '₹' + Math.round(v).toLocaleString('en-IN'));
    countUp('kpi-live', d.live_orders);
    countUp('kpi-waste', d.waste_orders);
  } catch {}
}

function countUp(id, target, fmt) {
  const el = document.getElementById(id);
  if (!el) return;
  const start = 0;
  const duration = 900;
  const t0 = performance.now();
  function tick(now) {
    const p = Math.min((now - t0) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);          // easeOutCubic
    const val = start + (target - start) * eased;
    el.textContent = fmt ? fmt(val) : Math.round(val);
    if (p < 1) requestAnimationFrame(tick);
    else el.textContent = fmt ? fmt(target) : target;
  }
  requestAnimationFrame(tick);
}

/* ── revenue bar chart with gradient + trend line ──────────── */
async function loadRevenue() {
  try {
    const r = await API.get(`/api/analytics/revenue?period=${period}`);
    const data = r.data || [];
    const labels = data.map(d => fmtDate(d.date));
    const totals = data.map(d => Math.round(d.total));
    const ctx = document.getElementById('revenueChart');
    if (charts.revenue) charts.revenue.destroy();

    charts.revenue = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Revenue (₹)',
            data: totals,
            backgroundColor: ctx => {
              const c = ctx.chart.ctx;
              const g = c.createLinearGradient(0, 0, 0, 280);
              g.addColorStop(0, 'rgba(168,85,247,0.9)');
              g.addColorStop(0.6, 'rgba(124,58,237,0.7)');
              g.addColorStop(1, 'rgba(6,182,212,0.5)');
              return g;
            },
            hoverBackgroundColor: ctx => {
              const c = ctx.chart.ctx;
              const g = c.createLinearGradient(0, 0, 0, 280);
              g.addColorStop(0, 'rgba(168,85,247,1)');
              g.addColorStop(1, 'rgba(6,182,212,0.8)');
              return g;
            },
            borderRadius: 10,
            maxBarThickness: 50,
            order: 2,
          },
          {
            label: 'Trend',
            data: totals,
            type: 'line',
            borderColor: '#f59e0b',
            borderWidth: 2.5,
            borderDash: [6, 4],
            pointBackgroundColor: '#f59e0b',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            pointRadius: 5,
            pointHoverRadius: 7,
            tension: 0.35,
            fill: false,
            order: 1,
          },
        ],
      },
      options: chartOpts({ legend: false, yMoney: true }),
    });
  } catch {}
}

/* ── top dishes horizontal bar chart ───────────────────────── */
async function loadPopular() {
  try {
    const r = await API.get(`/api/analytics/popular?period=${period}&limit=5`);
    const data = r.data || [];
    const labels = data.map(d => `${d.emoji || '🍽️'} ${d.name}`);
    const counts = data.map(d => d.total_ordered);
    const ctx = document.getElementById('popularChart');
    if (charts.popular) charts.popular.destroy();

    charts.popular = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Orders',
          data: counts,
          backgroundColor: ctx => {
            const i = ctx.dataIndex;
            const colors = ['#10b981', '#06b6d4', '#7c3aed', '#a855f7', '#ec4899'];
            return colors[i % colors.length];
          },
          borderRadius: 8,
          maxBarThickness: 28,
        }],
      },
      options: { ...chartOpts({ legend: false }), indexAxis: 'y' },
    });

    // ranked table
    const tb = document.getElementById('popular-table');
    tb.innerHTML = data.map((d, i) => `
      <tr><td class="rank">#${i+1}</td><td>${d.emoji||'🍽️'} ${escapeHtml(d.name)}</td>
      <td>${d.total_ordered}</td><td class="green">${money(d.revenue)}</td></tr>`).join('') ||
      `<tr><td colspan="4" class="faint text-center">No data yet</td></tr>`;
  } catch {}
}

/* ── PEAK HOURS HEATMAP (completely redesigned) ────────────── */
/* A CSS-grid heatmap with:
   • hour labels 7 AM–9 PM on the left, :00/:15/:30/:45 on top
   • color gradient from dark→yellow (like GitHub contributions)
   • hover tooltips with exact time + order count
   • staggered pop-in entrance animation
   • pulsing glow on the hottest cells
*/
async function loadPeak() {
  try {
    const r = await API.get(`/api/analytics/peak-hours?period=${period}`);
    const data = r.data || [];

    // Build the 2D grid: rows = hours 7..21, cols = 4 fifteen-min slots
    const HOURS = [];
    for (let h = 7; h <= 21; h++) HOURS.push(h);
    const SLOTS = [0, 1, 2, 3];
    const SLOT_LABELS = ['00', '15', '30', '45'];

    const grid = {};
    HOURS.forEach(h => { grid[h] = [0, 0, 0, 0]; });
    data.forEach(d => { if (grid[d.hour]) grid[d.hour][d.slot] = d.count; });

    const max = Math.max(1, ...HOURS.flatMap(h => grid[h]));
    const hotThreshold = max * 0.6;  // cells at or above this "pulse"

    // Assemble the HTML grid
    let html = '';
    // header row: empty corner + slot labels
    html += `<div class="hm-corner"></div>`;
    SLOT_LABELS.forEach(s => html += `<div class="hm-slot-label">:${s}</div>`);

    // body rows: hour label + 4 cells
    HOURS.forEach((h, hIdx) => {
      const ampm = h <= 12 ? `${h} AM` : `${h - 12} PM`;
      html += `<div class="hm-hour-label">${ampm}</div>`;
      SLOTS.forEach((s, sIdx) => {
        const count = grid[h][s];
        const intensity = count / max;
        const bg = heatColor(intensity);
        const isHot = count >= hotThreshold && count > 0;
        const delay = (hIdx * 4 + sIdx) * 28;  // staggered entrance
        html += `<div class="hm-cell ${isHot ? 'hot' : ''}"
          style="background:${bg};animation-delay:${delay}ms;${count === 0 ? 'color:transparent;' : ''}">
          ${count > 0 ? count : ''}
          <span class="hm-tooltip">${ampm} :${SLOT_LABELS[s]} · ${count} order${count !== 1 ? 's' : ''}</span>
        </div>`;
      });
    });

    const box = document.getElementById('heatmap');
    box.innerHTML = html;
  } catch {}
}

/* Heat color: 0 → dark surface, 1 → bright yellow (GitHub-style ramp) */
function heatColor(t) {
  if (t <= 0) return '#1c1e28';
  // interpolate through a warm gradient: dark→brown→orange→amber→yellow
  const stops = [
    { p: 0.00, c: [28, 30, 40] },     // #1c1e28 (surface)
    { p: 0.15, c: [59, 31, 14] },     // dark brown
    { p: 0.35, c: [124, 45, 18] },    // #7c2d12
    { p: 0.55, c: [234, 88, 12] },    // #ea580c
    { p: 0.75, c: [245, 158, 11] },   // #f59e0b
    { p: 1.00, c: [253, 224, 71] },   // #fde047
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    if (t <= stops[i + 1].p) {
      const span = stops[i + 1].p - stops[i].p;
      const f = (t - stops[i].p) / span;
      const r = Math.round(stops[i].c[0] + f * (stops[i + 1].c[0] - stops[i].c[0]));
      const g = Math.round(stops[i].c[1] + f * (stops[i + 1].c[1] - stops[i].c[1]));
      const b = Math.round(stops[i].c[2] + f * (stops[i + 1].c[2] - stops[i].c[2]));
      return `rgb(${r},${g},${b})`;
    }
  }
  return '#fde047';
}

/* ── waste tracker ─────────────────────────────────────────── */
async function loadWaste() {
  try {
    const r = await API.get(`/api/analytics/waste?period=${period}`);
    const data = r.data || [];
    const box = document.getElementById('waste-box');
    box.innerHTML = data.length ? data.map((d, i) => `
      <div class="menu-mgr-card fade-in" style="border-left:4px solid var(--red);animation-delay:${i * 60}ms">
        <span class="emoji">🗑️</span>
        <div class="info"><div class="nm">${escapeHtml(d._id)}</div>
        <div class="sub">${d.wasted_qty} wasted · ${d.count} cancelled order${d.count !== 1 ? 's' : ''}</div></div>
        <span class="red" style="font-weight:700">-${money(d.lost_revenue)}</span>
      </div>`).join('') :
      `<div class="empty"><div class="emoji">🎉</div><p>No wasted food this period — amazing!</p></div>`;
  } catch {}
}

/* ── top spending students ─────────────────────────────────── */
async function loadTopStudents() {
  try {
    const r = await API.get(`/api/analytics/top-students?period=${period}`);
    const data = r.data || [];
    const tb = document.getElementById('students-table');
    tb.innerHTML = data.map((d, i) => `
      <tr style="animation:fadeInUp .4s ease ${i * 50}ms both"><td class="rank">#${i+1}</td>
      <td>${escapeHtml(d.name)}</td><td>${d.orders}</td>
      <td class="green">${money(d.spent)}</td></tr>`).join('') ||
      `<tr><td colspan="4" class="faint text-center">No data yet</td></tr>`;
  } catch {}
}

/* ── category doughnut with center total ───────────────────── */
async function loadCategory() {
  try {
    const r = await API.get(`/api/analytics/categories?period=${period}`);
    const data = r.data || [];
    const labels = data.map(d => d._id);
    const values = data.map(d => Math.round(d.revenue));
    const total = values.reduce((s, v) => s + v, 0);
    const ctx = document.getElementById('categoryChart');
    if (charts.category) charts.category.destroy();

    charts.category = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: PALETTE,
          borderWidth: 0,
          hoverOffset: 14,
          borderColor: 'transparent',
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '64%',
        animation: { animateRotate: true, animateScale: true, duration: 900 },
        plugins: {
          legend: { position: 'right', labels: { color: '#c5c6c7', font: { size: 11 }, padding: 12, usePointStyle: true, pointStyle: 'circle' } },
          tooltip: { callbacks: { label: c => ` ${c.label}: ₹${c.parsed.toLocaleString('en-IN')}` } },
        },
      },
      plugins: [{
        // draw total in the doughnut center
        id: 'centerText',
        afterDraw(chart) {
          const { ctx, chartArea } = chart;
          if (!chartArea) return;
          const cx = (chartArea.left + chartArea.right) / 2;
          const cy = (chartArea.top + chartArea.bottom) / 2;
          ctx.save();
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillStyle = '#8a8fa8'; ctx.font = '500 11px Poppins';
          ctx.fillText('Total', cx, cy - 14);
          ctx.fillStyle = '#10b981'; ctx.font = '700 20px "Fira Code"';
          ctx.fillText('₹' + total.toLocaleString('en-IN'), cx, cy + 10);
          ctx.restore();
        },
      }],
    });
  } catch {}
}

/* ── CSV export ─────────────────────────────────────────────── */
function exportCsv() {
  const a = document.createElement('a');
  a.href = `/api/analytics/export?period=${period}`;
  a.download = `canteen_report_${period}.csv`;
  a.click();
  Toast.info('Preparing CSV download…');
}

/* ── shared chart options with animation ──────────────────── */
function chartOpts({ legend = true, yMoney = false } = {}) {
  return {
    responsive: true, maintainAspectRatio: false,
    animation: { duration: 800, easing: 'easeOutQuart' },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: legend, labels: { color: '#c5c6c7', usePointStyle: true, padding: 14 } },
      tooltip: {
        backgroundColor: '#1c1e28', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1,
        padding: 12, cornerRadius: 8, titleColor: '#fff', bodyColor: '#c5c6c7',
        callbacks: yMoney ? { label: c => '₹' + c.parsed.y.toLocaleString('en-IN') } : {} ,
      },
    },
    scales: {
      x: { ticks: { color: '#8a8fa8' }, grid: { display: false } },
      y: { ticks: { color: '#8a8fa8', callback: v => yMoney ? '₹' + v : v }, grid: { color: 'rgba(255,255,255,0.04)' } },
    },
  };
}

/* ══════════════════════════════════════════════════════════════
   MENU MANAGEMENT
   ══════════════════════════════════════════════════════════════ */

/* ── Load and render the dish list ─────────────────────────── */
async function loadMenuList() {
  const box = document.getElementById('menu-list');
  if (!box) return;
  box.innerHTML = `<div class="center-load"><div class="spinner"></div></div>`;
  try {
    const r = await API.get('/api/menu');
    const items = r.data || [];
    if (!items.length) {
      box.innerHTML = `<div class="empty"><div class="emoji">🍽️</div><p>No dishes yet — add the first one above.</p></div>`;
      return;
    }
    box.innerHTML = items.map((item, i) => `
      <div class="menu-mgr-card fade-in" style="animation-delay:${i*40}ms">
        <div class="emoji">${item.emoji || '🍽️'}</div>
        <div class="info">
          <div class="nm">${escapeHtml(item.name)} ${item.is_daily_special ? '<span style="font-size:.7rem;color:var(--orange2)">⭐ Special</span>' : ''}</div>
          <div class="sub">
            ${escapeHtml(item.category)} · ${money(item.price)} · Stock: ${item.stock_qty ?? '∞'}
            · ${item.is_available ? '<span style="color:var(--green2)">Available</span>' : '<span style="color:var(--red2)">Out of stock</span>'}
          </div>
        </div>
        <div class="actions">
          <button class="btn btn-ghost btn-sm" onclick="openEditModal(${JSON.stringify(item).replace(/'/g,"&#39;")})">✏️ Edit</button>
        </div>
      </div>`).join('');
  } catch {
    box.innerHTML = `<div class="empty"><p>Could not load menu.</p></div>`;
  }
}

/* ── Add new dish ────────────────────────────────────────────── */
async function addDish() {
  const name  = document.getElementById('dish-name').value.trim();
  const price = parseFloat(document.getElementById('dish-price').value);
  if (!name) return Toast.error('Dish name is required.');
  if (isNaN(price) || price <= 0) return Toast.error('Enter a valid price.');
  try {
    await API.post('/api/menu', {
      name,
      category: document.getElementById('dish-cat').value,
      price,
      description: document.getElementById('dish-desc').value.trim(),
      emoji: document.getElementById('dish-emoji').value.trim() || '🍽️',
      stock_qty: parseInt(document.getElementById('dish-stock').value) || 50,
      prep_time_mins: parseInt(document.getElementById('dish-prep').value) || 5,
      is_daily_special: document.getElementById('dish-special').checked,
    });
    Toast.success(`"${name}" added to the menu!`);
    // clear form
    ['dish-name','dish-price','dish-desc','dish-emoji','dish-stock','dish-prep'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });
    document.getElementById('dish-special').checked = false;
    await loadMenuList();
  } catch { /* toast shown */ }
}

/* ── Edit modal open/close ───────────────────────────────────── */
let _editItem = null;
function openEditModal(item) {
  _editItem = item;
  document.getElementById('edit-id').value = item._id;
  document.getElementById('edit-name').value = item.name;
  document.getElementById('edit-cat').value = item.category;
  document.getElementById('edit-price').value = item.price;
  document.getElementById('edit-stock').value = item.stock_qty ?? '';
  document.getElementById('edit-emoji').value = item.emoji || '';
  document.getElementById('edit-prep').value = item.prep_time_mins || '';
  document.getElementById('edit-desc').value = item.description || '';
  document.getElementById('edit-special').checked = !!item.is_daily_special;
  document.getElementById('edit-image').value = '';
  document.getElementById('edit-modal').classList.add('open');
}
function closeEditModal() {
  document.getElementById('edit-modal').classList.remove('open');
  _editItem = null;
}
document.addEventListener('DOMContentLoaded', () => {
  const em = document.getElementById('edit-modal');
  if (em) em.addEventListener('click', e => { if (e.target === em) closeEditModal(); });
});

/* ── Save dish changes ───────────────────────────────────────── */
async function saveDish() {
  const id = document.getElementById('edit-id').value;
  if (!id) return;
  const price = parseFloat(document.getElementById('edit-price').value);
  if (isNaN(price) || price <= 0) return Toast.error('Enter a valid price.');
  try {
    await API.put(`/api/menu/${id}`, {
      name:          document.getElementById('edit-name').value.trim(),
      category:      document.getElementById('edit-cat').value,
      price,
      description:   document.getElementById('edit-desc').value.trim(),
      emoji:         document.getElementById('edit-emoji').value.trim() || '🍽️',
      stock_qty:     parseInt(document.getElementById('edit-stock').value) || 50,
      prep_time_mins:parseInt(document.getElementById('edit-prep').value) || 5,
      is_daily_special: document.getElementById('edit-special').checked,
    });
    // upload image if one selected
    const imgInput = document.getElementById('edit-image');
    if (imgInput.files.length) {
      const fd = new FormData();
      fd.append('image', imgInput.files[0]);
      await fetch(`/api/menu/${id}/image`, { method: 'POST', body: fd });
    }
    Toast.success('Dish updated!');
    closeEditModal();
    await loadMenuList();
  } catch { /* toast shown */ }
}

/* ── Delete dish ─────────────────────────────────────────────── */
async function deleteDish() {
  const id = document.getElementById('edit-id').value;
  const name = document.getElementById('edit-name').value;
  if (!id) return;
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try {
    await API.del(`/api/menu/${id}`);
    Toast.success(`"${name}" removed from the menu.`);
    closeEditModal();
    await loadMenuList();
  } catch { /* toast shown */ }
}
