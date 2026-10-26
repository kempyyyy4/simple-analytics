(function () {
  'use strict';

  // ---------- state ----------
  let view = null;              // last payload from Python (see metrics.build_view)
  let filter = 'all';           // all | long | short
  let sortKey = 'publishedAt';
  let sortDir = -1;             // -1 = descending
  let currentId = null;         // video open on the Video page
  let tab = 'overview';         // overview | targets | video
  let draft = null;             // editable copy of the targets while on the Targets tab

  const COLS = [
    { key: 'title', label: 'Title' },
    { key: 'type', label: 'Type' },
    { key: 'publishedAt', label: 'Published' },
    { key: 'views', label: 'Views', num: true },
    { key: 'impressions', label: 'Impressions', num: true },
    { key: 'ctr', label: 'CTR', num: true },
    { key: 'avdSec', label: 'Avg view duration', num: true },
    { key: 'avp', label: 'Avg % viewed', num: true },
    { key: 'subs', label: 'Subs gained', num: true },
  ];
  const SORT_GET = {
    title: v => v.title.toLowerCase(), type: v => v.type, publishedAt: v => v.publishedAt,
    views: v => v.views, impressions: v => v.impressions, ctr: v => v.ctr,
    avdSec: v => v.avdSec, avp: v => v.avp, subs: v => v.subs,
  };
  const STATUS_CLASS = { red: 's-red', amber: 's-amber', green: 's-green', early: 's-early' };
  const WORD = { red: 'Red', amber: 'Amber', green: 'Green' };

  // ---------- helpers ----------
  const $ = sel => document.querySelector(sel);
  const api = () => window.pywebview.api;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtInt = n => (n == null ? '—' : Math.round(n).toLocaleString('en-GB'));
  const fmtPct = n => (n == null ? '—' : n.toFixed(1) + '%');
  const fmtDec = n => (n == null ? '—' : n.toFixed(1));
  const fmtDur = s => (s == null ? '—' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`);
  const fmtDate = iso => (iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');
  const fmtWhen = iso => (iso ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'never');

  // Text shown in a metric cell: the value, or why it can't be judged yet.
  function statusLabel(m, fmt) {
    if (!m) return '—';
    if (m.status === 'early') {
      const note = m.note || '';
      if (note.startsWith('Too early')) return 'too early';
      if (note.startsWith('Impressions')) return 'lag ~2 days';
      return 'not enough data';
    }
    return m.value == null ? '—' : fmt(m.value);
  }
  const cellClass = m => (m && STATUS_CLASS[m.status]) || '';

  function delta(cur, prev) {
    if (!prev) return cur ? '<span class="up">new</span>' : '—';
    const pct = (cur - prev) / prev * 100;
    const cls = pct >= 0 ? 'up' : 'down';
    return `<span class="${cls}">${pct >= 0 ? '+' : ''}${pct.toFixed(0)}%</span>`;
  }

  function showBanner(messages, isError) {
    const box = $('#banner');
    if (!messages.length) { box.classList.add('hidden'); return; }
    box.innerHTML = messages.map(esc).join('<br>');
    box.style.background = isError ? 'var(--red-bg)' : '';
    box.style.borderColor = isError ? 'var(--red)' : '';
    box.classList.remove('hidden');
  }

  // ---------- overview ----------
  function renderOverview() {
    const t = view.totals;
    $('#cards').innerHTML = view.empty ? '' : [
      `<div class="card"><div class="label">Subscribers</div><div class="big">${fmtInt(t.subscribers)}</div>
         <div class="sub">${fmtInt(t.channelViews)} views all time</div></div>`,
      `<div class="card"><div class="label">Views, last 28 days</div><div class="big">${fmtInt(t.views28)}</div>
         <div class="sub">${delta(t.views28, t.views28prev)} vs previous 28 (${fmtInt(t.views28prev)})</div></div>`,
      `<div class="card"><div class="label">Watch hours, last 28 days</div><div class="big">${fmtInt(t.watchHours28)}</div>
         <div class="sub">${delta(t.watchHours28, t.watchHours28prev)} vs previous 28 (${fmtInt(t.watchHours28prev)})</div></div>`,
      `<div class="card"><div class="label">Subs gained, last 28 days</div><div class="big">${fmtInt(t.subsGained28)}</div>
         <div class="sub">${delta(t.subsGained28, t.subsGained28prev)} vs previous 28 (${fmtInt(t.subsGained28prev)})</div></div>`,
    ].join('');

    document.querySelectorAll('#filters .chip-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === filter));

    $('#thead').innerHTML = '<tr>' + COLS.map(c => {
      const cls = [c.num ? 'num' : '', sortKey === c.key ? 'sorted' : '', sortKey === c.key && sortDir > 0 ? 'asc' : ''].join(' ');
      return `<th data-key="${c.key}" class="${cls}">${c.label}</th>`;
    }).join('') + '</tr>';

    const rows = view.videos
      .filter(v => filter === 'all' || v.type === filter)
      .sort((a, b) => {
        const x = SORT_GET[sortKey](a), y = SORT_GET[sortKey](b);
        if (x == null && y == null) return 0;
        if (x == null) return 1;   // blanks always sit at the bottom
        if (y == null) return -1;
        return (x > y ? 1 : x < y ? -1 : 0) * sortDir;
      });

    $('#tbody').innerHTML = rows.length ? rows.map(rowHtml).join('') :
      `<tr><td colspan="${COLS.length}" class="muted" style="white-space:normal">${view.empty ? esc(view.error) : 'No videos in this filter.'}</td></tr>`;
    $('#count').textContent = `${rows.length} video${rows.length === 1 ? '' : 's'}`;

    const foot = [...(view.notes || [])];
    if (view.reachLatest) foot.push(`Impressions and CTR are complete up to ${view.reachLatest}; they lag about 2 days.`);
    foot.push('Analytics runs 2–3 days behind, so the newest days can be incomplete.');
    $('#notes').innerHTML = foot.map(n => `<div>${esc(n)}</div>`).join('');
  }

  function rowHtml(v) {
    const m = v.metrics;
    const impr = v.impressions == null
      ? `<td class="num s-early" title="Impressions and CTR lag about 2 days">${v.hoursOld < 48 ? 'too early' : 'lag ~2 days'}</td>`
      : `<td class="num">${fmtInt(v.impressions)}</td>`;
    const avd = v.hoursOld < 48 ? '<td class="num s-early">too early</td>' : `<td class="num">${fmtDur(v.avdSec)}</td>`;
    const subsNote = m.subsPer1k.note || (v.subsPer1k != null ? `${fmtDec(v.subsPer1k)} subs per 1,000 views` : '');
    const subsText = m.subsPer1k.status === 'early' ? statusLabel(m.subsPer1k) : fmtInt(v.subs);
    return `<tr data-id="${esc(v.videoId)}">
      <td class="title">${esc(v.title)}</td>
      <td><span class="badge ${v.type}">${v.type === 'short' ? 'Short' : 'Long-form'}</span></td>
      <td>${fmtDate(v.publishedAt)}</td>
      <td class="num">${fmtInt(v.views)}</td>
      ${impr}
      <td class="num ${cellClass(m.ctr)}" title="${esc(m.ctr.note)}">${statusLabel(m.ctr, fmtPct)}</td>
      ${avd}
      <td class="num ${cellClass(m.avp)}" title="${esc(m.avp.note)}">${statusLabel(m.avp, fmtPct)}</td>
      <td class="num ${cellClass(m.subsPer1k)}" title="${esc(subsNote)}">${subsText}</td>
    </tr>`;
  }

  // ---------- video page ----------
  function tile(label, m, text, extra) {
    const note = (m && m.note) || extra || '';
    return `<div class="tile ${cellClass(m)}"><div class="label">${esc(label)}</div>
      <div class="val">${text}</div><div class="note">${esc(note)}</div></div>`;
  }

  function retentionSvg(v) {
    const pts = v.retention, dur = v.durationSec;
    if (!pts.length || !dur) return '<p class="muted">No retention data yet.</p>';
    const W = 720, H = 250, P = { l: 44, r: 12, t: 14, b: 28 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const maxY = Math.max(100, ...pts.map(p => p[1]));
    const x = s => P.l + (s / dur) * iw;
    const y = p => P.t + ih - (p / maxY) * ih;
    const line = pts.map(([s, p]) => `${x(s).toFixed(1)},${y(p).toFixed(1)}`).join(' ');
    const grid = [0, 50, 100].filter(g => g <= maxY).map(g =>
      `<line class="grid" x1="${P.l}" x2="${W - P.r}" y1="${y(g)}" y2="${y(g)}"/>
       <text class="axis" x="${P.l - 8}" y="${y(g) + 4}" text-anchor="end">${g}%</text>`).join('');
    const marks = v.drops.map(d =>
      `<line class="drop" x1="${x(d.sec)}" x2="${x(d.sec)}" y1="${P.t}" y2="${P.t + ih}"/>
       <text class="droplabel" x="${x(d.sec) + 5}" y="${P.t + 14}">${d.time} · −${d.lost}%</text>`).join('');
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Audience retention curve">
      ${grid}
      <polyline class="curve" points="${line}"/>
      ${marks}
      <text class="axis" x="${P.l}" y="${H - 6}">0:00</text>
      <text class="axis" x="${W - P.r}" y="${H - 6}" text-anchor="end">${fmtDur(dur)}</text>
    </svg>`;
  }

  function renderVideo() {
    const v = view.videos.find(x => x.videoId === currentId);
    if (!v) { $('#videoView').innerHTML = '<p class="muted">That video is no longer in the latest pull.</p>'; return; }
    const m = v.metrics;
    const vClass = {
      working: 'v-good', short_working: 'v-good', too_early: 'v-neutral', not_enough: 'v-neutral',
      no_return: 'v-warn', mixed: 'v-warn',
    }[v.verdict.id] || 'v-bad';

    const tiles = [
      tile('Views', null, fmtInt(v.views)),
      tile('Impressions', null, fmtInt(v.impressions), v.impressions == null ? 'Lags about 2 days' : ''),
      tile('CTR', m.ctr, statusLabel(m.ctr, fmtPct)),
      tile('Avg view duration', null, fmtDur(v.avdSec)),
      tile('Avg % viewed', m.avp, statusLabel(m.avp, fmtPct)),
      v.type === 'long'
        ? tile('First-30-seconds retention', m.first30, statusLabel(m.first30, fmtPct))
        : tile('Engaged-view rate', m.engaged, statusLabel(m.engaged, fmtPct)),
      tile('Subs gained', m.subsPer1k, fmtInt(v.subs), v.subsPer1k != null ? `${fmtDec(v.subsPer1k)} per 1,000 views` : ''),
    ].join('');

    const traffic = v.traffic.length ? v.traffic.map(t =>
      `<div class="row"><span>${esc(t.name)}</span>
         <div class="track"><div class="fill" style="width:${t.share}%"></div></div>
         <span class="num">${t.share}%</span></div>`).join('') : '<p class="muted">No traffic data yet.</p>';

    const f = v.first7;
    let firstWeek;
    if (!f.complete) {
      firstWeek = `First-week figures aren't final yet (${fmtInt(f.views)} views so far; Analytics lags 2–3 days).`;
    } else {
      const ratio = f.median ? ` = ${(f.views / f.median).toFixed(1)}× the channel median` : '';
      firstWeek = `${fmtInt(f.views)} views in the first 7 days. Channel median: ${fmtInt(f.median)}${ratio}.`;
    }

    const diag = v.diagnosis.length ? v.diagnosis.map(d => `
      <div class="diag ${cellClass({ status: d.status })}">
        <div class="dhead">${d.status && WORD[d.status] ? WORD[d.status] + ' · ' : ''}${esc(d.title)}</div>
        <p><b>Why this usually happens:</b> ${esc(d.why)}</p>
        <p><b>What to try next time:</b> ${esc(d.try)}</p>
      </div>`).join('') : `<p class="muted">${v.verdict.id === 'too_early' ? 'Too early to judge yet.' : 'Nothing flagged on this video.'}</p>`;

    const biggest = v.drops.length
      ? 'Biggest drops: ' + v.drops.map(d => `${d.time} (−${d.lost} pts)`).join(', ')
      : '';

    $('#videoView').innerHTML = `
      <div class="video-head">
        <h1>${esc(v.title)}</h1>
        <div class="meta"><span class="badge ${v.type}">${v.type === 'short' ? 'Short' : 'Long-form'}</span>
          &nbsp;Published ${fmtDate(v.publishedAt)} · ${fmtDur(v.durationSec)} long · ${esc(v.videoId)}</div>
      </div>
      <div class="verdict ${vClass}">${esc(v.verdict.text)}</div>
      <div class="tiles">${tiles}</div>
      <div class="panel"><h2>Audience retention</h2>${retentionSvg(v)}<div class="muted">${esc(biggest)}</div></div>
      <div class="panel"><h2>Traffic sources</h2><div class="bars">${traffic}</div></div>
      <div class="panel"><h2>First 7 days</h2><p>${esc(firstWeek)}</p></div>
      <div class="panel"><h2>Diagnosis</h2>${diag}</div>`;
  }

  // ---------- targets ----------
  function gaugeHtml(item, band) {
    const max = Math.max(item.green_above * 1.4, item.avg || 0, 1);
    const r = item.red_below / max * 100;
    const g = item.green_above / max * 100;
    const marker = item.avg == null ? '' :
      `<div class="marker" style="left:${Math.min(item.avg / max, 1) * 100}%"></div>`;
    return `<div class="gauge">
      <div class="seg red" style="width:${r}%"></div>
      <div class="seg amber" style="width:${g - r}%"></div>
      <div class="seg green" style="width:${100 - g}%"></div>${marker}</div>`;
  }

  function renderTargets() {
    if (!view || view.empty) { $('#targetsView').innerHTML = '<p class="muted">Pull data first, then set targets.</p>'; return; }
    if (!draft) draft = JSON.parse(JSON.stringify(view.targets));
    const blocks = ['long', 'short'].map(kind => {
      const items = view.averages[kind] || [];
      const title = kind === 'long' ? 'Long-form videos' : 'Shorts';
      const rows = items.map(item => {
        const band = draft[kind][item.key];
        const avgText = item.avg == null ? 'no data yet' : `${item.avg.toFixed(1)}${item.unit}`;
        const avgCls = STATUS_CLASS[item.status] || '';
        const unit = item.unit;
        return `<div class="metric">
          <div class="mhead"><b>${esc(item.label)}</b><span class="avg ${avgCls}">${avgText}</span></div>
          ${gaugeHtml(item, band)}
          <p class="summary">${esc(item.summary)}</p>
          <div class="edit">
            <label>Red below <input type="number" step="0.1" data-kind="${kind}" data-key="${item.key}" data-field="red_below" value="${band.red_below}">${esc(unit)}</label>
            <label>Green above <input type="number" step="0.1" data-kind="${kind}" data-key="${item.key}" data-field="green_above" value="${band.green_above}">${esc(unit)}</label>
            <span>Amber is in between.</span>
          </div>
        </div>`;
      }).join('');
      return `<div class="target-block"><h2>${title}</h2>${rows || '<p class="muted">No targets set.</p>'}</div>`;
    }).join('');

    $('#targetsView').innerHTML = blocks + `
      <div class="savebar">
        <button id="save-targets" class="btn primary">Save targets</button>
        <span id="save-msg" class="muted"></span>
      </div>
      <p class="footnote">Wording for the Diagnosis panel lives in <b>%APPDATA%\\Rupert Analytics\\diagnosis.json</b>. Open it in Notepad to edit.</p>`;
  }

  // ---------- screens ----------
  function showScreen(name) {
    tab = name;
    $('#screen-overview').classList.toggle('hidden', name !== 'overview');
    $('#screen-video').classList.toggle('hidden', name !== 'video');
    $('#screen-targets').classList.toggle('hidden', name !== 'targets');
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name || (name === 'video' && b.dataset.tab === 'overview')));
    if (name === 'targets') renderTargets();
    window.scrollTo(0, 0);
  }

  function openVideo(id) {
    currentId = id;
    renderVideo();
    showScreen('video');
  }

  function setView(v) {
    view = v;
    draft = null;
    const messages = [];
    if (v.error) messages.push(v.error);
    (v.warnings || []).forEach(w => messages.push(w));
    showBanner(messages, !!v.error);
    $('#pulled').textContent = v.empty ? '' : `· last pulled ${fmtWhen(v.pulledAt)}`;
    renderOverview();
    if (tab === 'video') renderVideo();
    if (tab === 'targets') renderTargets();
  }

  async function doRefresh() {
    const btn = $('#refresh');
    btn.disabled = true;
    btn.textContent = 'Refreshing… (about 30 s)';
    try {
      setView(await api().refresh());
    } catch (e) {
      showBanner([`Refresh failed: ${e}`], true);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Refresh';
    }
  }

  async function saveTargets() {
    const msg = $('#save-msg');
    for (const input of document.querySelectorAll('#targetsView input')) {
      const v = parseFloat(input.value);
      if (Number.isNaN(v)) { msg.textContent = 'Every target needs a number.'; msg.className = 'error-text'; return; }
      draft[input.dataset.kind][input.dataset.key][input.dataset.field] = v;
    }
    for (const kind of ['long', 'short']) {
      for (const [key, band] of Object.entries(draft[kind])) {
        if (band.red_below > band.green_above) {
          msg.textContent = `${band.label}: red below must be lower than green above.`;
          msg.className = 'error-text';
          return;
        }
      }
    }
    msg.className = 'muted';
    msg.textContent = 'Saving…';
    setView(await api().save_targets(draft));
    msg.textContent = 'Saved.';
  }

  // ---------- wiring ----------
  function wire() {
    document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => showScreen(b.dataset.tab)));
    $('#refresh').addEventListener('click', doRefresh);
    $('#filters').addEventListener('click', e => {
      const b = e.target.closest('[data-filter]');
      if (!b) return;
      filter = b.dataset.filter;
      renderOverview();
    });
    $('#thead').addEventListener('click', e => {
      const th = e.target.closest('th[data-key]');
      if (!th) return;
      const key = th.dataset.key;
      sortDir = sortKey === key ? -sortDir : (key === 'title' || key === 'type' ? 1 : -1);
      sortKey = key;
      renderOverview();
    });
    $('#tbody').addEventListener('click', e => {
      const tr = e.target.closest('tr[data-id]');
      if (tr) openVideo(tr.dataset.id);
    });
    $('#back').addEventListener('click', e => { e.preventDefault(); showScreen('overview'); });
    $('#targetsView').addEventListener('click', e => { if (e.target.id === 'save-targets') saveTargets(); });
  }

  function start() {
    api().dashboard().then(setView);
  }

  wire();
  if (window.pywebview && window.pywebview.api) start();
  else window.addEventListener('pywebviewready', start);
})();
