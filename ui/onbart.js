// Hand-drawn scenes for the first-run setup: little bean characters and line art in the app's palette, plus the motion
// that brings them to life (lines draw themselves on, characters bob, wave and blink, sparkles twinkle, confetti on a win).
// Loaded before onboarding.js. Every scene is a 400x240 SVG; colors and motion live in style.css ("First-run setup").

const OART_REDUCED = () => !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

const HEART = 'M0 6C-6 1.5 -9 -1.5 -9 -4.5C-9 -7.5 -6.5 -9 -4.5 -9C-2.5 -9 -.8 -7.8 0 -6C.8 -7.8 2.5 -9 4.5 -9C6.5 -9 9 -7.5 9 -4.5C9 -1.5 6 1.5 0 6Z';
const STAR = 'M0 -8C1 -2.5 2.5 -1 8 0C2.5 1 1 2.5 0 8C-1 2.5 -2.5 1 -8 0C-2.5 -1 -1 -2.5 0 -8Z';
const HAND = ['M8 11V5.5a1.3 1.3 0 0 1 2.6 0V10', 'M10.6 10V4.4a1.3 1.3 0 0 1 2.6 0V10', 'M13.2 10.2V5.4a1.3 1.3 0 0 1 2.6 0V12',
  'M15.8 12V8.6a1.3 1.3 0 0 1 2.5 0c0 3.2.1 4.4-.6 6.3-.8 2.2-2.4 3.6-4.8 3.6-2 0-3.2-.5-4.4-1.9l-2.7-3.2a1.35 1.35 0 0 1 1.9-1.9L7 11'];

const spark = (x, y, c = 'f-sun', s = 1, d = 0) =>
  `<g transform="translate(${x} ${y}) scale(${s})"><g class="a-twk" style="--td:${d}s"><path class="${c}" d="${STAR}"/></g></g>`;
const blob = (cx, cy, r) => `<circle class="f-bd a-nos keep a-popin" cx="${cx}" cy="${cy}" r="${r}"/>`;
const heart = (x, y, c, s = 1, d = 0, cls = 'a-hrt') =>
  `<g transform="translate(${x} ${y}) scale(${s})"><g class="${cls}" style="--hd:${d}s"><path class="${c}" d="${HEART}"/></g></g>`;

// A bean-shaped character standing with its feet at (x, y). c = body color class.
// arms: rest | wave | up | hold | five. extra = markup drawn in the character's own coordinates (it moves with them).
function bean(x, y, c, o = {}) {
  const s = o.s || 1, d = o.d || 0;
  const hand = (cx, cy) => `<circle class="${c}" cx="${cx}" cy="${cy}" r="4.2"/>`;
  const upR = (cls) => `<g class="a-arm ${cls}"><path d="M25 -50C33 -56 37 -64 38 -74"/>${hand(38.5, -78.5)}</g>`;
  const left = o.arms === 'up' ? `<g class="a-arm a-armu-l"><path d="M-25 -50C-33 -56 -37 -64 -38 -74"/>${hand(-38.5, -78.5)}</g>`
                               : '<path d="M-25 -46C-33 -42 -36 -34 -35 -27"/>';
  const right = { wave: upR('a-armw'), up: upR('a-armu-r'), five: upR('a-armf'),
                  hold: `<g class="a-arm a-armh"><path d="M25 -44C34 -44 41 -46 46 -50"/>${hand(48.5, -51.5)}</g>` }[o.arms]
                || '<path d="M25 -46C33 -42 36 -34 35 -27"/>';
  return `<g transform="translate(${x} ${y}) scale(${o.flip ? -s : s} ${s})">
    <ellipse class="f-sh a-nos keep a-shb" cx="0" cy="0" rx="22" ry="4" style="--bd:${d}s"/>
    <g class="a-bob ${o.mood || ''}" style="--bd:${d}s">
      <path d="M-9 -16L-10 -2L-16 -2"/><path d="M9 -16L10 -2L16 -2"/>
      <path class="${c}" d="M0 -90C17 -90 26 -74 26 -52C26 -28 19 -14 0 -14C-19 -14 -26 -28 -26 -52C-26 -74 -17 -90 0 -90Z"/>
      <g class="a-blink"><ellipse class="f-ol a-nos" cx="-8" cy="-63" rx="2.6" ry="3.3"/><ellipse class="f-ol a-nos" cx="8" cy="-63" rx="2.6" ry="3.3"/></g>
      <ellipse class="f-ck a-nos" cx="-15.5" cy="-54" rx="4.5" ry="2.6"/><ellipse class="f-ck a-nos" cx="15.5" cy="-54" rx="4.5" ry="2.6"/>
      <path d="M-5.5 -54Q0 -48.5 5.5 -54"/>
      ${o.extra || ''}${left}${right}
    </g></g>`;
}

const KEY = `<g class="a-keyj"><circle class="f-sun" cx="55" cy="-52" r="7"/><circle class="f-ol a-nos" cx="55" cy="-52" r="2"/>
  <path d="M62 -52H88M81 -52V-45M87 -52V-46"/></g>`;
const MUG = `<g><path class="a-steam nodraw" d="M47 -66C45 -70 49 -72 47 -77"/><path class="a-steam nodraw" style="--sd:.8s" d="M53 -66C51 -70 55 -72 53 -77"/>
  <path class="f-pp" d="M42 -61H58V-47C58 -43 55 -40 50 -40C45 -40 42 -43 42 -47Z"/><path d="M58 -57C64 -57 64 -48 58 -48"/></g>`;

const OSCENES = {
  welcome: (arms = 'wave') => `
    <g class="a-lay a-lay-b">${blob(200, 112, 82)}<circle class="a-ring keep" cx="200" cy="112" r="102"/>
      ${spark(122, 40, 'f-sun', 1, 0)}${spark(288, 34, 'f-lm', .8, .7)}${spark(336, 128, 'f-il', .9, 1.3)}${spark(68, 116, 'f-sun', .7, .4)}${spark(252, 200, 'f-il', .6, 1.8)}</g>
    <g class="a-lay a-lay-f">
      <g class="a-flt" style="--fd:.2s"><g transform="translate(131 45) scale(5.6)" style="stroke-width:.46">
        ${HAND.map(d => `<path class="f-pp" d="${d}"/>`).join('')}<circle class="f-pl a-nos a-nail" cx="12.4" cy="14.6" r="1.35"/></g></g>
      ${heart(266, 60, 'f-ck', 1, .4)}${heart(144, 72, 'f-il', .7, 2.1)}
      ${bean(86, 214, 'f-il', { arms, s: .92 })}
      ${bean(316, 214, 'f-lm', { arms, s: .86, flip: true, d: .7 })}
    </g>`,

  access: () => `
    <g class="a-lay a-lay-b">${blob(200, 112, 80)}${spark(124, 44, 'f-sun', .9, .2)}${spark(266, 26, 'f-il', .7, 1)}${spark(356, 150, 'f-lm', .8, .6)}</g>
    <g class="a-lay a-lay-f">
      <g class="a-flt" style="--fd:.3s"><g class="a-shield">
        <path class="f-pp" d="M200 42L250 61V104C250 139 227 161 200 174C173 161 150 139 150 104V61Z"/>
        <path class="f-lm2" d="M200 57L237 71V104C237 130 221 147 200 158C179 147 163 130 163 104V71Z"/>
        <g class="a-keyhole"><circle class="f-ol a-nos" cx="200" cy="99" r="8.5"/><path class="f-ol a-nos" d="M196 103L193 124H207L204 103Z"/></g>
        <path class="a-scheck nodraw" pathLength="1" d="M181 108L195 122L221 92"/>
      </g></g>
      <g transform="translate(318 64)"><g class="a-bell">
          <path class="f-sun" d="M-15 14C-15 -4 -9 -13 0 -13C9 -13 15 -4 15 14L19 19H-19Z"/><path d="M-5 23A5 5 0 0 0 5 23"/>
          <circle class="f-ol a-nos" cx="0" cy="-15" r="2.6"/></g>
        <path class="a-sw nodraw" d="M25 -6A16 16 0 0 1 25 14"/><path class="a-sw nodraw" style="--sd:.18s" d="M32 -11A23 23 0 0 1 32 19"/></g>
      ${bean(96, 214, 'f-il', { arms: 'hold', s: .92, extra: KEY })}
      ${bean(334, 214, 'f-lm', { arms: 'wave', s: .78, flip: true, d: .5 })}
    </g>`,

  ai: () => `
    <g class="a-lay a-lay-b">${blob(200, 112, 80)}${spark(108, 40, 'f-il', .8, .3)}${spark(298, 30, 'f-sun', 1, 1)}${spark(356, 118, 'f-lm', .7, .1)}</g>
    <g class="a-lay a-lay-f">
      <g class="a-flt" style="--fd:.1s">
        <rect class="f-pp" x="132" y="56" width="136" height="90" rx="10"/>
        <rect class="f-scr" x="142" y="66" width="116" height="70" rx="5"/>
        <rect class="a-lvl a-nos keep" x="143.5" y="67.5" width="113" height="67" rx="4"/>
        <g class="a-chip">
          <path d="M190 79V85M200 79V85M210 79V85M190 115V121M200 115V121M210 115V121M178 90H184M178 100H184M178 110H184M216 90H222M216 100H222M216 110H222"/>
          <rect class="f-il" x="184" y="84" width="32" height="32" rx="7"/><text class="a-chiptx" x="200" y="105" text-anchor="middle">AI</text></g>
        <path class="f-pp" d="M116 146H284L272 160H128Z"/><path d="M186 153H214"/>
      </g>
      <g class="a-dl"><path d="M200 10V36M190 27L200 37L210 27" style="stroke-width:3"/></g>
      <g class="a-okb"><circle class="f-lm a-nos keep" cx="264" cy="56" r="14"/><path class="a-okc nodraw" pathLength="1" d="M257 56L262 61L271 51"/></g>
      ${bean(84, 214, 'f-lm', { arms: 'wave', s: .88 })}
      ${bean(322, 214, 'f-il', { arms: 'hold', s: .84, flip: true, d: .4, extra: MUG })}
    </g>`,

  browser: () => `
    <g class="a-lay a-lay-b">${blob(200, 114, 80)}${spark(100, 46, 'f-sun', .9, .5)}${spark(320, 26, 'f-il', .7, 0)}${spark(76, 186, 'f-lm', .6, 1.2)}</g>
    <g class="a-lay a-lay-f">
      <g class="a-flt" style="--fd:.8s">
        <rect class="f-il2" x="170" y="32" width="136" height="98" rx="11"/><path d="M170 50H306"/>
        <circle class="f-ol a-nos" cx="182" cy="41" r="2.2"/><circle class="f-ol a-nos" cx="190" cy="41" r="2.2"/><circle class="f-ol a-nos" cx="198" cy="41" r="2.2"/></g>
      <g class="a-flt">
        <rect class="f-pp" x="98" y="62" width="156" height="114" rx="12"/><path d="M98 81H254"/>
        <circle class="f-ck" cx="111" cy="71.5" r="3.2"/><circle class="f-sun" cx="121.5" cy="71.5" r="3.2"/><circle class="f-lm" cx="132" cy="71.5" r="3.2"/>
        <rect class="f-il2" x="112" y="94" width="84" height="17" rx="8.5"/><rect class="f-lm2" x="152" y="118" width="88" height="17" rx="8.5"/>
        <rect class="f-il2" x="112" y="142" width="60" height="17" rx="8.5"/>
        <rect class="a-slot nodraw" x="227" y="65" width="17" height="13" rx="3"/>
        <g transform="translate(227.5 62) scale(.68)"><g class="a-pz"><path class="f-lm" d="M0 4H6A4 4 0 1 1 14 4H20V10A4 4 0 1 0 20 18V24H0Z"/></g></g>
      </g>
      <g transform="translate(200 126)"><circle class="a-clk nodraw" cx="0" cy="0" r="7"/>
        <g class="a-cur"><path class="f-pp" d="M0 0L0 20L5.5 15L9.5 24L13 22.5L9 13.5H16Z"/></g></g>
      <g class="a-flt" style="--fd:1.4s"><g transform="translate(34 120)">
        <rect class="f-pp" x="0" y="0" width="54" height="40" rx="7"/><path d="M0 11H54"/>
        <circle class="f-pl" cx="27" cy="26" r="8"/><path class="a-lt" d="M21.5 31.5L32.5 20.5"/></g></g>
      ${bean(332, 214, 'f-il', { arms: 'wave', s: .9, flip: true })}
    </g>`,

  account: () => `
    <g class="a-lay a-lay-b">${blob(200, 120, 80)}${spark(300, 38, 'f-sun', .9, .3)}${spark(62, 140, 'f-il', .7, 1.1)}${spark(350, 150, 'f-lm', .8, .7)}</g>
    <g class="a-lay a-lay-f">
      <g class="a-flt" style="--fd:.6s">
        <path class="f-pp" d="M70 40H130A11 11 0 0 1 141 51V67A11 11 0 0 1 130 78H96L84 89V78H70A11 11 0 0 1 59 67V51A11 11 0 0 1 70 40Z"/>
        <circle class="f-ol a-nos keep a-tdot" cx="86" cy="59" r="3.4"/><circle class="f-ol a-nos keep a-tdot" style="--t:.15s" cx="100" cy="59" r="3.4"/>
        <circle class="f-ol a-nos keep a-tdot" style="--t:.3s" cx="114" cy="59" r="3.4"/></g>
      ${bean(150, 214, 'f-il', { arms: 'five', s: .95 })}
      ${bean(250, 214, 'f-lm', { arms: 'five', s: .95, flip: true })}
      <g transform="translate(200 140)"><g class="a-burst"><path class="nodraw" d="M0 -13V-22M9 -9L15 -15M-9 -9L-15 -15M13 0H21M-13 0H-21"/></g></g>
      ${heart(200, 118, 'f-ck', 1, 0, 'a-hrt5')}${heart(216, 110, 'f-il', .7, .25, 'a-hrt5')}
    </g>`,

  klass: () => `
    <g class="a-lay a-lay-b">${blob(200, 118, 80)}${spark(112, 44, 'f-il', .8, .2)}${spark(300, 36, 'f-sun', 1, .9)}${spark(356, 140, 'f-lm', .6, 1.5)}</g>
    <g class="a-lay a-lay-f">
      <rect class="f-il" x="144" y="190" width="114" height="19" rx="4"/><path d="M155 190V209"/>
      <rect class="f-lm" x="152" y="171" width="100" height="19" rx="4"/><path d="M162 171V190"/>
      <rect class="f-pl" x="140" y="152" width="106" height="19" rx="4"/><path class="a-lt" d="M150 152V171"/>
      <g transform="rotate(-6 200 90)"><g class="a-flt" style="--fd:.3s">
        <path class="f-pp" d="M168 44H222L234 56V134H168Z"/><path d="M222 44V56H234"/>
        <rect class="a-hl a-nos keep" x="176" y="74" width="50" height="11" rx="3"/>
        <path d="M178 64H214M178 79.5H222M178 94H218M178 107H224M178 120H204"/></g></g>
      <g transform="translate(238 100)"><g class="a-mag"><circle class="f-glass" cx="0" cy="0" r="13"/><path d="M9.5 9.5L19 19" style="stroke-width:4.5"/></g></g>
      ${bean(80, 214, 'f-lm', { arms: 'wave', s: .86, d: .3 })}
      ${bean(330, 214, 'f-il', { arms: 'up', s: .9, flip: true })}
    </g>`,

  finish: () => OSCENES.welcome('up'),
};

function oartHTML(key, cls = '') {
  return `<div class="oart-wrap ${cls}" data-art="${key}"><svg class="oart" viewBox="0 0 400 240" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${OSCENES[key]()}</svg></div>`;
}

// Draw the scene on: every outline traces itself in document order, then its color fills in; dots pop.
function inkArt(svg) {
  if (!svg || OART_REDUCED()) return;
  let i = 0;
  svg.querySelectorAll('path,circle,ellipse,rect,line,polyline').forEach(el => {
    const c = el.getAttribute('class') || '';
    if (/\b(keep|nodraw)\b/.test(c)) return;
    const delay = Math.min(i++ * 0.04, 1.3);
    if (/\ba-nos\b/.test(c)) { el.style.animation = `opop .45s cubic-bezier(.3,1.6,.5,1) ${(delay + .45).toFixed(2)}s both`; return; }
    const len = typeof el.getTotalLength === 'function' ? el.getTotalLength() : 0;
    if (!len) return;
    el.style.strokeDasharray = `${len} ${len}`;
    el.style.strokeDashoffset = len;
    const fill = /\bf-/.test(c) ? `, ofillin .6s ease ${(delay + .4).toFixed(2)}s both` : '';
    el.style.animation = `odraw ${(.6 + Math.min(len, 420) / 700).toFixed(2)}s cubic-bezier(.55,.1,.3,1) ${delay.toFixed(2)}s forwards${fill}`;
  });
}

// The scene leans a little toward the pointer (background one way, foreground the other).
function oartParallax(host) {
  if (!host || host._par || OART_REDUCED()) return;
  host._par = true;
  host.addEventListener('mousemove', (e) => {
    const r = host.getBoundingClientRect();
    host.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 2 - 1).toFixed(3));
    host.style.setProperty('--my', ((e.clientY - r.top) / r.height * 2 - 1).toFixed(3));
  });
  host.addEventListener('mouseleave', () => { host.style.setProperty('--mx', 0); host.style.setProperty('--my', 0); });
}

const OCF_COLORS = ['#C99ACB', '#A9B620', '#8B5B7E', '#F5CF6B', '#F2A2B6', '#9FD3C7', '#1D2F2A', '#E2E8A8'];
function oconfetti(x, y, n = 26, power = 1) {
  if (OART_REDUCED()) return;
  const layer = document.createElement('div');
  layer.className = 'ocf-layer';
  for (let k = 0; k < n; k++) {
    const p = document.createElement('i'), b = document.createElement('b');
    const ang = Math.random() * Math.PI * 2, dist = (50 + Math.random() * 130) * power;
    p.style.left = x + 'px'; p.style.top = y + 'px';
    p.style.setProperty('--dx', Math.round(Math.cos(ang) * dist) + 'px');
    p.style.setProperty('--up', Math.round(-(30 + Math.random() * 110) * power) + 'px');
    p.style.setProperty('--fall', Math.round((70 + Math.random() * 150) * power) + 'px');
    p.style.setProperty('--r', Math.round(Math.random() * 900 - 450) + 'deg');
    p.style.setProperty('--t', (1 + Math.random() * .7).toFixed(2) + 's');
    b.style.background = OCF_COLORS[k % OCF_COLORS.length];
    b.className = ['', 'round', 'strip'][k % 3];
    p.appendChild(b); layer.appendChild(p);
  }
  document.body.appendChild(layer);
  setTimeout(() => layer.remove(), 2000);
}
function oconfettiAt(el, n, power) {
  if (!el || !el.getBoundingClientRect) return;
  const r = el.getBoundingClientRect();
  oconfetti(r.left + r.width / 2, r.top + r.height / 2, n, power);
}

// Count a number up (or down) smoothly instead of jumping.
function otween(el, to, ms = 700) {
  if (!el) return;
  const from = parseFloat(el.textContent) || 0;
  if (from === to || OART_REDUCED() || !window.requestAnimationFrame) { el.textContent = to; return; }
  const t0 = performance.now(), id = (el._tw = (el._tw || 0) + 1);
  const step = (t) => {
    if (el._tw !== id) return;
    const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
