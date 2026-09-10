/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — My Orders history (my_orders.js)
   The student's personal order history + one-tap reorder (plan.md).
   ═══════════════════════════════════════════════════════════════ */

let myOrderList = [];

async function myOrdersInit() {
  if (!Auth.isLoggedIn()) { location.href = '/login'; return; }
  if (!Auth.isStudent()) {
    document.getElementById('orders-wrap').innerHTML =
      `<div class="empty"><div class="emoji">👥</div><p>Students see their own order history here.</p></div>`;
    return;
  }
  await loadMyOrders();
}

async function loadMyOrders() {
  const box = document.getElementById('orders-list');
  box.innerHTML = `<div class="center-load"><div class="spinner"></div></div>`;
  try {
    const r = await API.get('/api/orders/my');
    myOrderList = r.data || [];
    renderOrders();
  } catch { box.innerHTML = `<div class="empty"><p>Could not load orders.</p></div>`; }
}

function renderOrders() {
  const box = document.getElementById('orders-list');
  if (!myOrderList.length) {
    box.innerHTML = `<div class="empty"><div class="emoji">📦</div><p>No orders yet. <a href="/menu" class="teal">Browse the menu →</a></p></div>`;
    return;
  }
  // spending summary
  const total = myOrderList.reduce((s, o) => s + (o.total_amount || 0), 0);
  const collected = myOrderList.filter(o => o.status === 'collected').length;
  const summary = document.getElementById('orders-summary');
  if (summary) summary.innerHTML = `
    <div class="stat-card teal"><div class="label">Total orders</div><div class="value">${myOrderList.length}</div></div>
    <div class="stat-card green"><div class="label">Total spent</div><div class="value">${money(total)}</div></div>
    <div class="stat-card purple"><div class="label">Collected</div><div class="value">${collected}</div></div>`;

  box.innerHTML = myOrderList.map((o, i) => {
    const items = o.items.map(i2 => `${i2.quantity}× ${i2.emoji || ''} ${escapeHtml(i2.name)}`).join(' · ');
    return `
    <div class="my-order-card fade-in" style="animation-delay:${i*50}ms">
      <div class="my-order-head">
        <span class="my-order-token">#${o.token_number}</span>
        ${statusBadge(o.status)}
      </div>
      <div class="my-order-items">${escapeHtml(items)}
        ${o.special_instructions ? `<br><span class="orange" style="font-size:.8rem">📝 ${escapeHtml(o.special_instructions)}</span>` : ''}
      </div>
      <div class="my-order-foot">
        <span class="my-order-total">${money(o.total_amount)}</span>
        <span class="my-order-date">${fmtDate(o.placed_at)} ${fmtTime(o.placed_at)}</span>
        <div class="flex gap-sm">
          <a href="/track?token=${o.token_number}" class="btn btn-ghost btn-sm">🎯 Track</a>
          <button class="btn btn-teal btn-sm" onclick="reorder('${o._id}')">↻ Reorder</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

async function reorder(orderId) {
  try {
    const r = await API.post(`/api/orders/reorder/${orderId}`);
    const items = r.data.items || [];
    // stash the rebuilt cart in localStorage and bounce to menu to confirm
    localStorage.setItem('pending_cart', JSON.stringify(items));
    Toast.success('Cart loaded — confirm on the menu page.');
    setTimeout(() => location.href = '/menu?reorder=1', 700);
  } catch { /* toast shown */ }
}
