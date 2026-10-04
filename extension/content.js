// HonestHands Guard — thin content script.
// It ONLY: (1) finds the composer, (2) intercepts send, (3) asks the desktop app,
// (4) obeys the verdict. No rules, no AI, no logging here. All of that is in the app.
// If the app is not running OR no session is active, this does nothing at all.

(() => {
  const APP = 'http://127.0.0.1:7673';
  const HOST = location.hostname;
  const DBG = true;  // set false to quiet
  const log = (...a) => { if (DBG) console.log('%c[HonestHands]', 'color:#c6a24c;font-weight:bold', ...a); };
  log('content script loaded on', HOST);

  // --- how to read the composer, per site (CSS selectors are stable inside the page) ---
  const SITES = {
    'gemini.google.com':   { input: 'rich-textarea .ql-editor, textarea' },
    'chatgpt.com':         { input: '#prompt-textarea, div.ProseMirror[contenteditable="true"], textarea' },
    'chat.openai.com':     { input: '#prompt-textarea, div.ProseMirror[contenteditable="true"], textarea' },
    'claude.ai':           { input: 'div.ProseMirror[contenteditable="true"], [contenteditable="true"]' },
    'claude.com':          { input: 'div.ProseMirror[contenteditable="true"], [contenteditable="true"]' },
    'copilot.microsoft.com':{ input: 'textarea, #searchbox, [contenteditable="true"]' },
    'www.perplexity.ai':   { input: 'textarea, [contenteditable="true"]' },
    'perplexity.ai':       { input: 'textarea, [contenteditable="true"]' },
    'chat.deepseek.com':   { input: 'textarea, #chat-input, [contenteditable="true"]' },
    'grok.com':            { input: 'textarea, [contenteditable="true"]' },
    'www.meta.ai':         { input: 'textarea, [contenteditable="true"]' },
    'meta.ai':             { input: 'textarea, [contenteditable="true"]' },
    'poe.com':             { input: 'textarea, [contenteditable="true"]' },
    'chat.mistral.ai':     { input: 'textarea, [contenteditable="true"]' },
    'you.com':             { input: 'textarea, [contenteditable="true"]' }
  };
  const profile = SITES[HOST] || { input: 'textarea, [contenteditable="true"]' };

  const readComposer = () => {
    const el = document.querySelector(profile.input);
    if (!el) return '';
    const t = (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') ? el.value : el.innerText;
    return (t || '').trim();
  };

  // --- talk to the app THROUGH the background worker (page CSP can't block this) ---
  function send(msg) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (chrome.runtime.lastError) { log('bg error:', chrome.runtime.lastError.message); resolve(null); }
          else resolve(resp);
        });
      } catch (e) { log('sendMessage threw:', e.message); resolve(null); }
    });
  }
  async function appStatus() {
    const r = await send({ type: 'status' });
    const active = !!(r && r.active);
    if (r && !r.reachable) log('app not reachable (is HonestHands running?)');
    return active;
  }
  async function askApp(text) {
    const r = await send({ type: 'check', text, site: HOST, url: location.href });
    return r || { active: false, verdict: 'allow' };
  }

  // --- intercept send: hold, ask, then allow or stop ---
  // We guard both Enter (keydown, capture) and clicks on the send control (capture).
  let passOnce = false;   // set true briefly to let our own re-dispatched event through
  let busy = false;

  async function guardSend(e, isEnter) {
    log('guardSend fired. isEnter=', isEnter, 'target=', e.target);
    if (passOnce) { passOnce = false; log('passOnce -> letting our own replay through'); return; }
    if (busy) { log('busy -> blocking extra event'); e.preventDefault(); e.stopImmediatePropagation(); return; }

    // We must hold the event SYNCHRONOUSLY (before any await), or the browser sends it
    // before our async check returns. Hold first, decide after.
    e.preventDefault();
    e.stopImmediatePropagation();
    if (e.stopPropagation) e.stopPropagation();

    const active = await appStatusCached();
    log('app active =', active);
    if (!active) { log('inactive -> replaying send (no interference)'); replaySend(e, isEnter); return; }

    const text = readComposer();
    log('composer text =', JSON.stringify(text).slice(0, 80));
    if (!text) { log('no text -> replaying send'); replaySend(e, isEnter); return; }

    busy = true;
    const verdict = await askApp(text);
    busy = false;
    log('verdict =', verdict);

    if (!verdict || verdict.active === false || verdict.verdict === 'allow') {
      log('allowed -> replaying send');
      replaySend(e, isEnter);
    } else {
      log('BLOCKED/WARNED -> not sending');
    }
  }

  function replaySend(e, isEnter) {
    passOnce = true;
    if (isEnter) {
      const el = e.target;
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    } else {
      passOnce = true;
      e.target.click();
    }
  }

  // Cache the active flag briefly so we don't hit the app on every keystroke.
  let activeCache = { v: false, t: 0 };
  async function appStatusCached() {
    const now = Date.now();
    if (now - activeCache.t < 1500) return activeCache.v;
    const v = await appStatus();
    activeCache = { v, t: now };
    return v;
  }

  // Enter to send (not Shift+Enter).
  window.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    const el = document.activeElement;
    if (!el) return;
    const inComposer = el.matches && (el.matches(profile.input) || el.closest(profile.input));
    if (!inComposer) return;
    guardSend(e, true);
  }, true);

  // Click on the send button. We detect it loosely: a button near the composer, or an
  // element whose icon/aria hints at send. Inside the page we CAN see these (unlike the OS).
  window.addEventListener('click', (e) => {
    const t = e.target;
    const btn = t.closest && t.closest('button, [role="button"], mat-icon, [data-testid*="send" i], [aria-label*="send" i], [aria-label*="submit" i]');
    if (!btn) return;
    // Heuristic: is this plausibly the send control?
    const hay = (btn.getAttribute('aria-label') || '') + ' ' + (btn.getAttribute('data-testid') || '') +
                ' ' + (btn.getAttribute('data-mat-icon-name') || '') + ' ' + (btn.getAttribute('fonticon') || '') +
                ' ' + (btn.className || '') + ' ' + (btn.textContent || '');
    const looksSend = /send|submit|arrow_upward|paper-?plane|→|↑/i.test(hay);
    const nearComposer = !!document.querySelector(profile.input);
    if (!looksSend && !nearComposer) return;
    if (!looksSend) {
      // Not clearly send; only guard if there's text AND the button is in the bottom area.
      if (!readComposer()) return;
    }
    guardSend(e, false);
  }, true);

  // Tiny heartbeat so the app can tell a browser is present (optional, harmless).
  appStatus();
})();
