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
  return `<div class="oprog">${ONB_STEPS.map((n, k) => `<div class="ostep ${k < i ? 'past' : ''} ${k === i ? 'now' : ''}"><i></i><span>${n}</span></div>`).join('')}</div>`;
}
const onbNav = (back, nextLabel, nextId = 'o-next', extra = '') =>
  `<div class="onav">${back ? '<button class="btn ghost big" id="o-back">Back</button>' : '<span></span>'}<div class="onav-r">${extra}<button class="btn big" id="${nextId}">${nextLabel}</button></div></div>`;

// ---------------------------------------------------------------- the steps
function stepWelcome() {
  return `<section class="ocard hero rise">
    <div class="oicon big">${oicon('hand')}</div>
    <h1 class="otitle xl">Welcome to HonestHands</h1>
    <p class="overse">“Let the thief no longer steal, but rather let him labor, doing honest work with his own hands, so that he may have something to share with anyone in need.”<br><span class="ref">Ephesians 4:28</span></p>
    <p class="olead">HonestHands checks what you’re about to send to an AI against your class’s own rules and warns you first, so AI stays a tutor and not a shortcut.</p>
    <div class="otrio">
      <div><b>Private</b><span>The AI runs on your Mac. What you type never leaves it.</span></div>
      <div><b>Honest</b><span>You can always send anyway. It’s just recorded.</span></div>
      <div><b>Together</b><span>Optionally pair up with a friend who keeps you accountable.</span></div>
    </div>
    <p class="osmall">Setup takes about three minutes.</p>
    <div class="onav center"><button class="btn big xl" id="o-next">Let’s set it up</button></div>
  </section>`;
}

function stepAccess() {
  const p = S.perms || {};
  const acc = !!p.accessibility;
  const notif = ONB_FLAGS.notifOk;
  return `<section class="ocard rise">
    <div class="oicon">${oicon('shield')}</div>
    <h1 class="otitle">Let HonestHands watch for sends</h1>
    <p class="olead">macOS asks you to approve a couple of things first. This is what lets the guard read a message and hold it for a check before it goes out.</p>

    <div class="oitem ${acc ? 'done' : ''}">
      <span class="oitem-i">${acc ? CHECK : oicon('lock')}</span>
      <div class="oitem-t"><b>Accessibility <em>required</em></b><span>Lets the guard see what you’re typing in an AI app or site, and hold the send for a moment.</span></div>
      ${acc ? `<span class="ostatus ok">${p.watching ? 'Granted · guard is on' : 'Granted'}</span>` : '<button class="btn" id="o-acc">Grant access</button>'}
    </div>
    ${acc ? '' : `<ol class="osteps"><li>Click <b>Grant access</b>. System Settings opens.</li><li>Switch on <b>HonestHands</b> in the list (if you’re running it from Terminal, switch on <b>Terminal</b> instead).</li><li>Come back here. This page notices by itself.</li></ol>`}

    <div class="oitem ${notif ? 'done' : ''}">
      <span class="oitem-i">${notif ? CHECK : oicon('bell')}</span>
      <div class="oitem-t"><b>Notifications <em class="opt">optional</em></b><span>Quiet alerts, like when a friend you watch sends something despite a warning.</span></div>
      ${notif ? '<span class="ostatus ok">Working</span>'
              : ONB_FLAGS.notifTried ? '<div class="obtns"><button class="btn sm" id="o-notif-yes">Yes, I saw it</button><button class="btn ghost sm" id="o-notif-no">No</button></div>'
                                     : '<button class="btn ghost" id="o-notif">Send a test</button>'}
    </div>
    ${ONB_FLAGS.notifTried && !notif ? '<p class="osmall left">Didn’t see anything? Turn on notifications for <b>Script Editor</b> (macOS shows alerts under that name). <a href="#" id="o-notif-open">Open notification settings</a></p>' : ''}
    ${onbNav(true, acc ? 'Continue' : 'Continue anyway', 'o-next')}
  </section>`;
}

function aiStatusHTML() {
  const e = S.engine;
  if (e.ready) return `<div class="oready">${CHECK}<div><b>The AI is ready</b><span>Running privately on your Mac.</span></div></div>`;
  if (e.state === 'downloading' || e.state === 'starting') {
    const pr = e.progress, pct = pr && pr.total ? Math.round(100 * pr.done / pr.total) : 0;
    const gb = pr && pr.total ? `${(pr.done / 1e9).toFixed(2)} of ${(pr.total / 1e9).toFixed(1)} GB` : (e.message || 'Starting…');
    return `<div class="obig"><div class="opct">${e.state === 'starting' ? '<span class="spin big"></span>' : pct + '<small>%</small>'}</div>
      <div class="obar"><i style="width:${e.state === 'starting' ? 100 : pct}%"></i></div>
      <div class="osmall">${e.state === 'starting' ? 'Loading the AI…' : gb}</div></div>`;
  }
  if (e.state === 'error') return `<div class="oerr"><b>That didn’t work.</b><span>${h(e.message)}</span><button class="btn" id="o-ai-go">Try again</button></div>`;
  return `<div class="oerr calm"><span>${h(e.message || 'The AI needs a one-time download.')}</span><button class="btn" id="o-ai-go">Download the AI (${e.size_gb} GB)</button></div>`;
}
function stepAI() {
  const e = S.engine;
  return `<section class="ocard rise">
    <div class="oicon">${oicon('chip')}</div>
    <h1 class="otitle">Your built-in AI guard</h1>
    <p class="olead">The AI reads each message against your class rules. It’s a one-time ${e.size_gb} GB download and it runs entirely on this Mac. Nothing you type is ever sent to a server.</p>
    <div class="oai" id="o-ai">${aiStatusHTML()}</div>
    <p class="osmall">You can keep going while it downloads. It finishes in the background.</p>
    ${onbNav(true, 'Continue')}
  </section>`;
}

function stepBrowser() {
  const chosen = S.browser && S.browser.chosen;
  return `<section class="ocard rise">
    <div class="oicon">${oicon('globe')}</div>
    <h1 class="otitle">Pick your browser</h1>
    <p class="olead">Sites like Gemini and ChatGPT hide their send button from your Mac, so a tiny extension covers the gap. Choose the one browser you’ll use for AI while you study.</p>
    <div id="o-brpanel">${browserPanelHTML()}</div>
    <div class="onav"><button class="btn ghost big" id="o-back">Back</button><div class="onav-r"><a href="#" class="oskip" id="o-skipbrowser">Skip for now</a><button class="btn big" id="o-next" ${chosen ? '' : 'disabled'}>Continue</button></div></div>
  </section>`;
}

function stepAccount() {
  const on = S.cloud_user && S.cloud_user.signed_in;
  return `<section class="ocard rise">
    <div class="oicon">${oicon('people')}</div>
    <h1 class="otitle">Walk this out together</h1>
    <p class="olead">An account lets you pair up with a friend, parent or mentor. They see when you lock in and any prompt you send despite a warning. It’s optional, and you can do it any time from the Community tab.</p>
    <div class="otrio two">
      <div><b>They can see</b><span>Prompts you send despite a warning, your session times, and daily counts.</span></div>
      <div><b>They never see</b><span>Your syllabi, your assignments, or what you typed in clean or flagged messages.</span></div>
    </div>
    ${on ? `<div class="oready">${CHECK}<div><b>You’re signed in</b><span>Nice. You can invite someone from the Community tab.</span></div></div>` : ''}
    <div class="onav"><button class="btn ghost big" id="o-back">Back</button><div class="onav-r">
      ${on ? '' : '<button class="btn big" id="o-acct-now">Set up an account</button>'}
      <button class="btn ${on ? '' : 'ghost'} big" id="o-next">${on ? 'Continue' : 'Maybe later'}</button></div></div>
  </section>`;
}

function stepClass() {
  const has = S.classes.length > 0;
  return `<section class="ocard rise">
    <div class="oicon">${oicon('book')}</div>
    <h1 class="otitle">Add your first class</h1>
    <p class="olead">Give HonestHands a syllabus (a PDF, a Word file, or pasted text). It pulls out the rules about AI word for word, and the guard uses them for every message. Add an assignment later to make it even sharper.</p>
    ${has ? `<div class="oready">${CHECK}<div><b>${h(S.classes[0].name)} added${S.classes.length > 1 ? ` and ${S.classes.length - 1} more` : ''}</b><span>You can add more or edit these any time in Classes.</span></div></div>` : ''}
    <div class="onav"><button class="btn ghost big" id="o-back">Back</button><div class="onav-r">
      <button class="btn ${has ? 'ghost' : ''} big" id="o-add">${has ? 'Add another' : 'Add a class'}</button>
      <button class="btn ${has ? '' : 'ghost'} big" id="o-done">${has ? 'Finish' : 'Finish without a class'}</button></div></div>
  </section>`;
}

// ---------------------------------------------------------------- paint + wiring
function paintOnboarding(animate = true) {
  const m = document.getElementById('main');
  const steps = [stepWelcome, stepAccess, stepAI, stepBrowser, stepAccount, stepClass];
  ONB = Math.min(ONB, steps.length - 1);
  m.innerHTML = `<div class="wrap onb2">${ONB > 0 ? onbProgress(ONB) : ''}${steps[ONB]()}</div>`;
  if (animate) { m.classList.remove('enter'); void m.offsetWidth; m.classList.add('enter'); }
  wireOnboarding();
  lastOnbSig = onbStructSig();
  // arriving at the AI step starts the download for you
  if (ONB === 2 && !ONB_FLAGS.aiStarted && !S.engine.ready && S.engine.state !== 'downloading' && S.engine.state !== 'starting') {
    ONB_FLAGS.aiStarted = true;
    api().setup_ai().then(r => { if (r && !r.error) { S = r; if (ONB === 2) updateOnbStatus(); } });
  }
}

// progress ticking: update in place so nothing flickers
function updateOnbStatus() {
  const box = document.getElementById('o-ai');
  if (box) { box.innerHTML = aiStatusHTML(); const go = document.getElementById('o-ai-go'); if (go) go.onclick = startAI; }
}
async function startAI() {
  const r = await api().setup_ai();
  if (r && !r.error) { S = r; updateOnbStatus(); }
}

function wireOnboarding() {
  const $$ = (id) => document.getElementById(id);
  const on = (id, fn) => { const n = $$(id); if (n) n.onclick = fn; };
  on('o-next', () => { ONB++; paintOnboarding(); });
  on('o-back', () => { ONB = Math.max(0, ONB - 1); paintOnboarding(); });
  on('o-skipbrowser', (e) => { e.preventDefault(); ONB++; paintOnboarding(); });
  on('o-done', finishOnboarding);
  on('o-add', () => openDocFlow('class'));
  on('o-ai-go', startAI);

  on('o-acc', async () => { await api().request_accessibility(); toast('Switch HonestHands on in System Settings. This page updates by itself.'); });
  on('o-notif', async () => { await api().test_notification(); ONB_FLAGS.notifTried = true; paintOnboarding(false); });
  on('o-notif-yes', () => { ONB_FLAGS.notifOk = true; paintOnboarding(false); });
  on('o-notif-no', async () => { await api().open_notification_settings(); });
  on('o-notif-open', async (e) => { e.preventDefault(); await api().open_notification_settings(); });

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
  veil.innerHTML = `<div class="ofin-card">${CHECK}<h1>You’re all set</h1><p>HonestHands is ready to guard. Start a study session whenever you sit down to work.</p></div>`;
  document.body.appendChild(veil);
  setTimeout(() => { TAB = 'home'; paint(); veil.classList.add('out'); setTimeout(() => veil.remove(), 500); }, 1700);
}
