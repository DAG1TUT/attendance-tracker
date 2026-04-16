// ── Device Fingerprint ────────────────────────────────────────────────────────
function generateDeviceId() {
  const raw = [
    navigator.userAgent,
    screen.width,
    screen.height,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    navigator.language,
  ].join('|');

  // FNV-1a 32-bit hash
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i++) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

const DEVICE_ID = (() => {
  let id = localStorage.getItem('device_id');
  if (!id) {
    id = generateDeviceId();
    localStorage.setItem('device_id', id);
  }
  return id;
})();

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = {
    method,
    credentials: 'include',
    headers: {},
  };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api/v1' + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
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
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    el.textContent = `${h}:${m}`;
    if (dateEl) {
      dateEl.textContent = `${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]}`;
    }
  }
  tick();
  setInterval(tick, 5000);
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function showAlert(msg, type = 'error') {
  const el = document.getElementById('alert');
  if (!el) return;
  el.textContent = msg;
  el.className = `alert ${type} show`;
  setTimeout(() => el.classList.remove('show'), 4000);
}

function showScreen(id) {
  document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  if (loading) {
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span>';
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.originalText || btn.innerHTML;
    btn.disabled = false;
  }
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
    if (badge) {
      badge.className = 'status-badge unknown';
      badge.innerHTML = `<span class="dot"></span> Статус неизвестен`;
    }
  }
}

// ── History ───────────────────────────────────────────────────────────────────
async function loadHistory() {
  const list = document.getElementById('history-list');
  if (!list) return;
  try {
    const items = await api('GET', '/attendance/history?limit=20');
    if (!items.length) {
      list.innerHTML = '<li style="color:var(--muted);font-size:14px;padding:12px 0;">Нет записей</li>';
      return;
    }
    list.innerHTML = items.map((item) => {
      const icon = item.action === 'check_in' ? '✅' : '🚪';
      const actionLabel = item.action === 'check_in' ? 'Пришёл' : 'Ушёл';
      const time = new Date(item.timestamp).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
      });
      const suspBadge = item.is_suspicious
        ? `<span class="badge-susp">⚠ подозрительно</span>`
        : '';
      return `
        <li class="history-item${item.is_suspicious ? ' suspicious' : ''}">
          <span class="history-action">${icon}</span>
          <div class="history-meta">
            <div class="history-time">${actionLabel} — ${time}</div>
            <div class="history-sub">IP: ${item.ip_address}</div>
          </div>
          ${suspBadge}
        </li>`;
    }).join('');
  } catch {
    list.innerHTML = '<li style="color:var(--muted);font-size:14px;padding:12px 0;">Ошибка загрузки</li>';
  }
}

// ── Check-in / Check-out ──────────────────────────────────────────────────────
async function doCheckIn() {
  setLoading('btn-checkin', true);
  try {
    const res = await api('POST', '/attendance/check-in', {
      device_id: DEVICE_ID,
      user_agent: navigator.userAgent,
    });
    showAlert(res.message || 'Приход зафиксирован', 'success');
    await loadStatus();
    await loadHistory();
  } catch (err) {
    showAlert(err.message);
  } finally {
    setLoading('btn-checkin', false);
  }
}

async function doCheckOut() {
  setLoading('btn-checkout', true);
  try {
    const res = await api('POST', '/attendance/check-out', {
      device_id: DEVICE_ID,
      user_agent: navigator.userAgent,
    });
    const dur = res.duration_minutes;
    const h = Math.floor(dur / 60);
    const m = dur % 60;
    const durStr = h > 0 ? `${h} ч ${m} мин` : `${m} мин`;
    showAlert(`Уход зафиксирован. Отработано: ${durStr}`, 'success');
    await loadStatus();
    await loadHistory();
  } catch (err) {
    showAlert(err.message);
  } finally {
    setLoading('btn-checkout', false);
  }
}

// ── Login ─────────────────────────────────────────────────────────────────────
async function doLogin(e) {
  e.preventDefault();
  const phone = document.getElementById('phone').value.trim();
  const password = document.getElementById('password').value;
  if (!phone || !password) return showAlert('Введите телефон и пароль');

  setLoading('btn-login', true);
  try {
    const res = await api('POST', '/auth/login', {
      phone,
      password,
      device_id: DEVICE_ID,
      user_agent: navigator.userAgent,
    });
    localStorage.setItem('role', res.role);
    localStorage.setItem('name', res.name);

    if (res.role === 'admin') {
      window.location.href = '/admin.html';
      return;
    }

    document.getElementById('user-name').textContent = res.name;
    document.getElementById('user-role').textContent = 'Сотрудник';
    showScreen('main-screen');
    await loadStatus();
    await loadHistory();
  } catch (err) {
    showAlert(err.message);
  } finally {
    setLoading('btn-login', false);
  }
}

// ── Logout ────────────────────────────────────────────────────────────────────
async function doLogout() {
  try { await api('POST', '/auth/logout'); } catch {}
  localStorage.removeItem('role');
  localStorage.removeItem('name');
  showScreen('login-screen');
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  startClock();

  // Check if already logged in
  try {
    const me = await api('GET', '/auth/me');
    if (me.role === 'admin') {
      window.location.href = '/admin.html';
      return;
    }
    document.getElementById('user-name').textContent = me.name;
    document.getElementById('user-role').textContent = 'Сотрудник';
    showScreen('main-screen');
    await loadStatus();
    await loadHistory();
  } catch {
    showScreen('login-screen');
  }

  // Event listeners
  document.getElementById('login-form').addEventListener('submit', doLogin);
  document.getElementById('btn-checkin').addEventListener('click', doCheckIn);
  document.getElementById('btn-checkout').addEventListener('click', doCheckOut);
  document.getElementById('logout-btn').addEventListener('click', doLogout);

  // Register service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  }
}

document.addEventListener('DOMContentLoaded', init);
