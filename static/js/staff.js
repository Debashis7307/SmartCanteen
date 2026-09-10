/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — Staff Kitchen Dashboard (staff.js)
   ───────────────────────────────────────────────────────────────
   Day 4/7 (theory): the kitchen board needs ZERO refreshes. New
   orders appear instantly via the `new_order` / `order_updated`
   WebSocket events.  Staff join the "staff_dashboard" room on load.
   ═══════════════════════════════════════════════════════════════ */

let liveOrders = [];
let menuItems = [];

async function staffInit() {
  if (!Auth.isLoggedIn()) { location.href = '/login'; return; }
  if (!Auth.isStaff() && !Auth.isAdmin()) {
    document.body.innerHTML = `<div class="container"><div class="empty" style="margin-top:60px"><div class="emoji">🚫</div><p>Staff access only.</p><a href="/" class="btn btn-ghost mt">Home</a></div></div>`;
    return;
  }
  await loadLive();
  await loadMenuMgr();
  joinStaffRoom();
  wireSocket();
}

async function loadLive() {
  try {
    const r = await API.get('/api/orders/live');
    liveOrders = r.data || [];
    renderBoard();
  } catch { /* toast shown */ }
}

function renderBoard() {
  const statuses = ['placed', 'preparing', 'ready'];
  const counts = { placed: 0, preparing: 0, ready: 0 };
  liveOrders.forEach(o => { if (counts[o.status] !== undefined) counts[o.status]++; });

  statuses.forEach(status => {
    const body = document.getElementById('body-' + status);
    const cnt  = document.getElementById('cnt-' + status);
    if (cnt) cnt.textContent = counts[status];
    if (!body) return;
    const orders = liveOrders.filter(o => o.status === status)
      .sort((a, b) => a.token_number - b.token_number);
    body.innerHTML = orders.length
      ? orders.map(orderCard).join('')
      : `<div class="empty" style="padding:30px 10px"><div class="emoji" style="font-size:2rem">😴</div><p style="font-size:.8rem">No orders</p></div>`;
  });
}

function orderCard(o) {
  const items = o.items.map(i => `<div class="item-line">${i.quantity}× ${i.emoji || ''} ${escapeHtml(i.name)}</div>`).join('');
  const paidBadge = o.payment_status === 'paid'
    ? '<span class="paid-badge">✅ Paid</span>'
    : '<span class="paid-badge pending">⏳ Pay at counter</span>';
  let actions = '';
  if (o.status === 'placed')
    actions = `<button class="btn btn-orange btn-sm" onclick="advance('${o._id}','preparing')">👨‍🍳 Start cooking</button>
               <button class="btn btn-ghost btn-sm" onclick="advance('${o._id}','cancelled')">✕ Cancel</button>`;
  else if (o.status === 'preparing')
    actions = `<button class="btn btn-teal btn-sm" onclick="advance('${o._id}','ready')">✅ Mark ready</button>`;
  else if (o.status === 'ready')
    actions = `<button class="btn btn-ghost btn-sm" onclick="advance('${o._id}','collected')">🥡 Collected</button>`;

  return `
    <div class="order-card" data-id="${o._id}">
      <div class="order-card-head">
        <span class="token-num">#${o.token_number}</span>
        ${paidBadge}
        <span class="order-time">${timeAgo(o.placed_at)}</span>
      </div>
      <div class="student-name">${escapeHtml(o.student_name)}</div>
      <div class="order-items-list">${items}</div>
      ${o.special_instructions ? `<div class="order-note">📝 ${escapeHtml(o.special_instructions)}</div>` : ''}
      <div class="order-amt">${money(o.total_amount)}</div>
      <div class="order-actions">${actions}</div>
    </div>`;
}

async function advance(id, status) {
  try {
    await API.patch(`/api/orders/${id}/status`, { status });
    // optimistically move it locally; the socket event will correct if needed
    liveOrders = liveOrders.map(o => o._id === id ? { ...o, status } : o);
    if (['collected', 'cancelled'].includes(status)) liveOrders = liveOrders.filter(o => o._id !== id);
    renderBoard();
  } catch { /* toast shown */ }
}

/* ── menu / out-of-stock management ─────────────────────────── */
async function loadMenuMgr() {
  const box = document.getElementById('menu-mgr');
  if (!box) return;
  try {
    const r = await API.get('/api/menu');
    // show ALL items incl. out of stock (we can't from /api/menu which
    // filters available) — instead query each? We'll show what we got.
    menuItems = r.data || [];
    renderMenuMgr();
  } catch { /* toast shown */ }
}
function renderMenuMgr() {
  const box = document.getElementById('menu-mgr');
  box.innerHTML = menuItems.map((m, i) => `
    <div class="stock-item fade-in" style="animation-delay:${i*35}ms">
      <div class="s-emoji">${m.emoji || '🍽️'}</div>
      <div class="s-info">
        <div class="s-name">${escapeHtml(m.name)}</div>
        <div class="s-price">${money(m.price)} · ${escapeHtml(m.category)}</div>
      </div>
      <label class="toggle" title="Toggle availability">
        <input type="checkbox" ${m.is_available ? 'checked' : ''} onchange="toggleStock('${m._id}', this.checked)"/>
        <span class="toggle-track"></span>
      </label>
    </div>`).join('') || `<div class="empty"><p>No menu items.</p></div>`;
}
async function toggleStock(id, available) {
  try {
    await API.patch(`/api/menu/${id}/availability`, { is_available: available });
    menuItems = menuItems.map(m => m._id === id ? { ...m, is_available: available } : m);
    renderMenuMgr();
    Toast.success(available ? 'Marked available.' : 'Marked out of stock.');
  } catch { /* toast shown */ }
}

/* ── real-time ──────────────────────────────────────────────── */
function joinStaffRoom() {
  const s = socket();
  if (!s) return;
  // (Re)join the staff room on every connect/reconnect so a dropped
  // socket doesn't silently stop delivering new orders.
  s.on('connect', () => s.emit('join_staff'));
  if (s.connected) s.emit('join_staff');
}
function wireSocket() {
  const s = socket();
  if (!s) return;
  s.on('new_order', (o) => {
    if (!liveOrders.find(x => x._id === o._id)) liveOrders.unshift(o);
    renderBoard();
    flashNew(o._id);
    // A prominent popup so the kitchen notices even from another tab.
    Toast.info(`🔔 New order #${o.token_number} — ${money(o.total_amount)}`, 6000);
    // gentle audio cue for the kitchen
    beep();
  });
  s.on('order_updated', (o) => {
    liveOrders = liveOrders.map(x => x._id === o._id ? o : x);
    if (['collected', 'cancelled'].includes(o.status)) liveOrders = liveOrders.filter(x => x._id !== o._id);
    renderBoard();
  });
  s.on('order_status_update', () => loadLive()); // keep in sync as a safety net
}
function flashNew(id) {
  setTimeout(() => {
    const el = document.querySelector(`.order-card[data-id="${id}"]`);
    if (el) { el.style.animation = 'popIn .4s ease both'; }
  }, 60);
}
function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator(); const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = 880; osc.type = 'sine';
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    osc.start(); osc.stop(ctx.currentTime + 0.25);
  } catch {}
}
