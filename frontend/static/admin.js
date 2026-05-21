// ── Current user (set in init) ────────────────────────────────────────────────
let _currentUser = null; // { is_owner, permissions, role, name }

// ── Permission helper ─────────────────────────────────────────────────────────
function hasPerm(key) {
  if (!_currentUser) return false;
  if (_currentUser.is_owner) return true;
  if (_currentUser.role !== 'admin') return false;
  // NULL permissions = full access for admins
  if (!_currentUser.permissions) return true;
  return !!_currentUser.permissions[key];
}

// ── Apply permissions to UI ───────────────────────────────────────────────────
function applyPermissionsToUI() {
  const tabPerms = {
    'nav-dashboard': 'dashboard', 'nav-employees': 'employees_view',
    'nav-salary': 'salary_view', 'nav-revenue': 'revenue_view',
    'nav-logs': 'logs_view', 'nav-schedule': 'schedule_view',
    'nav-suspicious': 'suspicious_view',
    'bn-dashboard': 'dashboard', 'bn-employees': 'employees_view',
    'bn-salary': 'salary_view', 'bn-revenue': 'revenue_view',
    'bn-logs': 'logs_view', 'bn-schedule': 'schedule_view',
    'bn-suspicious': 'suspicious_view',
  };
  for (const [id, perm] of Object.entries(tabPerms)) {
    const el = document.getElementById(id);
    if (el) el.style.display = hasPerm(perm) ? '' : 'none';
  }
  // Hide add employee button if no manage perm
  const addBtn = document.querySelector('[onclick="openCreateModal()"]');
  if (addBtn) addBtn.style.display = hasPerm('employees_manage') ? '' : 'none';
  // Hide save revenue if no revenue_manage
  const saveRevBtn = document.querySelector('[onclick="saveRevenue()"]');
  if (saveRevBtn) saveRevBtn.style.display = hasPerm('revenue_manage') ? '' : 'none';
}

// ── API ───────────────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = { method, credentials: 'include', headers: {} };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch('/api/v1' + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ── Navigation ────────────────────────────────────────────────────────────────
function showTab(tab) {
  // Permission check
  const tabPerms = {
    dashboard: 'dashboard', employees: 'employees_view',
    salary: 'salary_view', revenue: 'revenue_view',
    logs: 'logs_view', schedule: 'schedule_view',
    suspicious: 'suspicious_view',
  };
  if (tabPerms[tab] && !hasPerm(tabPerms[tab])) {
    showAlert('У вас нет доступа к этому разделу');
    return;
  }
  document.querySelectorAll('.tab-page').forEach((p) => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));
  document.querySelectorAll('.bn-item').forEach((n) => n.classList.remove('active'));
  document.getElementById(`page-${tab}`)?.classList.add('active');
  document.getElementById(`nav-${tab}`)?.classList.add('active');
  document.getElementById(`bn-${tab}`)?.classList.add('active');
  if (tab === 'dashboard') loadDashboard();
  if (tab === 'employees') loadEmployees();
  if (tab === 'salary') initSalaryDates();
  if (tab === 'revenue') { loadRevenue(); initRevenueDate(); }
  if (tab === 'logs') loadLogs();
  if (tab === 'schedule') initScheduleDates();
  if (tab === 'suspicious') loadSuspicious();
}

// ── Alert ─────────────────────────────────────────────────────────────────────
function showAlert(msg, type = 'error', containerId = 'alert-global') {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.textContent = msg;
  el.className = `alert ${type} show`;
  setTimeout(() => el.classList.remove('show'), 5000);
}

// ── Logout ────────────────────────────────────────────────────────────────────
async function doLogout() {
  try { await api('POST', '/auth/logout'); } catch {}
  localStorage.removeItem('role'); localStorage.removeItem('name');
  window.location.href = '/app.html';
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const s = await api('GET', '/admin/stats/today');
    // "На месте" = все кто пришёл (вовремя + опоздавшие)
    document.getElementById('stat-present').textContent = s.present.length + s.late.length;
    document.getElementById('stat-absent').textContent = s.absent.length;
    document.getElementById('stat-late').textContent = s.late.length;
    renderPresentList('list-present', s.present, s.late);
    renderPeopleList('list-absent', s.absent, false);
    renderLateList('list-late', s.late);
  } catch (err) { console.error('Dashboard error:', err); }
}

function renderPresentList(elId, present, late) {
  const el = document.getElementById(elId);
  if (!el) return;
  const all = [
    ...present.map(p => ({ ...p, isLate: false })),
    ...late.map(p => ({ ...p, isLate: true })),
  ].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
  if (!all.length) { el.innerHTML = '<div class="empty">Никого нет</div>'; return; }
  el.innerHTML = all.map((p) => `
    <div class="today-person">
      <span>${p.name}</span>
      <span class="today-time">
        ${p.checked_in_at || ''}
        ${p.isLate ? `<span class="badge badge-yellow" style="font-size:10px;margin-left:4px">+${p.late_minutes}м</span>` : ''}
      </span>
    </div>
  `).join('');
}

function renderPeopleList(elId, people, showTime) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!people.length) { el.innerHTML = '<div class="empty">Нет записей</div>'; return; }
  el.innerHTML = people.map((p) => `
    <div class="today-person"><span>${p.name}</span>
    ${showTime && p.checked_in_at ? `<span class="today-time">${p.checked_in_at}</span>` : ''}</div>
  `).join('');
}

function renderLateList(elId, people) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!people.length) { el.innerHTML = '<div class="empty">Опозданий нет 👍</div>'; return; }
  el.innerHTML = people.map((p) => `
    <div class="today-person"><span>${p.name}</span>
    <span class="today-time">${p.checked_in_at} <span style="color:var(--yellow)">+${p.late_minutes} мин</span></span></div>
  `).join('');
}

// ── Pending approvals ─────────────────────────────────────────────────────────
async function loadPending() {
  const tbody = document.getElementById('pending-tbody');
  const section = document.getElementById('pending-section');
  const badge = document.getElementById('pending-badge');
  if (!tbody) return;
  try {
    const pending = await api('GET', '/admin/employees/pending');
    if (!pending.length) {
      section.style.display = 'none';
      badge.style.display = 'none';
      return;
    }
    section.style.display = 'block';
    badge.style.display = 'inline';
    badge.textContent = pending.length;
    const bnBadge = document.getElementById('bn-pending-badge');
    if (bnBadge) { bnBadge.style.display = 'inline'; bnBadge.textContent = pending.length; }
    tbody.innerHTML = pending.map((e) => `
      <tr>
        <td>${e.name}</td>
        <td>${e.phone}</td>
        <td>${new Date(e.created_at).toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</td>
        <td>
          <button class="btn btn-primary btn-sm" onclick="approveEmployee(${e.id})">✅ Принять</button>
          <button class="btn btn-danger btn-sm" onclick="rejectEmployee(${e.id}, '${e.name}')">❌ Отклонить</button>
        </td>
      </tr>
    `).join('');
  } catch {}
}

async function approveEmployee(id) {
  try {
    await api('POST', `/admin/employees/${id}/approve`);
    showAlert('Сотрудник подтверждён', 'success');
    loadEmployees();
  } catch (err) { showAlert(err.message); }
}

async function rejectEmployee(id, name) {
  if (!confirm(`Отклонить заявку от "${name}"?`)) return;
  try {
    await api('POST', `/admin/employees/${id}/reject`);
    showAlert('Заявка отклонена', 'success');
    loadEmployees();
  } catch (err) { showAlert(err.message); }
}

// ── Employees ─────────────────────────────────────────────────────────────────
const POSITION_LABELS = {
  employee: 'Сотрудник', runner: 'Ранер', cook: 'Повар',
  barman: 'Бармен', admin: 'Администратор',
};

async function loadEmployees() {
  await loadPending();
  const tbody = document.getElementById('employees-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="8" class="empty">Загрузка...</td></tr>';
  try {
    const employees = await api('GET', '/admin/employees');
    if (!employees.length) { tbody.innerHTML = '<tr><td colspan="8" class="empty">Нет сотрудников</td></tr>'; return; }
    tbody.innerHTML = employees.map((e) => {
      const permsBtn = _currentUser?.is_owner && e.role === 'admin'
        ? `<button class="btn btn-ghost btn-sm" onclick="openPermsModal(${e.id},'${e.name.replace(/'/g, "\\'")}')">🔐 Права</button>`
        : '';
      const ownerBadge = e.is_owner ? ' <span class="badge badge-yellow" style="font-size:10px;">👑</span>' : '';
      return `
        <tr>
          <td>${e.name}${ownerBadge}</td>
          <td>${e.phone}</td>
          <td><span class="badge ${e.role === 'admin' ? 'badge-blue' : 'badge-green'}">${e.role === 'admin' ? 'Админ' : 'Сотрудник'}</span></td>
          <td>${POSITION_LABELS[e.position] || e.position}</td>
          <td>${Number(e.hourly_rate).toLocaleString('ru-RU')} ₽</td>
          <td>${Number(e.bonus_percent)}%</td>
          <td><span class="badge ${e.is_active ? 'badge-green' : 'badge-red'}">${e.is_active ? 'Активен' : 'Отключён'}</span></td>
          <td>
            <button class="btn btn-ghost btn-sm" onclick='editEmployee(${JSON.stringify(e)})'>Изменить</button>
            <button class="btn btn-danger btn-sm" onclick="deleteEmployee(${e.id}, '${e.name}')">Удалить</button>
            ${permsBtn}
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty">Ошибка: ${err.message}</td></tr>`;
  }
}

function openCreateModal() {
  document.getElementById('modal-title').textContent = 'Добавить сотрудника';
  document.getElementById('emp-id').value = '';
  document.getElementById('emp-name').value = '';
  document.getElementById('emp-phone').value = '';
  document.getElementById('emp-password').value = '';
  document.getElementById('emp-role').value = 'employee';
  document.getElementById('emp-position').value = 'employee';
  document.getElementById('emp-rate').value = '150';
  document.getElementById('emp-bonus').value = '5';
  document.getElementById('emp-active-group').style.display = 'none';
  document.getElementById('alert-emp').classList.remove('show');
  document.getElementById('emp-modal').classList.add('open');
}

function editEmployee(e) {
  document.getElementById('modal-title').textContent = 'Редактировать сотрудника';
  document.getElementById('emp-id').value = e.id;
  document.getElementById('emp-name').value = e.name;
  document.getElementById('emp-phone').value = e.phone;
  document.getElementById('emp-password').value = '';
  document.getElementById('emp-role').value = e.role;
  document.getElementById('emp-position').value = e.position || 'employee';
  document.getElementById('emp-rate').value = Number(e.hourly_rate);
  document.getElementById('emp-bonus').value = Number(e.bonus_percent);
  document.getElementById('emp-active').checked = e.is_active;
  document.getElementById('emp-active-group').style.display = 'block';
  document.getElementById('alert-emp').classList.remove('show');
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
  const position = document.getElementById('emp-position').value;
  const hourly_rate = parseFloat(document.getElementById('emp-rate').value);
  const bonus_percent = parseFloat(document.getElementById('emp-bonus').value);

  if (!name || !phone) return showAlert('Имя и телефон обязательны', 'error', 'alert-emp');
  if (isNaN(hourly_rate) || hourly_rate < 0) return showAlert('Укажите корректную ставку', 'error', 'alert-emp');

  try {
    if (id) {
      const body = { name, phone, role, position, hourly_rate, bonus_percent, is_active: document.getElementById('emp-active').checked };
      if (password) body.password = password;
      await api('PATCH', `/admin/employees/${id}`, body);
    } else {
      if (!password) return showAlert('Пароль обязателен', 'error', 'alert-emp');
      await api('POST', '/admin/employees', { name, phone, password, role, position, hourly_rate, bonus_percent });
    }
    closeEmpModal();
    showAlert('Сохранено', 'success');
    await loadEmployees();
  } catch (err) { showAlert(err.message, 'error', 'alert-emp'); }
}

async function deleteEmployee(id, name) {
  if (!confirm(`Удалить сотрудника "${name}"?`)) return;
  try {
    await api('DELETE', `/admin/employees/${id}`);
    showAlert('Удалено', 'success');
    await loadEmployees();
  } catch (err) { showAlert(err.message); }
}

// ── Revenue ───────────────────────────────────────────────────────────────────
function thirtyDaysAgo() {
  const d = new Date(); d.setDate(d.getDate() - 30);
  return d.toISOString().split('T')[0];
}

function initRevenueDate() {
  const revDate = document.getElementById('rev-date');
  if (revDate && !revDate.value) revDate.value = new Date().toISOString().split('T')[0];
}

async function loadRevenue() {
  const tbody = document.getElementById('revenue-tbody');
  if (!tbody) return;
  try {
    const items = await api('GET', '/admin/revenue?date_from=' + thirtyDaysAgo());
    if (!items.length) { tbody.innerHTML = '<tr><td colspan="3" class="empty">Нет данных</td></tr>'; return; }
    let total = 0;
    const rows = items.map((r) => {
      total += Number(r.amount);
      return `<tr>
        <td>${new Date(r.date + 'T00:00:00').toLocaleDateString('ru-RU')}</td>
        <td>${Number(r.amount).toLocaleString('ru-RU')} ₽</td>
        <td style="color:var(--muted)">${r.note || '—'}</td>
      </tr>`;
    });
    rows.push(`<tr style="font-weight:600;">
      <td>ИТОГО</td>
      <td>${total.toLocaleString('ru-RU')} ₽</td>
      <td></td>
    </tr>`);
    tbody.innerHTML = rows.join('');
  } catch {}
}

async function saveRevenue() {
  const date = document.getElementById('rev-date').value;
  const amount = document.getElementById('rev-amount').value;
  const note = document.getElementById('rev-note').value.trim();
  if (!date || !amount) return showAlert('Укажите дату и сумму');
  try {
    await api('POST', '/admin/revenue', { date, amount: parseFloat(amount), note: note || null });
    showAlert('Выручка сохранена', 'success');
    loadRevenue();
  } catch (err) { showAlert(err.message); }
}

function exportRevenue() {
  const params = new URLSearchParams({ date_from: thirtyDaysAgo() });
  window.location.href = `/api/v1/admin/revenue/export?${params}`;
}

// ── Salary ────────────────────────────────────────────────────────────────────
function initSalaryDates() {
  const from = document.getElementById('sal-date-from');
  const to = document.getElementById('sal-date-to');
  if (from && !from.value) from.value = thirtyDaysAgo();
  if (to && !to.value) to.value = new Date().toISOString().split('T')[0];
}

function exportSalary() {
  const dateFrom = document.getElementById('sal-date-from').value;
  const dateTo = document.getElementById('sal-date-to').value;
  if (!dateFrom || !dateTo) return showAlert('Выберите период');
  window.location.href = `/api/v1/admin/salary/export?date_from=${dateFrom}&date_to=${dateTo}`;
}

async function calcSalary() {
  const dateFrom = document.getElementById('sal-date-from').value;
  const dateTo = document.getElementById('sal-date-to').value;
  if (!dateFrom || !dateTo) return showAlert('Выберите период');

  const result = document.getElementById('salary-result');
  result.innerHTML = '<div class="empty">Расчёт...</div>';

  try {
    const rep = await api('GET', `/admin/salary?date_from=${dateFrom}&date_to=${dateTo}`);
    const fmtDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('ru-RU');
    const fmt = (n) => Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 2 });

    const totalAll = rep.employees.reduce((sum, e) => sum + Number(e.total_pay), 0);
    const totalBase = rep.employees.reduce((sum, e) => sum + Number(e.base_pay), 0);
    const totalBonus = rep.employees.reduce((sum, e) => sum + Number(e.bonus_pay), 0);

    result.innerHTML = `
      <div class="salary-summary">
        <span>Период: <b>${fmtDate(rep.date_from)} — ${fmtDate(rep.date_to)}</b></span>
        <span>Выручка: <b>${fmt(rep.total_revenue)} ₽</b></span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Сотрудник</th><th>Часов</th>
              <th>Ставка</th><th>База</th>
              <th>Бонус %</th><th>Бонус ₽</th>
              <th>Итого</th>
            </tr>
          </thead>
          <tbody>
            ${rep.employees.length ? rep.employees.map((e) => `
              <tr>
                <td>${e.name}</td>
                <td>${e.hours_worked}</td>
                <td>${fmt(e.hourly_rate)} ₽/ч</td>
                <td>${fmt(e.base_pay)} ₽</td>
                <td>${Number(e.bonus_percent)}%</td>
                <td>${fmt(e.bonus_pay)} ₽</td>
                <td><b>${fmt(e.total_pay)} ₽</b></td>
              </tr>
            `).join('') : '<tr><td colspan="7" class="empty">Нет сотрудников</td></tr>'}
          </tbody>
          ${rep.employees.length ? `
          <tfoot>
            <tr class="salary-total-row">
              <td><b>ИТОГО</b></td>
              <td>—</td><td>—</td>
              <td><b>${fmt(totalBase)} ₽</b></td>
              <td>—</td>
              <td><b>${fmt(totalBonus)} ₽</b></td>
              <td><b class="salary-grand-total">${fmt(totalAll)} ₽</b></td>
            </tr>
          </tfoot>` : ''}
        </table>
      </div>
    `;
  } catch (err) {
    result.innerHTML = `<div class="empty">Ошибка: ${err.message}</div>`;
  }
}

// ── Logs ──────────────────────────────────────────────────────────────────────
async function loadLogs() {
  const tbody = document.getElementById('logs-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="empty">Загрузка...</td></tr>';
  const params = new URLSearchParams({ limit: 100 });
  const dateFrom = document.getElementById('filter-date-from')?.value;
  const dateTo = document.getElementById('filter-date-to')?.value;
  const userId = document.getElementById('filter-user')?.value;
  if (dateFrom) params.set('date_from', dateFrom);
  if (dateTo) params.set('date_to', dateTo + 'T23:59:59Z');
  if (userId) params.set('user_id', userId);
  try {
    const logs = await api('GET', `/admin/logs?${params}`);
    if (!logs.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty">Нет записей</td></tr>'; return; }
    tbody.innerHTML = logs.map((l) => {
      const ts = new Date(l.timestamp).toLocaleString('ru-RU', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
      const suspBadge = l.is_suspicious
        ? `<span class="badge badge-red">⚠ ${l.suspicious_reason || 'подозрительно'}</span>`
        : '<span class="badge badge-green">OK</span>';
      return `<tr class="${l.is_suspicious ? 'suspicious' : ''}">
        <td>${l.employee_name}</td>
        <td>${l.action === 'check_in' ? '✅ Приход' : '🚪 Уход'}</td>
        <td>${ts}</td>
        <td><code style="font-size:12px">${l.ip_address}</code></td>
        <td><code style="font-size:11px;color:var(--muted)">${l.device_id}</code></td>
        <td>${suspBadge}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">Ошибка: ${err.message}</td></tr>`;
  }
}

function resetLogsFilter() {
  document.getElementById('filter-date-from').value = '';
  document.getElementById('filter-date-to').value = '';
  document.getElementById('filter-user').value = '';
  loadLogs();
}

async function loadSuspicious() {
  const tbody = document.getElementById('suspicious-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="empty">Загрузка...</td></tr>';
  try {
    const logs = await api('GET', '/admin/logs/suspicious?limit=100');
    if (!logs.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty">Подозрительных событий нет 👍</td></tr>'; return; }
    const reasonMap = { new_device:'Новое устройство', ip_change:'Смена IP', duplicate_device:'Чужое устройство' };
    tbody.innerHTML = logs.map((l) => {
      const ts = new Date(l.timestamp).toLocaleString('ru-RU', { day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit' });
      return `<tr class="suspicious">
        <td>${l.employee_name}</td>
        <td>${l.action === 'check_in' ? '✅ Приход' : '🚪 Уход'}</td>
        <td>${ts}</td>
        <td><code style="font-size:12px">${l.ip_address}</code></td>
        <td><span class="badge badge-red">${reasonMap[l.suspicious_reason] || l.suspicious_reason || '—'}</span></td>
        <td><code style="font-size:11px;color:var(--muted)">${l.device_id}</code></td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">Ошибка: ${err.message}</td></tr>`;
  }
}

// ── Schedule / Weekly table ───────────────────────────────────────────────────
function getMonday(d = new Date()) {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const mon = new Date(d); mon.setDate(d.getDate() + diff);
  return mon.toISOString().split('T')[0];
}

function addDays(isoStr, n) {
  const d = new Date(isoStr);
  d.setDate(d.getDate() + n);
  return d.toISOString().split('T')[0];
}

function initScheduleDates() {
  const fromEl = document.getElementById('sched-date-from');
  const toEl = document.getElementById('sched-date-to');
  if (fromEl && !fromEl.value) fromEl.value = getMonday();
  if (toEl && !toEl.value) toEl.value = addDays(getMonday(), 6);
}

function exportSchedule() {
  const dateFrom = document.getElementById('sched-date-from').value;
  const dateTo = document.getElementById('sched-date-to').value;
  if (!dateFrom || !dateTo) return showAlert('Выберите период');
  window.location.href = `/api/v1/admin/stats/week/export?date_from=${dateFrom}&date_to=${dateTo}`;
}

async function loadSchedule() {
  const dateFrom = document.getElementById('sched-date-from').value;
  const dateTo = document.getElementById('sched-date-to').value;
  if (!dateFrom || !dateTo) {
    const wrap = document.getElementById('schedule-wrap');
    if (wrap) wrap.innerHTML = '<div class="empty">Выберите период и нажмите «Показать»</div>';
    return;
  }

  const wrap = document.getElementById('schedule-wrap');
  if (wrap) wrap.innerHTML = '<div class="empty">Загрузка...</div>';
  try {
    const data = await api('GET', `/admin/stats/week?date_from=${dateFrom}&date_to=${dateTo}`);
    renderWeekSchedule(data);
  } catch (err) {
    if (wrap) wrap.innerHTML = `<div class="empty">Ошибка: ${err.message}</div>`;
  }
}

function renderWeekSchedule(data) {
  const wrap = document.getElementById('schedule-wrap');
  if (!wrap) return;

  const DAY_RU = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];
  const fmtTime = (iso) => new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const fmtDate = (iso) => {
    const d = new Date(iso + 'T00:00:00');
    return `${DAY_RU[d.getDay()]} ${String(d.getDate()).padStart(2,'0')}.${String(d.getMonth()+1).padStart(2,'0')}`;
  };

  // ── Header ──
  const headCells = data.dates.map((d) => {
    const isToday = d === new Date().toISOString().split('T')[0];
    return `<th class="${isToday ? 'week-today' : ''}">${fmtDate(d)}</th>`;
  }).join('');

  if (!data.employees.length) {
    wrap.innerHTML = '<div class="empty">Нет сотрудников</div>';
    return;
  }

  // ── Rows ──
  const rows = data.employees.map((emp) => {
    const cells = emp.days.map((day) => {
      const hasData = day.check_in || day.check_out;
      const inStr  = day.check_in  ? fmtTime(day.check_in)  : '—';
      const outStr = day.check_out ? fmtTime(day.check_out) : '—';
      const hStr   = day.hours > 0
        ? (day.hours >= 1 ? `${day.hours} ч` : `${Math.round(day.hours * 60)} м`)
        : '';
      const cls = hasData ? 'week-cell-filled' : 'week-cell-empty';
      return `<td class="week-cell ${cls}" onclick="openAttModal(${emp.user_id},'${emp.name}','${day.date}','${day.check_in ? fmtTime(day.check_in) : ''}','${day.check_out ? fmtTime(day.check_out) : ''}')">
        ${hasData
          ? `<div class="wc-in">↑ ${inStr}</div><div class="wc-out">↓ ${outStr}</div>${hStr ? `<div class="wc-h">${hStr}</div>` : ''}`
          : `<span class="wc-dash">—</span>`
        }
      </td>`;
    }).join('');
    return `<tr><td class="week-name">${emp.name}</td>${cells}</tr>`;
  }).join('');

  wrap.innerHTML = `
    <div class="table-wrap week-table-wrap">
      <table class="week-table">
        <thead><tr><th>Сотрудник</th>${headCells}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p style="margin-top:10px;font-size:12px;color:var(--muted)">
      Нажмите на любую ячейку чтобы отредактировать смену
    </p>
  `;
}

// ── Attendance edit modal ─────────────────────────────────────────────────────
function openAttModal(userId, name, date, checkIn, checkOut) {
  document.getElementById('att-modal-title').textContent = `${name} — ${new Date(date + 'T00:00:00').toLocaleDateString('ru-RU')}`;
  document.getElementById('att-user-id').value = userId;
  document.getElementById('att-date').value = date;
  document.getElementById('att-checkin').value = checkIn || '';
  document.getElementById('att-checkout').value = checkOut || '';
  document.getElementById('alert-att').classList.remove('show');
  document.getElementById('att-modal').classList.add('open');
}

function closeAttModal() {
  document.getElementById('att-modal').classList.remove('open');
}

async function saveAttDay() {
  const userId   = parseInt(document.getElementById('att-user-id').value);
  const date     = document.getElementById('att-date').value;
  const checkIn  = document.getElementById('att-checkin').value  || null;
  const checkOut = document.getElementById('att-checkout').value || null;
  try {
    await api('PUT', '/admin/attendance/day', { user_id: userId, date, check_in: checkIn, check_out: checkOut });
    closeAttModal();
    showAlert('Сохранено', 'success');
    loadSchedule();
  } catch (err) {
    showAlert(err.message, 'error', 'alert-att');
  }
}

async function clearAttDay() {
  if (!confirm('Очистить все отметки за этот день?')) return;
  const userId = parseInt(document.getElementById('att-user-id').value);
  const date   = document.getElementById('att-date').value;
  try {
    await api('PUT', '/admin/attendance/day', { user_id: userId, date, check_in: null, check_out: null });
    closeAttModal();
    showAlert('День очищен', 'success');
    loadSchedule();
  } catch (err) {
    showAlert(err.message, 'error', 'alert-att');
  }
}

// ── Position auto-rate ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const posEl = document.getElementById('emp-position');
  if (posEl) {
    posEl.addEventListener('change', () => {
      const rates = { employee: 150, runner: 150, cook: 200, barman: 200, admin: 250 };
      const pos = posEl.value;
      // Only set if creating new employee (no id)
      if (!document.getElementById('emp-id').value) {
        document.getElementById('emp-rate').value = rates[pos] || 150;
      }
    });
  }
});

// ── Polling ───────────────────────────────────────────────────────────────────
function startPolling() {
  setInterval(() => {
    const active = document.querySelector('.tab-page.active')?.id;
    if (active === 'page-dashboard') loadDashboard();
    if (active === 'page-employees') loadPending();
  }, 30000);
}

// ── Permissions modal ─────────────────────────────────────────────────────────
const PERM_LABELS = {
  dashboard: 'Сводка за сегодня',
  employees_view: 'Просмотр сотрудников',
  employees_manage: 'Управление сотрудниками (добавить/удалить/изменить)',
  salary_view: 'Просмотр зарплаты',
  revenue_view: 'Просмотр выручки',
  revenue_manage: 'Ввод / редактирование выручки',
  logs_view: 'История отметок',
  schedule_view: 'Просмотр графика',
  schedule_edit: 'Редактирование ячеек графика',
  suspicious_view: 'Подозрительные события',
};

async function openPermsModal(userId, name) {
  document.getElementById('perms-user-id').value = userId;
  document.getElementById('perms-modal-name').textContent = name;
  document.getElementById('alert-perms').classList.remove('show');

  try {
    const data = await api('GET', `/admin/employees/${userId}/permissions`);
    const currentPerms = data.permissions; // null = full access

    const list = document.getElementById('perms-list');
    list.innerHTML = Object.entries(PERM_LABELS).map(([key, label]) => {
      const checked = currentPerms === null ? true : !!currentPerms[key];
      return `
        <label style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--bg);border-radius:8px;border:1px solid var(--border);cursor:pointer;">
          <input type="checkbox" id="perm-${key}" ${checked ? 'checked' : ''} style="width:18px;height:18px;accent-color:var(--accent);" />
          <span style="font-size:14px;">${label}</span>
        </label>
      `;
    }).join('');

    document.getElementById('perms-modal').classList.add('open');
  } catch (err) {
    showAlert('Ошибка загрузки прав: ' + err.message);
  }
}

function closePermsModal() {
  document.getElementById('perms-modal').classList.remove('open');
}

function setFullAccess() {
  Object.keys(PERM_LABELS).forEach(key => {
    const el = document.getElementById(`perm-${key}`);
    if (el) el.checked = true;
  });
}

async function savePermissions() {
  const userId = document.getElementById('perms-user-id').value;
  const permissions = {};
  let allTrue = true;

  Object.keys(PERM_LABELS).forEach(key => {
    const el = document.getElementById(`perm-${key}`);
    permissions[key] = el ? el.checked : true;
    if (!permissions[key]) allTrue = false;
  });

  // If all true, send null (full access = default)
  const body = { permissions: allTrue ? null : permissions };

  try {
    await api('PUT', `/admin/employees/${userId}/permissions`, body);
    showAlert('Права сохранены', 'success');
    closePermsModal();
  } catch (err) {
    showAlert('Ошибка: ' + err.message, 'error', 'alert-perms');
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  try {
    const me = await api('GET', '/auth/me');
    if (me.role !== 'admin') { window.location.href = '/app.html'; return; }
    _currentUser = me;
    document.getElementById('admin-name').textContent = me.name;
    const mob = document.getElementById('mobile-admin-name');
    if (mob) mob.textContent = me.name;
  } catch { window.location.href = '/app.html'; return; }

  // Apply permissions to UI
  applyPermissionsToUI();

  // Set default schedule dates
  initScheduleDates();

  // Find first tab the user has access to
  const tabOrder = ['dashboard', 'employees', 'salary', 'revenue', 'logs', 'schedule', 'suspicious'];
  const tabPermMap = {
    dashboard: 'dashboard', employees: 'employees_view',
    salary: 'salary_view', revenue: 'revenue_view',
    logs: 'logs_view', schedule: 'schedule_view',
    suspicious: 'suspicious_view',
  };
  const firstAllowed = tabOrder.find(t => hasPerm(tabPermMap[t]));
  showTab(firstAllowed || 'dashboard');

  startPolling();
}

document.addEventListener('DOMContentLoaded', init);
