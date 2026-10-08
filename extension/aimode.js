// HonestHands Guard on Google: while a study session is on, AI Mode and the AI Overview box are removed from the results
// (searches typed into Google or the address bar are checked by the HonestHands app itself).
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
      // climb to the biggest block that holds the overview but no ordinary search result (those are links around a title) and not the search bar
      let el = n.parentElement, block = el;
      for (let i = 0; i < 25 && el && el.parentElement && el !== document.body; i++) {
        const up = el.parentElement;
        if (up.querySelector('a h3') || up.querySelector('textarea[name="q"], input[name="q"]') || up === document.body) break;
        el = up; block = up;
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

})();
