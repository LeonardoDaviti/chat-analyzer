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

  // --- Findings under charts (M2.2): each anchored finding renders as a
  //     compact strip inside its chart card (host id "fu-<anchor>"); only
  //     unanchored findings stay in the "Other findings" box. Helper: collect
  //     all strip HTML from every anchor host.
  const anchors = g('ANCHOR_IDS');
  const underHtml = () => { let s = ''; for (const a of anchors) { const h = byId['fu-' + a]; if (h && h._html) s += h._html; } return s; };
  const ridsIn = (h) => [...String(h).matchAll(/data-rid="([^"]*)"/g)].map(m => m[1]).filter(Boolean);

  flush();
  const under1 = underHtml();
  const has1 = /class="fstrip /.test(under1);
  console.log('findings 1v1 | insightsLoaded:', g('!!window.INSIGHTS'),
    '| lazyLoaded insights.js:', scriptsLoaded.includes('data/insights.js'),
    '| stripsUnderCharts:', has1);
  if (!has1) throw new Error('1v1 findings rendered no strips under charts');

  // Pick the biggest 1v1 chat that actually has all-time findings.
  const bigDyad = g("(function(){var ins=window.INSIGHTS||{};" +
    "var m=DASHBOARD_MANIFEST.filter(function(x){return !x.is_group && (ins[x.id]||[]).length;})[0];" +
    "return m?m.id:null;})()") || first;
  g(`selectChat(${JSON.stringify(bigDyad)})`); flush();

  // Find a narrow preset where windowed daily-table findings actually fire.
  let winPreset = null;
  for (const p of ['90', '180', '365']) {
    const n = g(`(function(){var wf=computeWindowedFindings(state.chat.daily,state.users,` +
      `addDays(state.fullEnd,-(${p}-1)),state.fullEnd,state.fullStart,state.fullEnd);return wf.length;})()`);
    if (n > 0) { winPreset = p; break; }
  }
  if (winPreset) {
    g(`applyPreset('${winPreset}')`); flush();
    const underW = underHtml();
    const fboxW = byId['findingsBox'] ? byId['findingsBox']._html : '';
    const winTag = /in this window/.test(underW);
    const allTag = /all-time/.test(underW);
    const ridsUnder = ridsIn(underW), ridsOther = ridsIn(fboxW);
    const allR = ridsUnder.concat(ridsOther);
    const noDup = allR.length === new Set(allR).size;
    const otherOnlyUnanchored = ridsOther.every(r => !ridsUnder.includes(r));
    console.log('windowed strips', winPreset + 'd | chat:', bigDyad,
      '| inThisWindowTag:', winTag, '| allTimeTag:', allTag,
      '| ruleIds:', allR.length, '| noDuplicateIds:', noDup,
      '| otherOnlyUnanchored:', otherOnlyUnanchored);
    if (!winTag) throw new Error('windowed range shows no "in this window" strip');
    if (!ridsUnder.length) throw new Error('no finding strips under charts on windowed range');
    if (!noDup) throw new Error('a rule id appears twice page-wide (dedup failed)');
    if (!otherOnlyUnanchored) throw new Error('Other-findings box holds an anchored rule id');
  } else {
    console.log('no windowed findings fire for bigDyad in tested presets — window tag not asserted');
  }

  g("applyPreset('all')"); flush();
  const underF = underHtml();
  const fullWin = /in this window/.test(underF);
  const fullStrips = /class="fstrip /.test(underF);
  console.log('full-range findings | anyWindowedTag:', fullWin, '| stripsUnderCharts:', fullStrips);
  if (fullWin) throw new Error('full range should not render windowed strips');
  if (!fullStrips) throw new Error('full range should render all-time strips under charts');
  g(`selectChat(${JSON.stringify(first)})`); flush(); // back to the biggest chat

  // --- Findings empty-state: a chat with no findings shows the empty line.
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

  // --- Hide chats (M1.4): hide a visible dyad -> it leaves the visible list and
  //     appears in the hidden section; unhide restores it.
  const hideId = g("(function(){var v=visibleManifest().filter(function(m){return !m.is_group && m.id!==state.chatId;});return v.length?v[0].id:null;})()");
  if (hideId) {
    const wasVisible = g(`visibleManifest().some(function(m){return m.id===${JSON.stringify(hideId)};})`);
    g(`hideChat(${JSON.stringify(hideId)})`); flush();
    const stillVisible = g(`visibleManifest().some(function(m){return m.id===${JSON.stringify(hideId)};})`);
    const inHidden = g(`hiddenManifest().some(function(m){return m.id===${JSON.stringify(hideId)};})`);
    console.log('hide chat | id:', hideId, '| wasVisible:', wasVisible,
      '| leftVisibleList:', !stillVisible, '| inHiddenSection:', inHidden);
    if (stillVisible) throw new Error('hidden chat still appears in the visible list');
    if (!inHidden) throw new Error('hidden chat not in the hidden section');
    g(`unhideChat(${JSON.stringify(hideId)})`); flush();
    if (!g(`visibleManifest().some(function(m){return m.id===${JSON.stringify(hideId)};})`))
      throw new Error('unhide did not restore the chat');
    console.log('unhide restored | visibleCount:', g('visibleManifest().length'));
  } else {
    console.log('no spare dyad to hide — hide/unhide not exercised');
  }

  // --- Compare mode (M2.3): enter compare, select 3 dyads, assert every metric
  //     chart rendered, then a range change re-renders them.
  g('selectCompare()'); flush();
  if (!g('state.isCompare')) throw new Error('compare mode not entered');
  g('(function(){state.compareIds=[];var ds=visibleManifest().filter(function(m){return !m.is_group;}).slice(0,3);' +
    'ds.forEach(function(m){toggleCompare(m.id);});})()'); flush();
  const cmpSel = g('state.compareIds.length');
  const cmpN = g('CMP_METRICS.length');
  const cmpCharts = g('CMP_METRICS.filter(function(mt){return !!charts[mt.id];}).length');
  console.log('compare | selectedDyads:', cmpSel, '| metricCharts:', cmpCharts, '/', cmpN,
    '| findingsRendered:', /cmp-dyad-row/.test(byId['cmpFindings'] ? byId['cmpFindings']._html : ''));
  if (cmpSel !== 3) throw new Error('expected exactly 3 selected dyads in compare');
  if (cmpCharts < cmpN) throw new Error('not every compare metric chart rendered');
  const cmpBefore = g('window.__setOptions');
  g("applyPreset('90')"); flush();
  const cmpAfter = g('window.__setOptions');
  console.log('compare range change | setOptionsDelta:', cmpAfter - cmpBefore);
  if (cmpAfter <= cmpBefore) throw new Error('compare did not re-render on range change');
  g("applyPreset('all')");
  g(`selectChat(${JSON.stringify(first)})`); flush();
  if (g('state.isCompare')) throw new Error('compare state did not unwind on chat select');

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

  // --- M3.1 capture-layer cards (calls, voice, reactions, stickers, edits).
  //     Gate invariant (must hold for EVERY chat): the Calls section renders iff
  //     the chat has a `calls` block; the Telegram-signals section (which now
  //     hosts the voice/reaction/signature/edit-latency/sticker cards) renders
  //     iff the chat carries a `telegram` block. Instagram-only chats therefore
  //     show none of these UNLESS they have call events.
  g("selectedPlatforms=null; buildPlatformFilter();");
  const gateOK = () => {
    const hasTg = g('!!(state.chat&&state.chat.telegram)');
    const hasCalls = g('!!(state.chat&&state.chat.calls)');
    const tgSec = g('telegramSection()') !== '';
    const callSec = g('callsSection()') !== '';
    return { hasTg, hasCalls, tgSec, callSec, ok: (tgSec === hasTg) && (callSec === hasCalls) };
  };
  if (tid) {
    g(`selectChat(${JSON.stringify(tid)})`); g("applyPreset('all')"); flush();
    const sec = g('telegramSection()');
    const newTgCards = ['cTgVoice', 'cTgReactLat', 'tgSigBox', 'cTgEditLat', 'tgStickerBox'];
    const cardsPresent = newTgCards.every(id => sec.includes(id));
    const gt = gateOK();
    // charts freshly set for the current chat -> present in the registry
    const drawn = ['cTgVoice', 'cTgReactLat', 'cTgEditLat'].filter(id => !!g(`charts[${JSON.stringify(id)}]`)).length;
    console.log('telegram new cards | id:', tid, '| tgCardsInSkeleton:', cardsPresent,
      '| tgChartsDrawn:', drawn + '/3', '| gateInvariant:', gt.ok,
      '| callsSection:', gt.callSec, '(hasCalls ' + gt.hasCalls + ')');
    if (!cardsPresent) throw new Error('telegram chat is missing the new signal cards');
    if (drawn < 3) throw new Error('telegram new charts did not render');
    if (!gt.ok) throw new Error('gate invariant failed on telegram chat');
    if (gt.hasCalls) {
      if (!g('callsSection()').includes('cCallsTime')) throw new Error('calls section missing cCallsTime');
      if (!g('charts["cCallsTime"]')) throw new Error('cCallsTime chart did not render');
    }
  }
  // Find a plain Instagram dyad with NO calls and NO telegram; assert it shows
  // none of the new sections (the negative half of the gate).
  const igDyads = g("DASHBOARD_MANIFEST.filter(function(m){return (m.platform||'instagram')==='instagram'&&!m.is_group;}).map(function(m){return m.id;})");
  let plainChecked = false;
  for (let i = 0; i < igDyads.length && i < 12; i++) {
    g(`selectChat(${JSON.stringify(igDyads[i])})`); flush();
    const gt = gateOK();
    if (!gt.ok) throw new Error('gate invariant failed on instagram chat ' + igDyads[i]);
    if (!gt.hasCalls && !gt.hasTg) {
      console.log('instagram gate | id:', igDyads[i], '| telegramSection:', gt.tgSec,
        '| callsSection:', gt.callSec, '(both should be false)');
      if (gt.tgSec || gt.callSec) throw new Error('plain instagram chat rendered capture-layer cards');
      plainChecked = true;
      break;
    }
  }
  if (!plainChecked) console.log('no plain instagram dyad (all have calls/telegram) — negative gate not exercised');
  g(`selectChat(${JSON.stringify(first)})`); flush();

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

  // --- M3.2: "Merge contacts" manage panel present in connected-all, plus a
  //     synthetic-fixture render of a merged (⧉) entity. No identities are ever
  //     created over the real contacts — we only exercise the render helpers.
  g('safe(renderConnMerge,"cmerge")'); flush();
  const mergeHtml = byId['connMergeBody'] ? byId['connMergeBody']._html : '';
  const badge = g("pfBadge('merged')");
  const mlabel = g("connLabel({name:'Fixture',platform:'merged'})");
  const msplit = g("connSplit({merged:true,platforms:{instagram:2,telegram:1}})");
  console.log('connected merge panel | hasPicker:', /Merge selected/.test(mergeHtml),
    '| badge:', badge, '| label:', mlabel, '| split:', msplit);
  if (!/Merge selected/.test(mergeHtml)) throw new Error('merge manage panel not rendered in connected-all');
  if (badge !== '⧉') throw new Error('merged badge should be ⧉');
  if (mlabel.indexOf('⧉') !== 0) throw new Error('merged label should lead with the ⧉ badge');
  if (!/📸/.test(msplit) || !/✈/.test(msplit)) throw new Error('merged split should list both platforms');

  // --- M3.1: reaction-latency leaderboards (both directions) in Contact
  //     leaderboards. Charts render whenever ≥1 contact clears the ≥30 gate.
  g("applyPreset('all')"); flush();
  const lbAll = g('(state.connected&&state.connected.leaderboards)||{}');
  const nYou = g('((state.connected&&state.connected.leaderboards&&state.connected.leaderboards.react_latency_you)||[]).length');
  const nThem = g('((state.connected&&state.connected.leaderboards&&state.connected.leaderboards.react_latency_them)||[]).length');
  const reactCharts = ['cxReactYou', 'cxReactThem'].filter(id => !!g(`charts[${JSON.stringify(id)}]`)).length;
  console.log('connected reaction-latency | youBoard:', nYou, '| themBoard:', nThem, '| chartsDrawn:', reactCharts + '/2');
  if ((nYou > 0 || nThem > 0) && reactCharts < 2) throw new Error('reaction-latency leaderboard charts did not render');

  // --- Findings: Connected view renders strips under its charts (or, when a
  //     finding is unanchored, in the Other-findings box).
  flush();
  const underC = underHtml();
  const fboxC = byId['findingsBox'] ? byId['findingsBox']._html : '';
  const hasC = /class="fstrip /.test(underC) || /class="findings-empty/.test(fboxC) || /class="fstrip /.test(fboxC);
  console.log('findings connected | rendered:', hasC,
    '| stripsUnderCharts:', /class="fstrip /.test(underC));
  if (!hasC) throw new Error('Connected Findings did not render');

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
