// ── API ───────────────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = { method, credentials: 'include', headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api/v1' + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ── Navigation ────────────────────────────────────────────────────────────────
function showTab(tab) {
  document.querySelectorAll('.tab-page').forEach((p) => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));
  document.getElementById(`page-${tab}`)?.classList.add('active');
  document.getElementById(`nav-${tab}`)?.classList.add('active');

  if (tab === 'dashboard') loadDashboard();
  if (tab === 'employees') loadEmployees();
  if (tab === 'logs') loadLogs();
  if (tab === 'suspicious') loadSuspicious();
}

// ── Alert ─────────────────────────────────────────────────────────────────────
function showAlert(msg, type = 'error', containerId = 'alert-global') {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.textContent = msg;
  el.className = `alert ${type} show`;
  setTimeout(() => el.classList.remove('show'), 4000);
}

// ── Logout ────────────────────────────────────────────────────────────────────
async function doLogout() {
  try { await api('POST', '/auth/logout'); } catch {}
  localStorage.removeItem('role');
  localStorage.removeItem('name');
  window.location.href = '/app.html';
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const s = await api('GET', '/admin/stats/today');
    document.getElementById('stat-present').textContent = s.present.length;
    document.getElementById('stat-absent').textContent = s.absent.length;
    document.getElementById('stat-late').textContent = s.late.length;

    renderPeopleList('list-present', s.present, true);
    renderPeopleList('list-absent', s.absent, false);
    renderLateList('list-late', s.late);
  } catch (err) {
    console.error('Dashboard error:', err);
  }
}

function renderPeopleList(elId, people, showTime) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!people.length) {
    el.innerHTML = '<div class="empty">Нет записей</div>';
    return;
  }
  el.innerHTML = people.map((p) => `
    <div class="today-person">
      <span>${p.name}</span>
      ${showTime && p.checked_in_at ? `<span class="today-time">${p.checked_in_at}</span>` : ''}
    </div>
  `).join('');
}

function renderLateList(elId, people) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!people.length) {
    el.innerHTML = '<div class="empty">Нет опозданий</div>';
    return;
  }
  el.innerHTML = people.map((p) => `
    <div class="today-person">
      <span>${p.name}</span>
      <span class="today-time">${p.checked_in_at} (+${p.late_minutes} мин)</span>
    </div>
  `).join('');
}

// ── Employees ─────────────────────────────────────────────────────────────────
async function loadEmployees() {
  const tbody = document.getElementById('employees-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" class="empty">Загрузка...</td></tr>';
  try {
    const employees = await api('GET', '/admin/employees');
    if (!employees.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">Нет сотрудников</td></tr>';
      return;
    }
    tbody.innerHTML = employees.map((e) => `
      <tr>
        <td>${e.name}</td>
        <td>${e.phone}</td>
        <td><span class="badge ${e.role === 'admin' ? 'badge-blue' : 'badge-green'}">${e.role === 'admin' ? 'Админ' : 'Сотрудник'}</span></td>
        <td><span class="badge ${e.is_active ? 'badge-green' : 'badge-red'}">${e.is_active ? 'Активен' : 'Отключён'}</span></td>
        <td>
          <button class="btn btn-ghost btn-sm" onclick="editEmployee(${e.id}, '${e.name}', '${e.phone}', '${e.role}', ${e.is_active})">Изменить</button>
          <button class="btn btn-danger btn-sm" onclick="deleteEmployee(${e.id}, '${e.name}')">Удалить</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">Ошибка: ${err.message}</td></tr>`;
  }
}

function openCreateModal() {
  document.getElementById('modal-title').textContent = 'Добавить сотрудника';
  document.getElementById('emp-id').value = '';
  document.getElementById('emp-name').value = '';
  document.getElementById('emp-phone').value = '';
  document.getElementById('emp-password').value = '';
  document.getElementById('emp-role').value = 'employee';
  document.getElementById('emp-active-group').style.display = 'none';
  document.getElementById('emp-modal').classList.add('open');
}

function editEmployee(id, name, phone, role, isActive) {
  document.getElementById('modal-title').textContent = 'Редактировать сотрудника';
  document.getElementById('emp-id').value = id;
  document.getElementById('emp-name').value = name;
  document.getElementById('emp-phone').value = phone;
  document.getElementById('emp-password').value = '';
  document.getElementById('emp-role').value = role;
  document.getElementById('emp-active').checked = isActive;
  document.getElementById('emp-active-group').style.display = 'block';
  document.getElementById('emp-modal').classList.add('open');
}

function closeEmpModal() {
  document.getElementById('emp-modal').classList.remove('open');
}

async function saveEmployee() {
  const id = document.getElementById('emp-id').value;
  const name = document.getElementById('emp-name').value.trim();
  const phone = document.getElementById('emp-phone').value.trim();
  const password = document.getElementById('emp-password').value;
  const role = document.getElementById('emp-role').value;

  if (!name || !phone) return showAlert('Имя и телефон обязательны', 'error', 'alert-emp');

  try {
    if (id) {
      const body = { name, phone, role, is_active: document.getElementById('emp-active').checked };
      if (password) body.password = password;
      await api('PATCH', `/admin/employees/${id}`, body);
    } else {
      if (!password) return showAlert('Пароль обязателен', 'error', 'alert-emp');
      await api('POST', '/admin/employees', { name, phone, password, role });
    }
    closeEmpModal();
    await loadEmployees();
  } catch (err) {
    showAlert(err.message, 'error', 'alert-emp');
  }
}

async function deleteEmployee(id, name) {
  if (!confirm(`Удалить сотрудника "${name}"?`)) return;
  try {
    await api('DELETE', `/admin/employees/${id}`);
    await loadEmployees();
  } catch (err) {
    showAlert(err.message);
  }
}

// ── Logs ──────────────────────────────────────────────────────────────────────
async function loadLogs(suspiciousOnly = false) {
  const tbody = document.getElementById('logs-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" class="empty">Загрузка...</td></tr>';

  const params = new URLSearchParams({ limit: 100 });
  if (suspiciousOnly) params.set('suspicious_only', 'true');

  const dateFrom = document.getElementById('filter-date-from')?.value;
  const dateTo = document.getElementById('filter-date-to')?.value;
  const userId = document.getElementById('filter-user')?.value;
  if (dateFrom) params.set('date_from', dateFrom);
  if (dateTo) params.set('date_to', dateTo + 'T23:59:59Z');
  if (userId) params.set('user_id', userId);

  try {
    const logs = await api('GET', `/admin/logs?${params}`);
    if (!logs.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">Нет записей</td></tr>';
      return;
    }
    tbody.innerHTML = logs.map((l) => {
      const ts = new Date(l.timestamp).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
      });
      const actionLabel = l.action === 'check_in' ? '✅ Приход' : '🚪 Уход';
      const suspBadge = l.is_suspicious
        ? `<span class="badge badge-red">⚠ ${l.suspicious_reason || 'подозрительно'}</span>`
        : '<span class="badge badge-green">OK</span>';
      return `
        <tr class="${l.is_suspicious ? 'suspicious' : ''}">
          <td>${l.employee_name}</td>
          <td>${actionLabel}</td>
          <td>${ts}</td>
          <td><code style="font-size:12px">${l.ip_address}</code></td>
          <td><code style="font-size:11px;color:var(--muted)">${l.device_id}</code></td>
          <td>${suspBadge}</td>
          <td style="font-size:11px;color:var(--muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${l.user_agent}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty">Ошибка: ${err.message}</td></tr>`;
  }
}

async function loadSuspicious() {
  const tbody = document.getElementById('suspicious-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="empty">Загрузка...</td></tr>';
  try {
    const logs = await api('GET', '/admin/logs/suspicious?limit=100');
    if (!logs.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Подозрительных событий нет 👍</td></tr>';
      return;
    }
    tbody.innerHTML = logs.map((l) => {
      const ts = new Date(l.timestamp).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit',
      });
      const actionLabel = l.action === 'check_in' ? '✅ Приход' : '🚪 Уход';
      const reasonMap = {
        new_device: 'Новое устройство',
        ip_change: 'Смена IP',
        duplicate_device: 'Чужое устройство',
      };
      return `
        <tr class="suspicious">
          <td>${l.employee_name}</td>
          <td>${actionLabel}</td>
          <td>${ts}</td>
          <td><code style="font-size:12px">${l.ip_address}</code></td>
          <td><span class="badge badge-red">${reasonMap[l.suspicious_reason] || l.suspicious_reason || '—'}</span></td>
          <td><code style="font-size:11px;color:var(--muted)">${l.device_id}</code></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">Ошибка: ${err.message}</td></tr>`;
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────
function startPolling() {
  setInterval(() => {
    const active = document.querySelector('.tab-page.active')?.id;
    if (active === 'page-dashboard') loadDashboard();
  }, 30000);
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  try {
    const me = await api('GET', '/auth/me');
    if (me.role !== 'admin') {
      window.location.href = '/app.html';
      return;
    }
    document.getElementById('admin-name').textContent = me.name;
  } catch {
    window.location.href = '/app.html';
    return;
  }

  showTab('dashboard');
  startPolling();
}

document.addEventListener('DOMContentLoaded', init);
