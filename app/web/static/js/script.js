// ─── State ───────────────────────────────────────────────────────────────────
let liveCh = null, liveRange = 1;
let histHumCh = null, histTmpCh = null;
let donutCh = null;
let dailyHumCh = null, dailyIrrCh = null, zoneHumCh = null, alertTypeCh = null;
let alertFilter = 'active';

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
function toast(msg, type) {
  type = type || 'success';
  const icons = { success: '✅', error: '❌', warn: '⚠️', info: 'ℹ️' };
  const el = document.createElement('div');
  el.className = 'toast' + (type === 'error' ? ' error' : type === 'warn' ? ' warn' : '');
  el.innerHTML = '<span>' + (icons[type] || '✅') + '</span> ' + msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(function() { el.remove(); }, 3500);
}

function fmtTime(ts) {
  if (!ts) return '—';
  var d = new Date(ts.replace(' ', 'T'));
  return d.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function getRecClass(rec) {
  if (!rec) return '';
  if (rec.includes('maintenant')) return 'urgent';
  if (rec.includes('2h') || rec.includes('Surveiller')) return 'warn';
  return '';
}

function mkChart(id, cfg) {
  var ctx = document.getElementById(id);
  if (!ctx) return null;
  return new Chart(ctx, cfg);
}

function destroyAndCreate(existing, id, cfg) {
  if (existing) existing.destroy();
  return mkChart(id, cfg);
}

// ─── API Helper ───────────────────────────────────────────────────────────────
async function fetchJSON(url, opts) {
  try {
    var res = await fetch(url, opts || {});
    return await res.json();
  } catch(e) {
    toast('Erreur réseau', 'error');
    return null;
  }
}

// ─── Dashboard ───────────────────────────────────────────────────────────────
async function loadDashboard() {
  var data = await fetchJSON('/api/dashboard');
  if (!data || !data.sensors) return;
  var sensors = data.sensors;

  // KPIs
  var avgHum = sensors.reduce(function(s, x) { return s + x.humidity; }, 0) / sensors.length;
  var avgTmp = sensors.reduce(function(s, x) { return s + x.temperature; }, 0) / sensors.length;
  document.getElementById('kpi-hum').innerHTML     = avgHum.toFixed(1) + '<small style="font-size:16px">%</small>';
  document.getElementById('kpi-tmp').innerHTML     = avgTmp.toFixed(1) + '<small style="font-size:16px">°C</small>';
  document.getElementById('kpi-alerts').textContent  = data.total_alerts;
  document.getElementById('kpi-irr').textContent     = data.total_irrigations;
  document.getElementById('alert-badge').textContent = data.total_alerts;
  document.getElementById('last-update').textContent = new Date().toLocaleTimeString('fr-FR');

  // Sensor Cards
  var container = document.getElementById('sensor-cards');
  container.innerHTML = sensors.map(function(s) {
    var humPct = Math.min(100, s.humidity);
    var tmpPct = Math.min(100, (s.temperature / 50) * 100);
    var recClass = getRecClass(s.recommendation);
    var alertBadge = s.alerts > 0
      ? '<span class="badge badge-red">⚠️ ' + s.alerts + ' alerte' + (s.alerts > 1 ? 's' : '') + '</span>'
      : '<span class="badge badge-green">✅ OK</span>';
    return '<div class="sensor-card">' +
      '<div class="sensor-header">' +
        '<div>' +
          '<div class="sensor-name">' + s.name + '</div>' +
          '<div class="sensor-zone">' + s.zone + '</div>' +
        '</div>' +
        alertBadge +
      '</div>' +
      '<div class="sensor-body">' +
        '<div class="sensor-metrics">' +
          '<div class="metric">' +
            '<div class="metric-icon">💧</div>' +
            '<div class="metric-val" style="color:var(--green-600)">' + s.humidity.toFixed(1) + '%</div>' +
            '<div class="metric-lbl">Humidité sol</div>' +
          '</div>' +
          '<div class="metric">' +
            '<div class="metric-icon">🌡️</div>' +
            '<div class="metric-val" style="color:var(--amber)">' + s.temperature.toFixed(1) + '°C</div>' +
            '<div class="metric-lbl">Température</div>' +
          '</div>' +
        '</div>' +
        '<div class="gauge-container">' +
          '<div class="gauge-label"><span>Humidité</span><span>' + humPct.toFixed(1) + '%</span></div>' +
          '<div class="gauge-bar"><div class="gauge-fill humidity" style="width:' + humPct + '%"></div></div>' +
        '</div>' +
        '<div class="gauge-container">' +
          '<div class="gauge-label"><span>Température</span><span>' + s.temperature.toFixed(1) + '°C</span></div>' +
          '<div class="gauge-bar"><div class="gauge-fill temp" style="width:' + tmpPct + '%"></div></div>' +
        '</div>' +
        '<div class="rec-box ' + recClass + '" style="margin-top:12px">' +
          '<div>' +
            '<div class="rec-text">🤖 ' + s.recommendation + '</div>' +
            '<div class="rec-conf">Confiance : ' + s.confidence + '%</div>' +
          '</div>' +
          '<button class="btn btn-primary btn-sm" onclick="quickIrrigate(' + s.id + ')">💧</button>' +
        '</div>' +
        '<div style="margin-top:8px;font-size:11px;color:var(--text-muted)">Dernière mesure : ' + fmtTime(s.timestamp) + '</div>' +
      '</div>' +
    '</div>';
  }).join('');

  await loadLiveChart(1, liveRange);
  await loadAlertDonut();
}

async function loadLiveChart(sensorId, hours) {
  var rows = await fetchJSON('/api/history/' + sensorId + '?hours=' + hours);
  if (!rows || !rows.length) return;

  var labels = rows.map(function(r) {
    return new Date(r.timestamp.replace(' ', 'T')).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  });
  var hums = rows.map(function(r) { return r.humidity; });
  var tmps = rows.map(function(r) { return r.temperature; });

  liveCh = destroyAndCreate(liveCh, 'chart-live', {
    type: 'line',
    data: {
      labels: labels,
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
          tension: 0.4, fill: false, pointRadius: 0, borderDash: [5, 3], yAxisID: 'y1'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
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
  var stats = await fetchJSON('/api/stats');
  if (!stats) return;
  var dist = stats.alert_distribution || [];
  if (!dist.length) return;

  var colors = ['#22a022', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6'];
  var labels = dist.map(function(d) {
    return (d.type === 'low_humidity' ? '💧 Humidité basse' : '🌡️ Temp élevée');
  });
  var values = dist.map(function(d) { return d.count; });

  donutCh = destroyAndCreate(donutCh, 'chart-alerts-donut', {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{ data: values, backgroundColor: colors.slice(0, values.length), borderWidth: 0 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '65%',
      plugins: { legend: { display: false } }
    }
  });

  document.getElementById('donut-legend').innerHTML = labels.map(function(l, i) {
    return '<div class="legend-item"><div class="legend-dot" style="background:' + colors[i] + '"></div>' + l + ' — <b>' + values[i] + '</b></div>';
  }).join('');
}

function setTimeRange(btn, hours) {
  document.querySelectorAll('.time-tab').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  liveRange = hours;
  loadLiveChart(1, hours);
}

// ─── History ─────────────────────────────────────────────────────────────────
async function loadHistory() {
  var sid  = document.getElementById('hist-sensor').value;
  var hrs  = document.getElementById('hist-period').value;
  var rows = await fetchJSON('/api/history/' + sid + '?hours=' + hrs);
  if (!rows || !rows.length) return;

  var labels = rows.map(function(r) {
    return new Date(r.timestamp.replace(' ', 'T')).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  });
  var hums = rows.map(function(r) { return r.humidity; });
  var tmps = rows.map(function(r) { return r.temperature; });
  var sub  = rows.length + ' relevés sur ' + hrs + 'h';
  document.getElementById('hist-hum-sub').textContent = sub;
  document.getElementById('hist-tmp-sub').textContent = sub;

  histHumCh = destroyAndCreate(histHumCh, 'chart-hist-hum', {
    type: 'line',
    data: {
      labels: labels,
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
      labels: labels,
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
  var stats = await fetchJSON('/api/stats');
  if (!stats) return;

  var dh = stats.daily_humidity     || [];
  var di = stats.daily_irrigation   || [];
  var zh = stats.zone_humidity      || [];
  var ad = stats.alert_distribution || [];

  if (dh.length) {
    dailyHumCh = destroyAndCreate(dailyHumCh, 'chart-daily-hum', {
      type: 'bar',
      data: {
        labels: dh.map(function(r) { return r.day.slice(5); }),
        datasets: [
          { label: 'Moy. Humidité (%)', data: dh.map(function(r) { return r.avg_hum; }), backgroundColor: 'rgba(34,160,34,.7)', borderRadius: 6 },
          { label: 'Min Humidité (%)',  data: dh.map(function(r) { return r.min_hum; }), backgroundColor: 'rgba(239,68,68,.5)', borderRadius: 6 }
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
  }

  if (di.length) {
    dailyIrrCh = destroyAndCreate(dailyIrrCh, 'chart-daily-irr', {
      type: 'bar',
      data: {
        labels: di.map(function(r) { return r.day.slice(5); }),
        datasets: [{ label: 'Nb irrigations', data: di.map(function(r) { return r.count; }), backgroundColor: 'rgba(59,130,246,.7)', borderRadius: 6 }]
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
  }

  if (zh.length) {
    zoneHumCh = destroyAndCreate(zoneHumCh, 'chart-zone-hum', {
      type: 'bar',
      data: {
        labels: zh.map(function(r) { return r.zone; }),
        datasets: [{
          label: 'Humidité (%)',
          data: zh.map(function(r) { return r.avg_hum; }),
          backgroundColor: ['#22a022', '#00c9a7', '#f59e0b', '#3b82f6'],
          borderRadius: 8
        }]
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
  }

 if (ad.length) {
    var adLabels = ad.map(function(d) {
      var typeLabel = d.type === 'low_humidity' ? '💧 Humidité basse' : '🌡️ Temp élevée';
      var sevLabel  = d.severity === 'critical' ? '🔴 critique' : '🟡 warning';
      return typeLabel + ' — ' + sevLabel;
    });

    alertTypeCh = destroyAndCreate(alertTypeCh, 'chart-alert-type', {
      type: 'pie',
      data: {
        labels: adLabels,
        datasets: [{
          data: ad.map(function(d) { return d.count; }),
          backgroundColor: ['#ef4444', '#f59e0b', '#C62828', '#FF8F00'],
          borderWidth: 2,
          borderColor: '#ffffff'
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: true, position: 'bottom', labels: { font: { size: 11 }, boxWidth: 12 } } }
      }
    });
  }
}

// ─── Alerts ──────────────────────────────────────────────────────────────────
async function loadAlerts() {
  var resolved = alertFilter === 'resolved' ? 1 : 0;
  var alerts = await fetchJSON('/api/alerts?resolved=' + resolved);
  if (!alerts) return;
  var list = document.getElementById('alert-list');

  if (!alerts.length) {
    list.innerHTML = '<div class="empty-state"><div class="emoji">' + (resolved ? '✅' : '🎉') + '</div><p>' + (resolved ? 'Aucune alerte résolue.' : 'Aucune alerte active !') + '</p></div>';
    return;
  }

  var icons = { low_humidity: '💧', high_temp: '🌡️', sensor_error: '⚡' };
  list.innerHTML = alerts.map(function(a) {
    return '<div class="alert-item ' + a.severity + '">' +
      '<div class="alert-icon">' + (icons[a.type] || '⚠️') + '</div>' +
      '<div class="alert-info">' +
        '<div class="alert-msg">' + a.message + '</div>' +
        '<div class="alert-meta">📍 ' + a.sensor_name + ' — ' + a.zone + ' &nbsp;|&nbsp; 🕐 ' + fmtTime(a.timestamp) + '</div>' +
      '</div>' +
      (!a.resolved ? '<div class="alert-actions"><button class="btn btn-outline btn-sm" onclick="resolveAlert(' + a.id + ')">✅ Résoudre</button></div>' : '') +
    '</div>';
  }).join('');
}

function filterAlerts(btn, type) {
  document.querySelectorAll('.filter-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  alertFilter = type;
  loadAlerts();
}

async function resolveAlert(id) {
  var res = await fetchJSON('/api/alerts/resolve/' + id, { method: 'POST' });
if (res && res.ok) {
    toast('Alerte résolue ✅', 'success');
    loadAlerts();
    loadDashboard();
  }
}

// ─── Irrigations ─────────────────────────────────────────────────────────────
async function loadIrrigations() {
  var rows = await fetchJSON('/api/irrigations');
  if (!rows) return;
  var tbody = document.getElementById('irr-tbody');

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="emoji">💧</div><p>Aucune irrigation enregistrée.</p></div></td></tr>';
    return;
  }

  var triggerLabel = { manual: '🖱️ Manuel', ai: '🤖 IA', auto: '⚙️ Auto' };
  tbody.innerHTML = rows.map(function(r) {
    return '<tr>' +
      '<td><b>' + r.sensor_name + '</b><br><span style="font-size:11px;color:var(--text-muted)">' + r.zone + '</span></td>' +
      '<td>' + fmtTime(r.started_at) + '</td>' +
      '<td>' + fmtTime(r.ended_at) + '</td>' +
      '<td><b>' + r.duration_min + '</b> min</td>' +
      '<td>' + (triggerLabel[r.trigger_type] || r.trigger_type) + '</td>' +
      '<td><span class="badge badge-' + (r.ended_at ? 'green' : 'blue') + '">' + (r.ended_at ? '✅ Terminée' : '🔄 En cours') + '</span></td>' +
    '</tr>';
  }).join('');
}

// ─── Modal ────────────────────────────────────────────────────────────────────
function openIrrigateModal(sensorId) {
  if (sensorId !== undefined) {
    var sel = document.getElementById('irr-sensor');
    if (sel) sel.value = sensorId;
  }
  document.getElementById('modal-irrigate').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-irrigate').classList.remove('open');
}

async function startIrrigation() {
  var sensor_id = parseInt(document.getElementById('irr-sensor').value);
  var duration  = parseInt(document.getElementById('irr-duration').value);
  var res = await fetchJSON('/api/irrigate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sensor_id: sensor_id, duration: duration })
  });
  closeModal();
  if (res) {
    toast(res.message || 'Irrigation démarrée 💧', 'success');
    loadIrrigations();
  }
}

function quickIrrigate(id) {
  openIrrigateModal(id);
}

// ─── Refresh ─────────────────────────────────────────────────────────────────
function refreshAll() {
  var active = document.querySelector('.nav-item.active');
  if (active) loadPage(active.dataset.page);
  toast('Données actualisées', 'info');
}

// Auto-refresh toutes les 30s sur le dashboard
setInterval(function() {
  var active = document.querySelector('.nav-item.active');
  if (active && active.dataset.page === 'dashboard') loadDashboard();
}, 30000);

// ─── Init ─────────────────────────────────────────────────────────────────────
loadDashboard();