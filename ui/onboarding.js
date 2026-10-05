// First-run setup: a guided, full-size walkthrough. Loaded before app.js; uses its globals (S, api, h, toast, openDocFlow, paint, TAB).
// Steps: welcome -> permissions -> the built-in AI -> browser extension -> account (optional) -> first class.

let ONB = 0;
let lastOnbSig = '';
const ONB_FLAGS = { notifTried: false, notifOk: false, aiStarted: false, extPrepared: false };
const ONB_STEPS = ['Welcome', 'Access', 'AI', 'Browser', 'Account', 'Class'];

const OICO = {
  hand: '<path d="M8 11V5.5a1.3 1.3 0 0 1 2.6 0V10"/><path d="M10.6 10V4.4a1.3 1.3 0 0 1 2.6 0V10"/><path d="M13.2 10.2V5.4a1.3 1.3 0 0 1 2.6 0V12"/><path d="M15.8 12V8.6a1.3 1.3 0 0 1 2.5 0c0 3.2.1 4.4-.6 6.3-.8 2.2-2.4 3.6-4.8 3.6-2 0-3.2-.5-4.4-1.9l-2.7-3.2a1.35 1.35 0 0 1 1.9-1.9L7 11"/><circle cx="12.4" cy="14.6" r="1.35" fill="#8B5B7E" stroke="none"/>',
  shield: '<path d="M12 3l7 3v5c0 5-3.5 8-7 10-3.5-2-7-5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2.5"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  people: '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M16 5.2a3.2 3.2 0 0 1 0 5.6"/><path d="M17.5 14.3A5.5 5.5 0 0 1 20.5 19"/>',
  book: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H18a2 2 0 0 1 2 2v13H6a2 2 0 0 0-2 2z"/><path d="M8 4v12"/>',
  bell: '<path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
};
const oicon = (k, cls = '') => `<svg class="oi ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${OICO[k]}</svg>`;
const CHECK = '<svg class="ocheck" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

function onbStructSig() {
  const e = S.engine, p = S.perms || {};
  return [ONB, S.classes.length, e.state, e.ready, p.accessibility, p.watching, S.ext_live, ONB_FLAGS.notifTried, ONB_FLAGS.notifOk,
          !!(S.extension && S.extension.installed_dir), S.browser && S.browser.chosen, S.cloud_user && S.cloud_user.signed_in].join('|');
}

function onbProgress(i) {
  return ONB_STEPS.map((n, k) => `<div class="ostep ${k < i ? 'past' : ''} ${k === i ? 'now' : ''}" title="${n}"><i></i></div>`).join('');
}
const words = (t) => t.split(' ').map((w, k) => `<span class="ow" style="--w:${k}"><span>${w}</span></span>`).join(' ');
const OBG = ['lilac', 'mint', 'sky', 'sand', 'rose', 'olive'];
const OART_KEY = ['welcome', 'access', 'ai', 'browser', 'account', 'klass'];
const arrow = '<svg class="oarr" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
// one screen: a pastel page, an illustration, a bold title, a short line, the step's own controls, then the big button and a skip link
function ostage({ title, sub, body = '', next = '', skip = '', art, small = false }) {
  return `<div class="ostg">
    <div class="oartbox ${small ? 'sm' : ''}">${oartHTML(art)}</div>
    <h1 class="otitle3">${words(title)}</h1>
    <p class="osub orise" style="--i:3">${sub}</p>
    ${body ? `<div class="obody orise" style="--i:4">${body}</div>` : ''}
    <div class="octa orise" style="--i:5">${next}${skip}</div>
  </div>`;
}
const nextBtn = (label, id = 'o-next', dis = false) => `<button class="obtn" id="${id}" ${dis ? 'disabled' : ''}><span>${label}</span>${arrow}</button>`;
const skipLnk = (label, id) => `<a href="#" class="oskip3" id="${id}">${label}</a>`;

// ---------------------------------------------------------------- the steps
function stepWelcome() {
  return ostage({ art: 'welcome', title: 'Welcome to HonestHands',
    sub: 'It checks what you’re about to send to an AI against your class’s own rules and warns you first, so AI stays a tutor and not a shortcut.',
    body: `<div class="otrio3"><div><b>Private</b><span>The AI runs on your Mac</span></div><div><b>Honest</b><span>Send anyway; it’s just recorded</span></div><div><b>Together</b><span>A friend can cheer you on</span></div></div>
      <p class="overse3">“…doing honest work with his own hands.” <span>Ephesians 4:28</span></p>`,
    next: nextBtn('Let’s set it up') });
}

function stepAccess() {
  const p = S.perms || {};
  const acc = !!p.accessibility, notif = ONB_FLAGS.notifOk;
  const body = `
    <div class="orow ${acc ? 'done' : ''}">
      <span class="orow-i">${acc ? CHECK : oicon('lock')}</span>
      <div class="orow-t"><b>Accessibility <em>required</em></b><span>Lets the guard see what you type and hold the send.</span></div>
      ${acc ? `<span class="ostatus ok">${p.watching ? 'Guard on' : 'Granted'}</span>` : '<button class="osm" id="o-acc">Grant</button>'}
    </div>
    ${acc ? '' : `<ol class="ohow"><li>Click <b>Grant</b>. System Settings opens.</li><li>Switch on <b>HonestHands</b> (or <b>Terminal</b> if you run it from there).</li><li>Come back. This page notices by itself.</li></ol>`}
    <div class="orow ${notif ? 'done' : ''}">
      <span class="orow-i">${notif ? CHECK : oicon('bell')}</span>
      <div class="orow-t"><b>Notifications <em class="opt">optional</em></b><span>Quiet alerts, like when a friend’s prompt is flagged.</span></div>
      ${notif ? '<span class="ostatus ok">Working</span>'
              : ONB_FLAGS.notifTried ? '<div class="obtns"><button class="osm" id="o-notif-yes">I saw it</button><button class="osm ghost" id="o-notif-no">No</button></div>'
                                     : '<button class="osm ghost" id="o-notif">Test</button>'}
    </div>
    ${ONB_FLAGS.notifTried && !notif ? '<p class="onote">Didn’t see it? Turn on notifications for <b>Script Editor</b>. <a href="#" id="o-notif-open">Open settings</a></p>' : ''}`;
  return ostage({ art: 'access', title: 'Let it watch for sends',
    sub: 'macOS needs your OK first. This is what lets the guard read a message and pause it for a check.', body,
    next: nextBtn(acc ? 'Next' : 'Continue anyway') });
}

function aiStatusHTML() {
  const e = S.engine;
  if (e.ready) return `<div class="oready">${CHECK}<div><b>The AI is ready</b><span>Running privately on your Mac.</span></div></div>`;
  if (e.state === 'downloading' || e.state === 'starting') {
    const pr = e.progress, pct = pr && pr.total ? Math.round(100 * pr.done / pr.total) : 0;
    const gb = pr && pr.total ? `${(pr.done / 1e9).toFixed(2)} of ${(pr.total / 1e9).toFixed(1)} GB` : (e.message || 'Starting…');
    return `<div class="obig"><div class="opct">${e.state === 'starting' ? '<span class="spin big"></span>' : `<b id="o-pct">${pct}</b><small>%</small>`}</div>
      <div class="obar"><i id="o-fill" style="width:${e.state === 'starting' ? 100 : pct}%"></i></div>
      <div class="osmall" id="o-gb">${e.state === 'starting' ? 'Loading the AI…' : gb}</div></div>`;
  }
  if (e.state === 'error') return `<div class="oerr"><b>That didn’t work.</b><span>${h(e.message)}</span><button class="osm" id="o-ai-go">Try again</button></div>`;
  return `<div class="oerr calm"><span>${h(e.message || 'The AI needs a one-time download.')}</span><button class="osm" id="o-ai-go">Download (${e.size_gb} GB)</button></div>`;
}
const aiKind = () => { const e = S.engine; return e.ready ? 'ready' : (e.state === 'downloading' || e.state === 'starting') ? e.state : e.state === 'error' ? 'error' : 'idle'; };
function stepAI() {
  const e = S.engine;
  return ostage({ art: 'ai', title: 'Your built-in AI guard',
    sub: `A one-time ${e.size_gb} GB download. It runs entirely on this Mac, so nothing you type is ever sent to a server.`,
    body: `<div class="oai" id="o-ai" data-kind="${aiKind()}">${aiStatusHTML()}</div><p class="onote c">You can keep going while it downloads.</p>`,
    next: nextBtn('Next') });
}

function stepBrowser() {
  const chosen = S.browser && S.browser.chosen;
  return ostage({ art: 'browser', small: !!chosen, title: 'Pick your browser',
    sub: 'Gemini and ChatGPT hide their send button from your Mac, so a tiny extension covers the gap. Choose the one browser you’ll use for AI.',
    body: `<div id="o-brpanel">${browserPanelHTML()}</div>`,
    next: nextBtn('Next', 'o-next', !chosen), skip: skipLnk('Skip for now', 'o-skipbrowser') });
}

function stepAccount() {
  const on = S.cloud_user && S.cloud_user.signed_in;
  const body = `<div class="otrio3 two"><div><b>They can see</b><span>Prompts you sent despite a warning, session times, daily counts</span></div>
      <div><b>They never see</b><span>Syllabi, assignments, or clean and flagged messages</span></div></div>
    ${on ? `<div class="oready">${CHECK}<div><b>You’re signed in</b><span>Invite someone from the Community tab.</span></div></div>` : ''}`;
  return ostage({ art: 'account', title: 'Walk this out together',
    sub: 'Pair up with a friend, parent or mentor so they can see when you lock in. It’s optional, and you can do it any time.', body,
    next: on ? nextBtn('Next') : nextBtn('Set up an account', 'o-acct-now'),
    skip: on ? '' : skipLnk('Maybe later', 'o-next') });
}

function stepClass() {
  const has = S.classes.length > 0;
  const body = has ? `<div class="oready">${CHECK}<div><b>${h(S.classes[0].name)} added${S.classes.length > 1 ? ` and ${S.classes.length - 1} more` : ''}</b><span>Add more or edit any time in Classes.</span></div></div>` : '';
  return ostage({ art: 'klass', title: 'Add your first class',
    sub: 'Give it a syllabus (PDF, Word, or pasted text). It pulls out the AI rules word for word, and the guard uses them for every message.', body,
    next: has ? nextBtn('Finish', 'o-done') : nextBtn('Add a class', 'o-add'),
    skip: has ? skipLnk('Add another', 'o-add') : skipLnk('Finish without a class', 'o-done') });
}

// ---------------------------------------------------------------- paint + wiring
let ONB_DIR = 1;      // 1 = moving forward, -1 = back: which way the page slides in
function paintOnboarding(animate = true) {
  const m = document.getElementById('main');
  const steps = [stepWelcome, stepAccess, stepAI, stepBrowser, stepAccount, stepClass];
  ONB = Math.min(ONB, steps.length - 1);
  const surf = document.getElementById('surface'); if (surf) surf.classList.add('onbing');
  const keep = m.querySelector('.onb3');
  const scroll = keep && !animate ? keep.scrollTop : 0;
  m.innerHTML = `<div class="onb3 bg-${OBG[ONB]} ${animate ? (ONB_DIR > 0 ? 'go-fwd' : 'go-back') : 'still'}">
    <div class="otop">${ONB > 0 ? '<button class="oback" id="o-back" aria-label="Back"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg></button>' : '<span class="oback ph"></span>'}
      <div class="obars">${onbProgress(ONB)}</div><span class="ocount">${ONB + 1}/${steps.length}</span></div>
    <div class="oscroll">${steps[ONB]()}</div></div>`;
  m.classList.remove('enter');
  const root = m.firstElementChild;
  if (scroll) root.querySelector('.oscroll').scrollTop = scroll;
  if (animate) inkArt(root.querySelector('.oart'));
  oartParallax(root.querySelector('.oart-wrap'));
  wireOnboarding();
  lastOnbSig = onbStructSig();
  // arriving at the AI step starts the download for you
  if (ONB === 2 && !ONB_FLAGS.aiStarted && !S.engine.ready && S.engine.state !== 'downloading' && S.engine.state !== 'starting') {
    ONB_FLAGS.aiStarted = true;
    api().setup_ai().then(r => { if (r && !r.error) { S = r; if (ONB === 2) updateOnbStatus(); } });
  }
  // a small celebration when a checkmark first lands
  const doneNow = document.querySelectorAll('.orow.done .ocheck, .oready .ocheck');
  if (doneNow.length && !animate) setTimeout(() => oconfettiAt(doneNow[doneNow.length - 1], 14, .6), 250);
}

// progress ticking: update in place so nothing flickers
function updateOnbStatus() {
  const box = document.getElementById('o-ai');
  if (!box) return;
  const kind = aiKind();
  if (box.dataset.kind === kind && (kind === 'downloading') && document.getElementById('o-pct')) {
    const pr = S.engine.progress, pct = pr && pr.total ? Math.round(100 * pr.done / pr.total) : 0;
    otween(document.getElementById('o-pct'), pct, 1200);
    document.getElementById('o-fill').style.width = pct + '%';
    const gb = document.getElementById('o-gb'); if (gb && pr && pr.total) gb.textContent = `${(pr.done / 1e9).toFixed(2)} of ${(pr.total / 1e9).toFixed(1)} GB`;
    return;
  }
  const was = box.dataset.kind;
  box.dataset.kind = kind;
  box.innerHTML = aiStatusHTML();
  const go = document.getElementById('o-ai-go'); if (go) go.onclick = startAI;
  if (kind === 'ready' && was !== 'ready') setTimeout(() => oconfettiAt(box.querySelector('.ocheck'), 30, 1), 300);
}
async function startAI() {
  const r = await api().setup_ai();
  if (r && !r.error) { S = r; updateOnbStatus(); }
}

function oripple(btn, e) {
  if (OART_REDUCED()) return;
  const r = btn.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2, i = document.createElement('i');
  i.className = 'orip'; i.style.cssText = `width:${d}px;height:${d}px;left:${(e.clientX || r.left + r.width / 2) - r.left - d / 2}px;top:${(e.clientY || r.top + r.height / 2) - r.top - d / 2}px`;
  btn.appendChild(i); setTimeout(() => i.remove(), 700);
}

function wireOnboarding() {
  const $$ = (id) => document.getElementById(id);
  const on = (id, fn) => { const n = $$(id); if (n) n.onclick = (e) => { if (e && e.preventDefault && n.tagName === 'A') e.preventDefault(); if (n.classList.contains('obtn')) oripple(n, e); fn(e); }; };
  const go = (d) => { ONB_DIR = d; ONB = Math.max(0, ONB + d); const r = document.querySelector('.onb3'); 
    if (r && !OART_REDUCED()) { r.classList.add('bye'); setTimeout(() => paintOnboarding(), 170); } else paintOnboarding(); };
  on('o-next', () => go(1));
  on('o-back', () => go(-1));
  on('o-skipbrowser', () => go(1));
  on('o-done', finishOnboarding);
  on('o-add', () => openDocFlow('class'));
  on('o-ai-go', startAI);

  on('o-acc', async () => { await api().request_accessibility(); toast('Switch HonestHands on in System Settings. This page updates by itself.'); });
  on('o-notif', async () => { await api().test_notification(); ONB_FLAGS.notifTried = true; paintOnboarding(false); });
  on('o-notif-yes', () => { ONB_FLAGS.notifOk = true; paintOnboarding(false); });
  on('o-notif-no', async () => { await api().open_notification_settings(); });
  on('o-notif-open', async () => { await api().open_notification_settings(); });

  const bp = document.getElementById('o-brpanel');
  if (bp) wireBrowserPanel(bp, () => paintOnboarding(false));

  on('o-acct-now', async () => { await api().finish_onboarding(); const r = await api().state(); S = r; TAB = 'community'; paint(); });
}

async function finishOnboarding() {
  const r = await api().finish_onboarding();
  if (!r || r.error) return;
  S = r;
  const veil = document.createElement('div');                       // a short, warm finish instead of an abrupt jump
  veil.className = 'ofinish';
  veil.innerHTML = `<div class="ofin-card">${oartHTML('finish', 'big')}<h1>You’re all set</h1><p>HonestHands is ready to guard. Start a study session whenever you sit down to work.</p></div>`;
  document.body.appendChild(veil);
  inkArt(veil.querySelector('.oart'));
  setTimeout(() => oconfetti(window.innerWidth / 2, window.innerHeight * .38, 46, 1.6), 500);
  setTimeout(() => oconfetti(window.innerWidth * .3, window.innerHeight * .5, 22, 1.1), 900);
  setTimeout(() => oconfetti(window.innerWidth * .7, window.innerHeight * .5, 22, 1.1), 1100);
  setTimeout(() => { TAB = 'home'; paint(); veil.classList.add('out'); setTimeout(() => veil.remove(), 600); }, 2600);
}
