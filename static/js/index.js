/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — Landing Page (index.js)
   Fetches a few featured dishes + live counters for the hero, then
   reveals them with the scroll observer (Day 8).
   ═══════════════════════════════════════════════════════════════ */

async function indexInit() {
  loadFeatured();
  loadLiveCounters();
  // redirect logged-in staff/admin to their dashboards
  if (Auth.isStaff() && !Auth.isStudent()) {}
  if (Auth.isAdmin()) { /* keep them on landing if they want */ }
}

async function loadFeatured() {
  const box = document.getElementById('featured');
  if (!box) return;
  try {
    const r = await API.get('/api/menu');
    const items = (r.data || []).slice(0, 6);
    if (!items.length) { box.classList.add('hide'); return; }
    box.classList.remove('hide');
    box.innerHTML = items.map(item => `
      <div class="menu-card reveal">
        <div class="photo">${item.emoji || '🍽️'}</div>
        <div class="body">
          <span class="cat">${escapeHtml(item.category)}</span>
          <h3>${escapeHtml(item.name)}</h3>
          <p class="desc">${escapeHtml(item.description || '')}</p>
          <div class="meta">
            <span class="price">${money(item.price)}</span>
            <span class="rating">⭐ ${item.avg_rating?.toFixed(1) || '—'}</span>
          </div>
          ${Auth.isStudent()
            ? `<button class="btn btn-teal btn-sm add-btn" onclick="location.href='/menu'">Order now →</button>`
            : `<a href="/menu" class="btn btn-ghost btn-sm add-btn" style="text-align:center">View menu</a>`}
        </div>
      </div>`).join('');
    initReveal();
  } catch { box.classList.add('hide'); }
}

async function loadLiveCounters() {
  const dishes = document.getElementById('count-dishes');
  if (!dishes) return;
  try {
    const r = await API.get('/api/menu');
    if (dishes) dishes.textContent = (r.data || []).length;
  } catch {}
  // animated count-up feel
  ['count-dishes', 'count-roles', 'count-realtime'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const target = parseInt(el.textContent || el.dataset.value || '0', 10);
    if (!target) { el.textContent = el.dataset.value || '0'; return; }
    let n = 0; el.textContent = '0';
    const step = Math.max(1, Math.ceil(target / 28));
    const t = setInterval(() => { n += step; if (n >= target) { n = target; clearInterval(t);} el.textContent = n; }, 35);
  });
}
