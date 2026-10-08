// HonestHands Guard on Google: while a study session is on, (1) AI Mode and the AI Overview box are removed from the results,
// and (2) a question typed into the search bar is checked like a message to an AI. A plain search is let through untouched.
// When the app isn't running or no session is active, this does nothing at all.
(() => {
  let active = false;
  let busy = false;
  const isAiMode = () => /(^|[?&])udm=50(&|$)/.test(location.search);
  const style = document.createElement('style');
  style.textContent = 'a[href*="udm=50"], [aria-label="AI Mode"], [aria-label="AI mode"], [data-hh-hidden] { display: none !important; }';

  // --- AI Overview: find the box by its heading and hide the whole block (it has a chat box and "show more" inside) ---
  const OVERVIEW = /^\s*(AI Overview|AI-generated overview|AI overview)\s*$/i;
  function hideOverview() {
    const root = document.querySelector('#rso, #center_col, #main') || document.body;
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      if (!OVERVIEW.test(n.nodeValue || '')) continue;
      let el = n.parentElement, block = null;
      for (let i = 0; i < 14 && el && el !== root; i++) {              // climb to the biggest block that is still only the overview
        const r = el.getBoundingClientRect();
        if (el.parentElement && (el.parentElement === root || el.parentElement.id === 'rso' || el.parentElement.id === 'center_col')) { block = el; break; }
        el = el.parentElement;
      }
      if (block && !block.hasAttribute('data-hh-hidden')) block.setAttribute('data-hh-hidden', '1');
    }
  }
  let mo = null;
  function watchPage() {
    if (mo) return;
    mo = new MutationObserver(() => { if (active) hideOverview(); });
    const go = () => { mo.observe(document.documentElement, { childList: true, subtree: true }); hideOverview(); };
    if (document.documentElement) go(); else document.addEventListener('DOMContentLoaded', go);
  }

  function apply(on) {
    active = on;
    if (!on) {
      style.remove();
      document.querySelectorAll('[data-hh-hidden]').forEach((e) => e.removeAttribute('data-hh-hidden'));
      return;
    }
    (document.head || document.documentElement).appendChild(style);
    watchPage();
    hideOverview();
    if (isAiMode()) {
      const u = new URL(location.href);
      u.searchParams.delete('udm');                                   // back to the normal results for the same words
      location.replace(u.toString());
    }
  }
  const ask = () => {
    try {
      chrome.runtime.sendMessage({ type: 'status' }, (r) => { if (!chrome.runtime.lastError) apply(!!(r && r.active)); });
    } catch (e) { /* extension was reloaded; the next page load re-arms this */ }
  };
  ask();
  setInterval(ask, 3000);                                             // a session can start or end while the page is open

  // --- the search bar used as an AI: check questions before they are searched ---
  const box = () => document.querySelector('textarea[name="q"], input[name="q"]');
  const looksLikeAsk = (q) => q.trim().split(/\s+/).length >= 4 || /\?/.test(q);
  const go = (q) => { location.href = location.origin + '/search?q=' + encodeURIComponent(q); };

  function showNote(msg) {
    const d = document.createElement('div');
    d.textContent = msg;
    d.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#222;color:#fff;' +
      'font:600 13px/1.4 -apple-system,sans-serif;padding:9px 14px;border-radius:10px;box-shadow:0 4px 18px rgba(0,0,0,.35)';
    document.documentElement.appendChild(d);
    setTimeout(() => d.remove(), 2500);
    return d;
  }

  async function guardSearch(e) {
    if (!active || busy) return;
    const el = box();
    const q = el ? (el.value || '').trim() : '';
    if (!q || !looksLikeAsk(q)) return;
    e.preventDefault(); e.stopImmediatePropagation();                // hold it now; decide after
    busy = true;
    const note = showNote('HonestHands is checking your search…');
    let verdict = null;
    try {
      verdict = await new Promise((res) => chrome.runtime.sendMessage({ type: 'check', text: q, site: 'google.com search', url: location.href, images: [], nImages: 0 }, (r) => res(chrome.runtime.lastError ? null : r)));
    } catch (err) { verdict = null; }
    busy = false;
    note.remove();
    if (!verdict || verdict.active === false || verdict.verdict === 'allow') go(q);   // allowed (or the app is unreachable): search as normal
    // otherwise the app is showing its warning; the search stays where it is
  }

  window.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    const el = document.activeElement;
    if (el && el === box()) guardSearch(e);
  }, true);
  window.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('button[aria-label="Search"], button[type="submit"], [role="button"][aria-label="Search"]');
    if (b && box() && (box().value || '').trim()) guardSearch(e);
  }, true);
})();
