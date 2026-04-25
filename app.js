(function () {
  'use strict';

  // ---------- 유틸 ----------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const fmt = (n) => new Intl.NumberFormat('ko-KR').format(Math.round(n));

  // 타일에서 사용할 압축 표기 (큰 숫자는 만/억으로 줄여서 폰트를 키워도 안 깨지게)
  const fmtTile = (n) => {
    n = Math.round(n);
    if (n >= 100000000) {
      const eok = n / 100000000;
      return eok.toFixed(2).replace(/\.?0+$/, '') + '억';
    }
    if (n >= 1000000) {
      return Math.floor(n / 10000).toLocaleString('ko-KR') + '만';
    }
    return n.toLocaleString('ko-KR');
  };
  const fmtDate = (d) =>
    `${d.getFullYear()}. ${String(d.getMonth() + 1).padStart(2, '0')}. ${String(
      d.getDate()
    ).padStart(2, '0')}.`;

  const marginKey = (id) => `margin:${id}`;
  const getMargin = (item) => {
    const v = parseFloat(localStorage.getItem(marginKey(item.id)));
    if (Number.isFinite(v) && v >= 0.75 && v <= 0.85) return v;
    return item.defaultMargin ?? 0.80;
  };
  const setMargin = (item, v) => {
    const clamped = Math.min(0.85, Math.max(0.75, v));
    localStorage.setItem(marginKey(item.id), String(clamped));
    return clamped;
  };

  // ---------- 홈 화면 ----------
  function renderHome() {
    $('#today-label').textContent = `오늘 ${fmtDate(TODAY)} 기준`;
    $('#item-count').textContent = ITEMS.length;

    const grid = $('#item-grid');
    grid.innerHTML = '';
    let prevCategory = null;
    ITEMS.forEach((item) => {
      if (item.category && item.category !== prevCategory) {
        grid.appendChild(buildCategoryHeader(item.category));
        prevCategory = item.category;
      }
      grid.appendChild(buildTile(item));
    });
  }

  function buildCategoryHeader(name) {
    const el = document.createElement('div');
    el.className = 'col-span-2 mt-6 mb-2 first:mt-1';
    el.innerHTML = `
      <div class="flex items-center gap-3 px-1">
        <div class="flex-1 h-px bg-gradient-to-r from-transparent via-brand-gold/20 to-brand-gold/40"></div>
        <span class="text-base font-bold tracking-wide text-brand-gold/90 whitespace-nowrap">${name}</span>
        <div class="flex-1 h-px bg-gradient-to-l from-transparent via-brand-gold/20 to-brand-gold/40"></div>
      </div>
    `;
    return el;
  }

  function buildTile(item) {
    const el = document.createElement('button');
    el.className =
      'group relative text-left rounded-2xl p-3.5 ring-1 ring-white/10 bg-ink-800/50 backdrop-blur overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:ring-white/20 active:scale-[0.98]';
    el.style.background = `linear-gradient(155deg, ${hexA(item.colorFrom, 0.18)} 0%, ${hexA(
      item.colorTo,
      0.06
    )} 60%, rgba(17,23,37,0.8) 100%)`;

    const trendColor =
      item.change > 0 ? 'text-emerald-300' : item.change < 0 ? 'text-rose-300' : 'text-slate-400';
    const trendSign = item.change > 0 ? '▲' : item.change < 0 ? '▼' : '—';

    const margin = getMargin(item);
    const myPrice = item.gwangju * margin;

    el.innerHTML = `
      <div class="absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-50 blur-2xl"
           style="background:${hexA(item.colorFrom, 0.6)}"></div>
      <div class="relative flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="text-xl font-bold tracking-tight leading-tight">${item.name}</div>
          <div class="text-xs text-slate-400 mt-1">${item.subtitle}</div>
        </div>
        <span class="shrink-0 text-[11px] ${trendColor} tabular-nums whitespace-nowrap mt-0.5">
          ${trendSign} ${Math.abs(item.change).toFixed(1)}%
        </span>
      </div>
      <div class="relative mt-3 pt-3 border-t border-white/5 space-y-1.5">
        <div class="flex items-baseline gap-2">
          <span class="text-[11px] tracking-wider text-slate-500 w-7 shrink-0">시세</span>
          <span class="text-xl font-bold tabular-nums whitespace-nowrap text-white">${fmtTile(item.gwangju)}</span>
          <span class="text-[10px] text-slate-500">원/kg</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span class="text-[11px] tracking-wider text-brand-gold/80 w-7 shrink-0">적정</span>
          <span class="text-xl font-bold tabular-nums whitespace-nowrap text-brand-gold">${fmtTile(myPrice)}</span>
          <span class="text-[10px] text-brand-gold/60">원/kg</span>
        </div>
      </div>
    `;

    el.addEventListener('click', () => openDetail(item.id));
    return el;
  }

  function hexA(hex, alpha) {
    const n = parseInt(hex.replace('#', ''), 16);
    const r = (n >> 16) & 255;
    const g = (n >> 8) & 255;
    const b = n & 255;
    return `rgba(${r},${g},${b},${alpha})`;
  }

  // ---------- 상세 화면 ----------
  let currentItem = null;
  let currentRange = 30;
  let chart = null;

  function openDetail(id) {
    currentItem = ITEMS.find((i) => i.id === id);
    if (!currentItem) return;

    $('#home-view').classList.add('hidden');
    const detail = $('#detail-view');
    detail.classList.remove('hidden');
    detail.scrollTop = 0;
    // 스크롤 잠금 (바디)
    document.body.style.overflow = 'hidden';

    renderDetail();
  }

  function closeDetail() {
    $('#detail-view').classList.add('hidden');
    $('#home-view').classList.remove('hidden');
    document.body.style.overflow = '';
    if (chart) {
      chart.destroy();
      chart = null;
    }
    currentItem = null;
    renderHome();
  }

  function renderDetail() {
    const it = currentItem;
    $('#detail-date').textContent = fmtDate(TODAY);
    $('#detail-name').textContent = it.name;
    $('#detail-subtitle').textContent = it.subtitle;
    $('#detail-symbol').textContent = it.symbol;
    $('#detail-symbol').style.background = `linear-gradient(135deg, ${it.colorFrom}, ${it.colorTo})`;
    $('#detail-symbol').style.color = '#0b0f1a';

    $('#detail-raw').textContent = fmt(it.raw);
    $('#detail-unit').textContent = it.unit;

    const changeEl = $('#detail-change');
    if (it.change > 0) {
      changeEl.className = 'text-xs px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/20';
      changeEl.textContent = `▲ ${it.change.toFixed(1)}% 전일비`;
    } else if (it.change < 0) {
      changeEl.className = 'text-xs px-2.5 py-1 rounded-full bg-rose-500/15 text-rose-300 ring-1 ring-rose-400/20';
      changeEl.textContent = `▼ ${Math.abs(it.change).toFixed(1)}% 전일비`;
    } else {
      changeEl.className = 'text-xs px-2.5 py-1 rounded-full bg-white/5 text-slate-300 ring-1 ring-white/10';
      changeEl.textContent = `— 보합`;
    }

    $('#detail-hero-bg').style.background = `radial-gradient(120% 120% at 0% 0%, ${hexA(
      it.colorFrom,
      0.35
    )}, transparent 60%), radial-gradient(120% 120% at 100% 100%, ${hexA(it.colorTo, 0.25)}, transparent 60%)`;

    // 매입가 + 적정가
    const margin = getMargin(it);
    $('#gwangju-price').textContent = fmt(it.gwangju);
    $('#my-price').textContent = fmt(it.gwangju * margin);
    $('#my-margin-label').textContent = `×${margin.toFixed(2)}`;
    $('#margin-ratio').textContent = margin.toFixed(2);
    $('#margin-slider').value = Math.round(margin * 100);

    // 최근 7일 일별 단가 (최신 → 과거 순)
    const recent7 = it.history.slice(-7).reverse();
    const recent7Box = $('#recent-7days');
    recent7Box.innerHTML = '';
    recent7.forEach((price, idx) => {
      const d = new Date(TODAY);
      d.setDate(d.getDate() - idx);
      const dateLabel = `${d.getMonth() + 1}.${String(d.getDate()).padStart(2, '0')}`;
      const isToday = idx === 0;

      // 전일 대비 (recent7는 최신 우선이므로 다음 인덱스가 전일)
      const prevPrice = idx < recent7.length - 1 ? recent7[idx + 1] : null;
      let changeText = '—';
      let changeClass = 'text-slate-500';
      if (prevPrice && prevPrice > 0) {
        const ch = ((price - prevPrice) / prevPrice) * 100;
        if (ch > 0) {
          changeText = `▲ ${ch.toFixed(1)}%`;
          changeClass = 'text-emerald-400';
        } else if (ch < 0) {
          changeText = `▼ ${Math.abs(ch).toFixed(1)}%`;
          changeClass = 'text-rose-400';
        } else {
          changeText = '— 보합';
        }
      }

      const row = document.createElement('div');
      row.className = 'flex items-center justify-between px-5 py-3';
      row.innerHTML = `
        <span class="text-sm ${isToday ? 'font-semibold text-brand-gold' : 'text-slate-300'}">
          ${dateLabel}${isToday ? ' (오늘)' : ''}
        </span>
        <div class="flex items-baseline gap-4">
          <span class="text-base tabular-nums ${isToday ? 'font-bold text-white' : 'text-slate-200'}">${fmt(price)}</span>
          <span class="text-xs ${changeClass} tabular-nums w-16 text-right">${changeText}</span>
        </div>
      `;
      recent7Box.appendChild(row);
    });

    // 매입 시점 분석 (30일 평균 vs 현재가, 90일 최저/최고)
    const last30 = it.history.slice(-30);
    const avg30 = last30.reduce((a, b) => a + b, 0) / last30.length;
    const last90 = it.history.slice(-90);
    const min90 = Math.min(...last90);
    const max90 = Math.max(...last90);
    const diffPct = ((it.gwangju - avg30) / avg30) * 100;

    let verdict, verdictClass;
    if (diffPct < -3) {
      verdict = `평균보다 ${Math.abs(diffPct).toFixed(1)}% 낮음 · 매입 적기`;
      verdictClass = 'text-emerald-400';
    } else if (diffPct > 3) {
      verdict = `평균보다 ${diffPct.toFixed(1)}% 높음 · 매입 신중`;
      verdictClass = 'text-rose-400';
    } else {
      verdict = `평균 수준 (${diffPct >= 0 ? '+' : ''}${diffPct.toFixed(1)}%) · 일반 매입`;
      verdictClass = 'text-slate-300';
    }

    const diffColor =
      diffPct > 3 ? 'text-rose-400' : diffPct < -3 ? 'text-emerald-400' : 'text-slate-400';

    $('#trend-analysis').innerHTML = `
      <div class="flex items-center justify-between px-5 py-3.5">
        <span class="text-sm text-slate-300">30일 평균</span>
        <span class="text-base tabular-nums text-slate-200">${fmt(avg30)} 원/kg</span>
      </div>
      <div class="flex items-center justify-between px-5 py-3.5">
        <span class="text-sm text-slate-300">현재가 vs 30일 평균</span>
        <span class="text-base tabular-nums font-semibold ${diffColor}">
          ${diffPct >= 0 ? '+' : ''}${diffPct.toFixed(1)}%
        </span>
      </div>
      <div class="flex items-center justify-between px-5 py-3.5">
        <span class="text-sm text-slate-300">90일 최저 / 최고</span>
        <span class="text-sm tabular-nums text-slate-200">${fmt(min90)} ~ ${fmt(max90)}</span>
      </div>
      <div class="px-5 py-4 bg-white/5">
        <div class="text-[10px] uppercase tracking-widest text-slate-500 mb-1.5">현재 시세 위치</div>
        <div class="text-sm font-semibold ${verdictClass}">${verdict}</div>
      </div>
    `;

    // 탭
    $$('.range-tab').forEach((t) => {
      const on = Number(t.dataset.range) === currentRange;
      t.className = `range-tab flex-1 rounded-full py-2 transition ${
        on
          ? 'bg-white/10 text-slate-100 font-medium'
          : 'text-slate-400 hover:text-slate-200'
      }`;
    });

    renderChart();
  }

  function renderChart() {
    const it = currentItem;
    const ctx = $('#price-chart').getContext('2d');
    const series = it.history.slice(-currentRange);
    const labels = series.map((_, i) => {
      const d = new Date(TODAY);
      d.setDate(d.getDate() - (series.length - 1 - i));
      return `${d.getMonth() + 1}/${d.getDate()}`;
    });

    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, hexA(it.colorFrom, 0.35));
    gradient.addColorStop(1, hexA(it.colorFrom, 0));

    if (chart) chart.destroy();
    chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            data: series,
            borderColor: it.colorFrom,
            backgroundColor: gradient,
            borderWidth: 2,
            fill: true,
            tension: 0.35,
            pointRadius: 0,
            pointHoverRadius: 4,
            pointHoverBackgroundColor: it.colorFrom,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(10,14,26,0.95)',
            borderColor: 'rgba(255,255,255,0.08)',
            borderWidth: 1,
            padding: 10,
            displayColors: false,
            titleColor: '#cbd5e1',
            bodyColor: '#f8fafc',
            callbacks: {
              label: (c) => ` ${fmt(c.parsed.y)} ${it.unit}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: '#64748b',
              font: { size: 10 },
              maxTicksLimit: 6,
            },
            border: { display: false },
          },
          y: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: {
              color: '#64748b',
              font: { size: 10 },
              callback: (v) => fmt(v),
            },
            border: { display: false },
          },
        },
      },
    });
  }

  // ---------- 이벤트 ----------
  function wireEvents() {
    $('#back-btn').addEventListener('click', closeDetail);

    $$('.range-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        currentRange = Number(tab.dataset.range);
        renderDetail();
      });
    });

    $('#margin-btn').addEventListener('click', () => {
      $('#margin-panel').classList.toggle('hidden');
    });

    $('#margin-slider').addEventListener('input', (e) => {
      if (!currentItem) return;
      const v = Number(e.target.value) / 100;
      const clamped = setMargin(currentItem, v);
      $('#my-price').textContent = fmt(currentItem.gwangju * clamped);
      $('#my-margin-label').textContent = `×${clamped.toFixed(2)}`;
      $('#margin-ratio').textContent = clamped.toFixed(2);
    });

    // ESC로 상세 닫기
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !$('#detail-view').classList.contains('hidden')) {
        closeDetail();
      }
    });
  }

  // ---------- 데이터 로딩 ----------
  // 크롤러가 매일 갱신하는 data.json 을 우선 사용, 실패하면 data.js 의 mock 사용.
  let LAST_LOADED_JSON = null;

  async function loadData() {
    try {
      const res = await fetch('data.json', { cache: 'no-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (Array.isArray(json.items) && json.items.length > 0) {
        ITEMS = json.items;
        if (json.today) TODAY = new Date(json.today);
        LAST_LOADED_JSON = json;
        console.log(
          `✅ data.json 로드: ${json.items.length}종 / ${json.today} / 갱신 ${
            json.generated_at || '?'
          }`
        );
        return;
      }
      throw new Error('items 비어있음');
    } catch (e) {
      console.warn(`⚠ data.json 사용 불가, 임시 mock 사용 (${e.message})`);
      LAST_LOADED_JSON = { _loadFailed: true, _error: e.message };
    }
  }

  // ---------- 상태 배너 ----------
  function renderStatusBanner() {
    const banner = $('#status-banner');
    if (!banner) return;
    const json = LAST_LOADED_JSON;

    const errors = [];
    const warnings = [];

    if (!json || json._loadFailed) {
      errors.push('실데이터 파일(data.json) 로드 실패. 임시 가격 표시 중.');
    } else {
      // 크롤러가 보고한 errors/warnings
      const status = json.status || {};
      (status.errors || []).forEach((e) => errors.push(e));
      (status.warnings || []).forEach((w) => warnings.push(w));

      // data.json 자체의 신선도 체크 (30시간 이상 → 의심)
      if (json.generated_at) {
        const generated = new Date(json.generated_at);
        const ageHrs = (Date.now() - generated.getTime()) / 3600000;
        if (ageHrs > 48) {
          errors.push(
            `시세가 ${Math.floor(ageHrs / 24)}일째 갱신 안 됨. 크롤러 또는 GitHub Actions 점검 필요.`
          );
        } else if (ageHrs > 30) {
          warnings.push(
            `시세 갱신 ${Math.floor(ageHrs)}시간 전 (보통 24시간 주기).`
          );
        }
      }
    }

    if (errors.length === 0 && warnings.length === 0) {
      banner.classList.add('hidden');
      return;
    }

    const isError = errors.length > 0;
    const all = isError ? errors : warnings;
    const tone = isError
      ? 'ring-rose-400/30 bg-rose-500/10 text-rose-200'
      : 'ring-amber-400/30 bg-amber-400/10 text-amber-200';
    const icon = isError ? '⚠️' : '📌';
    const title = isError ? '데이터 오류' : '알림';

    banner.className = `mb-6 rounded-2xl ring-1 px-4 py-3 ${tone}`;
    banner.innerHTML = `
      <div class="flex items-start gap-2">
        <span class="text-base leading-none mt-0.5">${icon}</span>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-semibold mb-1">${title}</div>
          <ul class="text-[12px] leading-relaxed space-y-0.5 opacity-90">
            ${all.map((m) => `<li>· ${m}</li>`).join('')}
          </ul>
          ${
            !isError && warnings.length > 0
              ? '<div class="text-[11px] mt-1.5 opacity-70">시세는 표시되지만 정확도 떨어질 수 있음</div>'
              : ''
          }
        </div>
      </div>
    `;
    banner.classList.remove('hidden');
  }

  // ---------- 부팅 ----------
  async function boot() {
    await loadData();
    renderStatusBanner();
    renderHome();
    wireEvents();
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
