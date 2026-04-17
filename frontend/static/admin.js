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
  document.querySelectorAll('.tab-page').forEach((p) => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));
  document.getElementById(`page-${tab}`)?.classList.add('active');
  document.getElementById(`nav-${tab}`)?.classList.add('active');
  if (tab === 'dashboard') loadDashboard();
  if (tab === 'employees') loadEmployees();
  if (tab === 'salary') { loadRevenue(); initSalaryDates(); }
  if (tab === 'logs') loadLogs();
  if (tab === 'schedule') loadSchedule();
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
    document.getElementById('stat-present').textContent = s.present.length;
    document.getElementById('stat-absent').textContent = s.absent.length;
    document.getElementById('stat-late').textContent = s.late.length;
    renderPeopleList('list-present', s.present, true);
    renderPeopleList('list-absent', s.absent, false);
    renderLateList('list-late', s.late);
  } catch (err) { console.error('Dashboard error:', err); }
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
  if (!people.length) { el.innerHTML = '<div class="empty">Нет опозданий</div>'; return; }
  el.innerHTML = people.map((p) => `
    <div class="today-person"><span>${p.name}</span>
    <span class="today-time">${p.checked_in_at} (+${p.late_minutes} мин)</span></div>
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
async function loadEmployees() {
  await loadPending();
  const tbody = document.getElementById('employees-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" class="empty">Загрузка...</td></tr>';
  try {
    const employees = await api('GET', '/admin/employees');
    if (!employees.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty">Нет сотрудников</td></tr>'; return; }
    tbody.innerHTML = employees.map((e) => `
      <tr>
        <td>${e.name}</td>
        <td>${e.phone}</td>
        <td><span class="badge ${e.role === 'admin' ? 'badge-blue' : 'badge-green'}">${e.role === 'admin' ? 'Админ' : 'Сотрудник'}</span></td>
        <td>${Number(e.hourly_rate).toLocaleString('ru-RU')} ₽</td>
        <td>${Number(e.bonus_percent)}%</td>
        <td><span class="badge ${e.is_active ? 'badge-green' : 'badge-red'}">${e.is_active ? 'Активен' : 'Отключён'}</span></td>
        <td>
          <button class="btn btn-ghost btn-sm" onclick='editEmployee(${JSON.stringify(e)})'>Изменить</button>
          <button class="btn btn-danger btn-sm" onclick="deleteEmployee(${e.id}, '${e.name}')">Удалить</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty">Ошибка: ${err.message}</td></tr>`;
  }
}

function openCreateModal() {
  document.getElementById('modal-title').textContent = 'Добавить сотрудника';
  document.getElementById('emp-id').value = '';
  document.getElementById('emp-name').value = '';
  document.getElementById('emp-phone').value = '';
  document.getElementById('emp-password').value = '';
  document.getElementById('emp-role').value = 'employee';
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
  const hourly_rate = parseFloat(document.getElementById('emp-rate').value);
  const bonus_percent = parseFloat(document.getElementById('emp-bonus').value);

  if (!name || !phone) return showAlert('Имя и телефон обязательны', 'error', 'alert-emp');
  if (isNaN(hourly_rate) || hourly_rate < 0) return showAlert('Укажите корректную ставку', 'error', 'alert-emp');

  try {
    if (id) {
      const body = { name, phone, role, hourly_rate, bonus_percent, is_active: document.getElementById('emp-active').checked };
      if (password) body.password = password;
      await api('PATCH', `/admin/employees/${id}`, body);
    } else {
      if (!password) return showAlert('Пароль обязателен', 'error', 'alert-emp');
      await api('POST', '/admin/employees', { name, phone, password, role, hourly_rate, bonus_percent });
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
async function loadRevenue() {
  const tbody = document.getElementById('revenue-tbody');
  if (!tbody) return;
  try {
    const items = await api('GET', '/admin/revenue?date_from=' + thirtyDaysAgo());
    if (!items.length) { tbody.innerHTML = '<tr><td colspan="3" class="empty">Нет данных</td></tr>'; return; }
    tbody.innerHTML = items.map((r) => `
      <tr>
        <td>${new Date(r.date + 'T00:00:00').toLocaleDateString('ru-RU')}</td>
        <td>${Number(r.amount).toLocaleString('ru-RU')} ₽</td>
        <td style="color:var(--muted)">${r.note || '—'}</td>
      </tr>
    `).join('');
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

// ── Salary ────────────────────────────────────────────────────────────────────
function thirtyDaysAgo() {
  const d = new Date(); d.setDate(d.getDate() - 30);
  return d.toISOString().split('T')[0];
}

function initSalaryDates() {
  const from = document.getElementById('sal-date-from');
  const to = document.getElementById('sal-date-to');
  if (from && !from.value) from.value = thirtyDaysAgo();
  if (to && !to.value) to.value = new Date().toISOString().split('T')[0];

  const revDate = document.getElementById('rev-date');
  if (revDate && !revDate.value) revDate.value = new Date().toISOString().split('T')[0];
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

// ── Schedule / Timeline ───────────────────────────────────────────────────────
async function loadSchedule() {
  const dateInput = document.getElementById('sched-date');
  if (!dateInput) return;
  const date = dateInput.value || new Date().toISOString().split('T')[0];
  const wrap = document.getElementById('schedule-wrap');
  if (wrap) wrap.innerHTML = '<div class="empty">Загрузка...</div>';
  try {
    const data = await api('GET', `/admin/stats/schedule?target_date=${date}`);
    renderSchedule(data);
  } catch (err) {
    if (wrap) wrap.innerHTML = `<div class="empty">Ошибка: ${err.message}</div>`;
  }
}

function renderSchedule(data) {
  const wrap = document.getElementById('schedule-wrap');
  if (!wrap) return;
  const fmtMoney = (n) => Number(n).toLocaleString('ru-RU', { maximumFractionDigits: 0 });

  if (!data.employees.length) {
    wrap.innerHTML = '<div class="empty">Нет сотрудников</div>';
    return;
  }

  // ── Determine time window ──
  let minH = 8, maxH = 20;
  data.employees.forEach((emp) => {
    emp.sessions.forEach((s) => {
      const inH = new Date(s.check_in).getHours() + new Date(s.check_in).getMinutes() / 60;
      minH = Math.min(minH, Math.floor(inH));
      const endTime = s.check_out ? new Date(s.check_out) : new Date();
      const outH = endTime.getHours() + endTime.getMinutes() / 60;
      maxH = Math.max(maxH, Math.ceil(outH));
    });
  });
  minH = Math.max(0, minH - 1);
  maxH = Math.min(24, maxH + 1);
  const span = maxH - minH;

  function toPct(isoStr) {
    const t = new Date(isoStr);
    const h = t.getHours() + t.getMinutes() / 60;
    return Math.max(0, Math.min(100, (h - minH) / span * 100)).toFixed(2);
  }

  // ── Axis labels ──
  const ticks = [];
  for (let h = minH; h <= maxH; h++) {
    const pct = ((h - minH) / span * 100).toFixed(2);
    ticks.push(`<div class="tl-tick" style="left:${pct}%">${String(h).padStart(2,'0')}:00</div>`);
  }

  // ── Rows ──
  const rows = data.employees.map((emp) => {
    const bars = emp.sessions.map((s) => {
      const left = toPct(s.check_in);
      const rightTs = s.check_out || new Date().toISOString();
      const right = toPct(rightTs);
      const w = Math.max(0.4, right - left).toFixed(2);
      const active = !s.check_out;
      const inStr = new Date(s.check_in).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
      const outStr = s.check_out
        ? new Date(s.check_out).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
        : 'сейчас';
      const label = Number(w) > 7 ? `<span class="tl-bar-lbl">${inStr}–${outStr}</span>` : '';
      return `<div class="tl-bar ${active ? 'tl-bar-active' : 'tl-bar-done'}"
        style="left:${left}%;width:${w}%"
        title="${inStr} — ${outStr} (${s.minutes} мин)">${label}</div>`;
    }).join('');

    const h = emp.total_hours;
    const hoursStr = h <= 0 ? '—' : (h >= 1
      ? `${Math.floor(h)} ч ${Math.round((h % 1) * 60)} м`
      : `${Math.round(h * 60)} м`);

    return `
      <div class="tl-row">
        <div class="tl-name">
          <span>${emp.name}</span>
          ${emp.is_active ? '<span class="badge badge-green tl-badge">в работе</span>' : ''}
        </div>
        <div class="tl-track">${bars || '<span style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:11px;color:var(--muted)">нет отметок</span>'}</div>
        <div class="tl-info">
          <div class="tl-earn">${fmtMoney(emp.total_pay)} ₽</div>
          <div class="tl-hours">${hoursStr}</div>
        </div>
      </div>`;
  }).join('');

  const revenueStr = Number(data.revenue) > 0
    ? `Выручка: <b>${Number(data.revenue).toLocaleString('ru-RU')} ₽</b>`
    : '<span style="color:var(--muted)">Выручка на этот день не указана</span>';

  wrap.innerHTML = `
    <div class="tl-summary">${revenueStr}</div>
    <div class="tl-container">
      <div class="tl-axis-wrap"><div class="tl-axis">${ticks.join('')}</div></div>
      <div class="tl-rows">${rows}</div>
    </div>
  `;
}

// ── Polling ───────────────────────────────────────────────────────────────────
function startPolling() {
  setInterval(() => {
    const active = document.querySelector('.tab-page.active')?.id;
    if (active === 'page-dashboard') loadDashboard();
    if (active === 'page-employees') loadPending();
  }, 30000);
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  try {
    const me = await api('GET', '/auth/me');
    if (me.role !== 'admin') { window.location.href = '/app.html'; return; }
    document.getElementById('admin-name').textContent = me.name;
  } catch { window.location.href = '/app.html'; return; }
  const today = new Date().toISOString().split('T')[0];
  const schedDate = document.getElementById('sched-date');
  if (schedDate) schedDate.value = today;

  showTab('dashboard');
  startPolling();
}

document.addEventListener('DOMContentLoaded', init);
