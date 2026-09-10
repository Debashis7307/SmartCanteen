/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — Menu Page (menu.js)
   ───────────────────────────────────────────────────────────────
   Day 8 (theory): State management. The `cart` array is the single
   source of truth; the UI is just a visual reflection of it. When
   the state changes we re-render the cart drawer.
   Loads the menu, filters/searches, builds a cart, places an order,
   and shows reviews. Real-time out-of-stock grays cards via the
   `menu_changed` WebSocket event (Day 4/7).
   ═══════════════════════════════════════════════════════════════ */

let allItems = [];
let activeCategory = 'all';
let cart = [];          // [{ item_id, name, price, emoji, quantity }]

async function menuInit() {
  if (!Auth.isLoggedIn()) { location.href = '/login'; return; }
  // Only students can place orders — hide the cart FAB for staff/admin.
  const fab = document.getElementById('cart-fab');
  if (fab && !Auth.isStudent()) {
    fab.style.display = 'none';
  }
  if (!Auth.isStudent()) {
    document.getElementById('student-only').classList.add('hide');
  }
  bindCart();
  bindSearch();
  restoreReorderCart();          // one-tap reorder: load stashed items
  await loadDishOfTheDay();
  await loadSuggestions();
  await loadMenu();
  wireSocket();
}

/* ── restore a cart pushed from /my-orders (plan.md: one-tap reorder) ── */
function restoreReorderCart() {
  const params = new URLSearchParams(location.search);
  if (params.get('reorder') !== '1') return;
  const stashed = localStorage.getItem('pending_cart');
  if (!stashed) return;
  try {
    const items = JSON.parse(stashed);
    // items are [{item_id, quantity}] — look up names/prices from menu
    API.get('/api/menu').then(r => {
      const byId = {};
      (r.data || []).forEach(i => byId[i._id] = i);
      cart = items.map(it => {
        const m = byId[it.item_id];
        if (!m) return null;
        return { item_id: it.item_id, name: m.name, price: m.price,
                 emoji: m.emoji, quantity: it.quantity };
      }).filter(Boolean);
      updateCartUI();
      if (cart.length) Toast.info(`Reorder loaded — ${cartCount()} item(s) in cart.`);
    });
  } catch {}
  localStorage.removeItem('pending_cart');
  history.replaceState(null, '', '/menu');
}

/* ── load + render menu ─────────────────────────────────────── */
async function loadMenu(query = '') {
  const grid = document.getElementById('menu-grid');
  grid.innerHTML = `<div class="center-load"><div class="spinner"></div></div>`;
  let url = '/api/menu';
  if (activeCategory !== 'all' && !query) url += `?category=${encodeURIComponent(activeCategory)}`;
  if (query) url += `?search=${encodeURIComponent(query)}`;
  try {
    const r = await API.get(url);
    allItems = r.data || [];
    renderMenu();
    renderCategoryChips();
  } catch { grid.innerHTML = emptyState('Could not load the menu 😕'); }
}

function renderCategoryChips() {
  const box = document.getElementById('cat-chips');
  if (!box) return;
  const cats = ['all', ...new Set(allItems.map(i => i.category))];
  // keep full category list stable across filters: pull from a cached set
  box.innerHTML = cats.map(c =>
    `<span class="chip ${c === activeCategory ? 'active' : ''}" onclick="filterCategory('${escapeHtml(c)}')">${c === 'all' ? '🍽️ All' : escapeHtml(c)}</span>`
  ).join('');
}

function filterCategory(c) { activeCategory = c; loadMenu(); }

function renderMenu() {
  const grid = document.getElementById('menu-grid');
  if (!allItems.length) { grid.innerHTML = emptyState('No dishes found 😕'); return; }
  grid.innerHTML = allItems.map(item => `
    <div class="menu-card ${item.is_available ? '' : 'out'} fade-in" data-id="${item._id}">
      ${item.is_available ? '' : '<span class="stock-flag">Out of stock</span>'}
      ${item.is_daily_special ? '<span class="special-flag">⭐ Special</span>' : ''}
      <div class="photo" data-photo="${item._id}">
        ${photoUrl(item._id) ? `<img src="${photoUrl(item._id)}" alt="${escapeHtml(item.name)}" onerror="this.replaceWith(document.createTextNode('${item.emoji || '🍽️'}'))">`
                              : (item.emoji || '🍽️')}
        <div class="photo-overlay"></div>
      </div>
      <div class="body">
        <span class="cat">${escapeHtml(item.category)}</span>
        <h3>${escapeHtml(item.name)}</h3>
        <p class="desc">${escapeHtml(item.description || '')}</p>
        <div class="meta">
          <span class="price">${money(item.price)}</span>
          <span class="rating">⭐ ${item.avg_rating?.toFixed(1) || '—'} <small class="faint">(${item.total_ratings || 0})</small></span>
        </div>
        <div class="card-actions">
          <button class="btn btn-teal btn-sm add-btn"
            ${item.is_available ? '' : 'disabled'}
            onclick="addToCart('${item._id}', ${item.price}, '${escapeHtml(item.name)}', '${item.emoji || '🍽️'}')">
            ${item.is_available ? '➕ Add' : 'Unavailable'}
          </button>
          <button class="btn btn-ghost btn-sm review-btn"
            onclick="openReviewModal('${item._id}','${escapeHtml(item.name)}','${item.emoji||'🍽️'}','${escapeHtml(item.category)}')">
            ⭐ Rate
          </button>
        </div>
      </div>
    </div>`).join('');
}

/* ── cart state ─────────────────────────────────────────────── */
function addToCart(id, price, name, emoji) {
  const existing = cart.find(i => i.item_id === id);
  if (existing) existing.quantity++;
  else cart.push({ item_id: id, name, price, emoji, quantity: 1 });
  updateCartUI();
  Toast.success(`${name} added`, 1800);
  bumpFab();
}
function changeQty(id, delta) {
  const it = cart.find(i => i.item_id === id);
  if (!it) return;
  it.quantity += delta;
  if (it.quantity <= 0) cart = cart.filter(i => i.item_id !== id);
  updateCartUI();
}
function removeItem(id) { cart = cart.filter(i => i.item_id !== id); updateCartUI(); }

function cartCount() { return cart.reduce((s, i) => s + i.quantity, 0); }
function cartTotal() { return cart.reduce((s, i) => s + i.price * i.quantity, 0); }

function updateCartUI() {
  const list = document.getElementById('cart-items');
  const total = document.getElementById('cart-total');
  const fabCount = document.getElementById('fab-count');
  const fabTotal = document.getElementById('fab-total');
  const placeBtn = document.getElementById('place-btn');
  if (fabCount) fabCount.textContent = cartCount();
  if (fabTotal) fabTotal.textContent = money(cartTotal());
  if (placeBtn) placeBtn.disabled = !cart.length;
  if (!list) return;
  if (!cart.length) {
    list.innerHTML = `<div class="cart-empty"><div class="emoji">🛒</div><p>Your cart is empty.<br>Add some tasty food!</p></div>`;
    if (total) total.textContent = money(0);
    return;
  }
  list.innerHTML = cart.map(i => `
    <div class="cart-line">
      <span class="emoji">${i.emoji}</span>
      <div class="info">
        <div class="nm">${escapeHtml(i.name)}</div>
        <div class="pr">${money(i.price)} each</div>
      </div>
      <div class="qty">
        <button onclick="changeQty('${i.item_id}',-1)">−</button>
        <span>${i.quantity}</span>
        <button onclick="changeQty('${i.item_id}',1)">+</button>
      </div>
      <span class="line-total">${money(i.price * i.quantity)}</span>
      <button class="rm" onclick="removeItem('${i.item_id}')">✕</button>
    </div>`).join('');
  if (total) total.textContent = money(cartTotal());
}

function bumpFab() {
  const fab = document.getElementById('cart-fab');
  if (!fab) return;
  fab.style.transform = 'scale(1.15)'; setTimeout(() => fab.style.transform = '', 180);
}

/* ── cart drawer open/close ─────────────────────────────────── */
function bindCart() {
  const fab = document.getElementById('cart-fab');
  const drawer = document.getElementById('cart-drawer');
  const overlay = document.getElementById('cart-overlay');
  const close = document.getElementById('cart-close');
  if (fab) fab.onclick = () => { drawer.classList.add('open'); overlay.classList.add('open'); };
  if (close) close.onclick = () => { drawer.classList.remove('open'); overlay.classList.remove('open'); };
  if (overlay) overlay.onclick = () => { drawer.classList.remove('open'); overlay.classList.remove('open'); };
}

/* ── checkout → payment modal → place order ─────────────────── */
/* Demo payment flow: "Place Order" opens a QR screen. The student
   taps "I've Paid" which marks the order paid and sends it to the
   kitchen dashboard in real time (no real money moves). */
function placeOrder() {
  if (!cart.length) return;
  openPayModal();
}

function openPayModal() {
  const total = cartTotal();
  document.getElementById('pay-amount').textContent = money(total);
  const qrEl = document.getElementById('pay-qr');
  qrEl.innerHTML = '';
  // A realistic UPI deep-link carrying the exact amount + a note.
  const upi = `upi://pay?pa=smartcanteen@upi&pn=SmartCanteen&am=${total}&cu=INR&tn=SmartCanteen Order`;
  if (typeof QRCode !== 'undefined') {
    new QRCode(qrEl, { text: upi, width: 196, height: 196 });
  } else {
    // Fallback to a public QR API if the library failed to load.
    qrEl.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=196x196&data=${encodeURIComponent(upi)}" alt="Payment QR"/>`;
  }
  document.getElementById('pay-modal').classList.add('open');
}

function closePayModal() {
  document.getElementById('pay-modal').classList.remove('open');
}

async function confirmPayment() {
  if (!cart.length) return;
  const btn = document.getElementById('pay-confirm-btn');
  const notes = document.getElementById('notes')?.value || '';
  btn.disabled = true; btn.textContent = 'Placing order…';
  try {
    const r = await API.post('/api/orders', {
      items: cart.map(i => ({ item_id: i.item_id, quantity: i.quantity })),
      special_instructions: notes,
      paid: true,
    });
    const token = r.data.token_number;
    Toast.success(`Payment done! Your token is #${token}`, 5000);
    cart = []; updateCartUI();
    closePayModal();
    document.getElementById('cart-drawer').classList.remove('open');
    document.getElementById('cart-overlay').classList.remove('open');
    if (notes && document.getElementById('notes')) document.getElementById('notes').value = '';
    // Jump straight to live tracking.
    setTimeout(() => location.href = `/track?token=${token}`, 1100);
  } catch { /* toast shown */ }
  btn.disabled = false; btn.textContent = "✅ I've Paid — Place Order";
}

/* ── search (debounced) ─────────────────────────────────────── */
let searchTimer;
function bindSearch() {
  const s = document.getElementById('search');
  if (!s) return;
  s.oninput = () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadMenu(s.value.trim()), 350);
  };
}

/* ── dish of the day ────────────────────────────────────────── */
async function loadDishOfTheDay() {
  const box = document.getElementById('dotd');
  if (!box) return;
  try {
    const r = await API.get('/api/menu/dish-of-the-day');
    const d = r.data;
    if (!d) { box.classList.add('hide'); return; }
    box.innerHTML = `
      <div class="plate">${d.emoji || '🍽️'}</div>
      <div>
        <span class="tag">Dish of the Day</span>
        <h3>${escapeHtml(d.name)}</h3>
        <p class="desc">${escapeHtml(d.description || '')}</p>
        <div class="flex gap center wrap">
          <span class="price">${money(d.price)}</span>
          <span class="rating">⭐ ${d.avg_rating?.toFixed(1) || '—'}</span>
          ${Auth.isStudent() ? `<button class="btn btn-primary" onclick="addToCart('${d._id}', ${d.price}, '${escapeHtml(d.name)}', '${d.emoji || '🍽️'}')">Order this →</button>` : ''}
        </div>
      </div>`;
  } catch { box.classList.add('hide'); }
}

/* ── smart suggestions ─────────────────────────────────────── */
async function loadSuggestions() {
  const box = document.getElementById('suggestions');
  if (!box || !Auth.isStudent()) { if (box) box.classList.add('hide'); return; }
  try {
    const r = await API.get('/api/orders/suggestions');
    const picks = r.data || [];
    if (!picks.length) { box.classList.add('hide'); return; }
    box.classList.remove('hide');
    box.innerHTML = `
      <h3 class="section-title">🧠 Your usuals</h3>
      <p class="muted" style="margin-bottom:14px">Based on your past orders — tap to reorder in one go.</p>
      <div class="grid-auto">
        ${picks.map(p => `
          <div class="card teal fade-in">
            <div style="font-size:2.4rem">${p.emoji || '🍽️'}</div>
            <h3 style="font-size:1rem;margin:8px 0 2px">${escapeHtml(p.name)}</h3>
            <div class="muted" style="font-size:.8rem">Ordered ${p.times_ordered}× before</div>
            <div class="flex between center" style="margin-top:10px">
              <span class="green" style="font-weight:700">${money(p.price)}</span>
              <button class="btn btn-ghost btn-sm" onclick="quickReorder('${p.item_id}', ${p.price}, '${escapeHtml(p.name)}', '${p.emoji || '🍽️'}')">+ Cart</button>
            </div>
          </div>`).join('')}
      </div>`;
  } catch { box.classList.add('hide'); }
}
function quickReorder(id, price, name, emoji) { addToCart(id, price, name, emoji); }

/* ── real-time out-of-stock ─────────────────────────────────── */
function wireSocket() {
  const s = socket();
  if (!s) return;
  s.on('menu_changed', (d) => {
    // gray out / restore the card instantly, no refresh (Day 4/7)
    const card = document.querySelector(`.menu-card[data-id="${d.item_id}"]`);
    if (!card) return;
    if (d.is_available === false) {
      card.classList.add('out');
      card.querySelector('.add-btn')?.setAttribute('disabled', '');
      const flag = document.createElement('span'); flag.className = 'stock-flag'; flag.textContent = 'Out of stock';
      if (!card.querySelector('.stock-flag')) card.appendChild(flag);
      Toast.warn('An item just went out of stock!', 2600);
    } else if (d.is_available === true) {
      card.classList.remove('out');
      card.querySelector('.stock-flag')?.remove();
      card.querySelector('.add-btn')?.removeAttribute('disabled');
    }
  });
}

function emptyState(msg) {
  return `<div class="empty"><div class="emoji">🍽️</div><p>${escapeHtml(msg)}</p></div>`;
}

/* ═══════════════════════════════════════════════════════════════
   REVIEW MODAL — open/close/submit/load
   ═══════════════════════════════════════════════════════════════ */
let _reviewItemId = null;

function openReviewModal(itemId, name, emoji, category) {
  _reviewItemId = itemId;
  document.getElementById('rm-emoji').textContent = emoji;
  document.getElementById('rm-name').textContent = name;
  document.getElementById('rm-cat').textContent = category;
  document.getElementById('rm-comment').value = '';
  document.querySelectorAll('#star-input input').forEach(r => r.checked = false);
  document.getElementById('star-hint').textContent = 'Click to rate (1–5 stars)';
  document.getElementById('review-modal').classList.add('open');
  loadReviews(itemId);
}

function closeReviewModal() {
  document.getElementById('review-modal').classList.remove('open');
  _reviewItemId = null;
}

// Close on backdrop click
document.addEventListener('DOMContentLoaded', () => {
  const backdrop = document.getElementById('review-modal');
  if (backdrop) backdrop.addEventListener('click', e => {
    if (e.target === backdrop) closeReviewModal();
  });
  const payBackdrop = document.getElementById('pay-modal');
  if (payBackdrop) payBackdrop.addEventListener('click', e => {
    if (e.target === payBackdrop) closePayModal();
  });
  // Update hint text when a star is selected
  document.querySelectorAll('#star-input input').forEach(inp => {
    inp.addEventListener('change', () => {
      const labels = ['','Terrible 😞','Poor 😕','OK 😐','Good 😊','Excellent 🤩'];
      document.getElementById('star-hint').textContent = labels[inp.value] || '';
    });
  });
});

async function submitReview() {
  if (!_reviewItemId) return;
  const ratingEl = document.querySelector('#star-input input:checked');
  if (!ratingEl) return Toast.warn('Pick a star rating first.');
  const btn = document.getElementById('rm-submit-btn');
  btn.disabled = true; btn.textContent = 'Submitting…';
  try {
    await API.post('/api/reviews', {
      item_id: _reviewItemId,
      rating: parseInt(ratingEl.value),
      comment: document.getElementById('rm-comment').value,
    });
    Toast.success('Thanks for your review! ⭐');
    closeReviewModal();
    // refresh menu to show updated avg_rating
    await loadMenu();
  } catch { /* toast shown */ }
  btn.disabled = false; btn.textContent = 'Submit Review';
}

async function loadReviews(itemId) {
  const box = document.getElementById('rm-reviews');
  box.innerHTML = `<div class="center-load"><div class="spinner"></div></div>`;
  try {
    const r = await API.get(`/api/reviews/${itemId}`);
    const reviews = r.data || [];
    if (!reviews.length) {
      box.innerHTML = `<div class="empty" style="padding:30px 0"><div class="emoji">💬</div><p>No reviews yet. Be the first!</p></div>`;
      return;
    }
    box.innerHTML = reviews.map(rv => {
      const name = rv.student_name || rv.reviewer_name || 'Anonymous';
      const initials = name.split(' ').map(w=>w[0]).slice(0,2).join('').toUpperCase();
      const starsHtml = '★'.repeat(rv.rating) + '<span style="opacity:.3">' + '★'.repeat(5-rv.rating) + '</span>';
      return `
        <div class="review-item">
          <div class="reviewer-avatar">${initials}</div>
          <div style="flex:1;min-width:0">
            <div class="reviewer-name">${escapeHtml(name)}</div>
            <div class="reviewer-stars">${starsHtml}</div>
            ${rv.comment ? `<div class="reviewer-text">${escapeHtml(rv.comment)}</div>` : ''}
            <div class="reviewer-time">${timeAgo(rv.created_at)}</div>
          </div>
        </div>`;
    }).join('');
  } catch {
    box.innerHTML = `<div class="empty"><p>Could not load reviews.</p></div>`;
  }
}

