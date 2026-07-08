// Dashboard smoke test — runs the real dashboard JS + real ECharts against a
// stubbed DOM in Node, driving chat selection / presets / ranges and reporting
// chart-render errors. No browser needed.
//
// Usage: node scripts/dashboard_smoke.js <path-to-Dashboard-dir>
//
// Caveats: the stub cannot render the calendar-coordinate chart (cCal) — its
// failure is expected here and verified separately via ECharts SSR; real
// browsers render it fine.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const DASH = process.argv[2] || 'Dashboard';

const html = fs.readFileSync(path.join(DASH, 'index.html'), 'utf8');

// --- minimal DOM stubs ------------------------------------------------------
function makeEl(tag) {
  const el = {
    tagName: (tag || 'div').toUpperCase(), children: [], style: {}, dataset: {},
    _text: '', _html: '', className: '', value: '', id: '',
    attributes: {}, _listeners: {}, options: [],
    remove(i) { if (typeof i === 'number') this.options.splice(i, 1); },
    setAttribute(k, v) { this.attributes[k] = String(v); if (k === 'id') this.id = v; },
    getAttribute(k) { return this.attributes[k] ?? null; },
    appendChild(c) { this.children.push(c); if (c.tagName === 'OPTION') this.options.push(c); c.parentNode = this; if (c.id) byId[c.id] = c; if (c.tagName === 'SCRIPT' && c.src) { loadScript(c.src); queue.push(() => { if (c.onload) c.onload(); }); } return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); return c; },
    addEventListener(t, fn) { (this._listeners[t] ||= []).push(fn); },
    removeEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return { forEach() {} }; },
    getBoundingClientRect() { return { width: 800, height: 400, top: 0, left: 0 }; },
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    focus() {}, blur() {}, click() {},
    getContext() {
      return new Proxy({ measureText: (t) => ({ width: 8 * String(t).length }), createLinearGradient: () => ({ addColorStop() {} }), createRadialGradient: () => ({ addColorStop() {} }), getImageData: () => ({ data: [] }), canvas: { width: 800, height: 400 } }, { get(t, k) { return k in t ? t[k] : () => {}; }, set() { return true; } });
    },
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v ?? ''); },
    get innerHTML() {
      return this._text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },
    set innerHTML(v) { this._html = String(v ?? ''); this.children = []; },
    clientWidth: 800, clientHeight: 400, offsetWidth: 800, offsetHeight: 400,
  };
  return el;
}
const byId = {};
for (const m of html.matchAll(/id="([^"]+)"/g)) byId[m[1]] = makeEl('div');
for (const m of html.matchAll(/id=\\?"([A-Za-z]\w*)\\?"/g)) byId[m[1]] ||= makeEl('div');
for (const m of html.matchAll(/id='([^']+)'/g)) byId[m[1]] ||= makeEl('div');
const inlineJsAll = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
for (const m of inlineJsAll.matchAll(/id=\\"(\w+)\\"|id="(\w+)"/g)) { const id = m[1] || m[2]; if (id) byId[id] ||= makeEl('div'); }

const scriptsLoaded = [];
function loadScript(src) {
  const p = path.join(DASH, src);
  scriptsLoaded.push(src);
  const code = fs.readFileSync(p, 'utf8');
  vm.runInContext(code, ctx, { filename: src });
  queue.push(() => {});
}
const queue = [];

const documentStub = {
  createElement: makeEl,
  createTextNode: (t) => ({ textContent: t }),
  getElementById: (id) => byId[id] || (byId[id] = makeEl('div')),
  head: makeEl('head'), body: makeEl('body'),
  addEventListener() {}, removeEventListener() {},
  querySelector() { return null; }, querySelectorAll() { return { forEach() {} }; },
  documentElement: makeEl('html'),
};

const sandbox = {
  console, setTimeout: (fn) => { queue.push(fn); return 1; }, clearTimeout() {},
  setInterval: () => 1, clearInterval() {},
  requestAnimationFrame: (fn) => { queue.push(fn); return 1; },
  navigator: { userAgent: 'node' },
  location: { hash: '', href: 'file:///dash/index.html' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addListener() {}, addEventListener() {} }),
  devicePixelRatio: 1,
  document: documentStub,
  Date, Math, JSON, Object, Array, String, Number, Boolean, RegExp, Error, Map, Set, Intl,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
const ctx = vm.createContext(sandbox);

vm.runInContext(fs.readFileSync(path.join(DASH, 'echarts.min.js'), 'utf8'), ctx, { filename: 'echarts.min.js' });
vm.runInContext(`
  (function(){
    var realInit = echarts.init;
    window.__charts = 0; window.__setOptions = 0;
    echarts.init = function(dom, theme, opts){
      var c = realInit.call(echarts, null, null, {renderer:'svg', ssr:true, width:800, height:400});
      window.__charts++;
      var so = c.setOption.bind(c);
      c.setOption = function(o, n){ window.__setOptions++; return so(o, n); };
      c.resize = function(){}; c.dispose = function(){};
      var on = c.on.bind(c); c.on = function(ev, fn){ try { return on(ev, fn); } catch(e) {} };
      c.off = function(){};
      return c;
    };
  })();
`, ctx, { filename: 'patch.js' });

vm.runInContext(fs.readFileSync(path.join(DASH, 'data/manifest.js'), 'utf8'), ctx, { filename: 'manifest.js' });

const inlineScripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
for (const m of inlineScripts) vm.runInContext(m[1], ctx, { filename: 'inline.js' });
for (let i = 0; i < 2000 && queue.length; i++) queue.shift()();

const g = (expr) => vm.runInContext(expr, ctx);
const flush = () => { for (let i = 0; i < 2000 && queue.length; i++) queue.shift()(); };
console.log('scripts lazy-loaded:', scriptsLoaded);

// isolate per-chart failures (cCal is a known stub limitation)
try { g("(function(){var _sc=setChart; setChart=function(id,opt){try{_sc(id,opt);}catch(e){if(id!=='cCal'&&id!=='cgCal')console.log('CHART FAIL:',id,'-',e.message.slice(0,60));}};})()"); } catch (e) {}

let failed = false;
try {
  // 1v1 chat (biggest)
  const first = g('DASHBOARD_MANIFEST[0].id');
  g(`selectChat(${JSON.stringify(first)})`); flush();
  console.log('1v1', first, '| isGroup:', g('state.isGroup'), '| charts:', g('window.__charts'), '| setOptions:', g('window.__setOptions'));
  g("applyPreset('90')");
  g("applyPreset('all')");
  console.log('1v1 presets OK | setOptions:', g('window.__setOptions'));

  // --- Findings: 1v1 chat should lazy-load data/insights.js and render cards.
  flush();
  const fbox1 = byId['findingsBox'] ? byId['findingsBox']._html : '';
  const has1 = /class="finding /.test(fbox1);
  console.log('findings 1v1 | insightsLoaded:', g('!!window.INSIGHTS'),
    '| lazyLoaded insights.js:', scriptsLoaded.includes('data/insights.js'),
    '| renderedCards:', has1);
  if (!has1) throw new Error('1v1 Findings section rendered no cards');

  // --- Findings empty-state: a chat with no findings shows the empty line,
  //     not a crash. Pick any dyad absent from window.INSIGHTS.
  const emptyId = g("(function(){var ins=window.INSIGHTS||{};" +
    "var m=DASHBOARD_MANIFEST.filter(function(x){return !x.is_group && !ins[x.id];})[0];" +
    "return m?m.id:null;})()");
  if (emptyId) {
    g(`selectChat(${JSON.stringify(emptyId)})`); flush();
    const fboxE = byId['findingsBox'] ? byId['findingsBox']._html : '';
    const isEmpty = /Nothing stands out/.test(fboxE);
    console.log('findings empty-state | chat:', emptyId, '| emptyStateShown:', isEmpty);
    if (!isEmpty) throw new Error('finding-less chat did not show the empty state');
    g(`selectChat(${JSON.stringify(first)})`); flush(); // back to the big chat
  } else {
    console.log('every dyad has findings — empty-state not exercised');
  }

  // group chat (first group in manifest, if any)
  const gid = g('(DASHBOARD_MANIFEST.filter(function(m){return m.is_group;})[0]||{}).id');
  if (gid) {
    g(`selectChat(${JSON.stringify(gid)})`); flush();
    console.log('group', gid, '| isGroup:', g('state.isGroup'), '| charts:', g('window.__charts'), '| setOptions:', g('window.__setOptions'));
    g("applyPreset('90')");
    console.log('group preset OK | setOptions:', g('window.__setOptions'));
    // and back
    g(`selectChat(${JSON.stringify(first)})`); flush();
    console.log('back to 1v1 | isGroup:', g('state.isGroup'));
  } else {
    console.log('no group chats in manifest — group mode not exercised');
  }

  // Telegram chat (first telegram entry in manifest, if any)
  const tid = g("(DASHBOARD_MANIFEST.filter(function(m){return (m.platform||'instagram')==='telegram';})[0]||{}).id");
  if (tid) {
    g(`selectChat(${JSON.stringify(tid)})`); flush();
    console.log('telegram', tid, '| platform:', g(`(DASHBOARD_MANIFEST.filter(function(m){return m.id===${JSON.stringify(tid)};})[0]||{}).platform`),
      '| hasTgSignals:', g('!!(state.chat&&state.chat.telegram)'), '| charts:', g('window.__charts'), '| setOptions:', g('window.__setOptions'));
    g("applyPreset('all')");
    console.log('telegram preset OK | setOptions:', g('window.__setOptions'));

    // Platform filter: restrict to telegram only, then back to all.
    g("buildPlatformFilter()");
    g("togglePlatform('telegram')");
    const visTg = g("visibleManifest().every(function(m){return (m.platform||'instagram')==='telegram';})");
    const visN = g("visibleManifest().length");
    console.log('platform filter -> telegram only | allTelegram:', visTg, '| visibleCount:', visN);
    g("togglePlatform('telegram')"); // back to ALL
    console.log('platform filter reset | visibleCount:', g("visibleManifest().length"), '/ total:', g("DASHBOARD_MANIFEST.length"));
  } else {
    console.log('no telegram chats in manifest — telegram mode / platform filter not exercised');
  }

  // Connected (owner) mode — pinned "You — Connected" entry.
  // Ensure platform filter is at ALL so the default connected variant is 'all'.
  g("selectedPlatforms=null; buildPlatformFilter();");
  g('selectConnected()'); flush();
  console.log('connected | isConnected:', g('state.isConnected'),
    '| variant:', g('state.connectedVariant'),
    '| owner set:', g('!!(state.connected&&state.connected.owner)'),
    '| daily days:', g('state.connected?Object.keys(state.connected.daily).length:0'),
    '| charts:', g('window.__charts'), '| setOptions:', g('window.__setOptions'));
  if (g('state.connectedVariant') !== 'all') throw new Error('default connected variant should be all');
  g("applyPreset('90')");
  console.log('connected preset OK | setOptions:', g('window.__setOptions'));

  // --- Findings: Connected view should render its own finding cards.
  flush();
  const fboxC = byId['findingsBox'] ? byId['findingsBox']._html : '';
  const hasC = /class="finding /.test(fboxC) || /Nothing stands out/.test(fboxC);
  console.log('findings connected | rendered:', hasC,
    '| cards:', /class="finding /.test(fboxC));
  if (!hasC) throw new Error('Connected Findings section did not render');

  // Variant switching via the platform filter while in connected mode.
  const hasTg2 = g("MANIFEST.some(function(m){return (m.platform||'instagram')==='telegram';})");
  if (hasTg2) {
    g("applyPreset('all');");
    g("togglePlatform('telegram')"); flush(); // Instagram off? no — turns telegram-only on toggle from ALL adds telegram
    // From ALL (null), toggling telegram makes selectedPlatforms={telegram} -> telegram variant.
    console.log('connected -> telegram | variant:', g('state.connectedVariant'),
      '| platforms:', g('JSON.stringify((state.connected||{}).platforms)'),
      '| isConnected:', g('state.isConnected'));
    if (g('state.connectedVariant') !== 'telegram') throw new Error('expected telegram variant active');
    if (!g('state.connected && state.connected.variant==="telegram"')) throw new Error('telegram payload not active');
    // Back to ALL.
    g("togglePlatform('telegram')"); flush();
    console.log('connected -> back to ALL | variant:', g('state.connectedVariant'));
    if (g('state.connectedVariant') !== 'all') throw new Error('expected all variant after reset');
  } else {
    console.log('single-platform manifest — connected variant switching not exercised');
  }

  // Back to a normal 1v1 chat: connected state must fully unwind.
  g("selectedPlatforms=null; buildPlatformFilter();");
  g(`selectChat(${JSON.stringify(first)})`); flush();
  console.log('back from connected | isConnected:', g('state.isConnected'), '| isGroup:', g('state.isGroup'));
  if (g('state.isConnected')) throw new Error('connected state did not unwind');
} catch (e) {
  failed = true;
  console.log('SMOKE FAILED:', e.message, '\n', (e.stack || '').split('\n').slice(0, 3).join('\n'));
}
console.log(failed ? 'SMOKE FAILED' : 'SMOKE OK');
process.exit(failed ? 1 : 0);
