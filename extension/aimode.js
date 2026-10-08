// HonestHands Guard: keeps Google's "AI Mode" (a chat inside the search page) shut while a study session is on.
// A normal search is left alone. When the app isn't running or no session is active, this does nothing.
(() => {
  const isAiMode = () => /(^|[?&])udm=50(&|$)/.test(location.search);
  const entry = 'a[href*="udm=50"], [aria-label="AI Mode"], [aria-label="AI mode"]';
  const style = document.createElement('style');
  style.textContent = entry + ' { display: none !important; }';

  const apply = (active) => {
    if (!active) { style.remove(); return; }
    (document.head || document.documentElement).appendChild(style);
    if (isAiMode()) {
      const u = new URL(location.href);
      u.searchParams.delete('udm');                 // back to the normal results for the same words
      location.replace(u.toString());
    }
  };
  const ask = () => {
    try {
      chrome.runtime.sendMessage({ type: 'status' }, (r) => { if (!chrome.runtime.lastError) apply(!!(r && r.active)); });
    } catch (e) { /* extension was reloaded; the next page load re-arms this */ }
  };
  ask();
  setInterval(ask, 4000);                           // a session can start or end while the page is open
})();
