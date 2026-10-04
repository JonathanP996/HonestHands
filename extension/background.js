// Background service worker. It is NOT subject to any page's Content Security Policy,
// so it (not the content script) is what talks to the HonestHands desktop app.
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

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'status') {
    appStatus().then(sendResponse);
    return true;  // async response
  }
  if (msg.type === 'check') {
    appCheck(msg.text, msg.site, msg.url).then(sendResponse);
    return true;
  }
});
