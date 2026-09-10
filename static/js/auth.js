/* ═══════════════════════════════════════════════════════════════
   SmartCanteen — Auth Pages (auth.js) v2
   Day 8 (theory): fetch() + async/await talking to /api/auth/*
   ═══════════════════════════════════════════════════════════════ */

/* ── called by login.html: onsubmit="loginSubmit(event)" ────── */
async function loginSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById('login-btn');
  btn.disabled = true; btn.textContent = 'Signing in…';
  try {
    const r = await API.post('/api/auth/login', {
      email: document.getElementById('email').value,
      password: document.getElementById('password').value,
    });
    Toast.success(r.message || 'Welcome back!');
    const role = r.data.user.role;
    setTimeout(() => location.href =
      role === 'admin' ? '/admin' : role === 'staff' ? '/staff' : '/menu', 600);
  } catch { /* toast already shown */ }
  btn.disabled = false; btn.textContent = 'Login →';
}

/* ── called by register.html: onsubmit="registerSubmit(event)" ─ */
async function registerSubmit(e) {
  e.preventDefault();
  const pw = document.getElementById('password').value;
  if (pw.length < 6) return Toast.error('Password must be at least 6 characters.');
  const btn = document.getElementById('register-btn');
  btn.disabled = true; btn.textContent = 'Creating…';
  try {
    const role = (document.querySelector('#role-pick input[name="role"]:checked') || {}).value || 'student';
    const r = await API.post('/api/auth/register', {
      name: document.getElementById('name').value,
      email: document.getElementById('email').value,
      password: pw,
      roll_number: document.getElementById('roll_number')?.value || '',
      role,
    });
    Toast.success(r.message || 'Account created!');
    // Send the user to the dashboard that matches their chosen role.
    const home = role === 'admin' ? '/admin' : role === 'staff' ? '/staff' : '/menu';
    setTimeout(() => location.href = home, 700);
  } catch { /* toast already shown */ }
  btn.disabled = false; btn.textContent = 'Create Account →';
}

/* ── password toggle eye icon ────────────────────────────────── */
function togglePwd(btn) {
  const inp = btn.closest('.input-wrap').querySelector('.input');
  if (!inp) return;
  const isText = inp.type === 'text';
  inp.type = isText ? 'password' : 'text';
  btn.textContent = isText ? '👁' : '🙈';
}

/* ── quick-fill demo credentials ─────────────────────────────── */
function fillDemo(email, pw) {
  const e = document.getElementById('email'); const p = document.getElementById('password');
  if (e && p) { e.value = email; p.value = pw; Toast.info('Filled — click Login.'); }
}

/* ── boot init functions ─────────────────────────────────────── */
function loginInit() {
  // already logged in → redirect away
  if (Auth.user) {
    const role = Auth.user.role;
    location.href = role === 'admin' ? '/admin' : role === 'staff' ? '/staff' : '/menu';
  }
}
function registerInit() {
  if (Auth.user) location.href = '/menu';
}

/* Backward compat aliases */
const handleLogin    = loginSubmit;
const handleRegister = registerSubmit;
