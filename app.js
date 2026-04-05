async function loadSignal() {
  const res = await fetch('./signal.json?_=' + Date.now());
  const data = await res.json();

  // 제목
  document.title = data.title || 'TQQQ 우선 / 대체자산 추천 시그널';
  document.getElementById('page-title').textContent = data.title || 'TQQQ 우선 / 대체자산 추천 시그널';

  // 상단 기본 정보
  document.getElementById('today-date').textContent = `오늘 날짜: ${data.today_date}`;
  document.getElementById('signal-date').textContent = `기준일: ${data.signal_date} (직전일 마감 기준)`;

  // 최종 판단
  document.getElementById('reason').textContent = data.reason || '-';
  document.getElementById('final-trigger').textContent = data.final_trigger || '-';

  const badge = document.getElementById('signal-badge');
  badge.textContent = `오늘 대응: ${data.signal || '-'}`;
  badge.className = 'badge ' + getBadgeClass(data.signal);

  // QQQ 지표
  document.getElementById('last-close').textContent = data.last_close || '-';
  document.getElementById('daily-return').textContent = data.daily_return || '-';
  document.getElementById('ema5').textContent = data.ema5 || '-';
  document.getElementById('ema20').textContent = data.ema20 || '-';
  document.getElementById('ema5-slope').textContent = data.ema5_slope || '-';
  document.getElementById('ema20-slope').textContent = data.ema20_slope || '-';

  // QQQ 전략 체크
  const primaryConditions = data.primary_review?.conditions || {};

  setCheck('cond-ema-cross', primaryConditions.cond_ema_cross);
  setCheck('cond-ema20-up', primaryConditions.cond_ema20_up);
  setCheck('cond-ema5-up', primaryConditions.cond_ema5_up);
  setCheck('cond-emergency-exit', primaryConditions.cond_emergency_exit);
  setCheck('cond-below-2', primaryConditions.cond_below_n);
  setCheck('cond-below-5-3', primaryConditions.cond_below_lookback_required);

  // QQQ 판단 요약
  document.getElementById('primary-trigger').textContent =
    data.primary_review?.final_trigger || '-';

  document.getElementById('primary-recommendation').textContent =
    data.primary_review?.recommendation || '-';

  document.getElementById('primary-market-state').textContent =
    data.primary_review?.market_state || '-';

  document.getElementById('primary-reason').textContent =
    data.primary_review?.reason || '-';

  // 대체자산 검토 결과
  renderAltReview(data.alt_review);

  // 차트
  renderChart(data);
}

function getBadgeClass(signal) {
  if (signal === 'TQQQ') return 'long';
  if (signal === 'CASH') return 'cash';
  return 'alt';
}

function setCheck(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  const isTrue = Boolean(value);
  el.textContent = isTrue ? 'YES' : 'NO';
  el.className = isTrue ? 'check-yes' : 'check-no';
}

function renderAltReview(altReview) {
  const selectedBox = document.getElementById('alt-selected');
  const listBox = document.getElementById('alt-candidates');

  if (!altReview) {
    selectedBox.innerHTML = '<div class="muted">대체자산 검토 정보가 없습니다.</div>';
    listBox.innerHTML = '';
    return;
  }

  if (altReview.selected_asset) {
    selectedBox.innerHTML = `
      <div class="alt-selected-box">
        <div class="alt-selected-title">선택 자산</div>
        <div class="alt-selected-signal">${altReview.selected_asset.leveraged_symbol}</div>
        <div class="alt-selected-desc">
          기준 자산: ${altReview.selected_asset.base_symbol}
        </div>
        <div class="alt-selected-desc">
          근거: ${altReview.selected_asset.reason}
        </div>
        <div class="alt-selected-desc">
          트리거: ${altReview.selected_asset.final_trigger}
        </div>
        <div class="alt-selected-desc">
          점수: ${altReview.selected_asset.score}
        </div>
      </div>
    `;
  } else {
    selectedBox.innerHTML = `
      <div class="alt-selected-box">
        <div class="alt-selected-title">선택 자산</div>
        <div class="alt-selected-signal">CASH</div>
        <div class="alt-selected-desc">
          대체자산(TLT, XLE, GLD) 모두 보유 조건을 충족하지 못했습니다.
        </div>
      </div>
    `;
  }

  const candidates = altReview.candidates || [];
  if (candidates.length === 0) {
    listBox.innerHTML = '<div class="muted">대체자산 검토 대상이 없습니다.</div>';
    return;
  }

  listBox.innerHTML = candidates.map(item => `
    <div class="alt-card">
      <div class="alt-card-header">
        <div>
          <div class="alt-base">${item.base_symbol}</div>
          <div class="alt-leveraged">실행 자산: ${item.leveraged_symbol}</div>
        </div>
        <div class="alt-status ${item.recommendation === '추천' ? 'status-yes' : 'status-no'}">
          ${item.recommendation}
        </div>
      </div>

      <div class="alt-reason">${item.reason}</div>

      <div class="alt-mini-grid">
        <div class="alt-mini-item">
          <div class="label">종가</div>
          <div class="value">${item.display?.last_close || '-'}</div>
        </div>
        <div class="alt-mini-item">
          <div class="label">전일 대비</div>
          <div class="value">${item.display?.daily_return || '-'}</div>
        </div>
        <div class="alt-mini-item">
          <div class="label">EMA5</div>
          <div class="value">${item.display?.ema5 || '-'}</div>
        </div>
        <div class="alt-mini-item">
          <div class="label">EMA20</div>
          <div class="value">${item.display?.ema20 || '-'}</div>
        </div>
        <div class="alt-mini-item">
          <div class="label">EMA5 기울기</div>
          <div class="value">${item.display?.ema5_slope || '-'}</div>
        </div>
        <div class="alt-mini-item">
          <div class="label">EMA20 기울기</div>
          <div class="value">${item.display?.ema20_slope || '-'}</div>
        </div>
      </div>

      <div class="alt-trigger">${item.final_trigger || '-'}</div>
    </div>
  `).join('');
}

let chart;
function renderChart(data) {
  const canvas = document.getElementById('chart');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  if (chart) chart.destroy();

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.labels || [],
      datasets: [
        {
          label: 'QQQ Close',
          data: data.close_data || [],
          borderWidth: 2,
          tension: 0.2
        },
        {
          label: 'EMA5',
          data: data.ema5_data || [],
          borderWidth: 2,
          tension: 0.2
        },
        {
          label: 'EMA20',
          data: data.ema20_data || [],
          borderWidth: 2,
          tension: 0.2
        }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'top' }
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10 } },
        y: { beginAtZero: false }
      }
    }
  });
}

loadSignal().catch(err => {
  const reasonEl = document.getElementById('reason');
  if (reasonEl) {
    reasonEl.textContent = 'signal.json을 불러오지 못했습니다: ' + err;
  }
});
