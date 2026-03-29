
// ─── State ───────────────────────────────────────────────────────────────────
let liveCh = null, liveRange = 1;
let histHumCh = null, histTmpCh = null;
let donutCh = null;
let dailyHumCh = null, dailyIrrCh = null, zoneHumCh = null, alertTypeCh = null;
let alertFilter = 'active';
let refreshInterval = null;

// ─── Navigation ──────────────────────────────────────────────────────────────
const PAGE_META = {
  dashboard:   { title: 'Dashboard',      sub: 'Vue d\'ensemble en temps réel' },
  history:     { title: 'Historique',     sub: 'Données historiques des capteurs' },
  stats:       { title: 'Statistiques',   sub: 'Analyse sur 7 jours' },
  alerts:      { title: 'Alertes',        sub: 'Notifications et incidents' },
  irrigations: { title: 'Irrigations',    sub: 'Journal des événements d\'irrigation' },
};

function navigate(btn) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const page = btn.dataset.page;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  document.getElementById('page-title').textContent = PAGE_META[page].title;
  document.getElementById('page-sub').textContent   = PAGE_META[page].sub;
  loadPage(page);
}

function loadPage(page) {
  if (page === 'dashboard')   loadDashboard();
  if (page === 'history')     loadHistory();
  if (page === 'stats')       loadStats();
  if (page === 'alerts')      loadAlerts();
  if (page === 'irrigations') loadIrrigations();
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function toast(msg, type='success') {
  const icons = { success:'✅', error:'❌', warn:'⚠️', info:'ℹ️' };
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : type === 'warn' ? 'warn' : ''}`;
  el.innerHTML = `<span>${icons[type]||'✅'}</span> ${msg}`;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function fmtTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts.replace(' ', 'T'));
  return d.toLocaleString('fr-FR', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
}

function getRecClass(rec) {
  if (!rec) return '';
  if (rec.includes('maintenant')) return 'urgent';
  if (rec.includes('2h') || rec.includes('Surveiller')) return 'warn';
  return '';
}

function mkChart(id, cfg) {
  const ctx = document.getElementById(id);
  if (!ctx) return null;
  return new Chart(ctx, cfg);
}

function destroyAndCreate(existing, id, cfg) {
  if (existing) existing.destroy();
  return mkChart(id, cfg);
}

const CHART_DEFAULTS = {
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b', font: { size: 10 } } },
    y: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b', font: { size: 10 } } }
  }
};

// ─── Dashboard ───────────────────────────────────────────────────────────────
async function loadDashboard() {
  const data = await fetch('/api/dashboard').then(r => r.json());
  const sensors = data.sensors;

  // KPIs
  const avgHum = sensors.reduce((s,x) => s+x.humidity, 0) / sensors.length;
  const avgTmp = sensors.reduce((s,x) => s+x.temperature, 0) / sensors.length;
  document.getElementById('kpi-hum').innerHTML    = `${avgHum.toFixed(1)}<small style="font-size:16px">%</small>`;
  document.getElementById('kpi-tmp').innerHTML    = `${avgTmp.toFixed(1)}<small style="font-size:16px">°C</small>`;
  document.getElementById('kpi-alerts').textContent = data.total_alerts;
  document.getElementById('kpi-irr').textContent   = data.total_irrigations;
  document.getElementById('alert-badge').textContent = data.total_alerts;
  document.getElementById('last-update').textContent = new Date().toLocaleTimeString('fr-FR');

  // Sensor Cards
  const container = document.getElementById('sensor-cards');
  container.innerHTML = sensors.map(s => {
    const humPct = Math.min(100, s.humidity);
    const tmpPct = Math.min(100, (s.temperature / 50) * 100);
    const recClass = getRecClass(s.recommendation);
    const alertBadge = s.alerts > 0
      ? `<span class="badge badge-red">⚠️ ${s.alerts} alerte${s.alerts>1?'s':''}</span>`
      : `<span class="badge badge-green">✅ OK</span>`;
    return `
    <div class="sensor-card">
      <div class="sensor-header">
        <div>
          <div class="sensor-name">${s.name}</div>
          <div class="sensor-zone">${s.zone}</div>
        </div>
        ${alertBadge}
      </div>
      <div class="sensor-body">
        <div class="sensor-metrics">
          <div class="metric">
            <div class="metric-icon">💧</div>
            <div class="metric-val" style="color:var(--green-600)">${s.humidity.toFixed(1)}%</div>
            <div class="metric-lbl">Humidité sol</div>
          </div>
          <div class="metric">
            <div class="metric-icon">🌡️</div>
            <div class="metric-val" style="color:var(--amber)">${s.temperature.toFixed(1)}°C</div>
            <div class="metric-lbl">Température</div>
          </div>
        </div>
        <div class="gauge-container">
          <div class="gauge-label"><span>Humidité</span><span>${humPct.toFixed(1)}%</span></div>
          <div class="gauge-bar"><div class="gauge-fill humidity" style="width:${humPct}%"></div></div>
        </div>
        <div class="gauge-container">
          <div class="gauge-label"><span>Température</span><span>${s.temperature.toFixed(1)}°C</span></div>
          <div class="gauge-bar"><div class="gauge-fill temp" style="width:${tmpPct}%"></div></div>
        </div>
        <div class="rec-box ${recClass}" style="margin-top:12px">
          <div>
            <div class="rec-text">🤖 ${s.recommendation}</div>
            <div class="rec-conf">Confiance : ${s.confidence}%</div>
          </div>
          <button class="btn btn-primary btn-sm" onclick="quickIrrigate(${s.id})">💧</button>
        </div>
        <div style="margin-top:8px;font-size:11px;color:var(--text-muted)">
          Dernière mesure : ${fmtTime(s.timestamp)}
        </div>
      </div>
    </div>`;
  }).join('');

  // Live chart - Zone A (sensor 1)
  await loadLiveChart(1, liveRange);
  // Donut alerts
  await loadAlertDonut();
}

async function loadLiveChart(sensorId, hours) {
  const rows = await fetch(`/api/history/${sensorId}?hours=${hours}`).then(r => r.json());
  const labels = rows.map(r => {
    const d = new Date(r.timestamp.replace(' ','T'));
    return d.toLocaleTimeString('fr-FR', {hour:'2-digit', minute:'2-digit'});
  });
  const hums = rows.map(r => r.humidity);
  const tmps = rows.map(r => r.temperature);

  liveCh = destroyAndCreate(liveCh, 'chart-live', {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Humidité (%)',
          data: hums,
          borderColor: '#22a022', backgroundColor: 'rgba(34,160,34,.12)',
          tension: 0.4, fill: true, pointRadius: 0, yAxisID: 'y'
        },
        {
          label: 'Température (°C)',
          data: tmps,
          borderColor: '#f59e0b', backgroundColor: 'transparent',
          tension: 0.4, fill: false, pointRadius: 0, borderDash: [5,3], yAxisID: 'y1'
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: true, labels: { boxWidth: 10, font: { size: 11 } } } },
      scales: {
        x: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b', font: { size: 9 }, maxTicksLimit: 10 } },
        y: { grid: { color: '#e5fde5' }, ticks: { color: '#22a022', font: { size: 9 } }, title: { display: true, text: 'Humidité (%)' } },
        y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#f59e0b', font: { size: 9 } }, title: { display: true, text: 'Temp (°C)' } }
      }
    }
  });
}

async function loadAlertDonut() {
  const stats = await fetch('/api/stats').then(r => r.json());
  const dist = stats.alert_distribution;
  const labels = dist.map(d => `${d.type === 'low_humidity' ? '💧 Humidité basse' : '🌡️ Temp élevée'} (${d.severity})`);
  const values = dist.map(d => d.count);
  const colors = ['#22a022', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6'];

  donutCh = destroyAndCreate(donutCh, 'chart-alerts-donut', {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: colors.slice(0, values.length), borderWidth: 0 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '65%',
      plugins: { legend: { display: false } }
    }
  });

  document.getElementById('donut-legend').innerHTML = labels.map((l,i) =>
    `<div class="legend-item"><div class="legend-dot" style="background:${colors[i]}"></div>${l} — <b>${values[i]}</b></div>`
  ).join('');
}

function setTimeRange(btn, hours) {
  document.querySelectorAll('.time-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  liveRange = hours;
  loadLiveChart(1, hours);
}

// ─── History ─────────────────────────────────────────────────────────────────
async function loadHistory() {
  const sid  = document.getElementById('hist-sensor').value;
  const hrs  = document.getElementById('hist-period').value;
  const rows = await fetch(`/api/history/${sid}?hours=${hrs}`).then(r => r.json());

  const labels = rows.map(r => {
    const d = new Date(r.timestamp.replace(' ','T'));
    return d.toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  });
  const hums = rows.map(r => r.humidity);
  const tmps = rows.map(r => r.temperature);
  const sub  = `${rows.length} relevés sur ${hrs}h`;
  document.getElementById('hist-hum-sub').textContent = sub;
  document.getElementById('hist-tmp-sub').textContent = sub;

  histHumCh = destroyAndCreate(histHumCh, 'chart-hist-hum', {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Humidité (%)', data: hums,
        borderColor: '#22a022', backgroundColor: 'rgba(34,160,34,.15)',
        tension: 0.4, fill: true, pointRadius: 0
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b', font: { size: 9 }, maxTicksLimit: 12 } },
        y: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b', font: { size: 9 } }, min: 0, max: 100 }
      }
    }
  });

  histTmpCh = destroyAndCreate(histTmpCh, 'chart-hist-tmp', {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Température (°C)', data: tmps,
        borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,.1)',
        tension: 0.4, fill: true, pointRadius: 0
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b', font: { size: 9 }, maxTicksLimit: 12 } },
        y: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b', font: { size: 9 } } }
      }
    }
  });
}

// ─── Stats ────────────────────────────────────────────────────────────────────
async function loadStats() {
  const stats = await fetch('/api/stats').then(r => r.json());

  // Daily humidity
  const dh = stats.daily_humidity;
  dailyHumCh = destroyAndCreate(dailyHumCh, 'chart-daily-hum', {
    type: 'bar',
    data: {
      labels: dh.map(r => r.day.slice(5)),
      datasets: [
        { label: 'Moy. Humidité (%)', data: dh.map(r => r.avg_hum), backgroundColor: 'rgba(34,160,34,.7)', borderRadius: 6 },
        { label: 'Min Humidité (%)', data: dh.map(r => r.min_hum), backgroundColor: 'rgba(239,68,68,.5)', borderRadius: 6 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: true, labels: { boxWidth: 12, font: { size: 11 } } } },
      scales: {
        x: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b' } },
        y: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b' }, max: 100 }
      }
    }
  });

  // Daily irrigations
  const di = stats.daily_irrigation;
  dailyIrrCh = destroyAndCreate(dailyIrrCh, 'chart-daily-irr', {
    type: 'bar',
    data: {
      labels: di.map(r => r.day.slice(5)),
      datasets: [{ label: 'Nb irrigations', data: di.map(r => r.count), backgroundColor: 'rgba(59,130,246,.7)', borderRadius: 6 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b' } },
        y: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b' }, stepSize: 1 }
      }
    }
  });

  // Zone humidity radar-like bar
  const zh = stats.zone_humidity;
  zoneHumCh = destroyAndCreate(zoneHumCh, 'chart-zone-hum', {
    type: 'bar',
    data: {
      labels: zh.map(r => r.zone),
      datasets: [
        { label: 'Humidité (%)', data: zh.map(r => r.avg_hum), backgroundColor: ['#22a022','#00c9a7','#f59e0b','#3b82f6'], borderRadius: 8 }
      ]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#e5fde5' }, ticks: { color: '#6b9b6b' }, max: 100 },
        y: { grid: { display: false }, ticks: { color: '#6b9b6b', font: { weight: '600' } } }
      }
    }
  });

  // Alert types donut
  const ad = stats.alert_distribution;
  const labels = ad.map(d => d.type === 'low_humidity' ? '💧 Humidité basse' : '🌡️ Temp élevée');
  alertTypeCh = destroyAndCreate(alertTypeCh, 'chart-alert-type', {
    type: 'pie',
    data: {
      labels,
      datasets: [{ data: ad.map(d => d.count), backgroundColor: ['#22a022','#ef4444','#f59e0b','#3b82f6'], borderWidth: 0 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: true, position: 'bottom', labels: { font: { size: 11 }, boxWidth: 12 } } }
    }
  });
}

// ─── Alerts ──────────────────────────────────────────────────────────────────
async function loadAlerts() {
  const resolved = alertFilter === 'resolved' ? 1 : 0;
  const alerts = await fetch(`/api/alerts?resolved=${resolved}`).then(r => r.json());
  const list = document.getElementById('alert-list');
  if (!alerts.length) {
    list.innerHTML = `<div class="empty-state"><div class="emoji">${resolved ? '✅' : '🎉'}</div><p>${resolved ? 'Aucune alerte résolue.' : 'Aucune alerte active !'}</p></div>`;
    return;
  }
  const icons = { low_humidity: '💧', high_temp: '🌡️', sensor_error: '⚡' };
  list.innerHTML = alerts.map(a => `
    <div class="alert-item ${a.severity}">
      <div class="alert-icon">${icons[a.type] || '⚠️'}</div>
      <div class="alert-info">
        <div class="alert-msg">${a.message}</div>
        <div class="alert-meta">
          📍 ${a.sensor_name} — ${a.zone} &nbsp;|&nbsp;
          🕐 ${fmtTime(a.timestamp)} &nbsp;|&nbsp;
          <span class="badge badge-${a.severity === 'critical' ? 'red' : 'amber'}">${a.severity}</span>
        </div>
      </div>
      ${!a.resolved ? `<div class="alert-actions">
        <button class="btn btn-outline btn-sm" onclick="resolveAlert(${a.id})">✅ Résoudre</button>
      </div>` : ''}
    </div>`).join('');
}

function filterAlerts(btn, type) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  alertFilter = type;
  loadAlerts();
}

async function resolveAlert(id) {
  await fetch(`/api/alerts/resolve/${id}`, { method: 'POST' });
  toast('Alerte résolue ✅');
  loadAlerts();
  loadDashboard();
}

// ─── Irrigations ─────────────────────────────────────────────────────────────
async function loadIrrigations() {
  const rows = await fetch('/api/irrigations').then(r => r.json());
  const tbody = document.getElementById('irr-tbody');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="emoji">💧</div><p>Aucune irrigation enregistrée.</p></div></td></tr>`;
    return;
  }
  const triggerLabel = { manual: '🖱️ Manuel', ai: '🤖 IA', auto: '⚙️ Auto' };
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td><b>${r.sensor_name}</b><br><span style="font-size:11px;color:var(--text-muted)">${r.zone}</span></td>
      <td>${fmtTime(r.started_at)}</td>
      <td>${fmtTime(r.ended_at)}</td>
      <td><b>${r.duration_min}</b> min</td>
      <td>${triggerLabel[r.trigger_type] || r.trigger_type}</td>
      <td><span class="badge badge-${r.ended_at ? 'green' : 'blue'}">${r.ended_at ? '✅ Terminée' : '🔄 En cours'}</span></td>
    </tr>`).join('');
}

// ─── Modal ────────────────────────────────────────────────────────────────────
function openIrrigateModal(sensorId) {
  if (sensorId) document.getElementById('irr-sensor').value = sensorId;
  document.getElementById('modal-irrigate').classList.add('open');
}
function closeModal() {
  document.getElementById('modal-irrigate').classList.remove('open');
}
async function startIrrigation() {
  const sensor_id = parseInt(document.getElementById('irr-sensor').value);
  const duration  = parseInt(document.getElementById('irr-duration').value);
  const res = await fetch('/api/irrigate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sensor_id, duration })
  }).then(r => r.json());
  closeModal();
  toast(res.message, 'success');
  loadIrrigations();
}
function quickIrrigate(id) { openIrrigateModal(id); }

// ─── Refresh ─────────────────────────────────────────────────────────────────
function refreshAll() {
  const active = document.querySelector('.nav-item.active');
  if (active) loadPage(active.dataset.page);
  toast('Données actualisées', 'info');
}

// Auto-refresh toutes les 30s
setInterval(() => {
  const active = document.querySelector('.nav-item.active');
  if (active && active.dataset.page === 'dashboard') loadDashboard();
}, 30000);

// ─── Init ─────────────────────────────────────────────────────────────────────
loadDashboard();
