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
function startTimerTick(startedEpoch){
  stopTimerTick();
  TIMER = setInterval(()=>{ const el=document.getElementById('sessTimer');
    if(!el){ return; }
    const sec = Math.floor(Date.now()/1000 - startedEpoch);
    el.textContent = fmtDur(sec);
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

// ---- top-level paint ----
const TAB_META = {
  home:      { title: 'Study session', crumb: 'HonestHands' },
  classes:   { title: 'Classes',       crumb: 'Your courses' },
  log:       { title: 'Activity',      crumb: 'What the guard has checked' },
  community: { title: 'Community',      crumb: 'HonestHands' },
  history:   { title: 'History',        crumb: 'Your study sessions' },
  insights:  { title: 'Insights',       crumb: 'How you\'re doing' },
  settings:  { title: 'Settings',      crumb: 'HonestHands' },
};
function engineChipHTML() {
  const e = S.engine;
  const names = { builtin: 'Built-in AI', ollama: 'Ollama', keywords: 'Keyword rules' };
  if (e.backend === 'keywords') return `<span class="chip">Keyword rules</span>`;
  if (e.ready) return `<span class="chip good"><span class="d"></span>${names[e.backend]} ready</span>`;
  if (e.state === 'downloading' || e.state === 'starting') return `<span class="chip warn"><span class="spin"></span> ${names[e.backend]}…</span>`;
  return `<span class="chip warn"><span class="d"></span>${names[e.backend]} not ready</span>`;
}
function extChipHTML() {
  if (S.ext_live) return `<span class="chip good"><span class="d"></span>Extension on</span>`;
  return `<span class="chip warn"><span class="d"></span>Extension off</span>`;
}
function paint() {
  stopTimerTick();
  const rail = document.getElementById('rail');
  if (S && !S.onboarded) { rail.style.visibility = 'hidden'; document.getElementById('topbar').style.visibility='hidden'; paintOnboarding(); return; }
  rail.style.visibility = 'visible'; document.getElementById('topbar').style.visibility='visible';
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
  ({ home: paintHome, classes: paintClasses, log: paintLog, history: paintHistory, insights: paintInsights, community: paintCommunity, settings: paintSettings }[TAB])();
  const m = document.getElementById('main'); m.classList.remove('enter'); void m.offsetWidth; m.classList.add('enter');
}
document.querySelectorAll('#rail .railbtn[data-tab]').forEach(b => b.onclick = () => { TAB = b.dataset.tab; paint(); });

function engineBanner() {
  const e = S.engine;
  if (e.backend === 'keywords') return '';
  if (e.ready) return '';
  if (e.state === 'needs_setup')
    return `<div class="banner warn"><div><b>The AI guard needs a one-time setup.</b><div class="small">Until then, checking uses keyword rules only. Set it up in Settings.</div></div><button class="btn sm" onclick="TAB='settings';paint()">Set up</button></div>`;
  if (e.state === 'downloading' || e.state === 'starting') {
    let bar = '';
    if (e.progress && e.progress.total) { const pct = Math.round(100 * e.progress.done / e.progress.total);
      bar = `<div class="progress"><div style="width:${pct}%"></div></div><div class="small">${e.progress.label}: ${pct}% of ${(e.progress.total/1e9).toFixed(1)} GB</div>`; }
    return `<div class="banner warn"><div><b><span class="spin"></span> ${h(e.message||'Preparing the AI guard…')}</b>${bar}</div></div>`;
  }
  if (e.state === 'error') return `<div class="banner warn"><div><b>AI guard problem.</b><div class="small">${h(e.message)} Checking falls back to keyword rules. See Settings.</div></div></div>`;
  return '';
}

function permBanner() {
  if (S.perms.accessibility && S.perms.watching) return '';
  return `<div class="banner warn"><div><b>Accessibility permission needed.</b>
    <div class="small">The guard can't read or hold your messages until you turn on AI Integrity Guard under Accessibility, then reopen the app.</div></div>
    <button class="btn sm" onclick="api().open_accessibility_settings()">Open settings</button></div>`;
}


// ---- Onboarding ----
let ONB = 0;
let lastOnbSig = '';
function onbStructSig() {
  const e = S.engine;
  return [ONB, S.classes.length, e.backend, e.model, e.state, e.ready].join('|');
}
function paintOnboarding(animate = true) {
  const m = document.getElementById('main');
  const steps = [welcomeStep, guardStep, extensionStep, firstClassStep];
  m.innerHTML = `<div class="wrap onb">${steps[Math.min(ONB, steps.length-1)]()}</div>`;
  if (animate) { m.classList.remove('enter'); void m.offsetWidth; m.classList.add('enter'); }
  wireOnboarding();
  lastOnbSig = onbStructSig();
}
// Update just the download status/progress without rebuilding the screen (no flicker).
function updateOnbStatus() {
  const box = document.querySelector('.onb-status');
  if (box) box.innerHTML = guardStatusHTML();
}
function dots(i){ return `<div class="onb-dots">${[0,1,2,3].map(n=>`<span class="${n===i?'on':''}"></span>`).join('')}</div>`; }

function welcomeStep() {
  return `<div class="onb-hero center">
    <div class="onb-seal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M8 11V5.5a1.3 1.3 0 0 1 2.6 0V10"/><path d="M10.6 10V4.4a1.3 1.3 0 0 1 2.6 0V10"/>
      <path d="M13.2 10.2V5.4a1.3 1.3 0 0 1 2.6 0V12"/>
      <path d="M15.8 12V8.6a1.3 1.3 0 0 1 2.5 0c0 3.2.1 4.4-.6 6.3-.8 2.2-2.4 3.6-4.8 3.6-2 0-3.2-.5-4.4-1.9l-2.7-3.2a1.35 1.35 0 0 1 1.9-1.9L7 11"/></svg></div>
    <h1 class="onb-title">Welcome to HonestHands</h1>
    <p class="onb-verse">“Let the thief no longer steal, but rather let him labor, doing honest work with his own hands, so that he may have something to share with anyone in need.”<br><span class="ref">Ephesians 4:28</span></p>
    <p class="onb-lead">HonestHands checks what you’re about to send to an AI against your class’s own rules, and warns you before you cross a line — so AI stays a tutor, not a shortcut. Everything runs on your Mac.</p>
    <div class="btnrow center-row"><button class="btn" id="o-next">Get started</button></div>
    ${dots(0)}</div>`;
}
function guardStatusHTML() {
  const e = S.engine;
  if (e.backend === 'keywords') return `<p class="small muted">You’re on keyword rules — no download, but less nuanced. You can switch to the AI guard anytime in Settings.</p>`;
  if (e.ready) return `<p class="small" style="color:var(--ok)">✓ The AI guard is ready.</p>`;
  if (e.state === 'downloading' || e.state === 'starting') {
    const pct = e.progress && e.progress.total ? Math.round(100*e.progress.done/e.progress.total) : 0;
    const of = e.progress && e.progress.total ? ` · ${(e.progress.done/1e9).toFixed(1)} of ${(e.progress.total/1e9).toFixed(1)} GB` : '';
    return `<p class="small"><span class="spin"></span> ${h(e.message||'Preparing…')}${of}</p><div class="progress"><div style="width:${pct}%"></div></div>`;
  }
  if (e.state === 'error') return `<p class="small" style="color:var(--stop)">${h(e.message)}</p>`;
  return `<p class="small muted">${h(e.message||'The AI guard needs a one-time setup.')}</p>`;
}
function guardStep() {
  const e = S.engine;
  const ready = e.ready;
  const status = guardStatusHTML();
  return `<div class="onb-card">
    <h1 class="onb-title">Choose your guard</h1>
    <p class="onb-lead">This is what decides whether a message is OK. The built-in AI runs privately on your Mac after a one-time download. On your machine, the larger model is a great fit.</p>
    <div class="field"><label>Guard</label><select id="o-be">
      <option value="builtin" ${e.backend==='builtin'?'selected':''}>Built-in AI — private, runs on this Mac</option>
      <option value="ollama" ${e.backend==='ollama'?'selected':''}>Ollama — if you already use it</option>
      <option value="keywords" ${e.backend==='keywords'?'selected':''}>Keyword rules only — no download</option>
    </select></div>
    <div class="field" id="o-mf" ${e.backend==='builtin'?'':'hidden'}><label>Model size</label><select id="o-mdl">
      ${Object.entries(e.models).map(([k,v])=>`<option value="${k}" ${e.model===k?'selected':''}>${h(v)}</option>`).join('')}</select></div>
    <div class="btnrow"><button class="btn ghost sm" id="o-apply">Download &amp; set up</button></div>
    <div class="onb-status">${status}</div>
    <div class="btnrow center-row mt"><button class="btn ghost" id="o-back">Back</button>
      <button class="btn" id="o-next">${ready||e.backend==='keywords'?'Continue':'Continue anyway'}</button></div>
    ${dots(1)}</div>`;
}
function extensionStep() {
  const ext = S.extension || {browsers:[], installed_dir:''};
  const ready = !!ext.installed_dir;
  const browsers = ext.browsers||[];
  return `<div class="onb-card">
    <h1 class="onb-title">Install the browser guard</h1>
    <p class="onb-lead">AI websites like Gemini hide their send button from the Mac. A small companion extension closes that gap. It only works while HonestHands is running and a session is active — it never watches anything otherwise. This step is required for website coverage.</p>
    <div class="btnrow"><button class="btn" id="o-extprep">${ready?'Re-copy files':'Set up the extension'}</button>
      ${ready?'<button class="btn ghost" id="o-extopen">Open folder</button>':''}</div>
    <div class="onb-status" id="o-extstatus"></div>
    ${ready?`<div class="step-note mt"><b>Enable it once in your browser:</b><ol class="small" style="margin:8px 0 0 18px;line-height:1.7"><li>Open Extensions ${browsers.length?'('+browsers.map(h).join(', ')+')':''}</li><li>Turn on <b>Developer mode</b></li><li><b>Load unpacked</b> → choose the folder</li></ol></div><div class="btnrow mt">`+browsers.filter(b=>['Google Chrome','Microsoft Edge','Brave'].includes(b)).map(b=>`<button class="btn ghost sm" data-obrowser="${h(b)}">Open ${h(b)}</button>`).join('')+`</div>`:''}
    <div class="btnrow center-row mt"><button class="btn ghost" id="o-back">Back</button>
      <button class="btn" id="o-next">${ready?'I\u2019ve enabled it — continue':'Continue'}</button></div>
    ${dots(2)}</div>`;
}
function firstClassStep() {
  const has = S.classes.length>0;
  return `<div class="onb-card center">
    <h1 class="onb-title">Add your first class</h1>
    <p class="onb-lead">Give HonestHands a syllabus and it learns that class’s AI rules — what’s allowed, what isn’t — straight from the document, with the exact lines quoted back to you.</p>
    ${has ? `<p class="small" style="color:var(--ok)">✓ ${h(S.classes[0].name)} added${S.classes.length>1?` and ${S.classes.length-1} more`:''}.</p>` : ''}
    <div class="btnrow center-row"><button class="btn" id="o-add">${has?'Add another':'Add a class'}</button>
      ${has?`<button class="btn" id="o-done">Finish</button>`:`<button class="btn ghost" id="o-later">I’ll do this later</button>`}</div>
    <button class="btn ghost sm" id="o-back" style="margin-top:14px">Back</button>
    ${dots(3)}</div>`;
}

function wireOnboarding() {
  const next = document.getElementById('o-next');
  if (next) next.onclick = () => { ONB++; paintOnboarding(); };
  const back = document.getElementById('o-back');
  if (back) back.onclick = () => { ONB = Math.max(0, ONB-1); paintOnboarding(); };
  const skip = document.getElementById('o-skip');
  if (skip) skip.onclick = finishOnboarding;
  const later = document.getElementById('o-later');
  if (later) later.onclick = finishOnboarding;
  const done = document.getElementById('o-done');
  if (done) done.onclick = finishOnboarding;

  const be = document.getElementById('o-be');
  if (be) be.onchange = () => { document.getElementById('o-mf').hidden = be.value !== 'builtin'; };
  const apply = document.getElementById('o-apply');
  if (apply) apply.onclick = async () => { apply.disabled = true;
    const r = await api().set_engine(be.value, (document.getElementById('o-mdl')||{}).value||'small', '');
    if (r.error) toast(r.error); else { S = r; paintOnboarding(); } };

  const add = document.getElementById('o-add');
  if (add) add.onclick = () => openDocFlow('class');

  const extprep = document.getElementById('o-extprep');
  if (extprep) extprep.onclick = async ()=>{ extprep.disabled=true;
    const st=document.getElementById('o-extstatus'); if(st) st.innerHTML='<span class="spin"></span> Copying files…';
    const r=await api().prepare_extension();
    if(r.error){ if(st) st.textContent=r.error; } else { S=await api().state(); paintOnboarding(false); }
  };
  const extopen = document.getElementById('o-extopen');
  if (extopen) extopen.onclick = ()=> api().open_extension_folder();
  document.querySelectorAll('[data-obrowser]').forEach(b=> b.onclick = ()=> api().open_browser_extensions_page(b.dataset.obrowser));
}

async function finishOnboarding() {
  const r = await api().finish_onboarding();
  if (r && !r.error) { S = r; TAB = 'home'; paint(); }
}

// ---- Home / study session ----
function paintHome() {
  const m = $('#main'); const sess = S.session;
  if (sess) {
    m.innerHTML = `<div class="wrap">${permBanner()}${engineBanner()}
      <div class="card cc cc-${sess.color || 'lav'}">
        <div class="sess-grid">
          <div><div class="small muted">Guarding now</div>
            <h1>${h(sess.class)}${sess.assignment ? ' <span class="muted" style="font-weight:400">/ '+h(sess.assignment)+'</span>' : ''}</h1>
            <div class="mt"><span class="tag ${sess.policy}">${h(S.policy_labels[sess.policy])}</span></div></div>
          <div class="timer-wrap"><div class="timer-lab">Locked in for</div><div class="timer" id="sessTimer">${fmtDur(sess.elapsed||0)}</div></div>
          <div class="timer-wrap"><div class="timer-lab">Today</div><div class="figure">${S.stats.today}</div><div class="small muted">${S.stats.flagged} flagged · ${S.stats.overridden} overridden</div></div>
        </div>
        <div class="btnrow mt" style="margin-top:20px"><button class="btn ghost" id="end">End session</button></div>
      </div>
      <p class="small muted center">Use your AI apps and sites as normal. Each message is checked the moment before it sends.</p></div>`;
    startTimerTick(sess.started || (Date.now()/1000 - (sess.elapsed||0)));
    $('#end').onclick = async () => { const pin = await askPin('Enter the PIN to end this session.'); if (pin === null) return;
      const r = await api().end_session(pin || ''); if (r.error) toast(r.error); else refresh(); };
    return;
  }
  const TUTOR = S.tutor_mode, ALL = [TUTOR, ...S.classes];
  let selC = (S.classes[0] || TUTOR).id, selA = '';
  m.innerHTML = `<div class="wrap sess">${permBanner()}${engineBanner()}
    <div class="sess-hero"><div><h1>Start a study session</h1>
      <p class="sub" style="margin:6px 0 0">Pick what you're working on. The guard stays idle until you do.</p></div></div>
    <div class="step"><span class="n">1</span>Which class?</div>
    <div class="classgrid" id="cg"></div>
    <div id="asgstep"><div class="step"><span class="n">2</span>Which assignment?</div>
    <div class="seg" id="ag"></div></div>
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
  paintPicks();
  $('#go').onclick = async () => { const r = await api().start_session(selC, selA, 'warn');
    if (r.error) toast(r.error); else { TAB = 'home'; refresh(); } };
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
const COLORS = ['lav', 'mint', 'sun', 'sky', 'rose', 'peach', 'sage', 'sand'];
let LOGPAGE = 1, LOGKIND = 'all';
async function paintLog() {
  const m = $('#main');
  m.innerHTML = `<div class="wrap"><div class="row" style="align-items:center">
    <div style="flex:2"><h1>Activity</h1><p class="sub">Everything the guard has checked. Stored only on this Mac.</p></div>
    <div style="flex:1;text-align:right"><div class="btnrow" style="justify-content:flex-end">
      <button class="btn ghost sm" id="exp">Export report</button><button class="btn danger sm" id="clr">Clear</button></div></div></div>
    <div class="filters" id="logfilters"></div>
    <div class="card" id="loglist"><p class="muted">Loading…</p></div></div>`;
  const pg = await api().get_log_page(LOGPAGE, 25, LOGKIND);
  LOGPAGE = pg.page;
  const rows = pg.rows.map(e => {
    const when = new Date(e.t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    if (e.event) return `<div class="logline"><span class="when">${when}</span><div class="txt muted">— ${h(e.event)}: ${h(e.class||'')} ${h(e.assignment||'')}</div></div>`;
    const over = e.result === 'sent anyway' || e.result === 'sent after warning';
    const ok = e.result.startsWith('ok'), warned = !over && !ok;
    const label = { 'ok': 'Clean', 'ok (disclose)': 'Clean · disclose AI use', 'ok (revised)': 'Clean', 'warned': 'Flagged', 'blocked': 'Flagged', 'sent anyway': 'Overridden', 'sent after warning': 'Overridden' }[e.result] || e.result;
    return `<div class="logline"><span class="when">${when}</span><span class="dot ${ok?'':over?'bad':'warn'}"></span>
      <div class="txt"><b>${h(label)}</b> · ${h(e.where||'')} · ${h(e.class||'')} ${e.assignment?'/ '+h(e.assignment):''}
      ${e.source?`<span class="small muted">(${e.source==='ai'?'AI':'keywords'})</span>`:''}
      <div class="q small">“${h(e.text||'')}”</div>${e.reasons?`<div class="small muted">${e.reasons.map(h).join(' ')}</div>`:''}</div></div>`;
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
  $('#exp').onclick = async () => { const p = await api().export_log(); if (p) toast('Saved to ' + p.split('/').pop()); };
  $('#clr').onclick = async () => { const pin = await askPin('Enter the PIN to clear the log.'); if (pin === null) return;
    const r = await api().clear_log(pin || ''); if (r && r.error) toast(r.error); else { LOGPAGE = 1; paintLog(); } };
}

// ---- Community (placeholder for the future) ----
function paintCommunity() {
  const m = $('#main');
  m.innerHTML = `<div class="wrap">
    <div class="comm-hero">
      <div class="onb-seal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M16 5.2a3.2 3.2 0 0 1 0 5.6"/><path d="M17.5 14.3A5.5 5.5 0 0 1 20.5 19"/></svg></div>
      <h1>Community</h1>
      <p class="onb-lead">A place to walk this out together. This is where HonestHands is headed next — you'll be able to pair up with an accountability partner, share your integrity record, and encourage each other to keep using AI the honest way.</p>
    </div>
    <div class="comm-grid">
      <div class="comm-card"><div class="soon">Coming soon</div><h2>Accountability partners</h2><p class="small muted">Invite a friend, parent, or mentor. They get a simple weekly summary of your sessions and any overrides.</p></div>
      <div class="comm-card"><div class="soon">Coming soon</div><h2>Tamper alerts</h2><p class="small muted">If the guard is turned off or stops running, your partner is notified — so the commitment stays real.</p></div>
      <div class="comm-card"><div class="soon">Coming soon</div><h2>Groups</h2><p class="small muted">Study groups and classes can set shared standards and cheer each other on.</p></div>
      <div class="comm-card"><div class="soon">Idea</div><h2>Streaks &amp; encouragement</h2><p class="small muted">Gentle streaks for honest work — celebrating the habit, not shaming the slip.</p></div>
    </div>
    <p class="small muted center mt">Have an idea for this space? It's being built with students like you in mind.</p>
  </div>`;
}

// ---- Settings ----
function paintSettings() {
  const m = $('#main'); const e = S.engine;
  const modelOpts = Object.entries(e.models).map(([k,v]) => `<option value="${k}" ${e.model===k?'selected':''}>${h(v)}</option>`).join('');
  m.innerHTML = `<div class="wrap"><h1>Settings</h1>
    <div class="card"><h2>The AI guard</h2><p class="sub">Who decides whether a message is OK.</p>
      <div class="field"><label>Guard</label><select id="be">
        <option value="builtin" ${e.backend==='builtin'?'selected':''}>Built-in AI — runs on this Mac, private, one-time download</option>
        <option value="ollama" ${e.backend==='ollama'?'selected':''}>Ollama — if you already use it</option>
        <option value="keywords" ${e.backend==='keywords'?'selected':''}>Keyword rules only — no AI, no download</option>
      </select></div>
      <div class="field" id="mf" ${e.backend==='builtin'?'':'hidden'}><label>Model size</label><select id="mdl">${modelOpts}</select></div>
      <div class="field" id="of" ${e.backend==='ollama'?'':'hidden'}><label>Ollama model name</label><input id="om" value="${h(e.ollama_model)}"></div>
      <div class="btnrow"><button class="btn" id="apply">Apply</button>
        <span class="small ${e.ready?'':'muted'}" id="est">${e.ready?'Ready.':h(e.message||'')}</span></div>
      <div id="eprog"></div>
    </div>
    <div class="card"><h2>Browser extension</h2>
      <p class="sub">For AI <b>websites</b> (Gemini, ChatGPT, Claude, and more), a small companion extension catches sends the Mac can't see on its own. It does nothing unless HonestHands is running and a session is active. Desktop AI apps are covered without it.</p>
      <div id="extBody"></div>
    </div>
    <div class="card"><h2>Accountability PIN</h2>
      <p class="sub">A friend or parent sets this. Then ending a session, deleting a class, or clearing the log needs it.</p>
      <div class="row">${S.has_pin?'<div class="field"><label>Current PIN</label><input type="password" id="op" inputmode="numeric"></div>':''}
        <div class="field"><label>${S.has_pin?'New PIN':'Set a PIN'}</label><input type="password" id="np" inputmode="numeric"></div></div>
      <div class="btnrow"><button class="btn ghost" id="pinbtn">${S.has_pin?'Change PIN':'Set PIN'}</button>
        ${S.has_pin?'<button class="btn danger" id="pinrm">Remove PIN</button>':''}</div>
      ${S.has_pin?'<p class="small muted mt">To remove it, type the current PIN above, then press Remove PIN.</p>':''}</div>
    <div class="card"><h2>This Mac</h2>
      <div class="btnrow"><button class="btn ghost sm" id="acc">Accessibility settings</button>
        <button class="btn ghost sm" id="data">Open data folder</button></div>
      <p class="small muted mt">Permission: ${S.perms.accessibility ? 'granted' : 'not granted'} · Guard ${S.perms.watching ? 'active' : 'inactive'}</p></div>
    </div>`;
  // extension section
  (function(){
    const ext = S.extension || {browsers:[], installed_dir:''};
    const box = document.getElementById('extBody');
    if(!box) return;
    const browsers = ext.browsers||[];
    let html = '';
    html += `<div class="btnrow" style="margin-bottom:10px">
      <button class="btn" id="extPrep">${ext.installed_dir?'Re-copy extension files':'Set up the extension'}</button>
      ${ext.installed_dir?'<button class="btn ghost" id="extOpen">Open extension folder</button>':''}
    </div>`;
    if(ext.installed_dir){
      html += `<p class="small muted">Extension files are ready at:<br><code>${h(ext.installed_dir)}</code></p>`;
      html += `<div class="step-note mt"><b>One-time enable (per browser):</b>
        <ol class="small" style="margin:8px 0 0 18px;line-height:1.7">
          <li>Open your browser's Extensions page ${browsers.length?'('+browsers.map(h).join(', ')+' detected)':''}</li>
          <li>Turn on <b>Developer mode</b> (top-right)</li>
          <li>Click <b>Load unpacked</b> and choose the folder above</li>
        </ol></div>`;
      html += `<div class="btnrow mt">` + browsers.filter(b=>['Google Chrome','Microsoft Edge','Brave'].includes(b))
        .map(b=>`<button class="btn ghost sm" data-extbrowser="${h(b)}">Open ${h(b)} extensions</button>`).join('') + `</div>`;
      html += `<p class="small muted mt">Chrome requires this one manual enable — no app can fully auto-install to a personal browser. After enabling once, it stays on.</p>`;
    } else {
      html += `<p class="small muted">Click “Set up the extension” to place the files, then enable it in your browser.</p>`;
    }
    box.innerHTML = html;
    const prep = document.getElementById('extPrep');
    if(prep) prep.onclick = async ()=>{ prep.disabled=true; const r=await api().prepare_extension();
      if(r.error) toast(r.error); else { toast('Extension files ready.'); S=await api().state(); paint(); } };
    const open = document.getElementById('extOpen');
    if(open) open.onclick = ()=> api().open_extension_folder();
    box.querySelectorAll('[data-extbrowser]').forEach(b=> b.onclick = ()=> api().open_browser_extensions_page(b.dataset.extbrowser));
  })();

  $('#be').onchange = () => { const v = $('#be').value; $('#mf').hidden = v !== 'builtin'; $('#of').hidden = v !== 'ollama'; };
  $('#apply').onclick = async () => { $('#apply').disabled = true;
    const r = await api().set_engine($('#be').value, $('#mdl').value, $('#om')?.value || '');
    if (r.error) toast(r.error); else { S = r; toast('Applied. Preparing…'); paint(); } };
  if ($('#pinrm')) $('#pinrm').onclick = async () => { const r = await api().remove_pin($('#op').value || '');
    if (r.error) toast(r.error); else { S = r; toast('PIN removed.'); paint(); } };
  $('#pinbtn').onclick = async () => { const r = await api().set_pin($('#op')?.value || '', $('#np').value);
    if (r.error) toast(r.error); else { S = r; toast('PIN updated.'); paint(); } };
  $('#acc').onclick = () => api().open_accessibility_settings();
  $('#data').onclick = () => api().open_data_folder();
}

// ---- boot + live polling for engine/session changes ----
window.addEventListener('pywebviewready', async () => {
  await refresh();
  setInterval(async () => {
    try { const sessSig = x => x ? [x.class_id,x.assignment_id,x.started].join(',') : '';
      const prev = JSON.stringify(S.engine) + S.perms.watching + S.ext_live + sessSig(S.session);
      const ns = await api().state();
      if (!ns.onboarded) {
        S = ns;
        if (onbStructSig() !== lastOnbSig) paintOnboarding(false);  // real change: rebuild, no animation
        else updateOnbStatus();                                    // just progress ticking: update in place
        return;
      }
      if (JSON.stringify(ns.engine) + ns.perms.watching + ns.ext_live + sessSig(ns.session) !== prev) { S = ns; paint(); }
      else { S = ns; if (TAB==='settings' && S.engine.progress){ const e=S.engine, pct=e.progress.total?Math.round(100*e.progress.done/e.progress.total):0;
        const box=$('#eprog'); if(box) box.innerHTML=`<div class="progress"><div style="width:${pct}%"></div></div><div class="small">${h(e.progress.label)}: ${pct}%</div>`; } }
    } catch (_) {}
  }, 1500);
});
