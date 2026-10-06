// Community: accounts, accountability partners, and the live feed of overridden prompts.
// Loaded before app.js; uses its globals (api, h, el, $, toast, modal, closeModal, TAB, fmtLong) and pages.js (countTo, nextFrame).

let COMM_TIMER = null;
const AV_HUES = [293, 315, 65, 160, 200, 340];
const avHue = (s) => AV_HUES[[...String(s || '?')].reduce((a, c) => a + c.charCodeAt(0), 0) % AV_HUES.length];
const avatar = (name, id, size = 44) => `<span class="avatar" style="--hue:${avHue(id || name)};--s:${size}px">${h((name || '?').trim()[0] || '?')}</span>`;

function ago(t) {
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 90) return 'just now';
  if (s < 3600) return Math.round(s / 60) + ' min ago';
  if (s < 86400) return Math.round(s / 3600) + ' h ago';
  const d = Math.round(s / 86400); return d + (d === 1 ? ' day ago' : ' days ago');
}
const isoSec = (s) => s ? new Date(s).getTime() / 1000 : 0;
// "Active" if the app checked in recently; a long silence is shown plainly, not accusingly.
function presence(lastSeen) {
  const t = isoSec(lastSeen);
  if (!t) return { cls: 'idle', text: 'No check-in yet' };
  const s = Date.now() / 1000 - t;
  if (s < 600) return { cls: 'on', text: 'Active now' };
  if (s < 86400) return { cls: 'mid', text: 'Checked in ' + ago(t) };
  return { cls: 'quiet', text: 'Quiet since ' + ago(t) };
}

// ---------------------------------------------------------------- entry
async function paintCommunity() {
  clearInterval(COMM_TIMER);
  const m = $('#main');
  m.innerHTML = `<div class="wrap comm"><p class="muted">Loading…</p></div>`;
  const st = await api().cloud_status();
  if (!st.signed_in) return paintSignIn();
  if (st.error) return paintCommError(st.error);
  if (!st.handle) return paintProfileSetup(st);
  paintCommHome(st);
}

function paintCommError(msg) {
  $('#main').innerHTML = `<div class="wrap comm"><div class="authcard rise"><h2>Can't reach the community</h2>
    <p class="sub">${h(msg)}</p><div class="btnrow"><button class="btn" id="retry">Try again</button><button class="btn ghost" id="so">Sign out</button></div></div></div>`;
  $('#retry').onclick = paintCommunity;
  $('#so').onclick = async () => { await api().cloud_sign_out(); await refreshWelcome(); paintCommunity(); };
}

// ---------------------------------------------------------------- sign in / create account (email + password)
function paintSignIn(email = '', mode = 'in') {
  const m = $('#main');
  m.innerHTML = `<div class="wrap comm"><div class="authwrap">
    <div class="authhero rise" style="--i:0"><div class="onb-seal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M16 5.2a3.2 3.2 0 0 1 0 5.6"/><path d="M17.5 14.3A5.5 5.5 0 0 1 20.5 19"/></svg></div>
      <h1>Walk this out together</h1>
      <p class="onb-lead">Pair up with someone you trust. They see when you lock in, and any prompt you send despite a warning. Nothing else.</p></div>
    <div class="authcard rise" style="--i:1" id="authcard">
      <div class="segmode authtabs" id="tabs"><button data-t="in" class="${mode === 'in' ? 'on' : ''}">Sign in</button><button data-t="up" class="${mode === 'up' ? 'on' : ''}">Create account</button></div>
      <label>Email</label>
      <input id="em" type="email" placeholder="example@gmail.com" autocomplete="email" value="${h(email)}">
      <label style="margin-top:14px">Password</label>
      <div class="pwbox"><input id="pw" type="password" placeholder="${mode === 'up' ? 'At least 8 characters' : 'Your password'}" autocomplete="${mode === 'up' ? 'new-password' : 'current-password'}"><button type="button" id="showpw">Show</button></div>
      <button class="btn wide" id="go">${mode === 'up' ? 'Create account' : 'Sign in'}</button>
      <p class="authmsg" id="authmsg"></p>
    </div>
    <div class="shares rise" style="--i:2">
      <div><b>Shared</b><span>Prompts you send despite a warning (with their text) · your session times · daily counts · when the app last checked in</span></div>
      <div><b>Never shared</b><span>Your syllabi and assignments · the text of clean or flagged messages (those are counts only)</span></div>
    </div></div></div>`;
  const msg = (t, bad = true) => { const e = $('#authmsg'); e.textContent = t; e.className = 'authmsg ' + (bad ? 'bad' : 'good'); };
  $('#tabs').querySelectorAll('button').forEach(b => b.onclick = () => paintSignIn($('#em').value, b.dataset.t));
  $('#showpw').onclick = () => { const p = $('#pw'); const show = p.type === 'password'; p.type = show ? 'text' : 'password'; $('#showpw').textContent = show ? 'Hide' : 'Show'; };
  let busy = false;
  const go = async () => {
    if (busy) return; busy = true; $('#go').disabled = true; msg(mode === 'up' ? 'Creating your account…' : 'Signing in…', false);
    const em = $('#em').value.trim(), pw = $('#pw').value;
    const r = mode === 'up' ? await api().cloud_sign_up(em, pw) : await api().cloud_sign_in(em, pw);
    busy = false; $('#go').disabled = false;
    if (r && r.error) return msg(r.error);
    if (r && r.needs_confirm) { paintSignIn(em, 'in'); return setTimeout(() => { const e = $('#authmsg'); if (e) { e.textContent = 'Account created. Click the link in the email we sent to confirm it, then sign in here. (The page the link opens may say "can\'t be reached". That is fine.)'; e.className = 'authmsg good'; } }, 30); }
    toast(mode === 'up' ? 'Account created.' : 'Signed in.'); refreshWelcome(); paintCommunity();
  };
  $('#go').onclick = go; $('#pw').onkeydown = (e) => { if (e.key === 'Enter') go(); }; $('#em').onkeydown = (e) => { if (e.key === 'Enter') $('#pw').focus(); };
}

// ---------------------------------------------------------------- pick a handle
function paintProfileSetup(st) {
  $('#main').innerHTML = `<div class="wrap comm"><div class="authwrap">
    <div class="authhero rise"><h1>Pick how friends find you</h1><p class="onb-lead">Your handle is what someone types to invite you. Your name is what they see.</p></div>
    <div class="authcard rise" style="--i:1">
      <label>Your name</label><input id="dn" value="${h(st.display_name || '')}" maxlength="40" placeholder="Alex">
      <label style="margin-top:14px">Handle</label>
      <div class="handlebox"><span>@</span><input id="hd" maxlength="24" placeholder="alex_k" autocapitalize="off" spellcheck="false"></div>
      <div class="small muted" style="margin-top:6px">3–24 letters, numbers or underscores. You can't change it later without asking a friend to re-invite you.</div>
      <button class="btn wide" id="go" style="margin-top:18px">Continue</button>
      <p class="authmsg" id="authmsg"></p>
    </div></div></div>`;
  const go = async () => {
    $('#go').disabled = true;
    const r = await api().cloud_set_profile($('#hd').value, $('#dn').value);
    $('#go').disabled = false;
    if (r && r.error) { const e = $('#authmsg'); e.textContent = r.error; e.className = 'authmsg bad'; return; }
    refreshWelcome(); paintCommunity();
  };
  $('#go').onclick = go; $('#hd').onkeydown = (e) => { if (e.key === 'Enter') go(); };
}

// ---------------------------------------------------------------- home
function paintCommHome(me) {
  $('#main').innerHTML = `<div class="wrap comm">
    <div class="commbar rise" style="--i:0">
      ${avatar(me.display_name, me.id, 54)}
      <div class="who"><b>${h(me.display_name)}</b><span>@${h(me.handle)} · ${h(me.email || '')}</span></div>
      <span class="syncpill" id="syncpill"></span>
      <label class="switch" title="When off, nothing is uploaded and partners see no new activity"><input type="checkbox" id="share" ${me.sharing ? 'checked' : ''}><i></i><span>Share my activity</span></label>
      <button class="btn ghost sm" id="so">Sign out</button>
    </div>

    <div id="releases"></div>
    <div class="icard rise" style="--i:1"><div class="ihead"><h2>Invite someone</h2><span class="icap">BY HANDLE</span></div>
      <div class="invite">
        <div class="handlebox"><span>@</span><input id="ih" maxlength="24" placeholder="their_handle" autocapitalize="off" spellcheck="false"></div>
        <div class="segmode" id="mode">
          <button data-m="watch_me" class="on">They can see me</button><button data-m="watch_them">I can see them</button><button data-m="both">Both ways</button>
        </div>
        <button class="btn" id="inv">Send invite</button>
      </div>
      <div class="small muted" id="invhint" style="margin-top:10px">They'll get a request to accept. Nothing is shared until they do.</div>
    </div>

    <div id="requests"></div>
    <div class="commgrid">
      <div class="icard rise" style="--i:2"><div class="ihead"><h2>People I watch</h2><span class="icap" id="wcap"></span></div><div id="watching"></div></div>
      <div class="icard rise" style="--i:3"><div class="ihead"><h2>Watching me</h2><span class="icap" id="mcap"></span></div><div id="watchers"></div></div>
    </div>
    <div class="icard rise" style="--i:5;margin-top:18px"><div class="ihead"><h2>Overridden Feed</h2><span class="icap">FROM PEOPLE YOU WATCH</span></div><div id="feed"></div></div>
  </div>`;
  let mode = 'watch_me';
  $('#mode').querySelectorAll('button').forEach(b => b.onclick = () => { mode = b.dataset.m;
    $('#mode').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    $('#invhint').textContent = { watch_me: 'They’ll see your activity once they accept.', watch_them: 'You’ll see theirs once they accept.', both: 'You’ll see each other’s once they accept.' }[mode]; });
  $('#inv').onclick = async () => {
    const hnd = $('#ih').value.trim(); if (!hnd) return toast('Type their handle first.');
    $('#inv').disabled = true; const r = await api().cloud_invite(hnd, mode); $('#inv').disabled = false;
    if (r && r.error) return toast(r.error);
    toast('Invite sent to ' + r.name + '.'); $('#ih').value = ''; refreshComm();
  };
  $('#ih').onkeydown = (e) => { if (e.key === 'Enter') $('#inv').click(); };
  $('#so').onclick = async () => { await api().cloud_sign_out(); await refreshWelcome(); paintCommunity(); };
  $('#share').onchange = async (e) => { const r = await api().cloud_set_sharing(e.target.checked); toast(e.target.checked ? 'Sharing on.' : 'Sharing paused. Nothing new is uploaded.'); };
  refreshComm();
  COMM_TIMER = setInterval(() => { if (TAB !== 'community' || !document.getElementById('feed')) { clearInterval(COMM_TIMER); return; } refreshComm(); }, 15000);
}

async function refreshComm() {
  const [ov, inc] = await Promise.all([api().cloud_overview(), api().cloud_incoming_unlocks()]);
  if (document.getElementById('releases')) drawReleases(Array.isArray(inc) ? inc : []);
  if (!document.getElementById('feed')) return;
  if (ov && ov.error) { $('#feed').innerHTML = `<p class="muted">${h(ov.error)}</p>`; return; }
  const sp = ov.status || {};
  const label = { ok: ['ok', 'Synced'], offline: ['bad', 'Offline'], error: ['bad', 'Sync problem'], idle: ['mid', 'Starting…'] }[sp.state] || ['mid', 'Starting…'];
  $('#syncpill').className = 'syncpill ' + label[0]; $('#syncpill').innerHTML = `<i></i>${label[1]}`; $('#syncpill').title = sp.message || '';

  $('#requests').innerHTML = ov.requests.length ? `<div class="icard reqcard rise"><div class="ihead"><h2>Requests</h2><span class="icap">${ov.requests.length} WAITING</span></div>` +
    ov.requests.map(r => `<div class="prow">${avatar(r.person.display_name, r.person.id)}<div class="pmain"><b>${h(r.person.display_name)}</b><span>@${h(r.person.handle || '')} wants ${r.direction === 'watching_me' ? 'to <b>see your activity</b>' : 'to <b>share their activity with you</b>'}</span></div>
      <div class="btnrow"><button class="btn sm" data-acc="${r.id}">Accept</button><button class="btn ghost sm" data-dec="${r.id}">Decline</button></div></div>`).join('') + '</div>' : '';
  $('#requests').querySelectorAll('[data-acc]').forEach(b => b.onclick = async () => { const r = await api().cloud_respond(b.dataset.acc, true); if (r && r.error) toast(r.error); else { toast('Accepted.'); refreshComm(); } });
  $('#requests').querySelectorAll('[data-dec]').forEach(b => b.onclick = async () => { await api().cloud_respond(b.dataset.dec, false); refreshComm(); });

  $('#wcap').textContent = ov.watching.length ? `${ov.watching.length} PERSON${ov.watching.length === 1 ? '' : 'S'}` : '';
  $('#watching').innerHTML = ov.watching.map(w => { const p = presence(w.person.last_seen), wk = w.week;
    return `<button class="prow clickable" data-friend="${w.person.id}">${avatar(w.person.display_name, w.person.id)}
      <div class="pmain"><b>${h(w.person.display_name)}${w.mutual ? ' <em class="mutual">mutual</em>' : ''}</b>
        <span class="pres ${p.cls}"><i></i>${p.text}</span>
        <span class="pweek">${fmtLong(wk.seconds)} locked in this week · <b class="${wk.overridden ? 'bad' : ''}">${wk.overridden} overridden</b></span></div><span class="chev">›</span></button>`; }).join('')
    || '<p class="muted small">You aren\'t watching anyone yet. Invite someone with “I can see them”.</p>';
  $('#watching').querySelectorAll('[data-friend]').forEach(b => b.onclick = () => openFriend(b.dataset.friend));

  $('#mcap').textContent = (ov.watchers.length + ov.outgoing.length) ? `${ov.watchers.length} ACTIVE` : '';
  const wrow = (x, pending) => `<div class="prow">${avatar(x.person.display_name, x.person.id)}<div class="pmain"><b>${h(x.person.display_name)}${x.mutual ? ' <em class="mutual">mutual</em>' : ''}</b>
      <span>${pending ? 'Invite sent. Waiting for them.' : '@' + h(x.person.handle || '') + ' can see your activity'}</span></div>
      <button class="btn danger sm" data-end="${x.id}">${pending ? 'Cancel' : 'Remove'}</button></div>`;
  $('#watchers').innerHTML = ov.watchers.map(x => wrow(x, false)).join('') + ov.outgoing.map(x => wrow(x, true)).join('')
    || '<p class="muted small">No one can see your activity yet.</p>';
  $('#watchers').querySelectorAll('[data-end]').forEach(b => b.onclick = async () => { const r = await api().cloud_end(b.dataset.end); if (r && r.error) toast(r.error); else { toast('Removed.'); refreshComm(); } });

  COMM_OV = ov; drawFeed();
}

// ---------------------------------------------------------------- the Overridden Feed
let COMM_OV = null;
const myVerdict = (e) => { const r = (e.reactions || []).find(x => x.reviewer === COMM_OV.me); return r ? r.verdict : ''; };
function drawFeed() {
  const ov = COMM_OV, box = document.getElementById('feed'); if (!box) return;
  box.innerHTML = ov.feed.length ? ov.feed.map((e, i) => {
    const note = Array.isArray(e.note) ? e.note[0] : e.note, mv = myVerdict(e);
    return `<div class="fitem" style="--i:${Math.min(i, 10)}">
      ${avatar((e.who || {}).display_name, (e.who || {}).id, 40)}
      <div class="fmain"><div class="fmeta"><b>${h((e.who || {}).display_name || 'Someone')}</b> sent this despite a warning · ${ago(isoSec(e.at))}
        ${e.class_label ? `<span class="muted"> · ${h(e.class_label)}${e.assignment_label ? ' / ' + h(e.assignment_label) : ''}</span>` : ''}${e.site ? `<span class="muted"> · ${h(e.site)}</span>` : ''}</div>
        <div class="fquote">“${h(e.prompt_text)}”</div>
        ${e.reason ? `<div class="fwhy">${h(e.reason)}</div>` : ''}
        ${note && note.body ? `<div class="fnote"><b>${h((e.who || {}).display_name || 'They')} says</b>${h(note.body)}</div>` : ''}
        <div class="fact">
          <button class="thumb up ${mv === 'up' ? 'on' : ''}" data-ev="${e.id}" data-v="up" title="This looks fine to me">${THUMB_UP}<span>Fine</span></button>
          <button class="thumb down ${mv === 'down' ? 'on' : ''}" data-ev="${e.id}" data-v="down" title="This doesn’t look right">${THUMB_DOWN}<span>Not okay</span></button>
          <button class="btn ghost sm" data-talk="${i}">Let’s talk about this</button>
        </div></div></div>`;
  }).join('')
    : `<div class="emptyfeed"><b>Nothing overridden.</b><span>${ov.watching.length ? 'A quiet feed is a good feed.' : 'Prompts people send despite a warning will show up here.'}</span></div>`;
  box.querySelectorAll('[data-v]').forEach(b => b.onclick = async () => {
    const e = ov.feed.find(x => x.id === b.dataset.ev); if (!e) return;
    const verdict = myVerdict(e) === b.dataset.v ? '' : b.dataset.v;               // tapping your choice again takes it back
    const before = e.reactions || [];
    e.reactions = before.filter(r => r.reviewer !== ov.me).concat(verdict ? [{ reviewer: ov.me, verdict }] : []);
    drawFeed();
    const r = await api().cloud_react(e.id, verdict, (e.who || {}).id || '', e.prompt_text || '', { site: e.site || '', cls: e.class_label || '', asg: e.assignment_label || '', at: e.at || '' });
    if (r && r.error) { e.reactions = before; drawFeed(); toast(/reactions|schema|exist/i.test(r.error) ? 'Thumbs need a one-time database update (cloud/migrations/003_notes_and_reactions.sql).' : r.error); }
  });
  box.querySelectorAll('[data-talk]').forEach(b => b.onclick = () => {
    const e = ov.feed[+b.dataset.talk], who = e.who || {};
    const person = (ov.watching.find(w => w.person.id === who.id) || {}).person || who;
    openChat(person, '', cardFromEvent(e));
  });
}

// ---------------------------------------------------------------- one person
async function openFriend(uid) {
  const node = el(`<div class="friendsheet"><p class="muted">Loading…</p></div>`);
  modal(node);
  const d = await api().cloud_friend(uid);
  if (d && d.error) { node.innerHTML = `<p class="muted">${h(d.error)}</p><div class="btnrow" style="justify-content:flex-end"><button class="btn" id="fc">Close</button></div>`; $('#fc').onclick = closeModal; return; }
  const p = d.profile, pr = presence(p.last_seen), t = d.totals;
  const days = {}; d.daily.forEach(x => days[x.day] = x);
  const last14 = []; for (let i = 13; i >= 0; i--) { const dt = new Date(Date.now() - i * 864e5); const k = dt.toLocaleDateString('en-CA'); last14.push({ k, lab: dt.toLocaleDateString([], { weekday: 'narrow' }), v: days[k] || { seconds: 0, overridden: 0, sessions: 0 } }); }
  const mx = Math.max(60, ...last14.map(x => x.v.seconds));
  node.innerHTML = `<div class="fhead">${avatar(p.display_name, p.id, 62)}<div><h2>${h(p.display_name)}</h2><span class="pres ${pr.cls}"><i></i>${pr.text}</span></div></div>
    <div class="ftiles">
      <div><b>${d.streak}</b><span>day streak</span></div><div><b>${fmtLong(t.seconds)}</b><span>locked in (60 days)</span></div>
      <div><b>${t.sessions}</b><span>sessions</span></div><div class="${t.overridden ? 'bad' : ''}"><b>${t.overridden}</b><span>overridden</span></div></div>
    <div class="fbars" title="Time locked in, last 14 days">${last14.map((x, i) => `<div class="fb" data-tip="${h(x.k)} · ${fmtLong(x.v.seconds)}${x.v.overridden ? ' · ' + x.v.overridden + ' overridden' : ''}">
      <div class="fbar"><div class="fbo" data-h="${100 * x.v.seconds / mx}" style="--d:${i * 40}ms"></div></div><span>${x.lab}</span></div>`).join('')}</div>
    <h3 class="fsub">Recently overridden</h3>
    <div class="flist">${d.events.length ? d.events.map(e => `<div class="fev"><div class="fmeta">${ago(isoSec(e.at))}${e.class_label ? ' · ' + h(e.class_label) : ''}${e.site ? ' · ' + h(e.site) : ''}</div>
      <div class="fquote">“${h(e.prompt_text)}”</div>${e.reason ? `<div class="fwhy">${h(e.reason)}</div>` : ''}</div>`).join('') : '<p class="muted small">None. Nothing sent despite a warning.</p>'}</div>
    <div class="btnrow" style="justify-content:flex-end;margin-top:14px"><button class="btn" id="fc">Done</button></div>`;
  $('#fc').onclick = closeModal;
  nextFrame(() => node.querySelectorAll('[data-h]').forEach(b => b.style.height = Math.max(parseFloat(b.dataset.h), 2) + '%'));
}


// ---------------------------------------------------------------- release requests (a friend is locked in and wants out)
function drawReleases(rows) {
  const box = document.getElementById('releases');
  if (!rows.length) { box.innerHTML = ''; return; }
  box.innerHTML = `<div class="icard relcard rise"><div class="ihead"><h2>Release requests</h2><span class="icap">${rows.length} WAITING</span></div>` +
    rows.map(r => { const w = r.who || {};
      return `<div class="relrow">${avatar(w.display_name, w.id, 46)}<div class="pmain"><b>${h(w.display_name || 'A friend')} wants out of their lock-in</b>
        <span>${r.class_label ? h(r.class_label) + ' · ' : ''}${r.minutes_left ? r.minutes_left + ' min left · ' : ''}asked ${ago(isoSec(r.created_at))}</span>
        ${r.note ? `<div class="relnote">“${h(r.note)}”</div>` : ''}</div>
        <div class="btnrow"><button class="btn sm" data-rel="${r.id}" data-ok="1">Release them</button><button class="btn ghost sm" data-rel="${r.id}" data-ok="0">Not now</button></div></div>`; }).join('') +
    '<p class="small muted" style="margin-top:10px">Think about it first: they chose this lock-in so they would stay on task. Releasing them is your call.</p></div>';
  box.querySelectorAll('[data-rel]').forEach(b => b.onclick = async () => {
    b.disabled = true;
    const r = await api().cloud_decide_unlock(b.dataset.rel, b.dataset.ok === '1');
    if (r && r.error) { toast(r.error); b.disabled = false; return; }
    toast(b.dataset.ok === '1' ? 'They’ve been released.' : 'Request declined.'); refreshComm();
  });
}

// ---------------------------------------------------------------- messages
let MSG_SEL = null, MSG_DRAFT = '', MSG_ATTACH = null, MSG_TIMER = null;
function previewOf(body) {
  const { card, text } = parseCard(body);
  if (card && card.t === 'verdict') return (card.v === 'up' ? '\u{1F44D} Fine' : '\u{1F44E} Not okay');
  if (card) return '\u{1F4CE} Shared a prompt' + (text.trim() ? ': ' + text.trim().slice(0, 40) : '');
  return text.split('\n')[0].slice(0, 60);
}
function drawConvos(rows) {
  const unread = rows.reduce((a, r) => a + r.unread, 0);
  const cap = document.getElementById('msgcap'); if (cap) cap.textContent = unread ? `${unread} UNREAD` : '';
  const box = document.getElementById('convos'); if (!box) return;
  box.innerHTML = rows.map(r => { const p = r.person, last = r.last;
    return `<button class="prow clickable ${MSG_SEL && MSG_SEL.id === p.id ? 'sel' : ''}" data-chat="${p.id}">${avatar(p.display_name, p.id)}
      <div class="pmain"><b>${h(p.display_name)}</b><span class="${r.unread ? 'unread' : ''}">${last ? (last.from_user === p.id ? '' : 'You: ') + h(previewOf(last.body)) : 'Say hello'}</span></div>
      ${r.unread ? `<i class="ubadge">${r.unread}</i>` : ''}</button>`; }).join('')
    || '<p class="muted small" style="padding:6px 10px">Messages appear here once you and a friend are connected (one of you can see the other).</p>';
  box.querySelectorAll('[data-chat]').forEach(b => b.onclick = () => selectChat(rows.find(r => r.person.id === b.dataset.chat).person));
}

// ---- picture-cards inside messages: a prompt (or a thumb on one) travels as a hidden token at the end of the message text ----
const CARD_RE = /\n?\[\[hh:([A-Za-z0-9+\/=]+)\]\]\s*$/;
function parseCard(body) {
  const m = CARD_RE.exec(body || '');
  if (!m) return { card: null, text: body || '' };
  try { return { card: JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(m[1]), c => c.charCodeAt(0)))), text: body.slice(0, m.index) }; }
  catch (e) { return { card: null, text: body.slice(0, m.index) }; }
}
function cardToken(card) {
  const bytes = new TextEncoder().encode(JSON.stringify(card)); let bin = '';
  bytes.forEach(b => bin += String.fromCharCode(b));
  return '[[hh:' + btoa(bin) + ']]';
}
function cardFromEvent(e, kind = 'prompt', v = '') {
  return { t: kind, v, text: (e.prompt_text || '').slice(0, 300), site: e.site || '', cls: e.class_label || '', asg: e.assignment_label || '', at: e.at || '' };
}
// The card itself: the same look as a row in Activity, but as an object you can hold: accent edge, site chip, big quote, class and time.
function cardHTML(c, removable = false) {
  const when = c.at ? new Date(c.at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '';
  const verdict = c.t === 'verdict' ? (c.v === 'up'
    ? `<div class="pc-verdict up">${THUMB_UP}<b>Fine</b></div>` : `<div class="pc-verdict down">${THUMB_DOWN}<b>Not okay</b></div>`) : '';
  return `<div class="pcard ${c.t === 'verdict' ? 'v' + c.v : ''}">
    ${verdict}
    <div class="pc-top"><span class="pc-dot"></span><b>Overridden</b>${c.site ? `<span class="pc-site">${h(c.site)}</span>` : ''}${removable ? '<button class="pc-x" id="attachx" title="Remove">×</button>' : ''}</div>
    <div class="pc-q"><i>“</i>${h(c.text || '')}<i>”</i></div>
    <div class="pc-foot"><span>${h([c.cls, c.asg].filter(Boolean).join(' / ') || 'Study session')}</span>${when ? `<span>${h(when)}</span>` : ''}</div>
  </div>`;
}

const THUMB_UP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 11v9H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h3z"/><path d="M7 11l4-8c1.7 0 3 1.3 3 3v3.5h5a2 2 0 0 1 2 2.3l-1.2 7a2 2 0 0 1-2 1.7H7"/></svg>';
const THUMB_DOWN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transform:scaleY(-1)"><path d="M7 11v9H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h3z"/><path d="M7 11l4-8c1.7 0 3 1.3 3 3v3.5h5a2 2 0 0 1 2 2.3l-1.2 7a2 2 0 0 1-2 1.7H7"/></svg>';

let CHAT_TIMER = null;
// Anything that wants to talk to someone (the feed, a friend's page, the list) lands on the Messages tab with them selected.
function openChat(person, draft = '', attach = null) {
  MSG_SEL = person; MSG_DRAFT = draft || ''; MSG_ATTACH = attach;
  TAB = 'messages'; paint();
}
function selectChat(person, draft = '', attach = null) {
  MSG_SEL = person; MSG_DRAFT = draft || ''; MSG_ATTACH = attach;
  document.querySelectorAll('#convos .prow').forEach(b => b.classList.toggle('sel', b.dataset.chat === person.id));
  mountChat(person);
}

async function paintMessages() {
  clearInterval(MSG_TIMER); clearInterval(CHAT_TIMER);
  const m = $('#main');
  const st = await api().cloud_status();
  if (!st || !st.signed_in) {
    m.innerHTML = `<div class="wrap"><div class="authcard rise"><h2>Sign in to message friends</h2><p class="sub">Messages are between you and the people you’re connected to. Sign in or create an account in Community first.</p><button class="btn" id="msg-go">Open Community</button></div></div>`;
    $('#msg-go').onclick = () => { TAB = 'community'; paint(); };
    return;
  }
  m.innerHTML = `<div class="wrap msgwrap rise"><div class="msgside"><div class="msghead"><h2>Messages</h2><span class="icap" id="msgcap"></span></div><div id="convos"><p class="muted small" style="padding:6px 10px">Loading…</p></div></div>
    <div class="msgmain" id="msgmain"><div class="msgempty"><b>Pick a conversation</b><span>Choose a friend on the left to read and reply.</span></div></div></div>`;
  const refresh = async () => {
    if (TAB !== 'messages' || !document.getElementById('convos')) { clearInterval(MSG_TIMER); return; }
    const rows = await api().cloud_conversations();
    drawConvos(Array.isArray(rows) ? rows : []);
  };
  await refresh();
  if (MSG_SEL) mountChat(MSG_SEL);
  MSG_TIMER = setInterval(refresh, 8000);
}

async function mountChat(person) {
  clearInterval(CHAT_TIMER);
  const main = document.getElementById('msgmain'); if (!main) return;
  main.innerHTML = `<div class="chat"><div class="chathead">${avatar(person.display_name, person.id, 44)}<div><h2>${h(person.display_name)}</h2><span class="muted small">@${h(person.handle || '')}</span></div></div>
    <div class="chatlist" id="chatlist"><p class="muted small">Loading…</p></div>
    <div id="attachbar" class="attachbar" hidden></div>
    <div class="chatbar"><textarea id="chatin" rows="1" maxlength="1500" placeholder="Write a message…"></textarea><button class="btn" id="chatsend">Send</button></div></div>`;
  const draft = MSG_DRAFT; MSG_DRAFT = '';
  const drawAttach = () => {
    const bar = document.getElementById('attachbar'); if (!bar) return;
    bar.hidden = !MSG_ATTACH;
    bar.innerHTML = MSG_ATTACH ? `<span class="att-l">Attached to your message</span>${cardHTML(MSG_ATTACH, true)}` : '';
    const x = document.getElementById('attachx'); if (x) x.onclick = () => { MSG_ATTACH = null; drawAttach(); $('#chatin').focus(); };
  };
  drawAttach();
  let sig = '';
  const load = async (stick) => {
    const box = document.getElementById('chatlist'); if (!box || !MSG_SEL || MSG_SEL.id !== person.id || TAB !== 'messages') { clearInterval(CHAT_TIMER); return; }
    const d = await api().cloud_thread(person.id);
    if (!d || d.error) { box.innerHTML = `<p class="muted small">${h((d && d.error) || 'Could not load.')}</p>`; return; }
    const s = d.messages.map(m => m.id).join(','); if (s === sig) return; sig = s;
    const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
    const vcls = (m) => m.kind === 'system' && m.body.startsWith('\u{1F44D}') ? ' vup' : m.kind === 'system' && m.body.startsWith('\u{1F44E}') ? ' vdown' : '';
    const bubble = (m) => {
      const { card, text } = parseCard(m.body), mine = m.from_user === d.me;
      const time = `<em>${new Date(m.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</em>`;
      if (card) return `<div class="bubble cardmsg ${mine ? 'mine' : 'theirs'}">${cardHTML(card)}${card.t !== 'verdict' && text.trim() ? `<span class="cm-t">${h(text.trim())}</span>` : ''}${time}</div>`;
      return null;
    };
    box.innerHTML = d.messages.length ? d.messages.map(m => bubble(m) || `<div class="bubble ${m.from_user === d.me ? 'mine' : 'theirs'}${vcls(m)}"><span>${h(m.body)}</span><em>${new Date(m.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</em></div>`).join('')
      : '<p class="muted small" style="text-align:center;margin-top:30px">No messages yet. Say hello.</p>';
    if (stick || atEnd) box.scrollTop = box.scrollHeight;
    if (d.messages.some(m => m.to_user === d.me)) paintMsgBadgeSoon();
  };
  const send = async () => {
    const inp = $('#chatin'), typed = inp.value.trim(); if (!typed && !MSG_ATTACH) return;
    const body = (typed + (MSG_ATTACH ? '\n' + cardToken(MSG_ATTACH) : '')).trim();
    const held = MSG_ATTACH;
    inp.value = ''; MSG_ATTACH = null; drawAttach(); $('#chatsend').disabled = true;
    const r = await api().cloud_send_message(person.id, body);
    $('#chatsend').disabled = false; inp.focus();
    if (r && r.error) { toast(r.error); inp.value = typed; MSG_ATTACH = held; drawAttach(); return; }
    await load(true);
    const rows = await api().cloud_conversations(); drawConvos(Array.isArray(rows) ? rows : []);
  };
  $('#chatsend').onclick = send;
  $('#chatin').onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
  if (draft) { $('#chatin').value = draft; $('#chatin').rows = 3; }
  await load(true); $('#chatin').focus(); $('#chatin').setSelectionRange($('#chatin').value.length, $('#chatin').value.length);
  CHAT_TIMER = setInterval(() => load(false), 4000);
}
// reading a thread marks it read on the server: refresh the sidebar number shortly after
function paintMsgBadgeSoon() { setTimeout(async () => { try { S = await api().state(); paintBadge(); } catch (e) {} }, 800); }
