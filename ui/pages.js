// Insights + History pages. Loaded before app.js; uses its globals (S, api, h, el, $, modal, fmtLong ...) at call time.

// ---------- small animation helpers ----------
const reduceMotion = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const nextFrame = (fn) => requestAnimationFrame(() => requestAnimationFrame(fn));

// Tween a number inside an element (remembers the last value, so live updates only animate the change).
function countTo(node, to, opts = {}) {
  if (!node) return;
  const fmt = opts.fmt || (v => Math.round(v).toLocaleString());
  const from = node._v ?? 0;
  node._v = to;
  if (reduceMotion() || from === to) { node.textContent = fmt(to); return; }
  const dur = opts.dur || 1100, t0 = performance.now();
  cancelAnimationFrame(node._raf);
  const tick = (now) => {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 4);
    node.textContent = fmt(from + (to - from) * e);
    if (p < 1) node._raf = requestAnimationFrame(tick);
  };
  node._raf = requestAnimationFrame(tick);
}

const DAYNAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const OUTCOME = {
  clean:      { word: 'clean',      label: 'Clean',              cls: 'ok' },
  flagged:    { word: 'flagged',    label: 'Flagged',            cls: 'some' },
  overridden: { word: 'overridden', label: 'Overridden',         cls: 'bad' },
};
const pill = (n, k) => n > 0 ? `<span class="opill ${OUTCOME[k].cls}">${n} ${OUTCOME[k].word}</span>` : '';

// =====================================================================
//  INSIGHTS
// =====================================================================
let INS_TIMER = null;
const FLAME = `<svg class="flame" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c.6 3.2-1.2 4.8-2.7 6.5C7.6 10.4 6 12.2 6 15a6 6 0 0 0 12 0c0-2.2-1-3.8-2.2-5.2-.3 1.2-.9 2-1.8 2.4.5-3.6-.4-7.7-2-10.2z"/></svg>`;

function paintInsights() {
  clearInterval(INS_TIMER);
  const m = $('#main');
  m.innerHTML = `<div class="wrap ins">
    <div class="ins-head"><p class="sub" style="margin:0">How your AI use is going, updated as you work.</p>
      <span class="livepill"><span class="d"></span>Live</span></div>

    <div class="ins-top">
      <div class="icard rise" style="--i:0">
        <div class="ilabel">Clean rate</div>
        <div class="gauge"><svg viewBox="0 0 200 112"><path class="gtrack" d="M14 104 A86 86 0 0 1 186 104"/>
          <path class="gfill" id="gfill" d="M14 104 A86 86 0 0 1 186 104"/></svg>
          <div class="gtxt"><div class="gnum"><span id="gnum">0</span><small>%</small></div><div class="gcap">passed cleanly</div></div></div>
      </div>
      <div class="icard rise" style="--i:1">
        <div class="ibig" id="i-total">0</div><div class="ilabel">Messages checked</div>
        <div class="irows" id="i-rows"></div>
      </div>
      <div class="icard rise" style="--i:2">
        <div class="ibig" id="i-time">0m</div><div class="ilabel">Time locked in</div>
        <div class="irows" id="i-trows"></div>
      </div>
    </div>

    <div class="ins-mid">
      <div class="icard rise" style="--i:3"><div class="ihead"><h2>Where you use AI</h2><span class="icap" id="i-sitecap"></span></div>
        <div class="sitebars" id="i-sites"></div></div>
      <div class="icard rise" style="--i:4"><div class="ihead"><h2><span id="i-streak">0</span> day streak</h2><span class="icap" id="i-longest"></span></div>
        <div class="streakmsg" id="i-streakmsg"></div>
        <div class="heat" id="i-heat"></div>
        <div class="heatkey"><span>Less</span><i class="l0"></i><i class="l1"></i><i class="l2"></i><i class="l3"></i><i class="l4"></i><span>More</span></div></div>
    </div>

    <div class="ins-bot">
      <div class="icard rise" style="--i:5"><div class="ihead"><h2>By class</h2>
        <span class="legend"><i class="ok"></i>clean <i class="some"></i>flagged <i class="bad"></i>overridden</span></div>
        <div class="classbars" id="i-classes"></div></div>
      <div class="icard rise" style="--i:6"><div class="ihead"><h2>This week</h2><span class="icap" id="i-run"></span></div>
        <div class="week" id="i-week"></div></div>
    </div>
  </div>`;

  let prev = {};
  const same = (k, v) => { const s = JSON.stringify(v); const r = prev[k] === s; prev[k] = s; return r; };
  const apply = (d) => {
    const t = d.totals;
    // gauge
    const len = 270.2, pct = d.clean_rate;
    $('#gfill').style.strokeDashoffset = len * (1 - pct / 100);
    countTo($('#gnum'), pct, { dur: 1400 });
    // messages card
    countTo($('#i-total'), t.total);
    $('#i-rows').innerHTML = ['clean', 'flagged', 'overridden'].map(k =>
      `<div class="irow"><span class="idot ${OUTCOME[k].cls}"></span><span>${OUTCOME[k].label}</span><b>${t[k]}</b></div>`).join('');
    // time card
    countTo($('#i-time'), t.seconds, { fmt: v => fmtLong(v), dur: 1300 });
    $('#i-trows').innerHTML = `<div class="irow"><span>Study sessions</span><b>${t.sessions}</b></div>
      <div class="irow"><span>Average session</span><b>${fmtLong(t.avg_session)}</b></div>
      <div class="irow"><span>Longest session</span><b>${fmtLong(t.longest_session)}</b></div>
      <div class="irow"><span>Judge speed</span><b>${t.avg_ms ? (t.avg_ms / 1000).toFixed(1) + 's' : '–'}</b></div>`;
    // sites
    if (!same('sites', d.sites)) {
      const tot = d.sites.reduce((a, s) => a + s.n, 0) || 1;
      $('#i-sitecap').textContent = `TOTAL SITES | ${d.sites.length}`;
      $('#i-sites').innerHTML = d.sites.map((s, i) => { const p = Math.round(100 * s.n / tot);
        return `<div class="sitebar"><span class="sbadge" style="--hue:${(i * 47 + 150) % 360}">${h(s.name[0])}</span>
          <div class="strack"><div class="sfill" data-w="${Math.max(p, 9)}" style="--d:${i * 90}ms"><span>${p}%</span></div></div>
          <span class="scount">${s.n} PROMPT${s.n === 1 ? '' : 'S'} · ${h(s.name)}</span></div>`; }).join('')
        || '<p class="muted">No messages yet. Start a session and they\'ll show up here.</p>';
      nextFrame(() => $('#i-sites').querySelectorAll('.sfill').forEach(f => f.style.width = f.dataset.w + '%'));
    }
    // streak + heatmap
    countTo($('#i-streak'), d.streak.current, { dur: 900 });
    $('#i-longest').textContent = `LONGEST STREAK | ${d.streak.longest} DAY${d.streak.longest === 1 ? '' : 'S'}`;
    $('#i-streakmsg').innerHTML = d.streak.current > 0
      ? `${FLAME}<span>${d.streak.today_done ? 'You\'ve locked in today. Nice.' : 'Study today to keep it going.'}</span>`
      : `<span class="muted">Start a study session to begin a streak.</span>`;
    if (!same('heat', d.heat)) {
      const cols = []; d.heat.forEach(c => { if (c.dow === 0 || !cols.length) cols.push([]); cols[cols.length - 1][c.dow] = c; });
      const lvl = c => !c.n ? 0 : c.s < 600 ? 1 : c.s < 1800 ? 2 : c.s < 3600 ? 3 : 4;
      let lastMonth = -1;
      const months = cols.map(col => { const f = col.find(Boolean); const mo = new Date(f.d + 'T12:00').getMonth();
        const label = mo !== lastMonth ? new Date(f.d + 'T12:00').toLocaleString([], { month: 'short' }) : ''; lastMonth = mo; return `<span>${label}</span>`; }).join('');
      const today = d.heat[d.heat.length - 1].d;
      $('#i-heat').innerHTML = `<div class="hmonths">${months}</div><div class="hgrid">` + cols.map((col, ci) =>
        `<div class="hcol">${[0, 1, 2, 3, 4, 5, 6].map(r => { const c = col[r]; if (!c) return '<i class="hc gone"></i>';
          const when = new Date(c.d + 'T12:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
          const tip = c.n ? `${when} · ${c.n} session${c.n === 1 ? '' : 's'} · ${fmtLong(c.s)} · ${c.c} checked` : `${when} · no sessions`;
          return `<i class="hc l${lvl(c)} ${c.d === today ? 'today' : ''}" data-tip="${h(tip)}" style="--dl:${ci * 22 + r * 7}ms"></i>`; }).join('')}</div>`).join('') + `</div>`;
    }
    // classes
    if (!same('classes', d.classes)) {
      $('#i-classes').innerHTML = d.classes.map((c, i) => { const sum = c.clean + c.flagged + c.overridden, tot = sum || 1;
        const seg = (k, cls) => c[k] ? `<div class="seg ${cls}" data-w="${100 * c[k] / tot}" style="--d:${i * 100}ms" title="${c[k]} ${k}"></div>` : '';
        return `<div class="cbar"><div class="cname"><i class="cdot cc-${c.color}"></i>${h(c.name)}</div>
          <div class="cstack">${seg('clean', 'ok')}${seg('flagged', 'some')}${seg('overridden', 'bad')}</div>
          <b class="ctot">${sum}</b></div>`; }).join('')
        || '<p class="muted">Add a class and start a session to see this.</p>';
      nextFrame(() => $('#i-classes').querySelectorAll('.seg').forEach(s => s.style.width = s.dataset.w + '%'));
    }
    // week
    if (!same('week', d.last7)) {
      const mx = Math.max(1, ...d.last7.map(x => x.total));
      $('#i-week').innerHTML = d.last7.map((x, i) => { const ok = x.total - x.bad;
        return `<div class="wcol" data-tip="${h(x.label)} · ${x.total} checked${x.bad ? ' · ' + x.bad + ' flagged/overridden' : ''}">
          <div class="wbar"><div class="wbad" data-h="${100 * x.bad / mx}" style="--d:${i * 70}ms"></div><div class="wok" data-h="${100 * ok / mx}" style="--d:${i * 70}ms"></div></div>
          <span class="wlab ${i === 6 ? 'now' : ''}">${x.label}</span></div>`; }).join('');
      nextFrame(() => $('#i-week').querySelectorAll('[data-h]').forEach(b => b.style.height = b.dataset.h + '%'));
    }
    $('#i-run').textContent = `CLEAN RUN | ${d.clean_run.current} NOW · BEST ${d.clean_run.best}`;
  };

  const load = async () => { try { apply(await api().insights()); } catch (e) { /* page changed mid-flight */ } };
  load();
  INS_TIMER = setInterval(() => { if (TAB !== 'insights' || !document.getElementById('i-total')) { clearInterval(INS_TIMER); return; } load(); }, 5000);
}

// =====================================================================
//  HISTORY  (days -> big blocks -> the prompts inside)
// =====================================================================
async function paintHistory() {
  const m = $('#main');
  m.innerHTML = `<div class="wrap hist"><p class="muted">Loading…</p></div>`;
  const sessions = await api().sessions(500);
  if (!sessions.length) {
    m.innerHTML = `<div class="wrap hist"><div class="hh-empty rise"><div class="hh-num">0</div><div class="hh-cap">lock-ins yet<br><span>Start one from the Study session tab and it'll appear here.</span></div></div></div>`;
    return;
  }
  const totalSec = sessions.reduce((a, s) => a + (s.seconds || 0), 0);
  const weekAgo = Date.now() / 1000 - 7 * 86400;
  const thisWeek = sessions.filter(s => s.start >= weekAgo).length;
  const groups = []; const idx = {};
  sessions.forEach(s => { const d = new Date(s.start * 1000); const key = d.toDateString();
    if (!(key in idx)) { idx[key] = groups.length; groups.push({ date: d, items: [] }); } groups[idx[key]].items.push(s); });
  const todayStr = new Date().toDateString(), yestStr = new Date(Date.now() - 864e5).toDateString();
  let n = 0;
  const block = (s) => {
    const d = new Date(s.start * 1000);
    const time = d.toLocaleString([], { hour: 'numeric', minute: '2-digit' });
    const pills = pill(s.overridden, 'overridden') + pill(s.flagged, 'flagged');
    return `<button class="hblock cc-${s.color} ${s.live ? 'live' : ''}" data-s="${s.id}" style="--i:${Math.min(n++, 14)}">
      <div class="htop"><span class="htime">${time}</span>${s.live ? '<span class="hlive"><i></i>live</span>' : ''}</div>
      <div class="hdur">${s.live ? 'now' : fmtLong(s.seconds)}</div>
      <div class="hbot"><div class="hclass">${h(s.class)}</div>${s.assignment ? `<div class="hasg">${h(s.assignment)}</div>` : ''}
        <div class="hpills">${pills || (s.checks ? '<span class="opill ok">all clean</span>' : '<span class="opill quiet">no messages</span>')}</div></div></button>`;
  };
  m.innerHTML = `<div class="wrap hist">
    <div class="hh-hero rise"><div class="hh-num" id="hh-num">0</div>
      <div class="hh-cap">lock-ins so far<br><span>${fmtLong(totalSec)} locked in · ${thisWeek} in the last 7 days</span></div></div>
    ${groups.map(g => { const ds = g.date.toDateString();
      const name = ds === todayStr ? 'Today' : ds === yestStr ? 'Yesterday' : DAYNAMES[g.date.getDay()];
      const secs = g.items.reduce((a, s) => a + (s.seconds || 0), 0);
      return `<section class="dgroup"><header class="dhead"><div class="dnum">${g.items.length}</div>
        <div class="dtxt"><b>${name}</b><span>${g.date.toLocaleDateString([], { month: 'long', day: 'numeric' })} · ${g.items.length === 1 ? '1 lock-in' : g.items.length + ' lock-ins'} · ${fmtLong(secs)}</span></div></header>
        <div class="hgrid2">${g.items.map(block).join('')}</div></section>`; }).join('')}
  </div>`;
  countTo($('#hh-num'), sessions.length, { dur: 1200 });
  m.querySelectorAll('.hblock').forEach(b => b.onclick = () => openSession(sessions.find(s => String(s.id) === b.dataset.s)));
}

async function openSession(s) {
  const d = new Date(s.start * 1000);
  const node = el(`<div class="sdetail"><div class="sd-head cc-${s.color}"><div>
      <div class="sd-class">${h(s.class)}${s.assignment ? ` <span>/ ${h(s.assignment)}</span>` : ''}</div>
      <div class="sd-when">${d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })} · ${d.toLocaleString([], { hour: 'numeric', minute: '2-digit' })} · ${s.live ? 'in progress' : fmtLong(s.seconds)}</div></div>
      <div class="sd-pills">${pill(s.clean, 'clean')}${pill(s.flagged, 'flagged')}${pill(s.overridden, 'overridden')}</div></div>
    <div class="sd-list" id="sd-list"><p class="muted">Loading the prompts…</p></div>
    <div class="btnrow" style="justify-content:flex-end;margin-top:14px"><button class="btn" id="sd-close">Done</button></div></div>`);
  node.querySelector('#sd-close').onclick = closeModal;
  modal(node);
  const msgs = await api().session_messages(s.start, s.end || 0);
  $('#sd-list').innerHTML = msgs.length ? msgs.map((e, i) => {
    const o = OUTCOME[e.kind] || OUTCOME.clean;
    const t = new Date(e.t * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    return `<div class="sd-msg" style="--i:${Math.min(i, 12)}"><span class="idot ${o.cls}"></span>
      <div><div class="sd-meta"><b>${o.label}</b> · ${t} · ${h(e.where || '')}</div>
      <div class="sd-text">“${h(e.text || '')}”</div>
      ${e.reasons ? `<div class="sd-why">${e.reasons.map(h).join(' ')}</div>` : ''}</div></div>`; }).join('')
    : '<p class="muted">No messages were checked in this session.</p>';
}
