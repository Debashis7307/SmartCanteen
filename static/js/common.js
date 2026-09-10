/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — Common Helpers (common.js)
   ───────────────────────────────────────────────────────────────
   Shared UI utilities loaded by every page:
     • Toast notifications
     • Auth state + role-aware navbar rendering (Day 5 RBAC)
     • Small helpers: escapeHtml, money, time-ago, initials…
     • Intersection-Observer reveal-on-scroll (Day 8)
     • Socket.IO singleton (Day 4/7)
   ═══════════════════════════════════════════════════════════════ */

/* ── Toast ────────────────────────────────────────────────────── */
const Toast = (() => {
  let box;
  function ensure() {
    box = document.getElementById('toaster') || (() => {
      const b = document.createElement('div'); b.id = 'toaster'; document.body.appendChild(b); return b;
    })();
  }
  function show(msg, type = 'info', ms = 4200) {
    ensure();
    const icons = { success: '✅', error: '⛔', info: 'ℹ️', warn: '⚠️' };
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span class="t-icon">${icons[type] || 'ℹ️'}</span><span>${escapeHtml(msg)}</span>`;
    box.appendChild(el);
    const remove = () => { el.classList.add('removing'); setTimeout(() => el.remove(), 300); };
    el.addEventListener('click', remove);
    setTimeout(remove, ms);
  }
  return {
    success: (m, ms) => show(m, 'success', ms),
    error:   (m, ms) => show(m, 'error', ms),
    info:    (m, ms) => show(m, 'info', ms),
    warn:    (m, ms) => show(m, 'warn', ms),
  };
})();

/* ── Auth state & navbar ─────────────────────────────────────── */
const Auth = {
  user: null,
  async load() {
    // silent:true → don't toast or redirect on 401 (landing page is public)
    try {
      const r = await API.get('/api/auth/me', { silent: true });
      if (r && r.success) this.user = r.data.user;
    } catch { this.user = null; }
    return this.user;
  },
  isAdmin()  { return this.user?.role === 'admin'; },
  isStaff()  { return this.user?.role === 'staff'; },
  isStudent(){ return this.user?.role === 'student'; },
  isLoggedIn(){ return !!this.user; },
};

async function renderNav() {
  await Auth.load();
  const slot = document.getElementById('nav-user');
  const links = document.getElementById('nav-links');
  if (!links) return;

  // student-only links
  const studentLinks = `
    <a href="/menu" data-nav="menu">🍽️ Menu</a>
    <a href="/my-orders" data-nav="my-orders">📦 My Orders</a>
    <a href="/track" data-nav="track">🎯 Track Token</a>`;
  const staffLinks = `<a href="/staff" data-nav="staff">👨‍🍳 Kitchen</a>`;
  const adminLinks = `<a href="/admin" data-nav="admin">📊 Analytics</a>`;

  let html = studentLinks;
  if (Auth.user && (Auth.user.role === 'staff' || Auth.user.role === 'admin')) html += staffLinks;
  if (Auth.user && Auth.user.role === 'admin') html += adminLinks;
  links.innerHTML = html;

  // highlight active link
  const path = location.pathname;
  links.querySelectorAll('a').forEach(a => {
    if (path === a.getAttribute('href')) a.classList.add('active');
  });

  if (slot) {
    if (Auth.user) {
      const initials = Auth.user.name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
      slot.innerHTML = `
        <span class="user-chip" title="${escapeHtml(Auth.user.email)}">
          <span class="avatar">${initials}</span>
          ${escapeHtml(Auth.user.name.split(' ')[0])}
          <span class="role-tag ${Auth.user.role}">${Auth.user.role}</span>
        </span>
        <button class="btn btn-ghost btn-sm" onclick="logout()">Logout</button>`;
    } else {
      slot.innerHTML = `
        <a href="/login" class="btn btn-ghost btn-sm">Login</a>
        <a href="/register" class="btn btn-primary btn-sm">Sign up</a>`;
    }
  }
}

async function logout() {
  try { await API.post('/api/auth/logout'); } catch {}
  Toast.info('Logged out. See you at the canteen!');
  setTimeout(() => location.href = '/login', 600);
}

/* ── Socket.IO singleton (Day 4/7) ───────────────────────────── */
let _socket = null;
function socket() {
  if (_socket) return _socket;
  if (typeof io === 'undefined') return null;
  _socket = io({ transports: ['websocket', 'polling'] });
  _socket.on('connect', () => console.log('⚡ ws connected', _socket.id));
  _socket.on('disconnect', () => console.log('🔌 ws disconnected'));
  return _socket;
}

/* ── small helpers ───────────────────────────────────────────── */
function escapeHtml(s) {
  // Build HTML entities from parts so they are never mis-decoded.
  return String(s ?? '').replace(/[&<>"']/g, c =>
    '&' + { '&': 'amp', '<': 'lt', '>': 'gt', '"': 'quot', "'": '#39' }[c] + ';'
  );
}
function money(n) { return '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }
function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}
function timeAgo(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
}
function stars(n) {
  const full = '★'.repeat(Math.round(n || 0));
  const empty = '☆'.repeat(5 - Math.round(n || 0));
  return `<span class="stars">${full}${empty}</span>`;
}
function statusBadge(s) {
  return `<span class="badge ${s}"><span class="dot"></span>${s}</span>`;
}
function photoUrl(id) { return id ? `/api/menu/${id}/image` : ''; }

/* ── reveal on scroll (Day 8: Intersection Observer) ────────── */
function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!els.length) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
  }, { threshold: 0.12 });
  els.forEach(el => io.observe(el));
}

/* ── page bootstrapper ───────────────────────────────────────── */
async function boot(page, init) {
  await renderNav();
  initReveal();
  if (typeof init === 'function') {
    try { await init(); } catch (e) { console.error(e); }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (typeof io !== 'undefined') socket(); // pre-connect websocket
});
