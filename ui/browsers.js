// Choosing the guarded browser + setting up its extension. Used by the first-run setup and by Settings.
// Loaded before app.js; uses its globals (S, api, h, toast).

const BR_MARK = { chrome: 'C', edge: 'E', firefox: 'F', safari: 'S' };
const BR_NOTE = {
  chrome:  'Works with the extension as is.',
  edge:    'Uses the same extension as Chrome.',
  firefox: 'Temporary until Firefox restarts (you re-load it after each restart).',
  safari:  'Needs Xcode (free) once, to build a small helper app.',
};

function browserPanelHTML() {
  const b = S.browser || { chosen: '', options: [] }, ext = S.extension || {}, live = !!S.ext_live;
  const pick = b.options.map(o => `<button class="brtile ${b.chosen === o.key ? 'on' : ''} ${o.installed ? '' : 'missing'}" data-pick="${o.key}">
      <span class="brmark">${BR_MARK[o.key]}</span><b>${h(o.name)}</b>
      <span class="brnote">${o.installed ? (b.chosen === o.key ? 'Your guarded browser' : 'Installed') : 'Not installed on this Mac'}</span>
      ${b.chosen === o.key ? '<i class="brtick">✓</i>' : ''}</button>`).join('');
  const info = `<p class="brinfo">While a study session is on, AI websites work <b>only in the browser you choose</b>. Sending a message to an AI site in any other browser is blocked, so there is no easy way around the guard.</p>`;
  if (!b.chosen) return `<div class="brgrid">${pick}</div>${info}`;

  const chosen = b.options.find(o => o.key === b.chosen) || { name: '', kind: '' }, kind = chosen.kind, name = h(chosen.name);
  const ready = !!ext.installed_dir;
  let steps = '';
  if (kind === 'chromium') steps = `
    <li class="${ready ? 'done' : ''}"><div><b>Download the extension</b><span>Saves a folder called <em>HonestHands Extension</em> to your Downloads. Keep it there: ${name} reads the extension from it.</span></div>
      <button class="btn ${ready ? 'ghost' : ''}" data-act="prep">${ready ? 'Download again' : 'Download'}</button></li>
    <li class="${ready ? '' : 'dim'}"><div><b>Open ${name}’s extensions page</b><span>Switch on <em>Developer mode</em> (top right).</span></div>
      <button class="btn ghost" data-act="page" ${ready ? '' : 'disabled'}>Open ${name}</button></li>
    <li class="${ready ? '' : 'dim'}"><div><b>Click “Load unpacked” and choose that folder</b><span>It’s the <em>HonestHands Extension</em> folder in Downloads. It stays on after that.</span></div>
      <button class="btn ghost" data-act="folder" ${ready ? '' : 'disabled'}>Show in Finder</button></li>`;
  else if (kind === 'firefox') steps = `
    <li class="${ready ? 'done' : ''}"><div><b>Download the Firefox extension</b><span>Saves a folder called <em>HonestHands Extension (Firefox)</em> to your Downloads, packaged the way Firefox wants it.</span></div>
      <button class="btn ${ready ? 'ghost' : ''}" data-act="prep">${ready ? 'Download again' : 'Download'}</button></li>
    <li class="${ready ? '' : 'dim'}"><div><b>Open Firefox’s add-on debugging page</b><span>Click <em>Load Temporary Add-on…</em></span></div>
      <button class="btn ghost" data-act="page" ${ready ? '' : 'disabled'}>Open Firefox</button></li>
    <li class="${ready ? '' : 'dim'}"><div><b>Choose the file named manifest.json</b><span>It’s inside the Downloads folder you just saved. Firefox forgets temporary add-ons when it quits, so repeat this after a restart.</span></div>
      <button class="btn ghost" data-act="folder" ${ready ? '' : 'disabled'}>Show in Finder</button></li>`;
  else if (kind === 'safari') steps = `
    <li class="${ready ? 'done' : ''}"><div><b>Build the Safari extension</b><span>Takes about 15 seconds. Needs Xcode installed (free in the App Store).</span></div>
      <button class="btn ${ready ? 'ghost' : ''}" data-act="prep">${ready ? 'Build again' : 'Build for Safari'}</button></li>
    <li class="${ready ? '' : 'dim'}"><div><b>Open the helper app once</b><span>macOS may ask you to confirm. It adds the extension to Safari.</span></div>
      <button class="btn ghost" data-act="app" ${ready ? '' : 'disabled'}>Open it</button></li>
    <li class="${ready ? '' : 'dim'}"><div><b>Turn it on in Safari</b><span>Safari › Settings › Advanced: tick <em>Show features for web developers</em>. Then Develop › <em>Allow Unsigned Extensions</em>. Then Settings › Extensions: switch on HonestHands and allow it on the AI sites.</span></div>
      <button class="btn ghost" data-act="page" ${ready ? '' : 'disabled'}>Open Safari</button></li>`;
  return `<div class="brgrid">${pick}</div>${info}
    <div class="ostatusbar ${live ? 'ok' : ''}"><i></i>${live ? `Connected. The extension in ${name} just checked in.` : `Waiting for the extension in ${name}…`}</div>
    <ol class="obig-steps">${steps}</ol>
    <p class="brnote2">${h(BR_NOTE[b.chosen] || '')}</p>`;
}

// Wires every button inside `root`. onChange() repaints the surrounding screen.
function wireBrowserPanel(root, onChange) {
  root.querySelectorAll('[data-pick]').forEach(t => t.onclick = async () => {
    const r = await api().set_browser(t.dataset.pick);
    if (r && r.error) return toast(r.error);
    S = r; onChange();
  });
  const act = (name, fn) => root.querySelectorAll(`[data-act="${name}"]`).forEach(b => b.onclick = () => fn(b));
  act('prep', async (b) => {
    const label = b.textContent; b.disabled = true; b.textContent = (S.browser.chosen === 'safari') ? 'Building…' : 'Saving…';
    const r = await api().prepare_extension();
    if (r && r.error) { toast(r.error); b.disabled = false; b.textContent = label; return; }
    S = await api().state(); onChange();
  });
  act('page', () => api().open_browser_extensions_page());
  act('folder', () => api().open_extension_folder());
  act('app', () => api().launch_extension_app());
}
