/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — Live Order Tracking (track.js) v2
   Day 4/7: WebSocket rooms for real-time status updates
   ═══════════════════════════════════════════════════════════════ */

const STEPS = ['placed', 'preparing', 'ready', 'collected'];
let currentToken = null;

async function trackInit() {
  const params = new URLSearchParams(location.search);
  const token = params.get('token');
  const input = document.getElementById('token-input');
  if (token) { if (input) input.value = token; await lookupToken(token); }
  if (input) input.addEventListener('keydown', e => {
    if (e.key === 'Enter') lookupToken(input.value.trim());
  });
  wireSocket();
}

async function lookupToken(token) {
  if (!token) return;
  const stage = document.getElementById('track-stage');
  stage.innerHTML = `<div class="center-load"><div class="spinner"></div></div>`;
  try {
    const r = await API.get(`/api/orders/token/${token}`);
    renderOrder(r.data);
    joinRoom(token);
  } catch {
    stage.innerHTML = `<div class="empty"><div class="emoji">🔍</div><p>No order #${escapeHtml(String(token))} found today.</p></div>`;
  }
}

function renderOrder(order) {
  currentToken = order.token_number;
  const stage = document.getElementById('track-stage');
  const idx = STEPS.indexOf(order.status);
  const icons = { placed: '🧾', preparing: '👨‍🍳', ready: '✅', collected: '🥡', cancelled: '✕' };
  const isCancelled = order.status === 'cancelled';
  const isReady = order.status === 'ready';
  const itemsHtml = order.items.map(i =>
    `<div class="track-item-row"><span>${escapeHtml(i.quantity + '× ' + i.name)}</span></div>`).join('');

  stage.innerHTML = `
    <div class="track-card fade-in" style="margin:0 auto">
      <div class="track-live-badge">
        <span class="badge ${isCancelled ? 'cancelled' : 'live'}">
          <span class="dot"></span>${isCancelled ? 'Cancelled' : 'Live updates'}
        </span>
      </div>

      <div class="track-token-num">#${order.token_number}</div>
      <div class="track-student">${escapeHtml(order.student_name)}</div>

      ${isReady ? `
        <div class="ready-banner">
          <span class="rb-icon">🎉</span>
          <p>Your food is READY — come collect it!</p>
        </div>` : ''}

      ${!isCancelled ? `
      <div class="stepper">
        ${STEPS.filter(s=>s!=='cancelled').map((s, i) => {
          const done = i < idx; const active = i === idx;
          return `<div class="step ${done?'done':''} ${active?'active':''}">
            <div class="step-dot">${done ? '✓' : (icons[s]||'•')}</div>
            <div class="step-label">${s.charAt(0).toUpperCase()+s.slice(1)}</div>
          </div>`;}).join('')}
      </div>` : ''}

      <div class="track-items">
        ${itemsHtml}
        ${order.special_instructions ? `<div class="track-item-row" style="color:var(--orange2);font-size:.84rem">📝 ${escapeHtml(order.special_instructions)}</div>` : ''}
        <div class="track-total">
          <span>Total</span>
          <span class="green">${money(order.total_amount)}</span>
        </div>
      </div>

      ${!isCancelled && order.status !== 'collected' && order.status !== 'ready' ? `
      <div class="track-wait">
        <span class="wait-num">${order.orders_ahead ?? 0}</span>
        <span class="wait-lbl">order${(order.orders_ahead??0)!==1?'s':''} ahead · est. ~${order.estimated_wait_mins} min</span>
      </div>` : ''}

      <div class="muted" style="text-align:center;font-size:.78rem;margin-top:16px">
        Placed ${timeAgo(order.placed_at)}
      </div>
    </div>

    ${(order.status === 'collected' || order.status === 'ready') && Auth.isStudent() ? reviewSection(order) : ''}
    ${staffControls(order)}

    <div class="text-center" style="margin-top:22px">
      <a href="/menu" class="btn btn-ghost">← Back to menu</a>
    </div>`;
  initReveal();
}

/* ── Staff quick controls ─────────────────────────────────────── */
function staffControls(order) {
  if (!Auth.isStaff() && !Auth.isAdmin()) return '';
  const id = order._id; const s = order.status;
  let buttons = '';
  if (s === 'placed')
    buttons = `<button class="btn btn-orange" onclick="trackAdvance('${id}','preparing')">👨‍🍳 Start preparing</button>
               <button class="btn btn-ghost btn-sm" onclick="trackAdvance('${id}','cancelled')">✕ Cancel</button>`;
  else if (s === 'preparing')
    buttons = `<button class="btn btn-teal" onclick="trackAdvance('${id}','ready')">✅ Mark ready</button>`;
  else if (s === 'ready')
    buttons = `<button class="btn btn-ghost" onclick="trackAdvance('${id}','collected')">🥡 Mark collected</button>`;
  else return '';
  return `
    <div class="card glow-orange" style="max-width:600px;margin:22px auto">
      <div class="flex between center wrap gap">
        <div>
          <span class="role-tag staff">Staff controls</span>
          <p class="muted" style="font-size:.84rem;margin-top:6px">Update status — student screen updates instantly.</p>
        </div>
        <div class="flex gap-sm wrap">${buttons}</div>
      </div>
    </div>`;
}

async function trackAdvance(id, status) {
  try {
    const r = await API.patch(`/api/orders/${id}/status`, { status });
    Toast.success(r.message);
    renderOrder(r.data);
  } catch { /* toast shown */ }
}

/* ── Inline review on track page ─────────────────────────────── */
function reviewSection(order) {
  const first = order.items[0];
  return `
    <div class="card" style="max-width:600px;margin:22px auto" id="review-box">
      <h3 class="section-title" style="margin-top:0">⭐ Rate ${escapeHtml(first?.name||'your meal')}</h3>
      <div class="star-input" id="stars-track">
        <input type="radio" name="trating" id="ts5" value="5"><label for="ts5">★</label>
        <input type="radio" name="trating" id="ts4" value="4"><label for="ts4">★</label>
        <input type="radio" name="trating" id="ts3" value="3"><label for="ts3">★</label>
        <input type="radio" name="trating" id="ts2" value="2"><label for="ts2">★</label>
        <input type="radio" name="trating" id="ts1" value="1"><label for="ts1">★</label>
      </div>
      <div class="field mt">
        <textarea class="textarea" id="review-comment" placeholder="Tell the canteen how it was…" rows="2"></textarea>
      </div>
      <button class="btn btn-primary" onclick="submitTrackReview('${first?.item_id||''}')">Submit review</button>
    </div>`;
}

async function submitTrackReview(itemId) {
  const ratingEl = document.querySelector('#stars-track input:checked');
  if (!ratingEl) return Toast.warn('Pick a star rating first.');
  if (!itemId) return Toast.error('No item to review.');
  try {
    await API.post('/api/reviews', {
      item_id: itemId,
      rating: parseInt(ratingEl.value),
      comment: document.getElementById('review-comment')?.value || '',
    });
    Toast.success('Thanks for your review!');
    document.getElementById('review-box')?.remove();
  } catch { /* toast shown */ }
}

/* ── WebSocket live updates ────────────────────────────────────── */
function wireSocket() {
  const s = socket();
  if (!s) return;
  s.on('order_status_update', (data) => {
    if (currentToken && data.token !== currentToken) return;
    API.get(`/api/orders/token/${currentToken}`).then(r => renderOrder(r.data)).catch(() => {});
    if (data.status === 'ready') Toast.success('🎉 Your food is READY!', 6000);
    else Toast.info(`Order #${data.token} is now ${data.status}.`, 3000);
  });
}

function joinRoom(token) {
  const s = socket();
  if (!s) { setTimeout(() => joinRoom(token), 800); return; }
  // (Re)join the order's room on every connect/reconnect so live
  // status updates resume even after a dropped connection.
  s.on('connect', () => { if (currentToken) s.emit('track_order', { token: currentToken }); });
  if (s.connected) s.emit('track_order', { token });
}
