/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — API Client (api.js)
   ───────────────────────────────────────────────────────────────
   Day 8 (theory): The Fetch API & Promises. Every call to our Flask
   backend goes through here.  We use async/await so the calling code
   reads top-to-bottom, and we centralise:
     • credentials: 'same-origin'  → send the httpOnly JWT cookie
       (Day 5: the cookie is httpOnly so JS can't read it, but the
        browser attaches it to same-origin requests automatically)
     • JSON parsing & a consistent { success, data, error } envelope
     • A toast + re-throw on error so pages can stay simple
   ═══════════════════════════════════════════════════════════════ */

const API = (() => {
  const base = '';  // same origin → /api/... served by the same Flask app

  async function request(method, path, { body, form, silent } = {}) {
    const opts = { method, credentials: 'same-origin', headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    } else if (form) {
      opts.body = form;  // FormData — browser sets the multipart boundary
    }

    let res;
    try {
      res = await fetch(base + path, opts);
    } catch (e) {
      if (!silent) Toast.error('Network error — is the server running?');
      throw e;
    }

    let data = null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) data = await res.json();
    else if (res.ok && method === 'GET' && path.includes('export')) return res;
    else { const t = await res.text(); data = t ? { error: t } : null; }

    if (!res.ok) {
      const msg = (data && data.error) || `Request failed (${res.status})`;
      if (!silent) Toast.error(msg);
      // 401 → bounce to login — but NOT for public pages (landing, login,
      // register) and NOT when the caller explicitly asked for silence
      // (e.g. Auth.load() just checking if you're logged in).
      const pub = location.pathname === '/' || location.pathname === '/index'
                  || location.pathname.startsWith('/login')
                  || location.pathname.startsWith('/register');
      if (res.status === 401 && !silent && !pub) {
        setTimeout(() => location.href = '/login', 700);
      }
      const err = new Error(msg);
      err.status = res.status; err.data = data;
      throw err;
    }
    return data;  // full envelope { success, data, ... }
  }

  return {
    get:  (p, o) => request('GET', p, o),
    post: (p, body, o) => request('POST', p, { body, ...o }),
    put:  (p, body, o) => request('PUT', p, { body, ...o }),
    patch:(p, body, o) => request('PATCH', p, { body, ...o }),
    del:  (p, o) => request('DELETE', p, o),
    call: async (m, p, ...rest) => (await request(m, p, ...rest)).data,
  };
})();
