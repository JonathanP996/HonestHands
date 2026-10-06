// ---- talk to the Python side ----
const api = () => window.pywebview.api;
const h = (s) => (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $ = (sel, el = document) => el.querySelector(sel);
const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };
let S = null, TAB = 'home';
function fmtDur(sec){ sec=Math.max(0,sec|0); const h=Math.floor(sec/3600), m=Math.floor(sec%3600/60), s=sec%60;
  return (h>0? h+':'+String(m).padStart(2,'0') : m) + ':' + String(s).padStart(2,'0'); }
function fmtLong(sec){ sec=Math.max(0,sec|0); const h=Math.floor(sec/3600), m=Math.round(sec%3600/60);
  return h>0 ? (h+'h '+m+'m') : (m+'m'); }
let TIMER = null, TIMER_BASE = 0, TIMER_T0 = 0;
function startTimerTick(startedEpoch, endsEpoch){
  stopTimerTick();
  let done = false;
  TIMER = setInterval(()=>{ const el=document.getElementById('sessTimer');
    if(!el){ return; }
    const now = Date.now()/1000;
    if (endsEpoch) {                                   // a timed lock-in: count down
      const left = Math.max(0, Math.ceil(endsEpoch - now));
      el.textContent = fmtDur(left);
      const f = document.getElementById('sb-prog-fill');
      if (f) f.style.width = Math.min(100, 100 * (now - startedEpoch) / Math.max(1, endsEpoch - startedEpoch)) + '%';
      if (left <= 0 && !done) { done = true; setTimeout(refresh, 2500); }       // the app ends it by itself; pick that up
    } else {
      el.textContent = fmtDur(Math.floor(now - startedEpoch));
    }
  }, 1000);
}
function stopTimerTick(){ if(TIMER){ clearInterval(TIMER); TIMER=null; } }

function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(() => t.hidden = true, 3200);
}
window.showToast = toast;
function modal(node) { $('#sheetBody').innerHTML = ''; $('#sheetBody').append(node); $('#modal').hidden = false; }
function closeModal() { $('#modal').hidden = true; }
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });

async function askPin(reason) {
  if (!S || !S.has_pin) return '';
  return new Promise(resolve => {
    const node = el(`<div><h2>Accountability PIN</h2><p class="sub">${h(reason)}</p>
      <div class="field"><input type="password" inputmode="numeric" id="pinIn" autofocus></div>
      <p class="small" style="color:var(--stop)" id="pinErr"></p>
      <div class="btnrow" style="justify-content:flex-end"><button class="btn ghost" id="pc">Cancel</button><button class="btn" id="pk">Unlock</button></div></div>`);
    node.querySelector('#pc').onclick = () => { closeModal(); resolve(null); };
    node.querySelector('#pk').onclick = () => { const v = node.querySelector('#pinIn').value; closeModal(); resolve(v); };
    node.querySelector('#pinIn').onkeydown = e => { if (e.key === 'Enter') node.querySelector('#pk').click(); };
    modal(node);
  });
}

async function refresh() { S = await api().state(); paint(); }

// Fit the sidebar's vertical spacing to the window so all its items stay visible (width and icons scale freely).
function fitRail() {
  const rv = Math.max(1, Math.min(1.06, (window.innerHeight - 28) / 700));
  document.documentElement.style.setProperty('--rv', rv.toFixed(3));
}
window.addEventListener('resize', fitRail); fitRail();

// A small dot on Community when a friend has messaged you or is asking you to release them.
function paintBadge() {
  const ib = (S && S.inbox) || {};
  const set = (tab, n) => {
    const btn = document.querySelector(`.railbtn[data-tab="${tab}"]`); if (!btn) return;
    let b = btn.querySelector('.rbadge');
    if (!n) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement('i'); b.className = 'rbadge'; btn.querySelector('.ico').appendChild(b); }
    b.textContent = n > 9 ? '9+' : n;
  };
  set('community', ib.requests || 0);          // release requests and invites live in Community
  set('messages', ib.unread || 0);             // unread messages live on their own tab
}

// ---- sidebar greeting (signed-in users) ----
function paintWelcome() {
  const cu = (S && S.cloud_user) || {}, box = document.getElementById('railwelcome');
  const first = (cu.name || '').trim().split(/\s+/)[0];
  const on = !!(cu.signed_in && first);
  box.hidden = !on;
  document.querySelector('#rail .logo').classList.toggle('has-welcome', on);
  if (!on) return;
  $('#rw-name').textContent = first;
  $('#rw-av').textContent = first[0].toUpperCase();
  $('#rw-av').style.setProperty('--hue', avHue(first));
}
async function refreshWelcome() { S = await api().state(); paintWelcome(); }

// ---- top-level paint ----
const TAB_META = {
  home:      { title: 'Study session', crumb: 'HonestHands' },
  classes:   { title: 'Classes',       crumb: 'Your courses' },
  log:       { title: 'Activity',      crumb: 'What the guard has checked' },
  community: { title: 'Community',      crumb: 'HonestHands' },
  messages:  { title: 'Messages',       crumb: 'Your friends' },
  history:   { title: 'History',        crumb: 'Your study sessions' },
  insights:  { title: 'Insights',       crumb: 'How you\'re doing' },
  settings:  { title: 'Settings',      crumb: 'HonestHands' },
};
function engineChipHTML() {
  const e = S.engine;
  if (e.ready) return `<span class="chip good"><span class="d"></span>AI ready</span>`;
  if (e.state === 'downloading' || e.state === 'starting') return `<span class="chip warn"><span class="spin"></span> AI…</span>`;
  return `<span class="chip warn"><span class="d"></span>AI not ready</span>`;
}
function extChipHTML() {
  if (S.ext_live) return `<span class="chip good"><span class="d"></span>Extension on</span>`;
  return `<span class="chip warn"><span class="d"></span>Extension off</span>`;
}
// A popup the first time a new version is seen (once per build per launch); "Update now" hands over to Sparkle.
const UPDATE_POPPED = {};
function maybeUpdatePopup() {
  const u = S && S.update;
  if (!u || !S.onboarded || UPDATE_POPPED[u.build]) return;
  if (S.session && S.session.locked) return;                       // never interrupt a lock-in
  const modalEl = document.getElementById('modal'); if (modalEl && !modalEl.hidden) return;
  UPDATE_POPPED[u.build] = true;
  const node = el(`<div class="updpop"><div class="up-ic"><span class="ub-dot"></span></div>
    <h2>A new version is ready</h2>
    <p class="up-ver">HonestHands ${h(u.version || '')}</p>
    ${u.notes ? `<p class="up-notes">${h(u.notes)}</p>` : ''}
    <p class="small muted">It downloads, installs and reopens HonestHands by itself. Your classes and settings stay as they are.</p>
    <div class="btnrow" style="justify-content:center;margin-top:16px"><button class="btn" id="up-now">Update now</button><button class="btn ghost" id="up-later">Later</button></div></div>`);
  modal(node);
  $('#up-now').onclick = async () => { closeModal(); await api().open_update(); toast('Opening the updater…'); };
  $('#up-later').onclick = () => closeModal();
}
function paintUpdateBar() {
  const bar = document.getElementById('updatebar'); if (!bar) return;
  const u = S && S.update, show = !!u && S.onboarded;
  bar.hidden = !show; if (!show) { bar.innerHTML = ''; return; }
  bar.innerHTML = `<span class="ub-dot"></span><div><b>A new version of HonestHands is ready${u.version ? ' (' + h(u.version) + ')' : ''}.</b>${u.notes ? ' <span>' + h(u.notes) + '</span>' : ''}
    <small>One click installs it and reopens the app.</small></div>
    <button class="btn sm" id="ub-go">Update now</button><button class="btn ghost sm" id="ub-later">Later</button>`;
  document.getElementById('ub-go').onclick = () => api().open_update();
  maybeUpdatePopup();
  document.getElementById('ub-later').onclick = async () => { const r = await api().dismiss_update(); if (r && !r.error) { S = r; paintUpdateBar(); } };
}
function paint() {
  stopTimerTick();
  if (S) applyTheme(S.theme);
  paintUpdateBar();
  const rail = document.getElementById('rail');
  if (S && !S.onboarded) { rail.style.display = 'none'; document.getElementById('topbar').style.display='none'; paintOnboarding(); return; }
  rail.style.display = ''; document.getElementById('topbar').style.display='';
  const sf = document.getElementById('surface'); if (sf) sf.classList.remove('onbing');
  paintWelcome(); paintBadge();
  document.querySelectorAll('#rail .railbtn').forEach(b => b.classList.toggle('active', b.dataset.tab === TAB));
  const meta = TAB_META[TAB] || TAB_META.home;
  const sess = S.session;
  $('#pageTitle').textContent = meta.title;
  $('#crumb').textContent = (TAB === 'home' && sess) ? ('Guarding · ' + sess.class) : meta.crumb;
  // chips: session state + engine
  let chips = '';
  if (sess) chips += `<span class="chip live"><span class="d"></span>Session active</span>`;
  if (sess) chips += extChipHTML();
  chips += engineChipHTML();
  $('#chips').innerHTML = chips;
  ({ home: paintHome, classes: paintClasses, log: paintLog, history: paintHistory, insights: paintInsights, community: paintCommunity, messages: paintMessages, settings: paintSettings }[TAB])();
  const m = document.getElementById('main'); m.classList.remove('enter'); void m.offsetWidth; m.classList.add('enter');
}
document.querySelectorAll('#rail .railbtn[data-tab]').forEach(b => b.onclick = () => { TAB = b.dataset.tab; paint(); });

function engineBanner() {
  const e = S.engine;
  if (e.ready) return '';
  if (e.state === 'needs_setup')
    return `<div class="banner warn"><div><b>The AI needs a one-time setup.</b><div class="small">Until then, checking uses simple keyword rules only. It's a ${e.size_gb} GB download, and everything stays on this computer.</div></div><button class="btn sm" onclick="TAB='settings';paint()">Set up</button></div>`;
  if (e.state === 'downloading' || e.state === 'starting') {
    let bar = '';
    if (e.progress && e.progress.total) { const pct = Math.round(100 * e.progress.done / e.progress.total);
      bar = `<div class="progress"><div style="width:${pct}%"></div></div><div class="small">${h(e.progress.label)}: ${pct}% of ${(e.progress.total/1e9).toFixed(1)} GB</div>`; }
    return `<div class="banner warn"><div><b><span class="spin"></span> ${h(e.message || 'Preparing the AI…')}</b>${bar}</div></div>`;
  }
  if (e.state === 'error') return `<div class="banner warn"><div><b>The AI ran into a problem.</b><div class="small">${h(e.message)} Checking falls back to keyword rules. You can retry in Settings.</div></div></div>`;
  return '';
}

function permBanner() {
  if (S.perms.accessibility && S.perms.watching) return '';
  return `<div class="banner warn"><div><b>Accessibility permission needed.</b>
    <div class="small">The guard can't read or hold your messages until you turn on AI Integrity Guard under Accessibility, then reopen the app.</div></div>
    <button class="btn sm" onclick="api().open_accessibility_settings()">Open settings</button></div>`;
}


// ---- Onboarding ----
// ---- Home / study session ----
function paintHome() {
  const m = $('#main'); const sess = S.session;
  if (sess) {
    const st = sess.stats || {};
    m.innerHTML = `<div class="wrap sb-wrap">${permBanner()}${engineBanner()}
      <div class="sessbig cc-${sess.color || 'lav'}" id="sessbig">
        <div class="sb-top sb-in" style="--i:0"><span class="sb-live"><i></i>Guarding now</span>
          <span class="sb-tag">${h(S.policy_labels[sess.policy] || '')}</span></div>
        <div class="sb-mid">
          <h1 class="sb-class sb-in" style="--i:1">${h(sess.class)}</h1>
          ${sess.assignment ? `<div class="sb-asg sb-in" style="--i:2">${h(sess.assignment)}</div>` : ''}
          <div class="sb-timer-lab sb-in" style="--i:3">${sess.locked ? 'Time left' : 'Locked in for'}</div>
          <div class="sb-timer sb-in" style="--i:4" id="sessTimer">${sess.locked ? fmtDur(Math.max(0, Math.ceil(sess.ends_at - Date.now()/1000))) : fmtDur(sess.elapsed||0)}</div>
          ${sess.locked ? `<div class="sb-prog sb-in" style="--i:4"><i id="sb-prog-fill" style="width:${Math.min(100, 100 * (Date.now()/1000 - sess.started) / Math.max(1, sess.ends_at - sess.started))}%"></i></div>
            <div class="sb-until sb-in" style="--i:4">Locked in until ${fmtClock(sess.ends_at)}</div>` : ''}
        </div>
        <div class="sb-bot sb-in" style="--i:5">
          <div class="sb-stats">
            <div class="ok"><b id="sb-n-today">0</b><span>clean</span></div>
            <div><b id="sb-n-flag">0</b><span>flagged</span></div>
            <div class="bad"><b id="sb-n-over">0</b><span>overridden</span></div>
          </div>
          <button class="btn ghost" id="end">${sess.locked ? 'Need out?' : 'End session'}</button>
        </div>
      </div>
      <p class="small muted center" style="margin-top:14px">Use your AI apps and sites as normal. Each message is checked the moment before it sends.</p></div>`;
    countTo($('#sb-n-today'), st.clean || 0, { dur: 900 }); countTo($('#sb-n-flag'), st.flagged || 0, { dur: 900 }); countTo($('#sb-n-over'), st.overridden || 0, { dur: 900 });
    clearInterval(window.SESS_POLL);
    window.SESS_POLL = setInterval(async () => {           // keep this session's numbers live
      if (TAB !== 'home' || !document.getElementById('sessbig')) { clearInterval(window.SESS_POLL); return; }
      const ns = await api().state();
      if (!ns.session) { S = ns; paint(); return; }
      S = ns; const t = ns.session.stats || {};
      countTo($('#sb-n-today'), t.clean || 0, { dur: 600 }); countTo($('#sb-n-flag'), t.flagged || 0, { dur: 600 }); countTo($('#sb-n-over'), t.overridden || 0, { dur: 600 });
    }, 3000);
    startTimerTick(sess.started || (Date.now()/1000 - (sess.elapsed||0)), sess.locked ? sess.ends_at : 0);
    if (sess.locked) { $('#end').onclick = openNeedOut; return; }
    $('#end').onclick = async () => { const pin = await askPin('Enter the PIN to end this session.'); if (pin === null) return;
      const r = await api().end_session(pin || ''); if (r.error) toast(r.error); else refresh(); };
    return;
  }
  const TUTOR = S.tutor_mode, ALL = [TUTOR, ...S.classes];
  let selC = (S.classes[0] || TUTOR).id, selA = '', selMin = 30, customMin = 45;
  m.innerHTML = `<div class="wrap sess">${permBanner()}${engineBanner()}
    <div class="sess-hero"><div><h1>Start a study session</h1>
      <p class="sub" style="margin:6px 0 0">Pick what you're working on. The guard stays idle until you do.</p></div></div>
    <div class="step"><span class="n">1</span>Which class?</div>
    <div class="classgrid" id="cg"></div>
    <div id="asgstep"><div class="step"><span class="n">2</span>Which assignment?</div>
    <div class="seg" id="ag"></div></div>
    <div class="step"><span class="n">${'3'}</span>How long?</div>
    <div class="seg dur" id="dur"></div>
    <p class="durhint">We encourage using a timer for accountability’s sake. It’s what makes this stick.</p>
    <div id="durnote"></div>
    ${S.classes.length ? '' : `<p class="small muted" style="margin-top:18px">Want your own syllabus rules? <a href="#" onclick="TAB='classes';paint();return false">Add a class</a> any time.</p>`}
    <div class="startbar"><div class="sum" id="sum"></div><button class="btn" id="go">Start session</button></div></div>`;
  const cls = () => ALL.find(x => x.id === selC);
  const paintPicks = () => {
    $('#cg').innerHTML = ALL.map(c => { const k = (c.assignments || []).length;
      return `<button class="pick cc-${c.color} ${c.builtin ? 'tutor' : ''} ${c.id === selC ? 'on' : ''}" data-c="${c.id}"><span class="tick">✓</span>
        <span class="nm">${h(c.name)}</span><span class="meta">${c.builtin ? 'Use AI as a study partner' : h(S.policy_labels[c.policy] || '') + ' · ' + k + ' assignment' + (k === 1 ? '' : 's')}</span></button>`; }).join('');
    const asg = cls().assignments || [];
    $('#asgstep').hidden = !!cls().builtin;
    if (!asg.some(a => a.id === selA)) selA = '';
    $('#ag').innerHTML = `<button class="${selA === '' ? 'on' : ''}" data-a="">General work</button>` +
      asg.map(a => `<button class="${a.id === selA ? 'on' : ''}" data-a="${a.id}">${h(a.name)}</button>`).join('');
    const an = (asg.find(a => a.id === selA) || {}).name;
    $('#sum').innerHTML = `${cls().builtin ? 'Using' : 'Guarding'} <b>${h(cls().name)}</b>${an ? ' / <b>' + h(an) + '</b>' : ''}`;
    m.querySelectorAll('.pick').forEach(b => b.onclick = () => { selC = b.dataset.c; paintPicks(); });
    m.querySelectorAll('#ag button').forEach(b => b.onclick = () => { selA = b.dataset.a; paintPicks(); });
  };
  const DURS = [[30, '30 min'], [60, '1 hour'], [120, '2 hours'], [-1, 'Custom'], [0, 'No timer']];
  const minutes = () => selMin === -1 ? Math.max(1, Math.min(720, Math.round(+customMin) || 1)) : selMin;
  const paintDur = () => {
    $('#dur').innerHTML = DURS.map(([v, l]) => `<button class="${selMin === v ? 'on' : ''}" data-d="${v}">${l}</button>`).join('') +
      (selMin === -1 ? `<span class="durcustom"><input id="cmin" type="number" min="1" max="720" value="${customMin}"><span>minutes</span></span>` : '');
    const mins = minutes(), ex = S.exit || { pin: false, friends: 0 }, can = ex.pin || ex.friends > 0;
    const until = new Date(Date.now() + mins * 60000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    $('#durnote').innerHTML = !mins ? `<div class="lockbox soft"><b>No timer</b><span>You can end the session whenever you like${ex.pin ? ' (with your PIN)' : ''}. We encourage using a timer for accountability's sake: it's what stops “it's just one question, no one will care”, and it lets a friend hold you to it.</span></div>`
      : `<div class="lockbox ${can ? '' : 'warn'}"><b>Locked in until ${until}.</b>
          <span>You won't be able to quit or end it early. The only ways out: ${ex.pin ? 'your <b>PIN</b>' : ''}${ex.pin && ex.friends ? ' or ' : ''}${ex.friends ? `a <b>friend</b> releasing you (${ex.friends} can)` : ''}${can ? '.' : ''}</span>
          ${can ? '' : `<span>You don't have a way out yet, and a timed lock needs one for emergencies.</span><div class="btnrow" style="margin-top:8px">
            <button class="btn ghost sm" id="lk-pin">Set a PIN</button><button class="btn ghost sm" id="lk-friend">Invite a friend</button></div>`}</div>`;
    $('#go').disabled = !!mins && !can;
    $('#go').textContent = mins ? `Lock in for ${mins >= 60 && mins % 60 === 0 ? mins / 60 + ' hour' + (mins > 60 ? 's' : '') : mins + ' min'}` : 'Start session';
    m.querySelectorAll('#dur button').forEach(b => b.onclick = () => { selMin = +b.dataset.d; paintDur(); });
    if ($('#cmin')) $('#cmin').oninput = (e) => { customMin = e.target.value; const mm = minutes(); $('#go').textContent = `Lock in for ${mm} min`; };
    if ($('#lk-pin')) $('#lk-pin').onclick = () => { TAB = 'settings'; paint(); };
    if ($('#lk-friend')) $('#lk-friend').onclick = () => { TAB = 'community'; paint(); };
  };
  paintPicks(); paintDur();
  REFRESH_DUR = () => { if (document.getElementById('dur')) paintDur(); };
  $('#go').onclick = async () => {
    const pick = m.querySelector('.pick.on'), mins = minutes();
    if (pick && !reduceMotion()) return morphStart(pick, api().start_session(selC, selA, 'warn', mins));
    const r = await api().start_session(selC, selA, 'warn', mins);
    if (r.error) toast(r.error); else { TAB = 'home'; refresh(); }
  };
}

// ---- Classes ----
function paintClasses() {
  const m = $('#main');
  m.innerHTML = `<div class="wrap">${engineBanner()}
    <h1>Classes</h1><p class="sub">Each class has its own AI rules, read from its syllabus.</p>
    <div class="grid">${S.classes.map(classCard).join('')}
      <button class="addtile" id="add" aria-label="Add a class" title="Add a class"><span>+</span></button></div></div>`;
  $('#add').onclick = () => openDocFlow('class');
  m.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => editClass(b.dataset.edit));
  m.querySelectorAll('[data-view]').forEach(b => b.onclick = () => viewClass(b.dataset.view));
  m.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
    const pin = await askPin('Enter the PIN to delete this class.'); if (pin === null) return;
    const r = await api().delete_class(b.dataset.del, pin || ''); if (r.error) toast(r.error); else refresh(); });
  m.querySelectorAll('[data-asg]').forEach(b => b.onclick = () => openDocFlow('assignment', b.dataset.asg));
}
function classCard(c) {
  return `<div class="card cc cc-${c.color}"><div class="row" style="align-items:flex-start">
    <div style="flex:1;cursor:pointer" data-view="${c.id}" title="See rules and assignments"><h2><span class="cdot"></span>${h(c.name)} <span class="muted" style="font-size:14px">›</span></h2><span class="tag ${c.policy}">${h(S.policy_labels[c.policy])}</span></div>
    <button class="x" data-del="${c.id}" title="Delete">×</button></div>
    <div class="small muted mt">${(c.assignments||[]).length} assignment${(c.assignments||[]).length === 1 ? '' : 's'}</div>
    <div class="btnrow mt"><button class="btn ghost sm" data-view="${c.id}">View</button>
      <button class="btn ghost sm" data-edit="${c.id}">Edit rules</button>
      <button class="btn ghost sm" data-asg="${c.id}">Add assignment</button></div>
    ${(c.assignments||[]).length ? '<div class="small muted mt">'+c.assignments.map(a=>h(a.name)).join(' · ')+'</div>' : ''}</div>`;
}

// Upload-and-read flow, shared by classes and assignments
function openDocFlow(kind, classId) {
  const isClass = kind === 'class';
  const node = el(`<div><h2>${isClass ? 'Add a class' : 'Add an assignment'}</h2>
    <p class="sub">${isClass ? 'Name the class and give it the syllabus. The AI-use parts are pulled out word for word, and the guard reads them for every message.' : 'Name the assignment and paste or upload it. Anything about AI in it applies on top of the class rules.'}</p>
    <div class="field"><label>${isClass ? 'Class name' : 'Assignment name'}</label><input id="dn" placeholder="${isClass ? 'e.g. CS 7641 Machine Learning' : 'e.g. Homework 3'}"></div>
    <div class="field"><label>Document</label><div class="btnrow"><button class="btn ghost sm" id="pick">Choose a file…</button>
      <span class="small muted" id="fn">PDF, Word, or text</span></div></div>
    <div class="field"><label>…or paste the text</label><textarea id="dt" rows="6" placeholder="Paste the ${isClass ? 'syllabus, or just its AI section' : 'assignment instructions'}"></textarea></div>
    <p class="small muted" id="hint"></p>
    <div class="btnrow" style="justify-content:flex-end"><button class="btn ghost" id="cx">Cancel</button>
      <button class="btn" id="go">Read it</button></div></div>`);
  let path = '';
  node.querySelector('#cx').onclick = closeModal;
  node.querySelector('#pick').onclick = async () => { const p = await api().choose_file(); if (p) { path = p; node.querySelector('#fn').textContent = p.split('/').pop(); } };
  node.querySelector('#go').onclick = async () => {
    const name = node.querySelector('#dn').value.trim(); if (!name) { toast('Give it a name first.'); return; }
    const text = node.querySelector('#dt').value.trim();
    if (!path && !text) { toast('Choose a file or paste the text.'); return; }
    node.querySelector('#hint').innerHTML = '<span class="spin"></span> Reading the document… this can take up to a minute.';
    node.querySelector('#go').disabled = true;
    const res = await api().analyze(kind, name, path, text, classId || '', '');
    if (res.error) { node.querySelector('#hint').textContent = res.error; node.querySelector('#go').disabled = false; return; }
    reviewDraft(kind, classId, { id: '', name, policy: res.policy, color: COLORS.find(k => !S.classes.some(c => c.color === k)) || COLORS[S.classes.length % COLORS.length], rules: [], examples: res.examples, source_text: res.source_text, policy_text: res.policy_text, category_reason: res.category_reason }, res);
  };
  modal(node);
}

function ruleRow(r, i) {
  return `<div class="ruleitem"><span class="rtype ${r.type}">${({allowed:'OK',not_allowed:'NOT OK',condition:'IF',exception:'EXCEPT'}[r.type]||'RULE')}</span>
    <div class="body"><div contenteditable data-k="rule" data-i="${i}">${h(r.rule)}</div>
      ${r.quote ? `<div class="quote">“${h(r.quote)}”</div>` : '<div class="quote muted">no quote — you added this</div>'}</div>
    <button class="x" data-rm="${i}">×</button></div>`;
}

function reviewDraft(kind, classId, draft, meta) {
  const isClass = kind === 'class';
  const node = el(`<div><h2>${isClass ? 'Your professor\'s rules for ' : 'AI rules for '}${h(draft.name)}</h2>
    <p class="sub">${isClass
      ? 'This is the part of the syllabus about AI, copied as written. For every message you send, the guard reads it and decides like the professor would: peer-style collaboration, or cheating? Edit it if anything is missing or wrong.'
      : 'Anything this assignment says about AI or outside help. It applies on top of the class rules.'}</p>
    ${meta && meta.note ? `<div class="banner warn"><div class="small">${h(meta.note)}</div></div>` : ''}
    <div class="field"><textarea id="ptext" rows="${isClass ? 13 : 7}" placeholder="Paste or type the AI / collaboration rules here">${h(draft.policy_text || '')}</textarea></div>
    ${isClass ? `<div class="field"><label>Color</label><div class="swatches" id="swatches">${COLORS.map(k => `<button type="button" class="sw cc-${k} ${draft.color === k ? 'on' : ''}" data-col="${k}" aria-label="${k}"></button>`).join('')}</div></div>` : ''}
    ${isClass ? `<div class="catline"><span class="muted small">Label:</span>
      <select id="pol" class="mini">${Object.entries(S.policy_labels).map(([k,v])=>`<option value="${k}" ${draft.policy===k?'selected':''}>${h(v)}</option>`).join('')}</select>
      ${draft.category_reason ? `<span class="small muted">${h(draft.category_reason)}</span>` : ''}</div>` : ''}
    <div class="btnrow mt" style="justify-content:flex-end"><button class="btn ghost" id="cx">Cancel</button>
      <button class="btn" id="save">Save ${isClass ? 'class' : 'assignment'}</button></div></div>`);
  node.querySelectorAll('.sw').forEach(b => b.onclick = () => { draft.color = b.dataset.col;
    node.querySelectorAll('.sw').forEach(x => x.classList.toggle('on', x === b)); });
  node.querySelector('#cx').onclick = closeModal;
  node.querySelector('#save').onclick = async () => {
    const payload = { color: draft.color, id: draft.id, name: draft.name, rules: draft.rules || [], examples: draft.examples || [], source_text: draft.source_text, policy_text: node.querySelector('#ptext').value };
    if (isClass) { payload.policy = node.querySelector('#pol').value; payload.category_reason = draft.category_reason || ''; }
    const r = isClass ? await api().save_class(payload) : await api().save_assignment(classId, payload);
    if (r.error) { toast(r.error); return; } closeModal(); toast('Saved.'); S = r; paint();
  };
  modal(node);
}

function viewClass(id) {
  const c = S.classes.find(x => x.id === id); if (!c) return;
  const text = c.policy_text || (c.rules || []).map(r => r.quote || r.rule).join('\n\n');
  const asg = c.assignments || [];
  const node = el(`<div><h2><span class="cdot cc-${c.color}"></span>${h(c.name)}</h2><span class="tag ${c.policy}">${h(S.policy_labels[c.policy])}</span>
    <div class="step" style="margin-top:20px"><span class="n">1</span>Class AI rules</div>
    <div class="policybox">${text ? h(text) : '<span class="muted">No AI rules saved for this class yet.</span>'}</div>
    <div class="step"><span class="n">2</span>Assignments <span class="muted small">(${asg.length})</span></div>
    ${asg.map(a => `<details class="asgrow"><summary><b>${h(a.name)}</b>
        <span class="small muted">${a.policy_text || (a.rules || []).length ? 'has its own AI rules' : 'no extra AI rules'}</span></summary>
      <div class="policybox">${a.policy_text ? h(a.policy_text) : (a.rules || []).length ? h(a.rules.map(r => r.quote || r.rule).join('\n\n')) : '<span class="muted">This assignment doesn\'t say anything about AI. The class rules apply.</span>'}</div>
      <div class="btnrow"><button class="btn ghost sm" data-ea="${a.id}">Edit</button><button class="btn danger sm" data-da="${a.id}">Delete</button></div></details>`).join('')
      || '<p class="small muted">No assignments yet.</p>'}
    <div class="btnrow mt" style="justify-content:flex-end"><button class="btn ghost" id="vadd">Add assignment</button><button class="btn" id="vcx">Done</button></div></div>`);
  node.querySelector('#vcx').onclick = closeModal;
  node.querySelector('#vadd').onclick = () => { closeModal(); openDocFlow('assignment', id); };
  node.querySelectorAll('[data-ea]').forEach(b => b.onclick = () => { const a = asg.find(x => x.id === b.dataset.ea); closeModal();
    reviewDraft('assignment', id, { id: a.id, name: a.name, rules: a.rules || [], examples: a.examples || [], source_text: '',
      policy_text: a.policy_text || (a.rules || []).map(r => r.quote || r.rule).join('\n\n') }, null); });
  node.querySelectorAll('[data-da]').forEach(b => b.onclick = async () => {
    const pin = await askPin('Enter the PIN to delete this assignment.'); if (pin === null) return;
    const r = await api().delete_assignment(id, b.dataset.da, pin || ''); if (r.error) toast(r.error); else { S = r; closeModal(); paint(); viewClass(id); } });
  modal(node);
}

async function editClass(id) {
  const c = S.classes.find(x => x.id === id);
  reviewDraft('class', id, { color: c.color, id: c.id, name: c.name, policy: c.policy, rules: c.rules || [], examples: c.examples || [], source_text: '', policy_text: c.policy_text || (c.rules || []).map(r => r.quote || r.rule).join('\n\n'), category_reason: c.category_reason || '' }, null);
}

// ---- Activity log ----
const COLORS = ['orchid', 'olive', 'lav', 'mint', 'sun', 'sky', 'rose', 'peach', 'sage', 'sand'];
let LOGPAGE = 1, LOGKIND = 'all';
async function paintLog() {
  const m = $('#main');
  m.innerHTML = `<div class="wrap"><div class="row" style="align-items:center">
    <div style="flex:2"><h1>Activity</h1><p class="sub">Everything the guard has checked. Stored only on this computer.</p></div>
    <div style="flex:1;text-align:right"><div class="btnrow" style="justify-content:flex-end">
      <button class="btn ghost sm" id="exp">Export report</button><button class="btn danger sm" id="clr">Clear</button></div></div></div>
    <div class="filters" id="logfilters"></div>
    <div class="card" id="loglist"><p class="muted">Loading…</p></div></div>`;
  const pg = await api().get_log_page(LOGPAGE, 25, LOGKIND);
  LOGPAGE = pg.page;
  const rows = pg.rows.map((e, idx) => {
    const when = new Date(e.t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    if (e.event) return `<div class="logline"><span class="when">${when}</span><div class="txt muted">— ${h(e.event)}: ${h(e.class||'')} ${h(e.assignment||'')}</div></div>`;
    const over = e.result === 'sent anyway' || e.result === 'sent after warning';
    const ok = e.result.startsWith('ok'), warned = !over && !ok;
    const label = { 'ok': 'Clean', 'ok (disclose)': 'Clean · disclose AI use', 'ok (revised)': 'Clean', 'warned': 'Flagged', 'blocked': 'Flagged', 'sent anyway': 'Overridden', 'sent after warning': 'Overridden' }[e.result] || e.result;
    return `<div class="logline"><span class="when">${when}</span><span class="dot ${ok?'':over?'bad':'warn'}"></span>
      <div class="txt"><b>${h(label)}</b> · ${h(e.where||'')} · ${h(e.class||'')} ${e.assignment?'/ '+h(e.assignment):''}
      ${e.source?`<span class="small muted">(${e.source==='ai'?'AI':'keywords'})</span>`:''}
      <div class="q small">“${h(e.text||'')}”</div>${e.reasons?`<div class="small muted">${e.reasons.map(h).join(' ')}</div>`:''}
      ${over && S.cloud_user && S.cloud_user.signed_in ? `<div class="lfb" data-i="${idx}"></div>` : ''}</div></div>`;
  }).join('');
  const FILTERS = [['all', 'All', ''], ['flagged', 'Flagged', 'warn'], ['overridden', 'Overridden', 'bad'], ['clean', 'Clean', 'ok']];
  $('#logfilters').innerHTML = FILTERS.map(([k, label, cls]) => `<button class="fchip ${LOGKIND === k ? 'on' : ''}" data-k="${k}">
    ${cls ? `<span class="idot ${cls}"></span>` : ''}${label}<span class="fcount">${pg.counts[k] ?? 0}</span></button>`).join('');
  $('#logfilters').querySelectorAll('.fchip').forEach(b => b.onclick = () => { LOGKIND = b.dataset.k; LOGPAGE = 1; paintLog(); });
  const pager = () => {
    if (pg.pages <= 1) return '';
    const nums = []; const add = n => { if (nums[nums.length - 1] !== n) nums.push(n); };
    for (let i = 1; i <= pg.pages; i++) { if (i === 1 || i === pg.pages || Math.abs(i - pg.page) <= 1) add(i); else add('…'); }
    const from = (pg.page - 1) * pg.per_page + 1, to = Math.min(pg.total, pg.page * pg.per_page);
    return `<div class="pager"><div class="pager-info">${from}–${to} of ${pg.total}</div>
      <div class="pager-ctl"><button class="pg arrow" data-pg="${pg.page - 1}" ${pg.page === 1 ? 'disabled' : ''} aria-label="Newer">‹</button>
      ${nums.map(n => n === '…' ? '<span class="pg gap">…</span>' : `<button class="pg ${n === pg.page ? 'on' : ''}" data-pg="${n}">${n}</button>`).join('')}
      <button class="pg arrow" data-pg="${pg.page + 1}" ${pg.page === pg.pages ? 'disabled' : ''} aria-label="Older">›</button></div></div>`;
  };
  $('#loglist').innerHTML = (rows || (LOGKIND === 'all' ? '<p class="muted">Nothing yet. Start a session and use AI, and it\'ll show up here.</p>' : '<p class="muted">Nothing in this category.</p>')) + pager();
  $('#loglist').querySelectorAll('[data-pg]').forEach(b => b.onclick = () => { LOGPAGE = +b.dataset.pg; paintLog(); $('#main').scrollTop = 0; });
  drawLogFeedback(pg.rows);
  $('#exp').onclick = async () => { const p = await api().export_log(); if (p) toast('Saved to ' + p.split('/').pop()); };
  $('#clr').onclick = async () => { const pin = await askPin('Enter the PIN to clear the log.'); if (pin === null) return;
    const r = await api().clear_log(pin || ''); if (r && r.error) toast(r.error); else { LOGPAGE = 1; paintLog(); } };
}


// Notes you leave on your own overridden prompts, and what your partners made of them.
async function drawLogFeedback(rows) {
  const boxes = [...document.querySelectorAll('.lfb')]; if (!boxes.length) return;
  const idx = boxes.map(b => +b.dataset.i), pairs = idx.map(i => [rows[i].t, rows[i].text || '']);
  const fb = await api().cloud_feedback(pairs);
  const list = Array.isArray(fb) ? fb : [];
  boxes.forEach((box, k) => paintLfb(box, rows[idx[k]], list[k] || { note: '', reactions: [] }));
}
function paintLfb(box, row, f) {
  const chips = (f.reactions || []).map(r => `<span class="rchip ${r.verdict}">${r.verdict === 'up' ? THUMB_UP : THUMB_DOWN}${h(r.name)}</span>`).join('');
  box.innerHTML = `${f.note ? `<div class="mynote"><b>Your note</b>${h(f.note)}</div>` : ''}
    <div class="lfrow">${chips}<button class="linkbtn" data-edit>${f.note ? 'Edit your note' : 'Add a note for your partners'}</button></div>`;
  box.querySelector('[data-edit]').onclick = () => {
    box.innerHTML = `<textarea class="lfta" rows="3" maxlength="1000" placeholder="Explain what happened (for example, the AI got this wrong). Your partners see this next to the prompt."></textarea>
      <div class="lfrow"><button class="btn sm" data-save>Save note</button><button class="btn ghost sm" data-cancel>Cancel</button>${f.note ? '<button class="linkbtn" data-del>Remove note</button>' : ''}</div>`;
    const ta = box.querySelector('textarea'); ta.value = f.note || ''; ta.focus();
    const save = async (body) => {
      const r = await api().cloud_set_note(row.t, row.text || '', body);
      if (r && r.error) return toast(r.error);
      toast(body ? 'Note saved. Your partners can see it.' : 'Note removed.');
      paintLfb(box, row, Object.assign({}, f, { note: body }));
    };
    box.querySelector('[data-save]').onclick = () => save(ta.value.trim());
    box.querySelector('[data-cancel]').onclick = () => paintLfb(box, row, f);
    const del = box.querySelector('[data-del]'); if (del) del.onclick = () => save('');
  };
}

// ---- Appearance: follows the system unless the person picks light or dark ----
function applyTheme(mode) {
  const root = document.documentElement;
  if (mode === 'light' || mode === 'dark') root.setAttribute('data-theme', mode); else root.removeAttribute('data-theme');
}

// ---- Settings ----
function paintSettings() {
  const m = $('#main'); const e = S.engine;
  m.innerHTML = `<div class="wrap"><h1>Settings</h1>
    <div class="card"><h2>About</h2><p class="sub">HonestHands ${h(S.version || '')}. ${S.auto_updates ? 'Updates install automatically when you say yes.' : S.update ? 'A newer version is ready.' : 'You have the latest version.'}</p>
      <div class="btnrow"><button class="btn ghost" id="chkup">Check for updates</button>${S.update ? '<button class="btn" id="getup">Download update</button>' : ''}</div></div>
    <div class="card"><h2>Appearance</h2><p class="sub">Light or dark. “Match my system” follows your system setting.</p>
      <div class="segmode themeseg" id="themeseg">${[['system', 'Match my system'], ['light', 'Light'], ['dark', 'Dark']].map(([k, l]) => `<button data-th="${k}" class="${(S.theme || 'system') === k ? 'on' : ''}">${l}</button>`).join('')}</div>
    </div>
    <div class="card"><h2>The Guard</h2><p class="sub">The built-in AI that reads each message against your class rules. It runs on this computer, so what you type stays private. One model, nothing to configure.</p>
      <div class="btnrow"><span class="chip ${e.ready ? 'good' : 'warn'}"><span class="d"></span>${e.ready ? 'Ready' : h(e.message || 'Not set up yet')}</span>
        ${e.ready ? '' : `<button class="btn" id="apply">${e.state === 'error' ? 'Try again' : 'Download &amp; set up'}</button>`}</div>
      <div id="eprog"></div>
    </div>
    <div class="card"><h2>Guarded browser</h2>
      <p class="sub">Pick the one browser where AI websites are allowed during a study session, and set up its extension. The extension does nothing unless HonestHands is running and a session is active. The Claude and ChatGPT desktop apps are covered by the app directly.</p>
      <div id="extBody"></div>
    </div>
    <div class="card"><h2>Stay locked in</h2>
      <p class="sub">While a study session is on, HonestHands notices when another app comes to the front. If it's on this list it's hidden and you're put back where you were, with a short note.</p>
      <label class="lockrow"><span class="switch"><input type="checkbox" id="lk-b" ${S.lock.browsers ? 'checked' : ''}><i></i></span>
        <div><b>Turn me back from other browsers</b><span>Only your guarded browser stays available${S.browser && S.browser.chosen ? '' : ' (pick one above first)'}.</span></div></label>
      <label class="lockrow"><span class="switch"><input type="checkbox" id="lk-a" ${S.lock.ai_apps ? 'checked' : ''}><i></i></span>
        <div><b>Also block AI desktop apps</b><span>Claude, ChatGPT and similar. Off by default, because the guard already checks messages you send from them.</span></div></label>
      <p class="small muted mt">This is a speed bump for the moment of temptation, not a cage: you can still quit HonestHands. Set an accountability PIN below so ending a session or quitting needs someone else.</p>
    </div>
    <div class="card"><h2>Accountability PIN</h2>
      <p class="sub">A friend or parent sets this. Then ending a session, deleting a class, or clearing the log needs it.</p>
      <div class="row">${S.has_pin?'<div class="field"><label>Current PIN</label><input type="password" id="op" inputmode="numeric"></div>':''}
        <div class="field"><label>${S.has_pin?'New PIN':'Set a PIN'}</label><input type="password" id="np" inputmode="numeric"></div></div>
      <div class="btnrow"><button class="btn ghost" id="pinbtn">${S.has_pin?'Change PIN':'Set PIN'}</button>
        ${S.has_pin?'<button class="btn danger" id="pinrm">Remove PIN</button>':''}</div>
      ${S.has_pin?'<p class="small muted mt">To remove it, type the current PIN above, then press Remove PIN.</p>':''}</div>
    <div class="card"><h2>This computer</h2>
      <div class="btnrow">${S.platform === 'mac' ? '<button class="btn ghost sm" id="acc">Accessibility settings</button>' : ''}
        <button class="btn ghost sm" id="data">Open data folder</button></div>
      <p class="small muted mt">${S.platform === 'mac' ? `Permission: ${S.perms.accessibility ? 'granted' : 'not granted'} · ` : ''}The guard is ${S.perms.watching ? 'on' : 'off'}</p></div>
    </div>`;
  const extBox = document.getElementById('extBody');
  extBox.innerHTML = browserPanelHTML();
  wireBrowserPanel(extBox, () => paint());

  const saveLock = async () => { const r = await api().set_lock($('#lk-b').checked, $('#lk-a').checked); if (r && !r.error) { S = r; toast('Saved.'); } };
  $('#lk-b').onchange = saveLock; $('#lk-a').onchange = saveLock;
  if ($('#apply')) $('#apply').onclick = async () => { $('#apply').disabled = true;
    const r = await api().setup_ai();
    if (r.error) toast(r.error); else { S = r; toast('Getting the AI ready…'); paint(); } };
  if ($('#pinrm')) $('#pinrm').onclick = async () => { const r = await api().remove_pin($('#op').value || '');
    if (r.error) toast(r.error); else { S = r; toast('PIN removed.'); paint(); } };
  $('#pinbtn').onclick = async () => { const r = await api().set_pin($('#op')?.value || '', $('#np').value);
    if (r.error) toast(r.error); else { S = r; toast('PIN updated.'); paint(); } };
  $('#themeseg').querySelectorAll('button').forEach(b => b.onclick = async () => {
    const r = await api().set_theme(b.dataset.th); if (r && !r.error) { S = r; applyTheme(S.theme); }
    $('#themeseg').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
  });
  $('#chkup').onclick = async () => { $('#chkup').disabled = true; const r = await api().check_update(); $('#chkup').disabled = false; if (r && !r.error) { S = r; if (!S.auto_updates) toast(S.update ? 'A new version is ready.' : 'You have the latest version.'); paintSettings(); paintUpdateBar(); } };
  if ($('#getup')) $('#getup').onclick = () => api().open_update();
  if ($('#acc')) $('#acc').onclick = () => api().open_accessibility_settings();
  $('#data').onclick = () => api().open_data_folder();
}

// ---- boot + live polling for engine/session changes ----
let REFRESH_DUR = null;     // set by the start page: redraws the duration buttons when the friend count arrives
window.addEventListener('pywebviewready', async () => {
  await refresh();
  setInterval(async () => {
    try { const sessSig = x => x ? [x.class_id,x.assignment_id,x.started].join(',') : '';
      const prevExit = JSON.stringify(S.exit);
      const prev = JSON.stringify(S.engine) + S.perms.watching + S.perms.accessibility + S.ext_live + sessSig(S.session);
      const ns = await api().state();
      if (!ns.onboarded) {
        S = ns;
        if (onbStructSig() !== lastOnbSig) paintOnboarding(false);  // real change: rebuild, no animation
        else updateOnbStatus();                                    // just progress ticking: update in place
        return;
      }
      if (JSON.stringify(ns.engine) + ns.perms.watching + ns.perms.accessibility + ns.ext_live + sessSig(ns.session) !== prev) { S = ns; paint(); }
      else { S = ns; paintBadge(); paintUpdateBar();
        // friends/PIN known now: un-gray the timed options on the start page
        if (JSON.stringify(ns.exit) !== prevExit && TAB === 'home' && REFRESH_DUR) REFRESH_DUR();
        if (TAB==='settings' && S.engine.progress){ const e=S.engine, pct=e.progress.total?Math.round(100*e.progress.done/e.progress.total):0;
        const box=$('#eprog'); if(box) box.innerHTML=`<div class="progress"><div style="width:${pct}%"></div></div><div class="small">${h(e.progress.label)}: ${pct}%</div>`; } }
    } catch (_) {}
  }, 1500);
});
