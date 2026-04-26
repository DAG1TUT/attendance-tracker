// ── Device Fingerprint ────────────────────────────────────────────────────────
function generateDeviceId() {
  const raw = [
    navigator.userAgent, screen.width, screen.height,
    Intl.DateTimeFormat().resolvedOptions().timeZone, navigator.language,
  ].join('|');
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i++) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

const DEVICE_ID = (() => {
  let id = localStorage.getItem('device_id');
  if (!id) { id = generateDeviceId(); localStorage.setItem('device_id', id); }
  return id;
})();

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = { method, credentials: 'include', headers: {} };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch('/api/v1' + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ── Employee tabs ─────────────────────────────────────────────────────────────
function switchEmpTab(tab) {
  document.querySelectorAll('.emp-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.emp-page').forEach(p => p.classList.remove('active'));
  document.getElementById(`etab-${tab}`)?.classList.add('active');
  document.getElementById(`emp-page-${tab}`)?.classList.add('active');
  if (tab === 'schedule') loadMySchedule();
}

// ── Employee weekly schedule ──────────────────────────────────────────────────
let _empWeekStart = null;

function empGetMonday(d = new Date()) {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const mon = new Date(d); mon.setDate(d.getDate() + diff);
  return mon.toISOString().split('T')[0];
}

function empAddDays(iso, n) {
  const d = new Date(iso); d.setDate(d.getDate() + n);
  return d.toISOString().split('T')[0];
}

function empShiftWeek(delta) {
  _empWeekStart = empAddDays(_empWeekStart, delta);
  loadMySchedule();
}

async function loadMySchedule() {
  if (!_empWeekStart) _empWeekStart = empGetMonday();
  const dateFrom = _empWeekStart;
  const dateTo   = empAddDays(_empWeekStart, 6);

  const d1 = new Date(dateFrom), d2 = new Date(dateTo);
  const fmtShort = (d) => d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
  const lbl = document.getElementById('emp-week-label');
  if (lbl) lbl.textContent = `${fmtShort(d1)} — ${fmtShort(d2)}`;

  const wrap = document.getElementById('emp-sched-wrap');
  if (wrap) wrap.innerHTML = '<div style="text-align:center;color:var(--muted);padding:24px 0;">Загрузка...</div>';

  try {
    const data = await api('GET', `/attendance/week?date_from=${dateFrom}&date_to=${dateTo}`);
    renderMySchedule(data);
  } catch (err) {
    if (wrap) wrap.innerHTML = `<div style="text-align:center;color:var(--muted);padding:24px 0;">Ошибка: ${err.message}</div>`;
  }
}

function renderMySchedule(data) {
  const wrap = document.getElementById('emp-sched-wrap');
  const totalEl = document.getElementById('emp-week-total');
  if (!wrap) return;

  const DAY_SHORT = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];
  const fmtTime = (iso) => new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const today = new Date().toISOString().split('T')[0];

  const cells = data.days.map((day) => {
    const isToday = day.date === today;
    const hasData = day.check_in || day.check_out;
    const d = new Date(day.date + 'T00:00:00');
    const dayLabel = `${DAY_SHORT[d.getDay()]} ${String(d.getDate()).padStart(2,'0')}.${String(d.getMonth()+1).padStart(2,'0')}`;

    return `
      <div class="my-day ${isToday ? 'my-day-today' : ''} ${hasData ? 'my-day-filled' : ''}">
        <div class="my-day-label">${dayLabel}</div>
        ${hasData ? `
          <div class="my-day-in">↑ ${day.check_in ? fmtTime(day.check_in) : '—'}</div>
          <div class="my-day-out">↓ ${day.check_out ? fmtTime(day.check_out) : '<span style="color:var(--accent);font-size:11px">сейчас</span>'}</div>
          ${day.hours > 0 ? `<div class="my-day-h">${day.hours} ч</div>` : ''}
        ` : `<div class="my-day-dash">—</div>`}
      </div>
    `;
  }).join('');

  wrap.innerHTML = `<div class="my-week-grid">${cells}</div>`;
  if (totalEl) {
    totalEl.innerHTML = data.total_hours > 0
      ? `Итого за неделю: <b>${data.total_hours} ч</b>` : '';
  }
}

// ── Auth tabs ─────────────────────────────────────────────────────────────────
function switchAuthTab(tab) {
  const isLogin = tab === 'login';
  document.getElementById('login-form').style.display = isLogin ? '' : 'none';
  document.getElementById('register-form').style.display = isLogin ? 'none' : '';
  document.getElementById('tab-login').classList.toggle('active', isLogin);
  document.getElementById('tab-register').classList.toggle('active', !isLogin);
  document.getElementById('auth-subtitle').textContent = isLogin
    ? 'Войдите, чтобы отметить приход'
    : 'Создайте аккаунт для работы';
  const alert = document.getElementById('alert');
  if (alert) { alert.classList.remove('show'); }
}

// ── Clock ─────────────────────────────────────────────────────────────────────
function startClock() {
  const el = document.getElementById('clock');
  const dateEl = document.getElementById('clock-date');
  if (!el) return;
  const days = ['Воскресенье','Понедельник','Вторник','Среда','Четверг','Пятница','Суббота'];
  const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
  function tick() {
    const now = new Date();
    el.textContent = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    if (dateEl) dateEl.textContent = `${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]}`;
  }
  tick(); setInterval(tick, 5000);
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function showAlert(msg, type = 'error') {
  const el = document.getElementById('alert');
  if (!el) return;
  el.textContent = msg;
  el.className = `alert ${type} show`;
  setTimeout(() => el.classList.remove('show'), 5000);
}

function showScreen(id) {
  document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  if (loading) { btn.dataset.originalText = btn.innerHTML; btn.innerHTML = '<span class="spinner"></span>'; btn.disabled = true; }
  else { btn.innerHTML = btn.dataset.originalText || btn.innerHTML; btn.disabled = false; }
}

// ── Status ────────────────────────────────────────────────────────────────────
async function loadStatus() {
  try {
    const s = await api('GET', '/attendance/status');
    const badge = document.getElementById('status-badge');
    if (!badge) return;
    if (s.action === 'check_in') {
      badge.className = 'status-badge in';
      const since = s.since ? new Date(s.since).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '';
      badge.innerHTML = `<span class="dot"></span> На месте с ${since}`;
      document.getElementById('btn-checkin').disabled = true;
      document.getElementById('btn-checkout').disabled = false;
    } else {
      badge.className = 'status-badge out';
      badge.innerHTML = `<span class="dot"></span> Не отмечен`;
      document.getElementById('btn-checkin').disabled = false;
      document.getElementById('btn-checkout').disabled = true;
    }
  } catch {
    const badge = document.getElementById('status-badge');
    if (badge) { badge.className = 'status-badge unknown'; badge.innerHTML = `<span class="dot"></span> Статус неизвестен`; }
  }
}

// ── History ───────────────────────────────────────────────────────────────────
async function loadHistory() {
  const list = document.getElementById('history-list');
  if (!list) return;
  try {
    const items = await api('GET', '/attendance/history?limit=20');
    if (!items.length) { list.innerHTML = '<li style="color:var(--muted);font-size:14px;padding:12px 0;">Нет записей</li>'; return; }
    list.innerHTML = items.map((item) => {
      const icon = item.action === 'check_in' ? '✅' : '🚪';
      const label = item.action === 'check_in' ? 'Пришёл' : 'Ушёл';
      const time = new Date(item.timestamp).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
      const susp = item.is_suspicious ? `<span class="badge-susp">⚠ подозрительно</span>` : '';
      return `<li class="history-item${item.is_suspicious ? ' suspicious' : ''}">
        <span class="history-action">${icon}</span>
        <div class="history-meta"><div class="history-time">${label} — ${time}</div><div class="history-sub">IP: ${item.ip_address}</div></div>
        ${susp}</li>`;
    }).join('');
  } catch {
    list.innerHTML = '<li style="color:var(--muted);font-size:14px;padding:12px 0;">Ошибка загрузки</li>';
  }
}

// ── Check-in / Check-out ──────────────────────────────────────────────────────
async function doCheckIn() {
  setLoading('btn-checkin', true);
  try {
    const res = await api('POST', '/attendance/check-in', { device_id: DEVICE_ID, user_agent: navigator.userAgent });
    showAlert(res.message || 'Приход зафиксирован', 'success');
    await loadStatus(); await loadHistory();
  } catch (err) { showAlert(err.message); }
  finally { setLoading('btn-checkin', false); }
}

async function doCheckOut() {
  setLoading('btn-checkout', true);
  try {
    const res = await api('POST', '/attendance/check-out', { device_id: DEVICE_ID, user_agent: navigator.userAgent });
    const dur = res.duration_minutes;
    const h = Math.floor(dur / 60), m = dur % 60;
    showAlert(`Уход зафиксирован. Отработано: ${h > 0 ? h + ' ч ' : ''}${m} мин`, 'success');
    await loadStatus(); await loadHistory();
  } catch (err) { showAlert(err.message); }
  finally { setLoading('btn-checkout', false); }
}

// ── Login ─────────────────────────────────────────────────────────────────────
async function doLogin(e) {
  e.preventDefault();
  const phone = document.getElementById('phone').value.trim();
  const password = document.getElementById('password').value;
  if (!phone || !password) return showAlert('Введите телефон и пароль');
  setLoading('btn-login', true);
  try {
    const res = await api('POST', '/auth/login', { phone, password, device_id: DEVICE_ID, user_agent: navigator.userAgent });
    localStorage.setItem('role', res.role);
    localStorage.setItem('name', res.name);
    if (res.role === 'admin') { window.location.href = '/admin.html'; return; }
    document.getElementById('user-name').textContent = res.name;
    document.getElementById('user-role').textContent = 'Сотрудник';
    showScreen('main-screen');
    await loadStatus(); await loadHistory();
  } catch (err) { showAlert(err.message); }
  finally { setLoading('btn-login', false); }
}

// ── Register ──────────────────────────────────────────────────────────────────
async function doRegister(e) {
  e.preventDefault();
  const name = document.getElementById('reg-name').value.trim();
  const phone = document.getElementById('reg-phone').value.trim();
  const password = document.getElementById('reg-password').value;
  if (!name || !phone || !password) return showAlert('Заполните все поля');
  if (password.length < 6) return showAlert('Пароль минимум 6 символов');
  setLoading('btn-register', true);
  try {
    await api('POST', '/auth/register', { name, phone, password });
    showAlert('Заявка отправлена! Ожидайте подтверждения администратора.', 'success');
    // Clear form
    document.getElementById('reg-name').value = '';
    document.getElementById('reg-phone').value = '';
    document.getElementById('reg-password').value = '';
    switchAuthTab('login');
  } catch (err) { showAlert(err.message); }
  finally { setLoading('btn-register', false); }
}

// ── Logout ────────────────────────────────────────────────────────────────────
async function doLogout() {
  try { await api('POST', '/auth/logout'); } catch {}
  localStorage.removeItem('role');
  localStorage.removeItem('name');
  showScreen('login-screen');
  switchAuthTab('login');
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  startClock();
  try {
    const me = await api('GET', '/auth/me');
    if (me.role === 'admin') { window.location.href = '/admin.html'; return; }
    document.getElementById('user-name').textContent = me.name;
    document.getElementById('user-role').textContent = 'Сотрудник';
    showScreen('main-screen');
    await loadStatus(); await loadHistory();
  } catch {
    showScreen('login-screen');
  }

  document.getElementById('login-form').addEventListener('submit', doLogin);
  document.getElementById('register-form').addEventListener('submit', doRegister);
  document.getElementById('btn-checkin').addEventListener('click', doCheckIn);
  document.getElementById('btn-checkout').addEventListener('click', doCheckOut);
  document.getElementById('logout-btn').addEventListener('click', doLogout);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  }
}

document.addEventListener('DOMContentLoaded', init);
