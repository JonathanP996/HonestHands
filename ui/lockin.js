// Timed lock-in: the "Need out?" sheet (your PIN, or ask a friend to release you) and a few helpers.
// Loaded before app.js; uses its globals (S, api, h, el, $, toast, modal, closeModal, paint, refresh, TAB).

const fmtClock = (epoch) => new Date(epoch * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
let NEEDOUT_TIMER = null;

async function openNeedOut() {
  clearInterval(NEEDOUT_TIMER);
  const s = S && S.session;
  const locked = !!(s && s.locked && s.ends_at > Date.now() / 1000);
  const ex = (S && S.exit) || { pin: false, friends: 0 };
  const signedIn = !!(S.cloud_user && S.cloud_user.signed_in);
  const node = el(`<div class="needout">
    <h2>${locked ? 'You’re locked in' : 'End this session?'}</h2>
    <p class="sub">${locked ? `Until <b>${fmtClock(s.ends_at)}</b>. You can leave early with your PIN, or if a friend lets you out.` : 'Enter your PIN to end the session.'}</p>
    ${ex.pin ? `<div class="no-block"><div class="no-h">Use your PIN</div>
        <div class="no-row"><input id="no-pin" type="password" inputmode="numeric" placeholder="PIN" autocomplete="off"><button class="btn" id="no-end">End session</button></div></div>` : ''}
    ${locked ? `<div class="no-block"><div class="no-h">Ask a friend to release you</div><div id="no-friends"><p class="muted small">Looking for your friends…</p></div></div>` : ''}
    ${!ex.pin && !locked ? '<p class="muted">No PIN is set, so this session can be ended from the Study session screen.</p>' : ''}
    <div class="btnrow" style="justify-content:flex-end;margin-top:6px"><button class="btn ghost" id="no-close">${locked ? 'Keep going' : 'Close'}</button></div></div>`);
  modal(node);
  $('#no-close').onclick = () => { clearInterval(NEEDOUT_TIMER); closeModal(); };
  const pin = $('#no-pin');
  if (pin) {
    const end = async () => { const r = await api().end_session(pin.value || ''); if (r.error) { toast(r.error); pin.select(); return; }
      clearInterval(NEEDOUT_TIMER); closeModal(); S = r; TAB = 'home'; paint(); toast('Session ended.'); };
    $('#no-end').onclick = end; pin.onkeydown = (e) => { if (e.key === 'Enter') end(); }; pin.focus();
  }
  if (!locked) return;

  const box = $('#no-friends');
  if (!signedIn) { box.innerHTML = '<p class="muted small">Sign in on the Community tab to ask a friend.</p>'; return; }
  const friends = await api().cloud_releasers();
  if (friends && friends.error) { box.innerHTML = `<p class="muted small">${h(friends.error)}</p>`; return; }
  let lastSig = '';
  const draw = async () => {
    const rows = await api().cloud_unlock_status();
    if (!document.getElementById('no-friends')) { clearInterval(NEEDOUT_TIMER); return; }
    const live = Array.isArray(rows) ? rows.filter(r => r.status !== 'cancelled') : [];
    if (live.some(r => r.status === 'approved')) { clearInterval(NEEDOUT_TIMER); toast('Released. You’re free to go.'); closeModal(); await refresh(); return; }
    const pending = live.filter(r => r.status === 'pending');
    const sig = JSON.stringify(live.map(r => [r.id, r.status])) + friends.length;
    if (sig === lastSig) return;                                  // nothing changed: leave what they're typing alone
    lastSig = sig;
    box.innerHTML = (live.length ? `<div class="no-status">${live.map(r => `<div class="no-st ${r.status}"><i></i><span>${r.status === 'pending' ? `Waiting for <b>${h((r.w || {}).display_name || 'your friend')}</b>…` : r.status === 'denied' ? `<b>${h((r.w || {}).display_name || 'Your friend')}</b> said not now.` : ''}</span>
        ${r.status === 'pending' ? `<button class="btn ghost sm" data-cancel="${r.id}">Cancel</button>` : ''}</div>`).join('')}</div>` : '')
      + (pending.length ? '' : (friends.length ? `<div class="no-form"><div class="no-who">${friends.map(f => `<label class="chk"><input type="checkbox" value="${f.id}" checked><span>${h(f.display_name)}</span></label>`).join('')}</div>
          <textarea id="no-note" rows="2" maxlength="500" placeholder="Why do you need out? (they’ll see this)"></textarea>
          <button class="btn" id="no-ask">Ask to be released</button></div>` : '<p class="muted small">No friend can release you yet. Invite someone with “They can see me” in Community, then try a new lock-in.</p>'));
    box.querySelectorAll('[data-cancel]').forEach(b => b.onclick = async () => { await api().cloud_cancel_unlock(b.dataset.cancel); draw(); });
    const ask = $('#no-ask');
    if (ask) ask.onclick = async () => {
      const ids = [...box.querySelectorAll('.no-who input:checked')].map(i => i.value);
      if (!ids.length) return toast('Pick at least one friend.');
      ask.disabled = true;
      const r = await api().cloud_request_unlock($('#no-note').value, ids);
      if (r && r.error) { toast(r.error); ask.disabled = false; return; }
      toast('Request sent.'); draw();
    };
  };
  await draw();
  NEEDOUT_TIMER = setInterval(draw, 3000);
}
