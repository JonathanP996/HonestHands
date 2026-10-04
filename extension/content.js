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
  let contextDead = false;
  function send(msg) {
    return new Promise((resolve) => {
      // If the extension was reloaded/updated, this tab's script is orphaned.
      if (!chrome.runtime || !chrome.runtime.id) { contextDead = true; resolve({ dead: true }); return; }
      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (chrome.runtime.lastError) {
            const m = chrome.runtime.lastError.message || '';
            if (/context invalidated|Receiving end does not exist/i.test(m)) { contextDead = true; resolve({ dead: true }); }
            else { log('bg error:', m); resolve(null); }
          } else resolve(resp);
        });
      } catch (e) {
        if (/context invalidated/i.test(e.message || '')) { contextDead = true; resolve({ dead: true }); }
        else { log('sendMessage threw:', e.message); resolve(null); }
      }
    });
  }

  // When our context is dead we cannot verify anything. Show a one-time banner asking the
  // user to reload the tab, and FAIL SAFE: hold sends rather than letting them through.
  let banner = null;
  function showReloadBanner() {
    if (banner) return;
    banner = document.createElement('div');
    banner.textContent = 'HonestHands updated — reload this tab (⌘R) to re-arm the guard.';
    banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#9c2b25;color:#fff;' +
      'font:600 13px/1.4 -apple-system,sans-serif;text-align:center;padding:8px 12px;cursor:pointer';
    banner.onclick = () => location.reload();
    document.documentElement.appendChild(banner);
  }
  async function appStatus() {
    const r = await send({ type: 'status' });
    const active = !!(r && r.active);
    if (r && !r.reachable) log('app not reachable (is HonestHands running?)');
    return active;
  }
  // --- pictures the student attaches: the guard reads them (on the Mac) so "do this" + a screenshot can't slip through ---
  const pendingFiles = [];                       // image Files seen via paste / drag-drop / file picker (a backup if the preview can't be read)
  const isImg = (f) => f && /^image\//.test(f.type || '');
  const remember = (files) => { for (const f of files || []) if (isImg(f) && !pendingFiles.includes(f)) pendingFiles.push(f); if (pendingFiles.length > 6) pendingFiles.splice(0, pendingFiles.length - 6); };
  window.addEventListener('paste', (e) => remember(Array.from((e.clipboardData && e.clipboardData.files) || [])), true);
  window.addEventListener('drop', (e) => remember(Array.from((e.dataTransfer && e.dataTransfer.files) || [])), true);
  window.addEventListener('change', (e) => { if (e.target && e.target.type === 'file') remember(Array.from(e.target.files || [])); }, true);

  function composerEl() { return document.querySelector(profile.input); }
  // thumbnails sitting at the message box right now (a picture the student removed, or one up in the chat history, doesn't count)
  function attachedImgs() {
    const el = composerEl();
    if (!el) return [];
    let root = el.closest('form');
    if (!root) { root = el; for (let i = 0; i < 8 && root.parentElement && root.parentElement !== document.body; i++) root = root.parentElement; }
    const cr = el.getBoundingClientRect();
    return Array.from(root.querySelectorAll('img')).filter((i) => {
      const w = i.naturalWidth || i.width || 0, h = i.naturalHeight || i.height || 0;
      if (w < 48 || h < 48 || i.closest('button, [role="button"], nav, header')) return false;
      const r = i.getBoundingClientRect();
      return r.bottom >= cr.top - 280 && r.top <= cr.bottom + 60 && r.right >= cr.left - 60 && r.left <= cr.right + 60;
    });
  }
  const readAsDataURL = (blob) => new Promise((res) => { try { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => res(null); r.readAsDataURL(blob); } catch (e) { res(null); } });
  async function shrink(blob) {                   // keep text readable but the upload small
    try {
      if (typeof createImageBitmap === 'function') {
        const bmp = await createImageBitmap(blob);
        const k = Math.min(1, 1800 / Math.max(bmp.width, bmp.height));
        const cv = document.createElement('canvas'); cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
        cv.getContext('2d').drawImage(bmp, 0, 0, cv.width, cv.height);
        return cv.toDataURL('image/jpeg', 0.88);
      }
    } catch (e) { /* fall through to the raw file */ }
    return readAsDataURL(blob);
  }
  async function collectImages() {
    const imgs = attachedImgs();
    if (!imgs.length) { pendingFiles.length = 0; return { n: 0, data: [] }; }
    const data = [];
    for (const img of imgs.slice(0, 3)) {
      try { const b = await (await fetch(img.currentSrc || img.src)).blob(); const d = await shrink(b); if (d) data.push(d); } catch (e) { /* cross-origin preview */ }
    }
    if (!data.length) for (const f of pendingFiles.slice(-3)) { const d = await shrink(f); if (d) data.push(d); }
    return { n: imgs.length, data };
  }

  async function askApp(text, imgs) {
    const r = await send({ type: 'check', text, site: HOST, url: location.href, images: (imgs && imgs.data) || [], nImages: (imgs && imgs.n) || 0 });
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

    const status = await send({ type: 'status' });
    if (status && status.dead) {
      log('context dead -> holding send + asking for tab reload');
      showReloadBanner();
      return;  // held: do NOT replay. User must reload the tab to re-arm.
    }
    const active = !!(status && status.active);
    log('app active =', active);
    if (!active) { log('inactive -> replaying send (no interference)'); replaySend(e, isEnter); return; }

    const text = readComposer();
    const imgs = await collectImages();
    log('composer text =', JSON.stringify(text).slice(0, 80), '| pictures =', imgs.n);
    if (!text && !imgs.n) { log('no text, no picture -> replaying send'); replaySend(e, isEnter); return; }

    busy = true;
    const verdict = await askApp(text, imgs);
    busy = false;
    log('verdict =', verdict);

    if (!verdict || verdict.active === false || verdict.verdict === 'allow') {
      log('allowed -> replaying send');
      pendingFiles.length = 0;
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
    // Otherwise, only a button physically next to the composer counts. Page buttons
    // elsewhere (close X, menus, "give me the answer" chips) must never trigger a check.
    if (!looksSend) {
      const box = document.querySelector(profile.input);
      if (!box || !readComposer()) return;
      const r = box.getBoundingClientRect(), b = btn.getBoundingClientRect();
      const near = b.right >= r.left - 20 && b.left <= r.right + 20 && b.bottom >= r.top - 20 && b.top <= r.bottom + 70;
      if (!near) return;
    }
    guardSend(e, false);
  }, true);

  // One ping on load so the app knows a guarded browser is present. After this the
  // background alarm keeps presence fresh; we don't need a tab-based timer.
  (async () => {
    const r = await send({ type: 'ping' });
    if (r && r.dead) showReloadBanner();  // orphaned on load (extension updated) -> prompt reload
  })();
})();
