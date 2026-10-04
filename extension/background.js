// Background service worker. Not subject to page CSP, so it talks to the desktop app.
//
// Design: the extension does NOT need to be "always awake". Manifest V3 workers sleep,
// and that's fine — the only thing that MUST work live is guarding a send, and a send
// always wakes the worker automatically. The heartbeat below is ONLY so the desktop app
// can show "a guarded browser is present". It runs via chrome.alarms, which wake the
// worker on schedule even after it sleeps. No dependency on tabs or focus.

const APP = 'http://127.0.0.1:7673';

async function appStatus() {
  try {
    const r = await fetch(APP + '/status', { method: 'GET' });
    const j = await r.json();
    return { active: !!j.active, reachable: true };
  } catch (e) {
    return { active: false, reachable: false };
  }
}

async function appCheck(text, site, url) {
  try {
    const r = await fetch(APP + '/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, site, url })
    });
    return await r.json();
  } catch (e) {
    return { active: false, verdict: 'allow', reachable: false };
  }
}

// Content scripts talk to the app through here (page CSP can't block this path).
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'check')  { appCheck(msg.text, msg.site, msg.url).then(sendResponse); return true; }
  // 'status'/'ping' both just report presence + session state.
  appStatus().then(sendResponse);
  return true;
});

// Presence heartbeat via alarms (survive worker sleep). 30s is Chrome's practical minimum.
function ensureAlarm() {
  chrome.alarms.get('hh', (a) => { if (!a) chrome.alarms.create('hh', { periodInMinutes: 0.5 }); });
}
chrome.runtime.onInstalled.addListener(ensureAlarm);
chrome.runtime.onStartup.addListener(() => { ensureAlarm(); appStatus(); });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === 'hh') appStatus(); });

// Fire one ping as soon as the worker loads/wakes for any reason.
ensureAlarm();
appStatus();
