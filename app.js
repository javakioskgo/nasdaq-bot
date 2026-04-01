async function loadSignal() {
  const res = await fetch('./signal.json?_=' + Date.now());
  const data = await res.json();

  document.getElementById('today-date').textContent = `오늘 날짜: ${data.today_date}`;
  document.getElementById('signal-date').textContent = `기준일: ${data.signal_date} (전일 마감 기준)`;
  document.getElementById('reason').textContent = data.reason;
  document.getElementById('last-close').textContent = data.last_close;
  document.getElementById('daily-return').textContent = data.daily_return;
  document.getElementById('ema5').textContent = data.ema5;
  document.getElementById('ema20').textContent = data.ema20;
  document.getElementById('ema5-slope').textContent = data.ema5_slope;
  document.getElementById('ema20-slope').textContent = data.ema20_slope;
  document.getElementById('final-trigger').textContent = data.final_trigger;

  const badge = document.getElementById('signal-badge');
  badge.textContent = `오늘 대응: ${data.signal}`;
  badge.className = 'badge ' + (data.signal === 'TQQQ' ? 'long' : 'cash');

  setCheck('cond-ema-cross', data.cond_ema_cross);
  setCheck('cond-ema20-up', data.cond_ema20_up);
  setCheck('cond-ema5-up', data.cond_ema5_up);
  setCheck('cond-emergency-exit', data.cond_emergency_exit);
  setCheck('cond-below-2', data.cond_below_2);
  setCheck('cond-below-5-3', data.cond_below_5_3);

  renderChart(data);
}

function setCheck(id, value) {
  const el = document.getElementById(id);
  el.textContent = value ? 'YES' : 'NO';
  el.className = value ? 'check-yes' : 'check-no';
}

let chart;
function renderChart(data) {
  const ctx = document.getElementById('chart').getContext('2d');
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.labels,
      datasets: [
        { label: 'QQQ Close', data: data.close_data, borderWidth: 2, tension: 0.2 },
        { label: 'EMA5', data: data.ema5_data, borderWidth: 2, tension: 0.2 },
        { label: 'EMA20', data: data.ema20_data, borderWidth: 2, tension: 0.2 }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'top' } },
      scales: { x: { ticks: { maxTicksLimit: 10 } }, y: { beginAtZero: false } }
    }
  });
}

loadSignal().catch(err => {
  document.getElementById('reason').textContent = 'signal.json을 불러오지 못했습니다: ' + err;
});
