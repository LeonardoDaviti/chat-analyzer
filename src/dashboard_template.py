"""HTML/CSS/JS template for the interactive dashboard.

``render_index_html()`` returns the full ``index.html`` written by the exporter.
The page is framework-free: vanilla JS + vendored ECharts. Chat data files are
lazy-loaded by injecting ``<script src="data/{slug}.js">`` on selection (works on
``file://``; ``fetch()`` does not, so it is never used).

All aggregation happens client-side from each chat's compact ``daily`` table, so
any date range / granularity recomputes instantly.
"""


def render_index_html() -> str:
    return _TEMPLATE


_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relationship Analytics Dashboard</title>
<style>
:root{
  --bg:#181B1F; --panel:#22262B; --panel-2:#1f2329; --border:#2c3137;
  --text:#D8D9DA; --muted:#8e9297; --faint:#6b7076;
  --a:#4DB6AC; --b:#9E9E9E; --accent:#4DB6AC;
  --good:#73BF69; --warn:#F2CC0C; --bad:#E02F44;
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);
  font-family:var(--font);font-size:14px;line-height:1.4}
a{color:var(--a)}
.wrap{max-width:1400px;margin:0 auto;padding:0 16px 64px}
h1,h2,h3{font-weight:600;margin:0}
.muted{color:var(--muted)}
.faint{color:var(--faint)}

/* ---- top bar ---- */
.topbar{position:sticky;top:0;z-index:50;background:rgba(24,27,31,.96);
  backdrop-filter:blur(6px);border-bottom:1px solid var(--border)}
.topbar-inner{max-width:1400px;margin:0 auto;padding:10px 16px;
  display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center}
.brand{font-size:15px;font-weight:700;letter-spacing:.2px;margin-right:6px}
.brand .dot{color:var(--a)}
.control{display:flex;flex-direction:column;gap:3px}
.control label{font-size:10px;text-transform:uppercase;letter-spacing:.6px;color:var(--faint)}
.dd{position:relative}
.dd-btn,select,input,button{font-family:inherit;font-size:13px;color:var(--text);
  background:var(--panel);border:1px solid var(--border);border-radius:6px;
  padding:6px 10px;cursor:pointer;outline:none}
select:focus,input:focus,.dd-btn:focus{border-color:var(--a)}
.dd-btn{min-width:220px;text-align:left;display:flex;justify-content:space-between;gap:8px}
.dd-panel{position:absolute;top:calc(100% + 4px);left:0;z-index:60;min-width:300px;
  max-height:60vh;overflow:auto;background:var(--panel);border:1px solid var(--border);
  border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,.5);display:none;padding:6px}
.dd-panel.open{display:block}
.dd-search{width:100%;margin-bottom:6px}
.dd-item{padding:7px 9px;border-radius:5px;cursor:pointer;display:flex;
  justify-content:space-between;gap:10px}
.dd-item:hover,.dd-item.active{background:var(--panel-2)}
.dd-item .n{color:var(--faint);font-variant-numeric:tabular-nums}
.dd-item.connected{border:1px solid var(--a);background:rgba(77,182,172,.08);
  font-weight:600;margin-bottom:6px}
.dd-item.connected:hover,.dd-item.connected.active{background:rgba(77,182,172,.16)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:5px 10px;border-radius:14px;border:1px solid var(--border);
  background:var(--panel);color:var(--muted);cursor:pointer;font-size:12px;user-select:none}
.chip:hover{border-color:var(--a);color:var(--text)}
.chip.active{background:var(--a);border-color:var(--a);color:#08201d;font-weight:600}
.chip.reset{border-style:dashed}
.daterow{display:flex;align-items:center;gap:6px}
.daterow input[type=date]{cursor:text}

/* ---- layout ---- */
.section{margin-top:26px}
.section-title{font-size:12px;text-transform:uppercase;letter-spacing:1px;
  color:var(--muted);margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.grid{display:grid;gap:14px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;
  padding:14px 16px 10px}
.card h3{font-size:13px;font-weight:600;margin-bottom:2px}
.card .sub{font-size:11px;color:var(--faint);margin-bottom:8px}
.chart{width:100%;height:280px}
.chart.tall{height:340px}
.chart.short{height:200px}
.placeholder{display:flex;align-items:center;justify-content:center;height:100%;
  color:var(--faint);font-size:13px}

/* KPI tiles */
.kpis{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.kpi .label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.kpi .value{font-size:26px;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums;
  display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.kpi .delta{font-size:12px;font-weight:600}
.kpi .delta.up{color:var(--good)} .kpi .delta.down{color:var(--bad)}
.kpi .split{display:block;font-size:13px;margin-top:4px;font-variant-numeric:tabular-nums}
.dotA,.dotB{display:inline-block;width:9px;height:9px;border-radius:2px;vertical-align:middle;margin-right:4px}
.dotA{background:var(--a)} .dotB{background:var(--b)}

/* lifetime table */
.lt-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.lt-table th,.lt-table td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);font-size:13px}
.lt-table th{color:var(--faint);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.4px}
.lt-table td.num{text-align:right}
.legend-inline{display:flex;gap:16px;font-size:12px;color:var(--muted);margin-bottom:8px}
.cols-2{grid-template-columns:repeat(2,1fr)}
@media(max-width:900px){.cols-2{grid-template-columns:1fr}}

/* shifts diff (git-style) */
.diff{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
.diff .drow{display:flex;gap:10px;padding:5px 10px;border-left:3px solid transparent;
  border-radius:4px;margin:2px 0;align-items:baseline}
.diff .drow.up{background:rgba(115,191,105,.08);border-left-color:var(--good)}
.diff .drow.down{background:rgba(224,47,68,.08);border-left-color:var(--bad)}
.diff .sign{width:12px;font-weight:700}
.diff .drow.up .sign,.diff .drow.up .d{color:var(--good)}
.diff .drow.down .sign,.diff .drow.down .d{color:var(--bad)}
.diff .m{flex:1;color:var(--text)}
.diff .vals{color:var(--muted);white-space:nowrap}
.diff .d{font-weight:600;min-width:70px;text-align:right}
.diff-head{font-size:11px;color:var(--faint);margin:0 0 8px 2px}

/* language / NLP cards */
.tag{display:inline-block;padding:2px 9px;margin:2px 3px 2px 0;border-radius:10px;
  background:var(--panel-2);border:1px solid var(--border);font-size:12px;color:var(--text)}
.tag .n{color:var(--faint);margin-left:5px;font-size:11px}
.tag.hot{border-color:var(--a)}
.emoji-row{font-size:20px;line-height:1.7;letter-spacing:2px;word-break:break-all}
.emoji-row .n{font-size:11px;color:var(--faint);letter-spacing:0;vertical-align:super;margin:0 6px 0 1px}
.nlp-label{font-size:10px;text-transform:uppercase;letter-spacing:.6px;color:var(--faint);margin:10px 0 4px}
.vocab-line{font-size:12px;color:var(--muted);margin-top:10px;font-variant-numeric:tabular-nums}
/* findings ("insights") */
.findings{display:grid;gap:10px}
.finding{background:var(--panel);border:1px solid var(--border);border-radius:10px;
  padding:12px 14px;border-left:3px solid var(--border)}
.finding.sev-signal{border-left-color:var(--accent)}
.finding.sev-notable{border-left-color:var(--b)}
.finding.sev-fun{border-left-color:var(--faint)}
.finding .f-head{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.finding .f-chip{font-size:10px;text-transform:uppercase;letter-spacing:.6px;
  padding:2px 7px;border-radius:10px;border:1px solid var(--border);color:var(--muted)}
.finding.sev-signal .f-chip{border-color:var(--accent);color:var(--accent)}
.finding .f-title{font-size:13px;font-weight:600;color:var(--text)}
.finding .f-sentence{font-size:13px;color:var(--text);line-height:1.5}
.finding .f-foot{display:flex;align-items:center;gap:12px;margin-top:6px;flex-wrap:wrap}
.finding .f-evidence{font-size:11px;color:var(--faint);font-variant-numeric:tabular-nums}
.finding .f-showme{font-size:11px;color:var(--accent);cursor:pointer;
  background:none;border:0;padding:0}
.finding .f-showme:hover{text-decoration:underline}
.findings-empty{color:var(--muted);font-size:13px;font-style:italic;
  padding:6px 2px}
.findings-note{color:var(--faint);font-size:11px;margin-top:2px}
</style>
</head>
<body data-palette="#4DB6AC,#9E9E9E">
<div class="topbar">
  <div class="topbar-inner">
    <div class="brand">Relationship<span class="dot">·</span>Analytics</div>
    <div class="control">
      <label>Chat</label>
      <div class="dd" id="chatDD">
        <button class="dd-btn" id="chatBtn"><span id="chatBtnLabel">Select chat…</span><span>▾</span></button>
        <div class="dd-panel" id="chatPanel">
          <input class="dd-search" id="chatSearch" placeholder="Search chats…" autocomplete="off">
          <div id="chatList"></div>
        </div>
      </div>
    </div>
    <div class="control" id="platformControl" style="display:none">
      <label>Platform</label>
      <div class="chips" id="platformSeg"></div>
    </div>
    <div class="control">
      <label>Time range</label>
      <div class="chips" id="presetChips"></div>
    </div>
    <div class="control">
      <label>Custom range</label>
      <div class="daterow">
        <input type="date" id="dFrom"><span class="faint">→</span>
        <input type="date" id="dTo">
        <button id="applyRange">Apply</button>
      </div>
    </div>
    <div class="control">
      <label>Month</label>
      <select id="monthSel"><option value="">Pick month…</option></select>
    </div>
    <div class="control">
      <label>Granularity</label>
      <select id="gran">
        <option value="auto">Auto</option>
        <option value="day">Day</option>
        <option value="week">Week</option>
        <option value="month">Month</option>
      </select>
    </div>
  </div>
</div>

<div class="wrap">
  <div id="app"></div>
</div>

<script src="echarts.min.js"></script>
<script src="data/manifest.js"></script>
<script>
"use strict";
/* ============================================================ *
 * Relationship Analytics dashboard — vanilla JS client.
 * All windowed aggregation is derived here from each chat's
 * compact daily table; Python only ships daily rows + lifetime.
 * ============================================================ */
var COLORS = {a:'#4DB6AC', b:'#9E9E9E'};
/* Fixed categorical palette for group members, assigned by lifetime rank so a
   member keeps the same colour across every chart. Others is always grey.
   1v1 chats never touch this — they keep COLORS.a / COLORS.b exactly. */
var GROUP_PAL=['#4DB6AC','#E4A11B','#B5179E','#3B8EA5','#73BF69','#D64550'];
var OTHERS_COLOR='#6b7076';
var TEXT='#D8D9DA', MUTED='#8e9297', GRID='#2c3137', PANEL='#22262B';
var HEAT = ['#12233a','#173a5e','#1c5cab','#2a78d6','#5598e7','#86b6ef','#cde2fb'];
var WEEKDAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
var HOURS=[]; for(var h=0;h<24;h++) HOURS.push((h<10?'0':'')+h);

var MANIFEST = window.DASHBOARD_MANIFEST || [];
var DATA = window.DASHBOARD_DATA = window.DASHBOARD_DATA || {};

var state = {
  chatId:null, chat:null, isGroup:false,
  isConnected:false, connected:null, connectedVariant:'all', // owner cross-chat ("You — Connected") mode
  users:[null,null],
  fullStart:null, fullEnd:null,   // Date objects (chat extent)
  start:null, end:null,           // Date objects (active range)
  preset:'all', gran:'auto'
};
var charts = {};                  // id -> echarts instance

/* ---------- small utils ---------- */
function el(id){return document.getElementById(id);}
function txt(node,s){node.textContent=(s==null?'':String(s));}
function pad(n){return (n<10?'0':'')+n;}
function ymd(d){return d.getUTCFullYear()+'-'+pad(d.getUTCMonth()+1)+'-'+pad(d.getUTCDate());}
function parseYMD(s){var p=s.split('-');return new Date(Date.UTC(+p[0],+p[1]-1,+p[2]));}
function addDays(d,n){var r=new Date(d.getTime());r.setUTCDate(r.getUTCDate()+n);return r;}
function dayDiff(a,b){return Math.round((b-a)/86400000);}

function fmtNum(v){
  if(v==null||isNaN(v)) return '—';
  var n=Number(v);
  if(Math.abs(n)>=1e6) return (n/1e6).toFixed(1).replace(/\.0$/,'')+'M';
  if(Math.abs(n)>=1e3) return (n/1e3).toFixed(1).replace(/\.0$/,'')+'k';
  if(Number.isInteger(n)) return String(n);
  return n.toFixed(Math.abs(n)<1?2:1);
}
function fmtPct(v,dp){ if(v==null||isNaN(v)) return '—'; return (v*100).toFixed(dp==null?0:dp)+'%'; }
function fmtDur(mins){
  if(mins==null||isNaN(mins)) return '—';
  var s=Math.round(mins*60);
  if(s<60) return s+'s';
  if(s<3600){var m=Math.floor(s/60);var r=s%60;return m+'m'+(r?' '+r+'s':'');}
  var h=Math.floor(s/3600);var m2=Math.round((s%3600)/60);return h+'h'+(m2?' '+m2+'m':'');
}

/* ---------- daily aggregation over a range ---------- */
function dailyEntries(){ // sorted [dateStr, {user:cell}]
  var d=state.chat.daily, keys=Object.keys(d).sort(), out=[];
  for(var i=0;i<keys.length;i++) out.push([keys[i],d[keys[i]]]);
  return out;
}
function inRange(dateStr){
  var t=parseYMD(dateStr).getTime();
  return t>=state.start.getTime() && t<=state.end.getTime();
}
function blank(){return {msgs:0,words:0,chars:0,emoji:0,questions:0,
  questions_answered:0,laughs:0,night_msgs:0,
  reactions_given:0,reactions_received:0,media:0,photos:0,videos:0,voice:0,shares:0,
  turns:0,turns_answered:0,endings:0,self_restarts:0,reacted_leave:0,
  wait_reply_sum_min:0,wait_reply_n:0,resp_lat_sum_min:0,resp_lat_n:0,initiations:0,
  we_words:0,i_words:0,you_words:0,pos_words:0,neg_words:0,gratitude:0,apology:0,
  edits:0};}
function addInto(acc,cell){
  for(var k in acc){ if(cell[k]!=null) acc[k]+=cell[k]; }
}

function effGran(){
  if(state.gran!=='auto') return state.gran;
  var days=dayDiff(state.start,state.end)+1;
  if(days<=92) return 'day';
  if(days<=400) return 'week';
  return 'month';
}
function bucketStart(dateStr,gran){
  var d=parseYMD(dateStr);
  if(gran==='day') return dateStr;
  if(gran==='week'){ var wd=(d.getUTCDay()+6)%7; return ymd(addDays(d,-wd)); }
  return dateStr.slice(0,7)+'-01'; // month
}

/* Build buckets: returns {labels:[ts...], A:{field:[...]}, B:{...}, users:[a,b]} */
function buildBuckets(){
  var gran=effGran(), A=state.users[0], B=state.users[1];
  var map={}; // bucketStart -> {A:blank,B:blank}
  var ents=dailyEntries();
  for(var i=0;i<ents.length;i++){
    var ds=ents[i][0]; if(!inRange(ds)) continue;
    var bs=bucketStart(ds,gran);
    if(!map[bs]) map[bs]={A:blank(),B:blank()};
    var cells=ents[i][1];
    if(cells[A]) addInto(map[bs].A,cells[A]);
    if(cells[B]) addInto(map[bs].B,cells[B]);
  }
  var starts=Object.keys(map).sort();
  var res={starts:starts,ts:[],A:map,B:map,gran:gran,rows:[]};
  res.ts=starts.map(function(s){return parseYMD(s).getTime();});
  res.rows=starts.map(function(s){return map[s];});
  return res;
}

/* whole-range totals per user (for KPI + heatmap hours) */
function rangeTotals(startD,endD){
  var A=state.users[0], B=state.users[1];
  var tot={A:blank(),B:blank()};
  var hours={A:new Array(168).fill(0),B:new Array(168).fill(0)};
  var ents=dailyEntries();
  for(var i=0;i<ents.length;i++){
    var ds=ents[i][0];
    var t=parseYMD(ds).getTime();
    if(t<startD.getTime()||t>endD.getTime()) continue;
    var cells=ents[i][1];
    var wd=(parseYMD(ds).getUTCDay()+6)%7;
    if(cells[A]){ addInto(tot.A,cells[A]);
      if(cells[A].hours) for(var h=0;h<24;h++) hours.A[wd*24+h]+=cells[A].hours[h]; }
    if(cells[B]){ addInto(tot.B,cells[B]);
      if(cells[B].hours) for(var h2=0;h2<24;h2++) hours.B[wd*24+h2]+=cells[B].hours[h2]; }
  }
  return {tot:tot,hours:hours};
}

/* ---------- ECharts helpers ---------- */
function baseGrid(){return {left:52,right:18,top:30,bottom:34};}
function timeAxis(){return {type:'time',axisLine:{lineStyle:{color:GRID}},
  axisLabel:{color:MUTED},splitLine:{show:false},axisPointer:{label:{show:false}}};}
function valAxis(extra){var a={type:'value',axisLine:{show:false},
  axisLabel:{color:MUTED},splitLine:{lineStyle:{color:GRID,opacity:.5}}};
  if(extra) for(var k in extra) a[k]=extra[k]; return a;}
function tooltipBase(){return {trigger:'axis',backgroundColor:PANEL,borderColor:GRID,
  textStyle:{color:TEXT},axisPointer:{type:'cross',crosshair:true,
  lineStyle:{color:MUTED,type:'dashed'},label:{backgroundColor:'#333'}}};}
function legend(names){return {data:names,textStyle:{color:MUTED},top:2,right:10,icon:'roundRect',itemWidth:10,itemHeight:10};}

function getChart(id){
  var node=el(id); if(!node) return null;
  if(charts[id]){ return charts[id]; }
  charts[id]=echarts.init(node,null,{renderer:'canvas'});
  return charts[id];
}
function setChart(id,opt){
  var c=getChart(id); if(!c) return;
  c.setOption(opt,true);
}
function disposeCharts(){
  for(var k in charts){ try{charts[k].dispose();}catch(e){} }
  charts={};
}
window.addEventListener('resize',function(){ for(var k in charts){ try{charts[k].resize();}catch(e){} } });

/* ============================================================ *
 * RENDER: page skeleton
 * ============================================================ */
function renderSkeleton(){
  var A=state.users[0]||'A', B=state.users[1]||'B';
  el('app').innerHTML =
  section('Pulse','<div class="grid kpis" id="kpiRow"></div>')
  + section('Story timeline',
      card('Message volume','A above the line, partner mirrored below · change-points marked',
        '<div class="chart tall" id="cVolume"></div>')
      + card('Activity calendar','Daily message volume — spot streaks, bursts and silences at a glance',
        '<div class="chart" id="cCal"></div>'))
  + section('Balance & depth',
      '<div class="grid cols-2">'
      + card('Initiation share','Who opens conversations (per bucket)','<div class="chart" id="cInit"></div>')
      + card('Question rate','Interrogatives per 100 messages','<div class="chart" id="cQ"></div>')
      + card('Message depth','Average words per TURN — a full thought, however many messages it was split into','<div class="chart" id="cDepth"></div>')
      + card('Monologue ↔ dialogue','Average messages per turn — how long each person talks before the other interjects','<div class="chart" id="cTurns"></div>')
      + card('Turn length distribution','How many messages a turn usually holds (all-time)','<div class="chart" id="cTurnHist"></div>')
      + '</div>')
  + section('Responsiveness',
      card('Median in-session reply latency','Minutes · display capped near p95','<div class="chart" id="cLat"></div>'))
  + section('Affect',
      '<div class="grid cols-2">'
      + card('Reactions given','Acknowledgement channel','<div class="chart" id="cReact"></div>')
      + card('Emoji per 100 messages','Expressiveness channel','<div class="chart" id="cEmoji"></div>')
      + card('Media mix','What kind of media each person shares (in range)','<div class="chart" id="cMedia"></div>')
      + '</div>')
  + section('Rhythm',
      '<div class="grid cols-2">'
      + card('Activity clock · '+esc(A),'Messages by weekday × hour','<div class="chart" id="cHeatA"></div>')
      + card('Activity clock · '+esc(B),'Messages by weekday × hour','<div class="chart" id="cHeatB"></div>')
      + '</div>'
      + card('Night share','Share of messages during 23:00–02:59','<div class="chart short" id="cNight"></div>'))
  + section('Endings & restarts',
      '<div class="grid cols-2">'
      + card('Final word share','Who is left unanswered when a conversation dies (per bucket)','<div class="chart" id="cEnd"></div>')
      + card('Restart behavior','Re-knocks = restarting although your own last message was never answered · reacted-and-left counts','<div class="chart" id="cRestart"></div>')
      + card('Waiting eagerness','After waiting 1h+ for a reply — how fast the waiter answers once it lands (lower = they were waiting by the phone)','<div class="chart" id="cWait"></div>')
      + card('Talks into the void','Share of turns that ended the session with no answer','<div class="chart" id="cVoid"></div>')
      + '</div>')
  + section('Psycholinguistics',
      '<div class="grid cols-2">'
      + card('We-ness','Share of we/us vs I/me pronouns — "we-talk" is a replicated predictor of relationship quality','<div class="chart" id="cWe"></div>')
      + card('Positivity balance','Positive vs negative affect words (lexicon-based) · dashed line = Gottman 5:1 ratio','<div class="chart" id="cSent"></div>')
      + card('Language style matching','Similarity of function-word usage (pronouns, conjunctions, negations…) — the standard computational rapport measure','<div class="chart" id="cLSM"></div>')
      + card('Vocabulary richness','Unique words / total words per month — falling diversity can signal a conversational rut','<div class="chart" id="cTTR"></div>')
      + card('Courtesy markers','Gratitude and apologies per 100 messages (in range)','<div id="courtesyBox" style="min-height:120px"></div>')
      + '</div>')
  + section('Language',
      '<div class="grid cols-2" id="nlpCards"></div>')
  + telegramSection()
  + section('Shifts vs previous period',
      card('What changed','Every metric that moved, current range compared to the previous window of equal length',
        '<div class="diff" id="shiftList"></div>'))
  + findingsSection()
  + section('All-time lifetime metrics',
      '<div class="grid cols-2" id="ltCards"></div>');
}
/* Telegram-only section — rendered only when the loaded chat carries Telegram
   signals. Instagram chats get an empty string, so their layout is unchanged. */
function telegramSection(){
  if(!state.chat||!state.chat.telegram) return '';
  return section('Telegram signals',
    '<div class="grid cols-2">'
    + card('Edit rate','Share of messages later edited — a "second-guessing index" (in range)','<div class="chart" id="cTgEdit"></div>')
    + card('Reply share','Share of messages that are explicit replies (all-time)','<div class="chart" id="cTgReply"></div>')
    + card('Reply depth','How deep reply chains go (count of replies at each chain depth)','<div class="chart" id="cTgDepth"></div>')
    + card('Forward share','Share of messages that are forwards (all-time)','<div class="chart" id="cTgForward"></div>')
    + card('Entity mix','Links, hashtags and mentions used per person (all-time)','<div class="chart" id="cTgEntities"></div>')
    + '</div>');
}
function renderTelegram(rt){
  if(!state.chat||!state.chat.telegram) return;
  var A=state.users[0], B=state.users[1];
  var tg=state.chat.telegram, pu=tg.per_user||{};
  var pa=pu[A]||{}, pb=pu[B]||{};
  var names=[A,B], cols=[COLORS.a,COLORS.b];
  function barPct(id,va,vb,unit){
    setChart(id,{grid:baseGrid(),tooltip:{trigger:'axis',backgroundColor:PANEL,
      borderColor:GRID,textStyle:{color:TEXT}},
      xAxis:{type:'category',data:names,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
      yAxis:valAxis({axisLabel:{color:MUTED,formatter:'{value}'+(unit||'')}}),
      series:[{type:'bar',data:[{value:va,itemStyle:{color:cols[0]}},
        {value:vb,itemStyle:{color:cols[1]}}],barMaxWidth:60,
        label:{show:true,position:'top',color:TEXT,formatter:function(o){return fmtNum(o.value)+(unit||'');}}}]});
  }
  // Edit rate — range-scoped (edits/msgs from the daily table).
  var ea=rt&&rt.tot&&rt.tot.A?rt.tot.A:{msgs:0,edits:0};
  var eb=rt&&rt.tot&&rt.tot.B?rt.tot.B:{msgs:0,edits:0};
  barPct('cTgEdit', ea.msgs?+(ea.edits/ea.msgs*100).toFixed(1):0,
                    eb.msgs?+(eb.edits/eb.msgs*100).toFixed(1):0, '%');
  barPct('cTgReply', +((pa.reply_share||0)*100).toFixed(1), +((pb.reply_share||0)*100).toFixed(1), '%');
  barPct('cTgForward', +((pa.forward_share||0)*100).toFixed(1), +((pb.forward_share||0)*100).toFixed(1), '%');
  // Reply depth histogram.
  var rd=tg.reply_depth||{};
  var order=['1','2','3','4','5','6+'];
  var dk=order.filter(function(k){return rd[k]!=null;});
  if(!dk.length) dk=Object.keys(rd).sort();
  setChart('cTgDepth',{grid:baseGrid(),tooltip:{trigger:'axis',backgroundColor:PANEL,
    borderColor:GRID,textStyle:{color:TEXT}},
    xAxis:{type:'category',data:dk,name:'depth',nameTextStyle:{color:MUTED},
      axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({}),
    series:[{type:'bar',data:dk.map(function(k){return rd[k];}),
      itemStyle:{color:COLORS.a},barMaxWidth:40}]});
  // Entity mix — grouped bars per person.
  setChart('cTgEntities',{grid:baseGrid(),legend:legend(names),
    tooltip:{trigger:'axis',backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT}},
    xAxis:{type:'category',data:['Links','Hashtags','Mentions'],
      axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({}),
    series:[
      {name:A,type:'bar',itemStyle:{color:COLORS.a},
        data:[pa.links||0,pa.hashtags||0,pa.mentions||0]},
      {name:B,type:'bar',itemStyle:{color:COLORS.b},
        data:[pb.links||0,pb.hashtags||0,pb.mentions||0]}]});
}
function section(title,inner){return '<div class="section"><div class="section-title">'+esc(title)+'</div>'+inner+'</div>';}
function card(title,sub,inner){return '<div class="card"><h3>'+esc(title)+'</h3>'
  +(sub?'<div class="sub">'+esc(sub)+'</div>':'')+inner+'</div>';}
function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}

/* ============================================================ *
 * FINDINGS ("Insights") — lazy-loaded from data/insights.js.
 * Precomputed all-time findings (Tier 1). Graceful when absent.
 * ============================================================ */
var INSIGHTS_STATE = {loaded:false, loading:false, cbs:[]};
function ensureInsights(cb){
  if(INSIGHTS_STATE.loaded){ cb&&cb(); return; }
  if(cb) INSIGHTS_STATE.cbs.push(cb);
  if(INSIGHTS_STATE.loading) return;
  INSIGHTS_STATE.loading=true;
  function done(){ INSIGHTS_STATE.loaded=true; INSIGHTS_STATE.loading=false;
    var cbs=INSIGHTS_STATE.cbs; INSIGHTS_STATE.cbs=[];
    for(var i=0;i<cbs.length;i++){ try{cbs[i]();}catch(e){} } }
  var s=document.createElement('script');
  s.src='data/insights.js';
  s.onload=done;
  s.onerror=function(){ window.INSIGHTS=window.INSIGHTS||{}; done(); };
  document.body.appendChild(s);
}
function findingsSection(){
  return section('📋 Findings','<div id="findingsBox"><div class="findings-empty">Reading the room…</div></div>');
}
function fEvidenceLine(f){
  var ev=f.evidence||{}, parts=[];
  for(var k in ev){
    var v=ev[k];
    if(v==null) continue;
    if(typeof v==='object') continue; // skip nested arrays/objects
    var key=String(k).replace(/_/g,' ');
    parts.push(esc(key)+' '+esc(fmtNum(v)));
  }
  return parts.slice(0,4).join(' · ');
}
/* Render findings for the current scope into #findingsBox.
   scopeKey: a chat id, or 'connected:<variant>'. */
function renderFindings(scopeKey){
  var box=el('findingsBox'); if(!box) return;
  var all=window.INSIGHTS||{};
  var list;
  if(scopeKey.indexOf('connected:')===0){
    var v=scopeKey.slice('connected:'.length);
    list=((all.connected||{})[v])||[];
  } else {
    list=all[scopeKey]||[];
  }
  if(!list.length){
    box.innerHTML='<div class="findings-empty">Nothing stands out in this window — that’s a finding too.</div>';
    return;
  }
  var html='<div class="findings">';
  for(var i=0;i<list.length;i++){
    var f=list[i];
    var sev=(f.severity==='signal'||f.severity==='notable'||f.severity==='fun')?f.severity:'notable';
    var anchor=f.anchor&&el(f.anchor)?f.anchor:null;
    html+='<div class="finding sev-'+sev+'">'
      +'<div class="f-head"><span class="f-chip">'+esc(f.severity||'')+'</span>'
      +'<span class="f-title">'+esc(f.title||'')+'</span></div>'
      +'<div class="f-sentence">'+esc(f.sentence||'')+'</div>'
      +'<div class="f-foot">'
      +'<span class="f-evidence">'+fEvidenceLine(f)+'</span>'
      +(anchor?'<button class="f-showme" data-anchor="'+esc(anchor)+'">show me →</button>':'')
      +'</div></div>';
  }
  html+='</div><div class="findings-note">All-time findings across this chat’s full history.</div>';
  box.innerHTML=html;
  var btns=box.querySelectorAll?box.querySelectorAll('.f-showme'):[];
  Array.prototype.forEach.call(btns,function(btn){
    btn.onclick=function(){ var a=btn.getAttribute('data-anchor'); var node=el(a);
      if(node&&node.scrollIntoView) node.scrollIntoView({behavior:'smooth',block:'center'}); };
  });
}
function loadAndRenderFindings(scopeKey){
  ensureInsights(function(){ try{ renderFindings(scopeKey); }catch(e){} });
}

/* ============================================================ *
 * RENDER: everything from active range
 * ============================================================ */
function renderAll(){
  if(!state.chat){return;}
  var b=buildBuckets();
  var rt=rangeTotals(state.start,state.end);
  var hasData=b.starts.length>0;
  safe(function(){renderKPIs(rt,hasData);},'kpi');
  safe(function(){renderVolume(b);},'volume');
  safe(renderCalendar,'calendar');
  safe(function(){renderBalance(b);},'balance');
  safe(function(){renderDepth(b);},'depth');
  safe(function(){renderTurns(b);},'turns');
  safe(function(){renderResponsiveness(b);},'latency');
  safe(function(){renderAffect(b);},'affect');
  safe(function(){renderMediaMix(rt);},'media');
  safe(function(){renderRhythm(rt,b);},'rhythm');
  safe(function(){renderEndings(b,rt);},'endings');
  safe(function(){renderPsycho(b,rt);},'psycho');
  safe(renderLanguage,'language');
  safe(function(){renderTelegram(rt);},'telegram');
  safe(function(){renderShifts(rt);},'shifts');
  // Lifetime + turn-hist cards are range-independent; rendered per chat.
}
/* One broken chart must never take down the rest of the page. */
function safe(fn,tag){ try{fn();}catch(e){ try{console.error('render '+tag+' failed:',e);}catch(_){} } }

function noData(id){
  var c=getChart(id);
  if(c){ c.clear(); }
  var node=el(id);
  if(node){ node.innerHTML='<div class="placeholder">No data in range</div>'; charts[id]=null; }
}
function ensureCanvas(id){
  var node=el(id);
  if(node && node.querySelector('.placeholder')){ node.innerHTML=''; charts[id]=null; }
}

/* ---- KPI row ---- */
/* Relative change vs a previous value; null when no baseline. */
function relDelta(cur,prev){
  if(cur==null||prev==null||!isFinite(prev)||prev===0) return null;
  return (cur-prev)/prev;
}
/* previous equal-length window totals for the active range */
function prevWindowTotals(){
  var days=dayDiff(state.start,state.end)+1;
  var prevEnd=addDays(state.start,-1), prevStart=addDays(state.start,-days);
  return {days:days, start:prevStart, end:prevEnd,
          tot:rangeTotals(prevStart,prevEnd).tot};
}
function renderKPIs(rt,hasData){
  var A=state.users[0],B=state.users[1];
  var tot=rt.tot;
  var pw=prevWindowTotals(), prev=pw.tot, days=pw.days;
  var hasPrev=(prev.A.msgs+prev.B.msgs)>0;

  var totalMsgs=tot.A.msgs+tot.B.msgs;
  var perDay=days>0?totalMsgs/days:0;
  var prevTotal=prev.A.msgs+prev.B.msgs;
  var prevPerDay=days>0?prevTotal/days:0;

  var latA=tot.A.resp_lat_n?tot.A.resp_lat_sum_min/tot.A.resp_lat_n:null;
  var latB=tot.B.resp_lat_n?tot.B.resp_lat_sum_min/tot.B.resp_lat_n:null;
  var latAll=(tot.A.resp_lat_n+tot.B.resp_lat_n)>0?
    (tot.A.resp_lat_sum_min+tot.B.resp_lat_sum_min)/(tot.A.resp_lat_n+tot.B.resp_lat_n):null;
  var pLatAll=(prev.A.resp_lat_n+prev.B.resp_lat_n)>0?
    (prev.A.resp_lat_sum_min+prev.B.resp_lat_sum_min)/(prev.A.resp_lat_n+prev.B.resp_lat_n):null;

  var initTot=tot.A.initiations+tot.B.initiations;
  var initA=initTot?tot.A.initiations/initTot:null;
  var pInitTot=prev.A.initiations+prev.B.initiations;
  var pInitA=pInitTot?prev.A.initiations/pInitTot:null;

  var reacts=tot.A.reactions_given+tot.B.reactions_given;
  var pReacts=prev.A.reactions_given+prev.B.reactions_given;

  var nightTot=tot.A.night_msgs+tot.B.night_msgs;
  var nightShare=totalMsgs?nightTot/totalMsgs:null;
  var pNightShare=prevTotal?(prev.A.night_msgs+prev.B.night_msgs)/prevTotal:null;

  // when there is no previous window at all, suppress all delta chips
  function D(v,opts){ if(!hasPrev||v==null||!isFinite(v)) return null;
    var o=opts||{}; return {v:v,invert:!!o.invert,pp:!!o.pp}; }

  var words=tot.A.words+tot.B.words, pWords=prev.A.words+prev.B.words;
  var mediaT=tot.A.media+tot.B.media, pMediaT=prev.A.media+prev.B.media;
  var turnsT=tot.A.turns+tot.B.turns;
  var dlg=totalMsgs?turnsT/totalMsgs:null; // 100% = strict turn-taking
  var pMsgsT=prev.A.msgs+prev.B.msgs, pTurnsT=prev.A.turns+prev.B.turns;
  var pDlg=pMsgsT?pTurnsT/pMsgsT:null;
  var kinds='📷 '+fmtNum(tot.A.photos+tot.B.photos)+' · 🎥 '+fmtNum(tot.A.videos+tot.B.videos)
    +' · 🎙 '+fmtNum(tot.A.voice+tot.B.voice)+' · 🔗 '+fmtNum(tot.A.shares+tot.B.shares);

  var tiles=[];
  tiles.push(kpi('Messages', fmtNum(totalMsgs),
     D(relDelta(totalMsgs,prevTotal)),
     '<span class="split"><span class="dotA"></span>'+fmtNum(tot.A.msgs)
     +' &nbsp;<span class="dotB"></span>'+fmtNum(tot.B.msgs)+'</span>'));
  tiles.push(kpi('Messages / day', fmtNum(perDay),
     D(relDelta(perDay,prevPerDay)),
     '<span class="split faint">vs prev '+days+'d</span>'));
  tiles.push(kpi('Words', fmtNum(words),
     D(relDelta(words,pWords)),
     '<span class="split"><span class="dotA"></span>'+fmtNum(tot.A.words)
     +' &nbsp;<span class="dotB"></span>'+fmtNum(tot.B.words)+'</span>'));
  tiles.push(kpi('Media shared', fmtNum(mediaT),
     D(relDelta(mediaT,pMediaT)),
     '<span class="split"><span class="dotA"></span>'+fmtNum(tot.A.media)
     +' &nbsp;<span class="dotB"></span>'+fmtNum(tot.B.media)+'</span>'
     +'<span class="split faint">'+kinds+'</span>'));
  tiles.push(kpi('Dialogue index', dlg==null?'—':fmtPct(dlg),
     D(dlg!=null&&pDlg!=null?dlg-pDlg:null,{pp:true}),
     '<span class="split faint">100% = strict turn-taking</span>'));
  var endT=tot.A.endings+tot.B.endings, pEndT=prev.A.endings+prev.B.endings;
  var endA=endT?tot.A.endings/endT:null;
  var pEndA=pEndT?prev.A.endings/pEndT:null;
  tiles.push(kpi('Final word', endA==null?'—':fmtPct(endA),
     D(endA!=null&&pEndA!=null?endA-pEndA:null,{pp:true}),
     '<span class="split"><span class="dotA"></span>'+fmtNum(tot.A.endings)
     +' &nbsp;<span class="dotB"></span>'+fmtNum(tot.B.endings)+'</span>'));
  var weT=tot.A.we_words+tot.B.we_words, iT=tot.A.i_words+tot.B.i_words;
  var weness=(weT+iT)?weT/(weT+iT):null;
  var pWeT=prev.A.we_words+prev.B.we_words, pIT=prev.A.i_words+prev.B.i_words;
  var pWeness=(pWeT+pIT)?pWeT/(pWeT+pIT):null;
  tiles.push(kpi('We-ness', weness==null?'—':fmtPct(weness),
     D(weness!=null&&pWeness!=null?weness-pWeness:null,{pp:true}),
     '<span class="split faint">we/us vs I/me talk</span>'));
  tiles.push(kpi('Reply latency', fmtDur(latAll),
     D(relDelta(latAll,pLatAll),{invert:true}),
     '<span class="split"><span class="dotA"></span>'+fmtDur(latA)
     +' &nbsp;<span class="dotB"></span>'+fmtDur(latB)+'</span>'));
  tiles.push(kpi('Initiation', initA==null?'—':fmtPct(initA),
     D(initA!=null&&pInitA!=null?initA-pInitA:null,{pp:true}),
     '<span class="split"><span class="dotA"></span>'+fmtPct(initA)
     +' &nbsp;<span class="dotB"></span>'+(initA==null?'—':fmtPct(1-initA))+'</span>'));
  tiles.push(kpi('Reactions given', fmtNum(reacts),
     D(relDelta(reacts,pReacts)),
     '<span class="split"><span class="dotA"></span>'+fmtNum(tot.A.reactions_given)
     +' &nbsp;<span class="dotB"></span>'+fmtNum(tot.B.reactions_given)+'</span>'));
  tiles.push(kpi('Night share', nightShare==null?'—':fmtPct(nightShare),
     D(nightShare!=null&&pNightShare!=null?nightShare-pNightShare:null,{pp:true}),
     '<span class="split faint">23:00–02:59</span>'));

  el('kpiRow').innerHTML = hasData ? tiles.join('')
     : '<div class="kpi"><div class="placeholder">No data in range</div></div>';
}
function kpi(label,value,delta,extra,hideValue){
  var d='';
  if(delta&&delta.v!=null&&isFinite(delta.v)){
    var up=delta.v>=0;
    var good=delta.invert?!up:up;   // e.g. latency going up is bad
    var mag=delta.pp?(Math.abs(delta.v)*100).toFixed(1)+'pp':fmtPct(Math.abs(delta.v),0);
    d='<span class="delta '+(good?'up':'down')+'">'+(up?'▲ ':'▼ ')+mag+'</span>';
  }
  var val = hideValue ? '' : '<span>'+value+'</span>';
  return '<div class="kpi"><div class="label">'+esc(label)+'</div>'
    +'<div class="value">'+val+d+'</div>'+(extra||'')+'</div>';
}

/* ---- Volume mirrored area (master) ---- */
function renderVolume(b){
  if(!b.starts.length){ noData('cVolume'); return; }
  ensureCanvas('cVolume');
  var A=state.users[0],B=state.users[1];
  var sa=[],sb=[];
  for(var i=0;i<b.starts.length;i++){
    var ts=b.ts[i];
    sa.push([ts, b.rows[i].A.msgs]);
    sb.push([ts, -b.rows[i].B.msgs]);
  }
  var marks=changePointMarks();
  var opt={
    grid:baseGrid(),
    legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{formatter:function(ps){
      var d=new Date(ps[0].value[0]); var s=esc(fmtDate(d))+'<br>';
      ps.forEach(function(p){var v=Math.abs(p.value[1]);
        s+=markDot(p.color)+esc(p.seriesName)+': <b>'+fmtNum(v)+'</b><br>';});
      return s;}}),
    xAxis:timeAxis(),
    yAxis:valAxis({axisLabel:{color:MUTED,formatter:function(v){return fmtNum(Math.abs(v));}}}),
    dataZoom:[{type:'slider',bottom:2,height:16,borderColor:GRID,
      textStyle:{color:MUTED},fillerColor:'rgba(77,182,172,.15)'},
      {type:'inside'}],
    series:[
      areaSeries(A,sa,COLORS.a,marks),
      areaSeries(B,sb,COLORS.b,null)
    ]
  };
  setChart('cVolume',opt);
  var c=charts['cVolume'];
  c.off('datazoom'); c.on('datazoom',onVolumeZoom);
}
function areaSeries(name,data,color,markLine){
  var s={name:name,type:'line',data:data,showSymbol:false,smooth:false,
    lineStyle:{width:1.5,color:color},itemStyle:{color:color},
    areaStyle:{color:color,opacity:.22}};
  if(markLine) s.markLine=markLine;
  return s;
}
function changePointMarks(){
  var cps=(state.chat.change_points||[]).filter(function(cp){
    if(!cp.date) return false;
    var t=parseYMD(cp.date).getTime();
    return t>=state.start.getTime() && t<=state.end.getTime();
  });
  if(!cps.length) return null;
  return {symbol:'none',silent:false,
    lineStyle:{color:'#E02F44',type:'dashed',width:1.2},
    label:{show:true,color:'#E02F44',fontSize:10,formatter:function(p){return p.data.lbl;}},
    data:cps.map(function(cp){
      var top=(cp.signals&&cp.signals[0])?cp.signals[0].metric:'shift';
      return {xAxis:parseYMD(cp.date).getTime(),lbl:top.replace(/_/g,' ')};
    })};
}
var _zoomGuard=false;
function onVolumeZoom(){
  if(_zoomGuard) return;
  var c=charts['cVolume']; if(!c) return;
  var opt=c.getOption(); var dz=opt.dataZoom&&opt.dataZoom[0];
  if(!dz) return;
  var ax=c.getModel().getComponent('xAxis').axis.scale.getExtent();
  // ax gives current axis extent in ms after zoom
  var lo=new Date(ax[0]), hi=new Date(ax[1]);
  if(isNaN(lo)||isNaN(hi)) return;
  var ns=clampDate(lo), ne=clampDate(hi);
  if(dayDiff(ns,ne)<1) return;
  _zoomGuard=true;
  state.start=ns; state.end=ne; state.preset=null;
  syncControls();
  renderAllExceptVolumeZoom();
  _zoomGuard=false;
}
function renderAllExceptVolumeZoom(){
  // re-render dependent charts + KPIs but leave the master zoom interaction intact
  var b=buildBuckets(); var rt=rangeTotals(state.start,state.end);
  var has=b.starts.length>0;
  safe(function(){renderKPIs(rt,has);},'kpi'); safe(renderCalendar,'calendar');
  safe(function(){renderBalance(b);},'balance'); safe(function(){renderDepth(b);},'depth');
  safe(function(){renderTurns(b);},'turns');
  safe(function(){renderResponsiveness(b);},'latency'); safe(function(){renderAffect(b);},'affect');
  safe(function(){renderMediaMix(rt);},'media');
  safe(function(){renderRhythm(rt,b);},'rhythm');
  safe(function(){renderEndings(b,rt);},'endings');
  safe(function(){renderPsycho(b,rt);},'psycho');
  safe(renderLanguage,'language');
  safe(function(){renderShifts(rt);},'shifts');
}
function clampDate(d){
  var t=d.getTime();
  if(t<state.fullStart.getTime()) return new Date(state.fullStart.getTime());
  if(t>state.fullEnd.getTime()) return new Date(state.fullEnd.getTime());
  return parseYMD(ymd(d));
}
function markDot(color){return '<span style="display:inline-block;width:9px;height:9px;'
  +'border-radius:2px;margin-right:5px;background:'+color+'"></span>';}
function fmtDate(d){return d.getUTCFullYear()+'-'+pad(d.getUTCMonth()+1)+'-'+pad(d.getUTCDate());}

/* ---- Balance: initiation 100% stacked + question rate lines ---- */
function renderBalance(b){
  var A=state.users[0],B=state.users[1];
  if(!b.starts.length){ noData('cInit'); noData('cQ'); return; }
  ensureCanvas('cInit'); ensureCanvas('cQ');
  // initiation share stacked to 100%
  var ia=[],ib=[],cats=[];
  for(var i=0;i<b.starts.length;i++){
    var t=b.rows[i].A.initiations+b.rows[i].B.initiations;
    cats.push(b.starts[i]);
    ia.push(t?+(b.rows[i].A.initiations/t*100).toFixed(1):0);
    ib.push(t?+(b.rows[i].B.initiations/t*100).toFixed(1):0);
  }
  setChart('cInit',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{formatter:function(ps){
      var s=esc(ps[0].axisValue)+'<br>';
      ps.forEach(function(p){s+=markDot(p.color)+esc(p.seriesName)+': <b>'+p.value+'%</b><br>';});
      return s;}}),
    xAxis:{type:'category',data:cats,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({max:100,axisLabel:{color:MUTED,formatter:'{value}%'}}),
    series:[
      {name:A,type:'bar',stack:'i',data:ia,itemStyle:{color:COLORS.a},barMaxWidth:30},
      {name:B,type:'bar',stack:'i',data:ib,itemStyle:{color:COLORS.b},barMaxWidth:30}
    ]
  });
  // question rate lines
  var qa=[],qb=[];
  for(var j=0;j<b.starts.length;j++){
    var ts=b.ts[j];
    qa.push([ts, b.rows[j].A.msgs?+(b.rows[j].A.questions/b.rows[j].A.msgs*100).toFixed(1):0]);
    qb.push([ts, b.rows[j].B.msgs?+(b.rows[j].B.questions/b.rows[j].B.msgs*100).toFixed(1):0]);
  }
  setChart('cQ',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v+'/100';}}),
    xAxis:timeAxis(), yAxis:valAxis({axisLabel:{color:MUTED,formatter:'{value}'}}),
    series:[ lineSeries(A,qa,COLORS.a), lineSeries(B,qb,COLORS.b) ]
  });
}
function lineSeries(name,data,color){
  return {name:name,type:'line',data:data,showSymbol:false,smooth:true,
    lineStyle:{width:2,color:color},itemStyle:{color:color},connectNulls:true};
}

/* ---- Responsiveness: median-ish reply latency (mean of in-session gaps) ---- */
function renderResponsiveness(b){
  var A=state.users[0],B=state.users[1];
  if(!b.starts.length){ noData('cLat'); return; }
  ensureCanvas('cLat');
  var la=[],lb=[],allv=[];
  for(var i=0;i<b.starts.length;i++){
    var ts=b.ts[i];
    var va=b.rows[i].A.resp_lat_n?b.rows[i].A.resp_lat_sum_min/b.rows[i].A.resp_lat_n:null;
    var vb=b.rows[i].B.resp_lat_n?b.rows[i].B.resp_lat_sum_min/b.rows[i].B.resp_lat_n:null;
    if(va!=null){la.push([ts,+va.toFixed(2)]);allv.push(va);} else la.push([ts,null]);
    if(vb!=null){lb.push([ts,+vb.toFixed(2)]);allv.push(vb);} else lb.push([ts,null]);
  }
  var cap=p95(allv); if(cap!=null) cap=+(cap*1.2).toFixed(1);
  setChart('cLat',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':fmtDur(v);}}),
    xAxis:timeAxis(),
    yAxis:valAxis({max:cap||null,axisLabel:{color:MUTED,formatter:function(v){return v+'m';}}}),
    series:[ lineSeries(A,la,COLORS.a), lineSeries(B,lb,COLORS.b) ]
  });
}
function p95(arr){ if(!arr.length) return null; var s=arr.slice().sort(function(x,y){return x-y;});
  return s[Math.min(s.length-1,Math.floor(s.length*0.95))]; }

/* ---- Affect: reactions bars + emoji/100 lines ---- */
function renderAffect(b){
  var A=state.users[0],B=state.users[1];
  if(!b.starts.length){ noData('cReact'); noData('cEmoji'); return; }
  ensureCanvas('cReact'); ensureCanvas('cEmoji');
  var cats=b.starts.slice();
  var ra=b.rows.map(function(r){return r.A.reactions_given;});
  var rb=b.rows.map(function(r){return r.B.reactions_given;});
  setChart('cReact',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{}),
    xAxis:{type:'category',data:cats,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({}),
    series:[
      {name:A,type:'bar',data:ra,itemStyle:{color:COLORS.a},barMaxWidth:18,barGap:'10%'},
      {name:B,type:'bar',data:rb,itemStyle:{color:COLORS.b},barMaxWidth:18}
    ]
  });
  var ea=[],eb=[];
  for(var i=0;i<b.starts.length;i++){
    var ts=b.ts[i];
    ea.push([ts,b.rows[i].A.msgs?+(b.rows[i].A.emoji/b.rows[i].A.msgs*100).toFixed(1):0]);
    eb.push([ts,b.rows[i].B.msgs?+(b.rows[i].B.emoji/b.rows[i].B.msgs*100).toFixed(1):0]);
  }
  setChart('cEmoji',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v+'/100';}}),
    xAxis:timeAxis(), yAxis:valAxis({}),
    series:[ lineSeries(A,ea,COLORS.a), lineSeries(B,eb,COLORS.b) ]
  });
}

/* ---- Endings & restarts ---- */
function renderEndings(b,rt){
  var A=state.users[0],B=state.users[1];
  if(!b.starts.length){ noData('cEnd'); noData('cRestart'); noData('cWait'); noData('cVoid'); return; }
  // Final word share (stacked 100%)
  ensureCanvas('cEnd');
  var ea=[],eb=[],cats=[];
  for(var i=0;i<b.starts.length;i++){
    var t=b.rows[i].A.endings+b.rows[i].B.endings;
    cats.push(b.starts[i]);
    ea.push(t?+(b.rows[i].A.endings/t*100).toFixed(1):0);
    eb.push(t?+(b.rows[i].B.endings/t*100).toFixed(1):0);
  }
  setChart('cEnd',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{formatter:function(ps){
      var s=esc(ps[0].axisValue)+'<br>';
      ps.forEach(function(p){s+=markDot(p.color)+esc(p.seriesName)+': <b>'+p.value+'%</b><br>';});
      return s;}}),
    xAxis:{type:'category',data:cats,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({max:100,axisLabel:{color:MUTED,formatter:'{value}%'}}),
    series:[
      {name:A,type:'bar',stack:'e',data:ea,itemStyle:{color:COLORS.a},barMaxWidth:30},
      {name:B,type:'bar',stack:'e',data:eb,itemStyle:{color:COLORS.b},barMaxWidth:30}
    ]
  });
  // Restart behavior (range totals, grouped by category)
  ensureCanvas('cRestart');
  var tot=rt.tot;
  var catsR=['Re-knocks (no reply came)','Restarts after a reply','Reacted & left'];
  var va=[tot.A.self_restarts, Math.max(0,tot.A.initiations-tot.A.self_restarts), tot.A.reacted_leave];
  var vb=[tot.B.self_restarts, Math.max(0,tot.B.initiations-tot.B.self_restarts), tot.B.reacted_leave];
  setChart('cRestart',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{axisPointer:{type:'shadow'}}),
    xAxis:{type:'category',data:catsR,axisLine:{lineStyle:{color:GRID}},
      axisLabel:{color:MUTED,fontSize:10,interval:0}},
    yAxis:valAxis({}),
    series:[
      {name:A,type:'bar',data:va,itemStyle:{color:COLORS.a},barMaxWidth:30,barGap:'15%'},
      {name:B,type:'bar',data:vb,itemStyle:{color:COLORS.b},barMaxWidth:30}
    ]
  });
  // Waiting eagerness (avg minutes to answer a long-awaited reply)
  ensureCanvas('cWait');
  var wa=[],wb=[],anyW=false;
  for(var j=0;j<b.starts.length;j++){
    var ts=b.ts[j], rA=b.rows[j].A, rB=b.rows[j].B;
    var va2=rA.wait_reply_n?rA.wait_reply_sum_min/rA.wait_reply_n:null;
    var vb2=rB.wait_reply_n?rB.wait_reply_sum_min/rB.wait_reply_n:null;
    if(va2!=null||vb2!=null) anyW=true;
    wa.push([ts,va2==null?null:+va2.toFixed(2)]);
    wb.push([ts,vb2==null?null:+vb2.toFixed(2)]);
  }
  if(!anyW){ noData('cWait'); }
  else setChart('cWait',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':fmtDur(v);}}),
    xAxis:timeAxis(), yAxis:valAxis({axisLabel:{color:MUTED,formatter:function(v){return v+'m';}}}),
    series:[ lineSeries(A,wa,COLORS.a), lineSeries(B,wb,COLORS.b) ]
  });
  // Talks into the void: (turns - answered) / turns
  ensureCanvas('cVoid');
  var vva=[],vvb=[];
  for(var k=0;k<b.starts.length;k++){
    var ts2=b.ts[k], rA2=b.rows[k].A, rB2=b.rows[k].B;
    vva.push([ts2, rA2.turns?+((rA2.turns-rA2.turns_answered)/rA2.turns*100).toFixed(1):null]);
    vvb.push([ts2, rB2.turns?+((rB2.turns-rB2.turns_answered)/rB2.turns*100).toFixed(1):null]);
  }
  setChart('cVoid',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':v+'%';}}),
    xAxis:timeAxis(), yAxis:valAxis({axisLabel:{color:MUTED,formatter:'{value}%'}}),
    series:[ lineSeries(A,vva,COLORS.a), lineSeries(B,vvb,COLORS.b) ]
  });
}

/* ---- Turn length distribution (all-time, from extras) ---- */
function renderTurnHist(){
  var ex=state.chat.extras||{}; var th=ex.turn_hist||{};
  var A=state.users[0],B=state.users[1];
  var keys=['1','2','3','4','5','6','7','8','9','10+'];
  var ha=th[A]||{}, hb=th[B]||{};
  var sum=0; keys.forEach(function(k){sum+=(ha[k]||0)+(hb[k]||0);});
  if(!sum){ noData('cTurnHist'); return; }
  ensureCanvas('cTurnHist');
  setChart('cTurnHist',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{axisPointer:{type:'shadow'}}),
    xAxis:{type:'category',data:keys,name:'msgs / turn',nameLocation:'middle',nameGap:26,
      nameTextStyle:{color:MUTED,fontSize:10},
      axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({}),
    series:[
      {name:A,type:'bar',data:keys.map(function(k){return ha[k]||0;}),itemStyle:{color:COLORS.a},barMaxWidth:18,barGap:'10%'},
      {name:B,type:'bar',data:keys.map(function(k){return hb[k]||0;}),itemStyle:{color:COLORS.b},barMaxWidth:18}
    ]
  });
}

/* ---- Language cards (range-scoped: merged from monthly NLP blocks) ---- */
function monthsInRange(){
  var lo=ymd(state.start).slice(0,7), hi=ymd(state.end).slice(0,7);
  var ex=state.chat.extras||{}; var nm=ex.nlp_monthly||{};
  return Object.keys(nm).filter(function(m){return m>=lo&&m<=hi;}).sort();
}
function renderLanguage(){
  var host=el('nlpCards'); if(!host) return;
  var ex=state.chat.extras||{}; var nm=ex.nlp_monthly||{};
  var A=state.users[0],B=state.users[1];
  var months=monthsInRange();
  if(!months.length){
    host.innerHTML='<div class="card"><div class="placeholder" style="height:100px">No language data in range</div></div>';
    return;
  }
  // merge monthly counters over the active range
  function merged(user){
    var w={}, e={}, uniq=0, total=0;
    months.forEach(function(mo){
      var d=(nm[mo]||{})[user]; if(!d) return;
      (d.words||[]).forEach(function(it){w[it[0]]=(w[it[0]]||0)+it[1];});
      (d.emojis||[]).forEach(function(it){e[it[0]]=(e[it[0]]||0)+it[1];});
      uniq+=d.uniq||0; total+=d.total||0;
    });
    return {w:w,e:e,uniq:uniq,total:total};
  }
  var MA=merged(A), MB=merged(B);
  function top(counts,n){
    return Object.keys(counts).map(function(k){return [k,counts[k]];})
      .sort(function(x,y){return y[1]-x[1];}).slice(0,n);
  }
  // distinctive: log-odds with +1 smoothing over the merged range counts
  function distinctive(mine,other){
    var tu=0,to=0,k;
    for(k in mine.w) tu+=mine.w[k];
    for(k in other.w) to+=other.w[k];
    if(!tu) return [];
    var outArr=[];
    for(k in mine.w){
      var cu=mine.w[k], co=other.w[k]||0;
      if(cu+co<5) continue;
      var score=Math.log((cu+1)/(tu-cu+1))-Math.log((co+1)/(to-co+1));
      if(score>0) outArr.push([k,cu,score]);
    }
    outArr.sort(function(x,y){return y[2]-x[2];});
    return outArr.slice(0,12).map(function(it){return [it[0],it[1]];});
  }
  function tags(list,hot){
    if(!list||!list.length) return '<span class="faint">—</span>';
    return list.map(function(it){
      return '<span class="tag'+(hot?' hot':'')+'">'+esc(it[0])
        +'<span class="n">'+fmtNum(it[1])+'</span></span>';
    }).join('');
  }
  function emojiRow(list){
    if(!list||!list.length) return '<span class="faint">no emojis</span>';
    return list.map(function(it){
      return esc(it[0])+'<span class="n">'+fmtNum(it[1])+'</span>';
    }).join('');
  }
  var rangeLbl=months.length===1?months[0]:months[0]+' → '+months[months.length-1];
  function cardFor(user,cls,M,other){
    var inner=
      '<div class="nlp-label">Top emojis</div><div class="emoji-row">'+emojiRow(top(M.e,15))+'</div>'
      +'<div class="nlp-label">Signature words (used far more than the other)</div><div>'+tags(distinctive(M,other),true)+'</div>'
      +'<div class="nlp-label">Most used words</div><div>'+tags(top(M.w,18),false)+'</div>'
      +'<div class="vocab-line">In range: <b>'+fmtNum(M.total)+'</b> content words</div>';
    return '<div class="card"><h3><span class="dot'+(cls==='a'?'A':'B')+'"></span> '+esc(user)
      +'</h3><div class="sub">'+esc(rangeLbl)+' · monthly resolution</div>'+inner+'</div>';
  }
  host.innerHTML=cardFor(A,'a',MA,MB)+cardFor(B,'b',MB,MA);
}

/* ---- Psycholinguistics: we-ness, sentiment, LSM, TTR, courtesy ---- */
function renderPsycho(b,rt){
  var A=state.users[0],B=state.users[1];
  var ex=state.chat.extras||{};
  if(!b.starts.length){ noData('cWe'); noData('cSent'); noData('cLSM'); noData('cTTR');
    var cb0=el('courtesyBox'); if(cb0) cb0.innerHTML='<div class="placeholder">No data in range</div>';
    return; }
  // We-ness per bucket
  ensureCanvas('cWe');
  var wa=[],wb=[];
  for(var i=0;i<b.starts.length;i++){
    var ts=b.ts[i], rA=b.rows[i].A, rB=b.rows[i].B;
    var da=rA.we_words+rA.i_words, db=rB.we_words+rB.i_words;
    wa.push([ts, da?+(rA.we_words/da*100).toFixed(1):null]);
    wb.push([ts, db?+(rB.we_words/db*100).toFixed(1):null]);
  }
  setChart('cWe',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':v+'%';}}),
    xAxis:timeAxis(), yAxis:valAxis({axisLabel:{color:MUTED,formatter:'{value}%'}}),
    series:[ lineSeries(A,wa,COLORS.a), lineSeries(B,wb,COLORS.b) ]
  });
  // Positivity balance per bucket, with Gottman 5:1 (83.3%) reference
  ensureCanvas('cSent');
  var sa=[],sb=[];
  for(var j=0;j<b.starts.length;j++){
    var ts2=b.ts[j], rA2=b.rows[j].A, rB2=b.rows[j].B;
    var ta=rA2.pos_words+rA2.neg_words, tb=rB2.pos_words+rB2.neg_words;
    sa.push([ts2, ta?+(rA2.pos_words/ta*100).toFixed(1):null]);
    sb.push([ts2, tb?+(rB2.pos_words/tb*100).toFixed(1):null]);
  }
  setChart('cSent',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':v+'% positive';}}),
    xAxis:timeAxis(), yAxis:valAxis({max:100,axisLabel:{color:MUTED,formatter:'{value}%'}}),
    series:[ lineSeries(A,sa,COLORS.a), lineSeries(B,sb,COLORS.b),
      {name:'5:1',type:'line',showSymbol:false,silent:true,
       data:b.ts.map(function(t){return [t,83.3];}),
       lineStyle:{color:MUTED,type:'dashed',width:1},itemStyle:{color:MUTED},tooltip:{show:false}} ]
  });
  // LSM per month (couple-level), filtered to range months
  var months=monthsInRange();
  var lsm=ex.lsm_monthly||{};
  var lsmPts=months.map(function(mo){
    return [parseYMD(mo+'-01').getTime(), lsm[mo]==null?null:+(lsm[mo]*100).toFixed(1)];
  }).filter(function(p){return p[1]!=null;});
  if(!lsmPts.length){ noData('cLSM'); }
  else { ensureCanvas('cLSM');
    setChart('cLSM',{
      grid:baseGrid(),
      tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':v+'%';}}),
      xAxis:timeAxis(), yAxis:valAxis({max:100,axisLabel:{color:MUTED,formatter:'{value}%'}}),
      series:[ lineSeries('Style matching',lsmPts,COLORS.a) ]
    }); }
  // Vocabulary richness (TTR) per month per user
  var nm=ex.nlp_monthly||{};
  var ttrA=[],ttrB=[];
  months.forEach(function(mo){
    var t=parseYMD(mo+'-01').getTime();
    var da2=(nm[mo]||{})[A], db2=(nm[mo]||{})[B];
    if(da2&&da2.total>=100) ttrA.push([t,+(da2.uniq/da2.total*100).toFixed(1)]);
    if(db2&&db2.total>=100) ttrB.push([t,+(db2.uniq/db2.total*100).toFixed(1)]);
  });
  if(!ttrA.length&&!ttrB.length){ noData('cTTR'); }
  else { ensureCanvas('cTTR');
    setChart('cTTR',{
      grid:baseGrid(), legend:legend([A,B]),
      tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':v+'%';}}),
      xAxis:timeAxis(), yAxis:valAxis({axisLabel:{color:MUTED,formatter:'{value}%'}}),
      series:[ lineSeries(A,ttrA,COLORS.a), lineSeries(B,ttrB,COLORS.b) ]
    }); }
  // Courtesy markers (range totals per 100 msgs)
  var cb=el('courtesyBox'); if(!cb) return;
  var tot=rt.tot;
  function row(user,cls,c){
    var g=c.msgs?(c.gratitude/c.msgs*100):null, ap=c.msgs?(c.apology/c.msgs*100):null;
    return '<div style="margin:10px 0"><span class="dot'+cls+'"></span> <b>'+esc(user)+'</b>'
      +'<div class="vocab-line">🙏 gratitude: <b>'+fmtNum(c.gratitude)+'</b> ('+(g==null?'—':g.toFixed(1))+'/100 msgs)'
      +' &nbsp;·&nbsp; 🙇 apologies: <b>'+fmtNum(c.apology)+'</b> ('+(ap==null?'—':ap.toFixed(1))+'/100 msgs)</div></div>';
  }
  cb.innerHTML=row(A,'A',tot.A)+row(B,'B',tot.B);
}

/* ---- Rhythm: two 7x24 heatmaps + night-share line ---- */
function renderRhythm(rt,b){
  var A=state.users[0],B=state.users[1];
  var maxV=0;
  ['A','B'].forEach(function(u){for(var i=0;i<168;i++) maxV=Math.max(maxV,rt.hours[u][i]);});
  if(maxV<=0){ noData('cHeatA'); noData('cHeatB'); }
  else { ensureCanvas('cHeatA'); ensureCanvas('cHeatB');
    heatmap('cHeatA',rt.hours.A,maxV); heatmap('cHeatB',rt.hours.B,maxV); }
  // night-share line per bucket
  if(!b.starts.length){ noData('cNight'); return; }
  ensureCanvas('cNight');
  var na=[],nb=[];
  for(var i=0;i<b.starts.length;i++){
    var ts=b.ts[i];
    na.push([ts,b.rows[i].A.msgs?+(b.rows[i].A.night_msgs/b.rows[i].A.msgs*100).toFixed(1):0]);
    nb.push([ts,b.rows[i].B.msgs?+(b.rows[i].B.night_msgs/b.rows[i].B.msgs*100).toFixed(1):0]);
  }
  setChart('cNight',{
    grid:{left:52,right:18,top:24,bottom:30}, legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v+'%';}}),
    xAxis:timeAxis(), yAxis:valAxis({axisLabel:{color:MUTED,formatter:'{value}%'}}),
    series:[ lineSeries(A,na,COLORS.a), lineSeries(B,nb,COLORS.b) ]
  });
}
function heatmap(id,flat,maxV){
  var data=[];
  for(var wd=0;wd<7;wd++) for(var h=0;h<24;h++) data.push([h,wd,flat[wd*24+h]]);
  setChart(id,{
    grid:{left:44,right:14,top:12,bottom:52,containLabel:false},
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){return WEEKDAYS[p.value[1]]+' '+HOURS[p.value[0]]+':00 · <b>'+fmtNum(p.value[2])+'</b>';}},
    xAxis:{type:'category',data:HOURS,splitArea:{show:false},
      axisLabel:{color:MUTED,interval:2,fontSize:10},axisLine:{lineStyle:{color:GRID}}},
    yAxis:{type:'category',data:WEEKDAYS,axisLabel:{color:MUTED,fontSize:11},axisLine:{lineStyle:{color:GRID}}},
    visualMap:{min:0,max:maxV||1,calculable:false,orient:'horizontal',left:'center',bottom:6,
      itemWidth:12,itemHeight:120,inRange:{color:HEAT},textStyle:{color:MUTED}},
    series:[{type:'heatmap',data:data,progressive:0,
      itemStyle:{borderColor:PANEL,borderWidth:1},emphasis:{itemStyle:{borderColor:TEXT}}}]
  });
}

/* ---- Activity calendar (GitHub-style daily heatmap) ---- */
function renderCalendar(){
  var A=state.users[0],B=state.users[1];
  var byYear={}, maxV=0, ents=dailyEntries();
  for(var i=0;i<ents.length;i++){
    var ds=ents[i][0]; if(!inRange(ds)) continue;
    var cells=ents[i][1];
    var v=(cells[A]?cells[A].msgs||0:0)+(cells[B]?cells[B].msgs||0:0);
    if(!v) continue;
    var y=ds.slice(0,4);
    (byYear[y]=byYear[y]||[]).push([ds,v]);
    if(v>maxV) maxV=v;
  }
  var years=Object.keys(byYear).sort();
  if(!years.length){ noData('cCal'); return; }
  var node=el('cCal'); if(!node) return;
  var ROW=150;
  var wantH=years.length*ROW+50;
  if(node.__h!==wantH){                 // height changed -> re-init the chart
    node.__h=wantH; node.style.height=wantH+'px';
    if(charts['cCal']){ try{charts['cCal'].dispose();}catch(e){} charts['cCal']=null; }
  }
  ensureCanvas('cCal');
  var rangeLo=ymd(state.start), rangeHi=ymd(state.end);
  var calendars=years.map(function(y,i){
    var lo=(y===rangeLo.slice(0,4))?rangeLo:(y+'-01-01');
    var hi=(y===rangeHi.slice(0,4))?rangeHi:(y+'-12-31');
    return {top:34+i*ROW,left:46,right:20,cellSize:['auto',13],range:[lo,hi],
      itemStyle:{color:PANEL,borderColor:GRID,borderWidth:1.5},
      splitLine:{lineStyle:{color:GRID,width:1}},
      dayLabel:{color:MUTED,fontSize:9,firstDay:1,nameMap:['S','M','T','W','T','F','S']},
      monthLabel:{color:MUTED,fontSize:10},
      yearLabel:{show:true,color:MUTED,fontSize:12,margin:28}};
  });
  var series=years.map(function(y,i){
    return {type:'heatmap',coordinateSystem:'calendar',calendarIndex:i,data:byYear[y]};
  });
  setChart('cCal',{
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){return esc(p.value[0])+' · <b>'+fmtNum(p.value[1])+'</b> msgs';}},
    visualMap:{min:0,max:maxV||1,orient:'horizontal',left:'center',bottom:0,
      itemWidth:10,itemHeight:110,inRange:{color:HEAT},textStyle:{color:MUTED},calculable:false},
    calendar:calendars,
    series:series
  });
}

/* ---- Message depth: average words per TURN (a turn = consecutive run of
   messages by one person, ended by the partner or a session gap). Someone who
   splits one thought into five short messages still gets the full thought's
   word count credited to a single turn. ---- */
function renderDepth(b){
  var A=state.users[0],B=state.users[1];
  if(!b.starts.length){ noData('cDepth'); return; }
  ensureCanvas('cDepth');
  var da=[],db=[];
  for(var i=0;i<b.starts.length;i++){
    var ts=b.ts[i], rA=b.rows[i].A, rB=b.rows[i].B;
    da.push([ts, rA.turns?+(rA.words/rA.turns).toFixed(2):null]);
    db.push([ts, rB.turns?+(rB.words/rB.turns).toFixed(2):null]);
  }
  setChart('cDepth',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':v+' w/turn';}}),
    xAxis:timeAxis(), yAxis:valAxis({}),
    series:[ lineSeries(A,da,COLORS.a), lineSeries(B,db,COLORS.b) ]
  });
}

/* ---- Monologue vs dialogue: average messages per turn ---- */
function renderTurns(b){
  var A=state.users[0],B=state.users[1];
  if(!b.starts.length){ noData('cTurns'); return; }
  ensureCanvas('cTurns');
  var ta=[],tb=[];
  for(var i=0;i<b.starts.length;i++){
    var ts=b.ts[i], rA=b.rows[i].A, rB=b.rows[i].B;
    ta.push([ts, rA.turns?+(rA.msgs/rA.turns).toFixed(2):null]);
    tb.push([ts, rB.turns?+(rB.msgs/rB.turns).toFixed(2):null]);
  }
  setChart('cTurns',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':v+' msg/turn';}}),
    xAxis:timeAxis(),
    yAxis:valAxis({min:1}),
    series:[ lineSeries(A,ta,COLORS.a), lineSeries(B,tb,COLORS.b),
      {name:'dialogue line',type:'line',showSymbol:false,silent:true,
       data:b.ts.map(function(t){return [t,1];}),
       lineStyle:{color:MUTED,type:'dashed',width:1},itemStyle:{color:MUTED},
       tooltip:{show:false}} ]
  });
}

/* ---- Media mix: kinds per person (range-scoped) ---- */
function renderMediaMix(rt){
  var A=state.users[0],B=state.users[1];
  var tot=rt.tot;
  var kinds=['Photos','Videos','Voice','Shares'];
  var va=[tot.A.photos,tot.A.videos,tot.A.voice,tot.A.shares];
  var vb=[tot.B.photos,tot.B.videos,tot.B.voice,tot.B.shares];
  var sum=0; va.concat(vb).forEach(function(v){sum+=v;});
  if(!sum){ noData('cMedia'); return; }
  ensureCanvas('cMedia');
  setChart('cMedia',{
    grid:baseGrid(), legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{axisPointer:{type:'shadow'}}),
    xAxis:{type:'category',data:kinds,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({}),
    series:[
      {name:A,type:'bar',data:va,itemStyle:{color:COLORS.a},barMaxWidth:34,barGap:'15%'},
      {name:B,type:'bar',data:vb,itemStyle:{color:COLORS.b},barMaxWidth:34}
    ]
  });
}

/* ---- Shifts vs previous period (git-diff style) ---- */
function renderShifts(rt){
  var host=el('shiftList'); if(!host) return;
  var A=state.users[0],B=state.users[1];
  var tot=rt.tot;
  var pw=prevWindowTotals(), prev=pw.tot, days=pw.days;
  var head='<div class="diff-head">'+esc(ymd(state.start))+' → '+esc(ymd(state.end))
    +' &nbsp;vs&nbsp; '+esc(ymd(pw.start))+' → '+esc(ymd(pw.end))+' ('+days+'d each)</div>';
  if(prev.A.msgs+prev.B.msgs===0){
    host.innerHTML=head+'<div class="placeholder" style="height:70px">No data in the previous window — nothing to compare against</div>';
    return;
  }
  function per100(c,f1,f2){return c[f2]?c[f1]/c[f2]*100:null;}
  function lat(c){return c.resp_lat_n?c.resp_lat_sum_min/c.resp_lat_n:null;}
  function wpm(c){return c.msgs?c.words/c.msgs:null;}
  function nshare(c){return c.msgs?c.night_msgs/c.msgs:null;}
  var fN=fmtNum, f1=function(v){return v.toFixed(1);},
      fP=function(v){return fmtPct(v,1);}, fD=fmtDur;
  function wpt(c){return c.turns?c.words/c.turns:null;}
  function mpt(c){return c.turns?c.msgs/c.turns:null;}
  // [label, fn(cell)->value, formatter, mode] mode: 'rel' (relative %) | 'pp' (share, point diff)
  var defs=[
    ['Messages',            function(c){return c.msgs;},               fN, 'rel'],
    ['Words',               function(c){return c.words;},              fN, 'rel'],
    ['Words / message',     wpm,                                       f1, 'rel'],
    ['Words / turn',        wpt,                                       f1, 'rel'],
    ['Turn length (msgs)',  mpt,                                       f1, 'rel'],
    ['Questions / 100',     function(c){return per100(c,'questions','msgs');}, f1, 'rel'],
    ['Emoji / 100',         function(c){return per100(c,'emoji','msgs');},     f1, 'rel'],
    ['Reactions given',     function(c){return c.reactions_given;},    fN, 'rel'],
    ['Reply latency',       lat,                                       fD, 'rel'],
    ['Night share',         nshare,                                    fP, 'pp'],
    ['Media shared',        function(c){return c.media;},              fN, 'rel'],
    ['Photos',              function(c){return c.photos;},             fN, 'rel'],
    ['Videos',              function(c){return c.videos;},             fN, 'rel'],
    ['Voice notes',         function(c){return c.voice;},              fN, 'rel'],
    ['Shares / links',      function(c){return c.shares;},             fN, 'rel'],
    ['Initiations',         function(c){return c.initiations;},        fN, 'rel'],
    ['Final words',         function(c){return c.endings;},            fN, 'rel'],
    ['Re-knocks',           function(c){return c.self_restarts;},      fN, 'rel'],
    ['Reacted & left',      function(c){return c.reacted_leave;},      fN, 'rel'],
    ['Wait-reply speed',    function(c){return c.wait_reply_n?c.wait_reply_sum_min/c.wait_reply_n:null;}, fD, 'rel'],
    ['Void-turn share',     function(c){return c.turns?(c.turns-c.turns_answered)/c.turns:null;}, fP, 'pp'],
    ['We-ness',             function(c){var d=c.we_words+c.i_words;return d?c.we_words/d:null;}, fP, 'pp'],
    ['Positivity',          function(c){var d=c.pos_words+c.neg_words;return d?c.pos_words/d:null;}, fP, 'pp'],
    ['Gratitude',           function(c){return c.gratitude;},          fN, 'rel'],
    ['Apologies',           function(c){return c.apology;},            fN, 'rel']
  ];
  var rows=[];
  function addRow(label,cv,pv,fmt,mode){
    if(cv==null&&pv==null) return;
    var c=cv==null?0:cv, p=pv==null?0:pv;
    var d,mag;
    if(mode==='pp'){ d=c-p; if(Math.abs(d)<0.005) return; mag=(Math.abs(d)*100).toFixed(1)+'pp'; }
    else { if(p===0&&c===0) return;
      if(p===0){ d=1; mag='new'; } else { d=(c-p)/p; if(Math.abs(d)<0.005) return; mag=fmtPct(Math.abs(d),Math.abs(d)<0.1?1:0); } }
    var up=d>=0;
    rows.push({up:up,label:label,prev:pv==null?'—':fmt(p),cur:cv==null?'—':fmt(c),mag:(up?'+':'−')+mag});
  }
  for(var i=0;i<defs.length;i++){
    var def=defs[i];
    addRow(def[0]+' · '+A, def[1](tot.A), def[1](prev.A), def[2], def[3]);
    addRow(def[0]+' · '+B, def[1](tot.B), def[1](prev.B), def[2], def[3]);
  }
  // couple-level rows
  var initTot=tot.A.initiations+tot.B.initiations, pInitTot=prev.A.initiations+prev.B.initiations;
  addRow('Initiation share · '+A,
    initTot?tot.A.initiations/initTot:null, pInitTot?prev.A.initiations/pInitTot:null, fP, 'pp');
  var msgsT=tot.A.msgs+tot.B.msgs, pMsgsT2=prev.A.msgs+prev.B.msgs;
  var turnsT2=tot.A.turns+tot.B.turns, pTurnsT2=prev.A.turns+prev.B.turns;
  addRow('Dialogue index',
    msgsT?turnsT2/msgsT:null, pMsgsT2?pTurnsT2/pMsgsT2:null, fP, 'pp');
  var endT2=tot.A.endings+tot.B.endings, pEndT2=prev.A.endings+prev.B.endings;
  addRow('Final word share · '+A,
    endT2?tot.A.endings/endT2:null, pEndT2?prev.A.endings/pEndT2:null, fP, 'pp');
  if(!rows.length){
    host.innerHTML=head+'<div class="placeholder" style="height:70px">No metric changed between the two windows</div>';
    return;
  }
  rows.sort(function(x,y){return (y.up?1:0)-(x.up?1:0);});
  var h=head;
  for(var r=0;r<rows.length;r++){
    var row=rows[r];
    h+='<div class="drow '+(row.up?'up':'down')+'">'
      +'<span class="sign">'+(row.up?'+':'−')+'</span>'
      +'<span class="m">'+esc(row.label)+'</span>'
      +'<span class="vals">'+esc(row.prev)+' → '+esc(row.cur)+'</span>'
      +'<span class="d">'+esc(row.mag)+'</span>'
      +'</div>';
  }
  host.innerHTML=h;
}

/* ---- Lifetime cards (range-independent) ---- */
function renderLifetime(){
  var lt=state.chat.lifetime||{}, A=state.users[0], B=state.users[1];
  function pu(block,user,field,fmt){
    var v=(block&&block[user])?block[user][field]:null;
    return v==null?'—':fmt(v);
  }
  var pct=function(v){return (v*100).toFixed(0)+'%';};
  var pct1=function(v){return (v*100).toFixed(1)+'%';};
  var num=function(v){return fmtNum(v);};
  var fw=lt.final_word_dominance||{};
  function fwv(u){return fw[u]==null?'—':pct(fw[u]);}
  var defs=[
    ['Final word %', function(u){return fwv(u);}],
    ['Initiation share', function(u){return pu(lt.initiation,u,'initiation_share',pct);}],
    ['Questions / 100 msgs', function(u){return pu(lt.question_asymmetry,u,'questions_per_100_msgs',num);}],
    ['Answered rate', function(u){return pu(lt.question_asymmetry,u,'answered_rate',pct1);}],
    ['Turning-toward (partner)', function(u){return pu(lt.bid_response,u,'partner_turned_toward_rate',pct1);}],
    ['Reactions given', function(u){return pu(lt.affect_economy,u,'reactions_given',num);}],
    ['Emoji / 100 msgs', function(u){return pu(lt.affect_economy,u,'emoji_per_100_msgs',num);}],
    ['Night share', function(u){return pu(lt.circadian&&lt.circadian.per_user,u,'night_share',pct);}],
    ['Repair share', function(u){return pu(lt.repair,u,'repair_share',pct);}],
    ['Double texts', function(u){return pu(lt.double_texting,u,'double_texts',num);}],
    ['Momentum-kill share', function(u){return pu(lt.half_life&&lt.half_life.per_user,u,'momentum_kill_share',pct1);}]
  ];
  function tableFor(user){
    var h='<table class="lt-table"><thead><tr><th>Metric</th><th class="num">Value</th></tr></thead><tbody>';
    for(var i=0;i<defs.length;i++){
      h+='<tr><td>'+esc(defs[i][0])+'</td><td class="num">'+defs[i][1](user)+'</td></tr>';
    }
    var ex=state.chat.extras||{}; var mr=(ex.media_recip||{})[user];
    var mrRow=(mr&&mr.media_sent)?('<tr><td>Media reciprocity</td><td class="num">'
      +pct(mr.media_reciprocated/mr.media_sent)+' of '+fmtNum(mr.media_sent)+'</td></tr>'):'';
    var mh=(lt.circadian&&lt.circadian.overlap_coefficient!=null)?
      ('<tr><td>Circadian overlap</td><td class="num">'+pct(lt.circadian.overlap_coefficient)+'</td></tr>'):'';
    var half=(lt.half_life&&lt.half_life.median_half_life_minutes!=null)?
      ('<tr><td>Median half-life</td><td class="num">'+fmtDur(lt.half_life.median_half_life_minutes)+'</td></tr>'):'';
    return h+mrRow+mh+half+'</tbody></table>';
  }
  el('ltCards').innerHTML =
    ltCard(A,'a',tableFor(A)) + ltCard(B,'b',tableFor(B));
}
function ltCard(user,cls,inner){
  return '<div class="card"><h3><span class="dot'+(cls==='a'?'A':'B')+'"></span> '+esc(user)
    +'</h3><div class="sub">All-time</div>'+inner+'</div>';
}

/* ============================================================ *
 * GROUP MODE (3+ participants)
 * All pair-only sections are hidden; a per-member layout is
 * rendered instead. 1v1 chats never enter any function here.
 * ============================================================ */
function groupMembers(){
  var mem=(state.chat.participants||[]).slice();
  var others=(state.chat.group&&state.chat.group.others_key)||'Others';
  var d=state.chat.daily, hasOthers=false;
  for(var k in d){ if(d[k][others]){ hasOthers=true; break; } }
  if(hasOthers && mem.indexOf(others)<0) mem.push(others);
  return {members:mem, others:others};
}
function memberColor(name,i,others){
  return name===others?OTHERS_COLOR:GROUP_PAL[i%GROUP_PAL.length];
}
function groupBuildBuckets(members){
  var gran=effGran(), map={}, ents=dailyEntries();
  for(var i=0;i<ents.length;i++){
    var ds=ents[i][0]; if(!inRange(ds)) continue;
    var bs=bucketStart(ds,gran);
    if(!map[bs]){ map[bs]={}; members.forEach(function(m){map[bs][m]=blank();}); }
    var cells=ents[i][1];
    members.forEach(function(m){ if(cells[m]) addInto(map[bs][m],cells[m]); });
  }
  var starts=Object.keys(map).sort();
  return {starts:starts, ts:starts.map(function(s){return parseYMD(s).getTime();}),
          rows:starts.map(function(s){return map[s];}), gran:gran};
}
function groupRangeTotals(members,startD,endD){
  var tot={}, hours={}, combined=new Array(168).fill(0);
  members.forEach(function(m){tot[m]=blank();hours[m]=new Array(168).fill(0);});
  var ents=dailyEntries();
  for(var i=0;i<ents.length;i++){
    var ds=ents[i][0], t=parseYMD(ds).getTime();
    if(t<startD.getTime()||t>endD.getTime()) continue;
    var wd=(parseYMD(ds).getUTCDay()+6)%7, cells=ents[i][1];
    members.forEach(function(m){
      if(!cells[m]) return;
      addInto(tot[m],cells[m]);
      if(cells[m].hours) for(var h=0;h<24;h++){ hours[m][wd*24+h]+=cells[m].hours[h]; combined[wd*24+h]+=cells[m].hours[h]; }
    });
  }
  return {tot:tot,hours:hours,combined:combined};
}

function renderSkeletonGroup(){
  var n=(state.chat.member_count||(state.chat.participants||[]).length);
  el('app').innerHTML =
    section('Pulse','<div class="grid kpis" id="kpiRow"></div>')
  + section('Story timeline',
      card('Message volume','Stacked messages per member (+ Others) — '+esc(String(n))+' members',
        '<div class="chart tall" id="cgVolume"></div>')
      + card('Activity calendar','Daily total message volume across the group',
        '<div class="chart" id="cgCal"></div>'))
  + section('Members',
      '<div class="grid cols-2">'
      + card('Member share','Message share across the group (in range)','<div class="chart tall" id="cgShare"></div>')
      + card('Who reacts to whom','Reaction giver (row) → receiver (column)','<div class="chart tall" id="cgReactMx"></div>')
      + '</div>')
  + section('Balance',
      '<div class="grid cols-2">'
      + card('Initiation share','Who opens conversations (per bucket)','<div class="chart" id="cgInit"></div>')
      + card('Question rate','Interrogatives per 100 messages','<div class="chart" id="cgQ"></div>')
      + '</div>')
  + section('Affect',
      card('Reactions given','Reactions handed out per member (per bucket)','<div class="chart" id="cgReact"></div>'))
  + section('Rhythm',
      card('Group activity clock','Combined messages by weekday × hour (all members)','<div class="chart" id="cgHeat"></div>'))
  + section('Language',
      '<div class="grid cols-2" id="nlpCards"></div>')
  + section('Shifts vs previous period',
      card('What changed','Per-member messages / words / reactions vs the previous window of equal length',
        '<div class="diff" id="shiftList"></div>'))
  + section('Pair metrics',
      card('Hidden for groups','',
        '<div class="placeholder" style="height:60px">Pair metrics are hidden for group chats</div>'));
}

function renderAllGroup(){
  if(!state.chat){return;}
  var gm=groupMembers(), members=gm.members, others=gm.others;
  var colors=members.map(function(m,i){return memberColor(m,i,others);});
  var b=groupBuildBuckets(members);
  var rt=groupRangeTotals(members,state.start,state.end);
  var has=b.starts.length>0;
  safe(function(){renderGroupKPIs(rt,members,has);},'gkpi');
  safe(function(){renderGroupVolume(b,members,colors);},'gvolume');
  safe(function(){renderGroupCalendar(members);},'gcal');
  safe(function(){renderGroupShare(rt,members,colors);},'gshare');
  safe(function(){renderGroupReactMatrix(members);},'greactmx');
  safe(function(){renderGroupInit(b,members,colors);},'ginit');
  safe(function(){renderGroupQ(b,members,colors);},'gq');
  safe(function(){renderGroupReact(b,members,colors);},'greact');
  safe(function(){renderGroupHeat(rt);},'gheat');
  safe(function(){renderGroupLanguage(colors);},'glang');
  safe(function(){renderGroupShifts(rt,members);},'gshifts');
}

function renderGroupKPIs(rt,members,has){
  var tot=rt.tot, totalMsgs=0, words=0, media=0, top=null, topv=-1;
  members.forEach(function(m){
    totalMsgs+=tot[m].msgs; words+=tot[m].words; media+=tot[m].media;
    if(tot[m].msgs>topv){topv=tot[m].msgs; top=m;}
  });
  var days=dayDiff(state.start,state.end)+1, perDay=days>0?totalMsgs/days:0;
  var share=totalMsgs?topv/totalMsgs:null;
  var tiles=[
    kpi('Messages',fmtNum(totalMsgs),null,'<span class="split faint">'+esc(String(members.length))+' members</span>'),
    kpi('Messages / day',fmtNum(perDay),null,'<span class="split faint">over '+days+'d</span>'),
    kpi('Words',fmtNum(words),null,''),
    kpi('Media shared',fmtNum(media),null,''),
    kpi('Most active member',share==null?'—':fmtPct(share),null,'<span class="split faint">'+esc(top||'—')+'</span>')
  ];
  el('kpiRow').innerHTML = has?tiles.join(''):'<div class="kpi"><div class="placeholder">No data in range</div></div>';
}

function renderGroupVolume(b,members,colors){
  if(!b.starts.length){ noData('cgVolume'); return; }
  ensureCanvas('cgVolume');
  var series=members.map(function(m,i){
    return {name:m,type:'line',stack:'v',
      data:b.starts.map(function(s,j){return [b.ts[j], b.rows[j][m].msgs];}),
      showSymbol:false,areaStyle:{color:colors[i],opacity:.55},
      lineStyle:{width:1,color:colors[i]},itemStyle:{color:colors[i]}};
  });
  setChart('cgVolume',{
    grid:baseGrid(), legend:legend(members),
    tooltip:Object.assign(tooltipBase(),{}),
    xAxis:timeAxis(), yAxis:valAxis({}),
    dataZoom:[{type:'slider',bottom:2,height:16,borderColor:GRID,
      textStyle:{color:MUTED},fillerColor:'rgba(77,182,172,.15)'},{type:'inside'}],
    series:series
  });
}

function renderGroupCalendar(members){
  var byYear={},maxV=0,ents=dailyEntries();
  for(var i=0;i<ents.length;i++){
    var ds=ents[i][0]; if(!inRange(ds)) continue;
    var cells=ents[i][1], v=0;
    members.forEach(function(m){ if(cells[m]) v+=cells[m].msgs||0; });
    if(!v) continue;
    var y=ds.slice(0,4); (byYear[y]=byYear[y]||[]).push([ds,v]); if(v>maxV)maxV=v;
  }
  var years=Object.keys(byYear).sort();
  if(!years.length){ noData('cgCal'); return; }
  var node=el('cgCal'); if(!node) return;
  var ROW=150, wantH=years.length*ROW+50;
  if(node.__h!==wantH){ node.__h=wantH; node.style.height=wantH+'px';
    if(charts['cgCal']){ try{charts['cgCal'].dispose();}catch(e){} charts['cgCal']=null; } }
  ensureCanvas('cgCal');
  var rangeLo=ymd(state.start), rangeHi=ymd(state.end);
  var calendars=years.map(function(y,i){
    var lo=(y===rangeLo.slice(0,4))?rangeLo:(y+'-01-01');
    var hi=(y===rangeHi.slice(0,4))?rangeHi:(y+'-12-31');
    return {top:34+i*ROW,left:46,right:20,cellSize:['auto',13],range:[lo,hi],
      itemStyle:{color:PANEL,borderColor:GRID,borderWidth:1.5},
      splitLine:{lineStyle:{color:GRID,width:1}},
      dayLabel:{color:MUTED,fontSize:9,firstDay:1,nameMap:['S','M','T','W','T','F','S']},
      monthLabel:{color:MUTED,fontSize:10},
      yearLabel:{show:true,color:MUTED,fontSize:12,margin:28}};
  });
  var series=years.map(function(y,i){
    return {type:'heatmap',coordinateSystem:'calendar',calendarIndex:i,data:byYear[y]};
  });
  setChart('cgCal',{
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){return esc(p.value[0])+' · <b>'+fmtNum(p.value[1])+'</b> msgs';}},
    visualMap:{min:0,max:maxV||1,orient:'horizontal',left:'center',bottom:0,
      itemWidth:10,itemHeight:110,inRange:{color:HEAT},textStyle:{color:MUTED},calculable:false},
    calendar:calendars, series:series
  });
}

function renderGroupShare(rt,members,colors){
  var tot=rt.tot, total=0;
  var arr=members.map(function(m,i){return {m:m,v:tot[m].msgs,c:colors[i]};});
  arr.forEach(function(x){total+=x.v;});
  if(!total){ noData('cgShare'); return; }
  arr.sort(function(a,b){return a.v-b.v;});   // ascending: biggest at top
  ensureCanvas('cgShare');
  setChart('cgShare',{
    grid:{left:130,right:46,top:10,bottom:24},
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){return esc(p.name)+': <b>'+fmtNum(p.value)+'</b> ('+(p.value/total*100).toFixed(1)+'%)';}},
    xAxis:valAxis({}),
    yAxis:{type:'category',data:arr.map(function(x){return x.m;}),
      axisLabel:{color:MUTED},axisLine:{lineStyle:{color:GRID}}},
    series:[{type:'bar',barMaxWidth:22,
      data:arr.map(function(x){return {value:x.v,itemStyle:{color:x.c}};}),
      label:{show:true,position:'right',color:MUTED,
        formatter:function(p){return (p.value/total*100).toFixed(1)+'%';}}}]
  });
}

function renderGroupReactMatrix(members){
  var rm=(state.chat.group&&state.chat.group.reaction_matrix)||{};
  var data=[],maxV=0;
  members.forEach(function(g,gi){
    members.forEach(function(r,ri){
      var v=(rm[g]&&rm[g][r])||0; data.push([ri,gi,v]); if(v>maxV)maxV=v;
    });
  });
  if(maxV<=0){ noData('cgReactMx'); return; }
  ensureCanvas('cgReactMx');
  setChart('cgReactMx',{
    grid:{left:110,right:20,top:16,bottom:96},
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){return esc(members[p.value[1]])+' → '+esc(members[p.value[0]])
        +': <b>'+fmtNum(p.value[2])+'</b>';}},
    xAxis:{type:'category',data:members,axisLabel:{color:MUTED,rotate:45,fontSize:10},axisLine:{lineStyle:{color:GRID}}},
    yAxis:{type:'category',data:members,axisLabel:{color:MUTED,fontSize:10},axisLine:{lineStyle:{color:GRID}}},
    visualMap:{min:0,max:maxV||1,calculable:false,orient:'horizontal',left:'center',bottom:8,
      itemWidth:12,itemHeight:100,inRange:{color:HEAT},textStyle:{color:MUTED}},
    series:[{type:'heatmap',data:data,itemStyle:{borderColor:PANEL,borderWidth:1},
      emphasis:{itemStyle:{borderColor:TEXT}}}]
  });
}

function renderGroupInit(b,members,colors){
  if(!b.starts.length){ noData('cgInit'); return; }
  ensureCanvas('cgInit');
  var cats=b.starts.slice();
  var series=members.map(function(m,i){
    return {name:m,type:'bar',stack:'i',barMaxWidth:30,itemStyle:{color:colors[i]},
      data:b.rows.map(function(r){ var t=0; members.forEach(function(mm){t+=r[mm].initiations;});
        return t?+(r[m].initiations/t*100).toFixed(1):0; })};
  });
  setChart('cgInit',{
    grid:baseGrid(), legend:legend(members),
    tooltip:Object.assign(tooltipBase(),{formatter:function(ps){
      var s=esc(ps[0].axisValue)+'<br>';
      ps.forEach(function(p){s+=markDot(p.color)+esc(p.seriesName)+': <b>'+p.value+'%</b><br>';});
      return s;}}),
    xAxis:{type:'category',data:cats,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({max:100,axisLabel:{color:MUTED,formatter:'{value}%'}}),
    series:series
  });
}

function renderGroupQ(b,members,colors){
  if(!b.starts.length){ noData('cgQ'); return; }
  ensureCanvas('cgQ');
  var series=members.map(function(m,i){
    return lineSeries(m,b.starts.map(function(s,j){
      return [b.ts[j], b.rows[j][m].msgs?+(b.rows[j][m].questions/b.rows[j][m].msgs*100).toFixed(1):null];
    }),colors[i]);
  });
  setChart('cgQ',{
    grid:baseGrid(), legend:legend(members),
    tooltip:Object.assign(tooltipBase(),{valueFormatter:function(v){return v==null?'—':v+'/100';}}),
    xAxis:timeAxis(), yAxis:valAxis({}), series:series
  });
}

function renderGroupReact(b,members,colors){
  if(!b.starts.length){ noData('cgReact'); return; }
  ensureCanvas('cgReact');
  var cats=b.starts.slice();
  var series=members.map(function(m,i){
    return {name:m,type:'bar',stack:'r',barMaxWidth:30,itemStyle:{color:colors[i]},
      data:b.rows.map(function(r){return r[m].reactions_given;})};
  });
  setChart('cgReact',{
    grid:baseGrid(), legend:legend(members),
    tooltip:Object.assign(tooltipBase(),{axisPointer:{type:'shadow'}}),
    xAxis:{type:'category',data:cats,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
    yAxis:valAxis({}), series:series
  });
}

function renderGroupHeat(rt){
  var maxV=0; for(var i=0;i<168;i++) maxV=Math.max(maxV,rt.combined[i]);
  if(maxV<=0){ noData('cgHeat'); return; }
  ensureCanvas('cgHeat');
  heatmap('cgHeat',rt.combined,maxV);
}

function renderGroupLanguage(colors){
  var host=el('nlpCards'); if(!host) return;
  var ex=state.chat.extras||{}, nm=ex.nlp_monthly||{};
  var months=monthsInRange();
  var top3=(state.chat.participants||[]).slice(0,3);
  if(!months.length){
    host.innerHTML='<div class="card"><div class="placeholder" style="height:100px">No language data in range</div></div>';
    return;
  }
  function merged(user){
    var w={},e={},total=0;
    months.forEach(function(mo){
      var d=(nm[mo]||{})[user]; if(!d) return;
      (d.words||[]).forEach(function(it){w[it[0]]=(w[it[0]]||0)+it[1];});
      (d.emojis||[]).forEach(function(it){e[it[0]]=(e[it[0]]||0)+it[1];});
      total+=d.total||0;
    });
    return {w:w,e:e,total:total};
  }
  function top(counts,n){return Object.keys(counts).map(function(k){return [k,counts[k]];})
    .sort(function(x,y){return y[1]-x[1];}).slice(0,n);}
  function tags(list){ if(!list||!list.length) return '<span class="faint">—</span>';
    return list.map(function(it){return '<span class="tag">'+esc(it[0])+'<span class="n">'+fmtNum(it[1])+'</span></span>';}).join(''); }
  function emojiRow(list){ if(!list||!list.length) return '<span class="faint">no emojis</span>';
    return list.map(function(it){return esc(it[0])+'<span class="n">'+fmtNum(it[1])+'</span>';}).join(''); }
  var rangeLbl=months.length===1?months[0]:months[0]+' → '+months[months.length-1];
  var html='';
  top3.forEach(function(u,i){
    var M=merged(u);
    var dot='<span style="display:inline-block;width:9px;height:9px;border-radius:2px;'
      +'vertical-align:middle;margin-right:4px;background:'+colors[i]+'"></span>';
    var inner='<div class="nlp-label">Top emojis</div><div class="emoji-row">'+emojiRow(top(M.e,15))+'</div>'
      +'<div class="nlp-label">Most used words</div><div>'+tags(top(M.w,18))+'</div>'
      +'<div class="vocab-line">In range: <b>'+fmtNum(M.total)+'</b> content words</div>';
    html+='<div class="card"><h3>'+dot+esc(u)+'</h3><div class="sub">'+esc(rangeLbl)+' · monthly resolution</div>'+inner+'</div>';
  });
  host.innerHTML=html;
}

function renderGroupShifts(rt,members){
  var host=el('shiftList'); if(!host) return;
  var tot=rt.tot;
  var days=dayDiff(state.start,state.end)+1;
  var prevEnd=addDays(state.start,-1), prevStart=addDays(state.start,-days);
  var prt=groupRangeTotals(members,prevStart,prevEnd).tot;
  var head='<div class="diff-head">'+esc(ymd(state.start))+' → '+esc(ymd(state.end))
    +' &nbsp;vs&nbsp; '+esc(ymd(prevStart))+' → '+esc(ymd(prevEnd))+' ('+days+'d each)</div>';
  var anyPrev=false; members.forEach(function(m){if(prt[m].msgs)anyPrev=true;});
  if(!anyPrev){ host.innerHTML=head+'<div class="placeholder" style="height:70px">No data in the previous window — nothing to compare against</div>'; return; }
  var defs=[['Messages',function(c){return c.msgs;}],
            ['Words',function(c){return c.words;}],
            ['Reactions',function(c){return c.reactions_given;}]];
  var rows=[];
  members.forEach(function(m){
    defs.forEach(function(def){
      var cv=def[1](tot[m]), pv=def[1](prt[m]);
      if(cv===0&&pv===0) return;
      var d,mag;
      if(pv===0){ d=1; mag='new'; }
      else { d=(cv-pv)/pv; if(Math.abs(d)<0.005) return; mag=fmtPct(Math.abs(d),Math.abs(d)<0.1?1:0); }
      var up=d>=0;
      rows.push({up:up,label:def[0]+' · '+m,prev:fmtNum(pv),cur:fmtNum(cv),mag:(up?'+':'−')+mag});
    });
  });
  if(!rows.length){ host.innerHTML=head+'<div class="placeholder" style="height:70px">No metric changed between the two windows</div>'; return; }
  rows.sort(function(x,y){return (y.up?1:0)-(x.up?1:0);});
  var h=head;
  rows.forEach(function(row){
    h+='<div class="drow '+(row.up?'up':'down')+'">'
      +'<span class="sign">'+(row.up?'+':'−')+'</span>'
      +'<span class="m">'+esc(row.label)+'</span>'
      +'<span class="vals">'+esc(row.prev)+' → '+esc(row.cur)+'</span>'
      +'<span class="d">'+esc(row.mag)+'</span></div>';
  });
  host.innerHTML=h;
}

/* Dispatch between the 1v1 and group render pipelines. */
function rerender(){
  if(state.isConnected) renderAllConnected();
  else if(state.isGroup) renderAllGroup();
  else renderAll();
}

/* ============================================================ *
 * CONNECTED (owner) mode — "👤 You — Connected"
 * Renders window.CONNECTED_V[variant] (built by build_connected.py): the owner's
 * cross-chat profile. Range-scoped charts derive from the flat per-day
 * owner table; leaderboards/funnel/code-switching are all-time.
 * ============================================================ */
var CONN_TYPE_COLORS={ping:'#6b7076',exchange:'#4DB6AC',hangout:'#E4A11B',deep_talk:'#B5179E'};
var CONN_TYPES=['ping','exchange','hangout','deep_talk'];
var CONN_TYPE_LBL={ping:'Ping',exchange:'Exchange',hangout:'Hangout',deep_talk:'Deep talk'};

function connBlank(){return {msgs:0,received:0,words:0,chars:0,emoji:0,questions:0,
  night_msgs:0,media:0,i_words:0,we_words:0,you_words:0,pos_words:0,neg_words:0,
  sessions:0,texting_minutes:0,bursts:0};}
function connEntries(){ // sorted [dateStr, cell]
  var d=state.connected.daily,ks=Object.keys(d).sort(),o=[];
  for(var i=0;i<ks.length;i++)o.push([ks[i],d[ks[i]]]);
  return o;
}
function connRangeTotals(sD,eD){
  var t=connBlank(),ents=connEntries(),daysActive=0;
  for(var i=0;i<ents.length;i++){
    var ts=parseYMD(ents[i][0]).getTime();
    if(ts<sD.getTime()||ts>eD.getTime()) continue;
    addInto(t,ents[i][1]);
    if(ents[i][1].msgs) daysActive++;
  }
  return {tot:t,daysActive:daysActive};
}
function connBuckets(){
  var gran=effGran(),map={},ents=connEntries();
  for(var i=0;i<ents.length;i++){
    var ds=ents[i][0]; if(!inRange(ds)) continue;
    var bs=bucketStart(ds,gran);
    if(!map[bs]) map[bs]=connBlank();
    addInto(map[bs],ents[i][1]);
  }
  var starts=Object.keys(map).sort();
  return {starts:starts,ts:starts.map(function(s){return parseYMD(s).getTime();}),
    rows:starts.map(function(s){return map[s];}),gran:gran};
}
function connMonthKeys(series){ // series keys 'YYYY-MM' clipped to active range
  var sm=ymd(state.start).slice(0,7), em=ymd(state.end).slice(0,7);
  return Object.keys(series||{}).filter(function(m){return m>=sm&&m<=em;}).sort();
}
function isoWeekStartDate(label){ // 'YYYY-Www' -> Date of that ISO week's Monday
  var y=+label.slice(0,4), w=+label.slice(6);
  var jan4=new Date(Date.UTC(y,0,4));
  var wd=(jan4.getUTCDay()+6)%7;
  return addDays(jan4,-wd+(w-1)*7);
}
function connWeekKeys(series){ // weekly keys whose week overlaps the active range
  return Object.keys(series||{}).filter(function(k){
    var t=isoWeekStartDate(k).getTime();
    return t>=state.start.getTime()-6*86400000 && t<=state.end.getTime();
  }).sort();
}

function renderSkeletonConnected(){
  var owner=state.connected.owner||'You';
  el('app').innerHTML =
  '<div class="section" style="padding-bottom:0"><div id="connVariantNote" class="sub" style="font-size:13px"></div></div>'
  + section('Pulse — '+owner+' across every chat','<div class="grid kpis" id="kpiRow"></div>')
  + section('Attention & texting span',
      '<div class="grid cols-2">'
      + card('Time spent texting','Sum of conversation-session minutes you took part in, any chat (per bucket)','<div class="chart" id="cxTexting"></div>')
      + card('Engagement bursts','Runs of your messages across ALL chats with gaps under 15 min (bursts started per bucket)','<div class="chart" id="cxBursts"></div>')
      + card('Burst length trend','Median burst duration per month, minutes (all-time series, clipped to range)','<div class="chart" id="cxBurstDur"></div>')
      + card('Focus vs juggling','Your active 10-min windows: one chat vs several at once · plus chat-switch rate (all-time)','<div class="chart" id="cxFocus"></div>')
      + '</div>')
  + section('Session portfolio',
      '<div class="grid cols-2">'
      + card('Conversation type mix','ping / exchange / hangout / deep talk per month (all chats, clipped to range)','<div class="chart" id="cxTypeMix"></div>')
      + card('Deep talks per week','Long sessions with long turns + questions or self-disclosure (clipped to range)','<div class="chart" id="cxDeep"></div>')
      + '</div>')
  + section('Contact leaderboards · all-time',
      '<div class="grid cols-2">'
      + card('Where your messages go','Share of everything you ever sent · top 12 + others (all-time)','<div class="chart tall" id="cxSentL"></div>')
      + card('Attention hierarchy','Your median reply latency per contact, fastest first · only contacts with ≥50 replies (all-time)','<div class="chart tall" id="cxLatL"></div>')
      + card('Initiation asymmetry','Share of conversations YOU started with each contact (all-time, volume-gated)','<div class="chart tall" id="cxInitL"></div>')
      + card('Night ownership','Who receives your 00:00–06:00 messages (all-time)','<div class="chart tall" id="cxNightL"></div>')
      + card('Openness','Your words per turn with each contact — where you talk in paragraphs vs monosyllables (all-time, volume-gated)','<div class="chart tall" id="cxOpenL"></div>')
      + card('Style mirroring & code-switching','How much your texting style shape-shifts between contacts (all-time)','<div id="connMirrorBox" style="min-height:200px"></div>')
      + '</div>')
  + section('Social portfolio dynamics',
      '<div class="grid cols-2">'
      + card('Attention concentration (Gini)','0 = attention spread evenly · 1 = one contact gets everything (monthly, clipped to range)','<div class="chart" id="cxGini"></div>')
      + card('Active · churned · reactivated contacts','Monthly counts (churn = silent for the next two months; clipped to range)','<div class="chart" id="cxDyn"></div>')
      + card('Reciprocity','Messages you send vs receive — biggest surpluses (you over-invest) and deficits (all-time)','<div id="connRecipBox" style="min-height:180px"></div>')
      + '</div>')
  + section('New-contact funnel · all-time',
      '<div class="grid cols-2">'
      + card('Met → talked again → recurring','Only accepted, still-existing chats are visible — rejected or deleted requests are not (survivorship bias)','<div class="chart" id="cxFunnel"></div>')
      + card('New contacts per month','A chat’s first-ever message · split by who texted first (clipped to range)','<div class="chart" id="cxNewC"></div>')
      + '</div>')
  + findingsSection()
  + section('Groups lane',
      card('Group chats','Kept separate so groups never pollute the contact rankings (all-time)','<div id="connGroupsBox" style="min-height:80px"></div>'));
}

/* Prepend the platform badge to a leaderboard/contact row name in the merged
   ('all') variant, matching the chat-picker badges (📸 / ✈️). */
function connLabel(r){
  return (state.connectedVariant==='all'&&r&&r.platform)
    ? pfBadge(r.platform)+' '+r.name : (r?r.name:'');
}
function renderConnVariantNote(){
  var box=el('connVariantNote'); if(!box) return;
  var v=state.connectedVariant, plats=(state.connected.platforms||[]);
  var lbl=CONN_VARIANT_LBL[v]||v;
  var badges=plats.map(function(p){return pfBadge(p);}).join(' ');
  var h='<b>Showing: '+esc(lbl)+'</b> '+badges;
  if(v==='all'){
    h+=' · Cross-platform attention: bursts, parallel-texting and chat-switches '
      +'span both platforms (switching an Instagram chat → a Telegram chat counts as a switch). '
      +'<span class="faint">Contacts are not merged across platforms — someone you talk to on both appears twice, once per platform (badge shown).</span>';
  } else {
    h+=' · single-platform owner profile.';
  }
  box.innerHTML=h;
}
function renderAllConnected(){
  if(!state.connected) return;
  var b=connBuckets();
  var rt=connRangeTotals(state.start,state.end);
  var has=b.starts.length>0;
  safe(renderConnVariantNote,'cvnote');
  safe(function(){renderConnKPIs(rt,has);},'ckpi');
  safe(function(){renderConnTexting(b);},'ctexting');
  safe(function(){renderConnBursts(b);},'cbursts');
  safe(renderConnBurstDur,'cburstdur');
  safe(renderConnFocus,'cfocus');
  safe(renderConnTypeMix,'ctypemix');
  safe(renderConnDeep,'cdeep');
  safe(renderConnLeaderboards,'clead');
  safe(renderConnGini,'cgini');
  safe(renderConnDyn,'cdyn');
  safe(renderConnRecip,'crecip');
  safe(renderConnFunnel,'cfunnel');
  safe(renderConnNewContacts,'cnewc');
  safe(renderConnGroups,'cgroups');
}

function renderConnKPIs(rt,has){
  var c=state.connected, tot=rt.tot;
  var days=dayDiff(state.start,state.end)+1;
  var prevEnd=addDays(state.start,-1), prevStart=addDays(state.start,-days);
  var prev=connRangeTotals(prevStart,prevEnd).tot;
  var hasPrev=prev.msgs>0;
  function D(v,opts){ if(!hasPrev||v==null||!isFinite(v)) return null;
    var o=opts||{}; return {v:v,invert:!!o.invert,pp:!!o.pp}; }

  // deep talks in range (weekly series, weeks overlapping range)
  var deepW=c.weekly&&c.weekly.deep_talk||{};
  var deepN=0; connWeekKeys(deepW).forEach(function(k){deepN+=deepW[k];});
  var burstsPerDay=rt.daysActive?tot.bursts/rt.daysActive:null;
  // contacts active in range (all-time first/last day overlap)
  var sr=ymd(state.start), er=ymd(state.end);
  var activeContacts=(c.contacts||[]).filter(function(x){
    return x.first_day&&x.last_day&&x.first_day<=er&&x.last_day>=sr;}).length;
  var att=c.attention||{}, ab=att.bursts||{}, ad=(ab.duration_min||{});

  var tiles=[
    kpi('Time texting',fmtDur(tot.texting_minutes),
      D(relDelta(tot.texting_minutes,prev.texting_minutes)),
      '<span class="split faint">'+fmtNum(tot.sessions)+' sessions · vs prev '+days+'d</span>'),
    kpi('Messages sent',fmtNum(tot.msgs),
      D(relDelta(tot.msgs,prev.msgs)),
      '<span class="split faint">received '+fmtNum(tot.received)+'</span>'),
    kpi('Deep talks',fmtNum(deepN),null,
      '<span class="split faint">'+fmtNum(deepN/Math.max(1,days/7))+' / week in range</span>'),
    kpi('Bursts / active day',burstsPerDay==null?'—':fmtNum(burstsPerDay),
      D(relDelta(tot.bursts,prev.bursts)),
      '<span class="split faint">'+fmtNum(tot.bursts)+' bursts in range</span>'),
    kpi('Median texting span',fmtDur(ad.median),null,
      '<span class="split faint">p90 '+fmtDur(ad.p90)+' · all-time</span>'),
    kpi('Parallel texting',fmtPct(att.parallel_texting_rate,1),null,
      '<span class="split faint">windows with ≥2 chats · all-time</span>'),
    kpi('Active contacts',fmtNum(activeContacts),null,
      '<span class="split faint">span overlaps range · '+fmtNum((c.totals||{}).contacts)+' all-time</span>'),
    kpi('Night messages',fmtNum(tot.night_msgs),
      D(relDelta(tot.night_msgs,prev.night_msgs)),
      '<span class="split faint">00:00–06:00</span>')
  ];
  el('kpiRow').innerHTML=has?tiles.join(''):'<div class="kpi"><div class="placeholder">No data in range</div></div>';
}

function renderConnTexting(b){
  if(!b.starts.length){ noData('cxTexting'); return; }
  ensureCanvas('cxTexting');
  setChart('cxTexting',{grid:baseGrid(),tooltip:Object.assign(tooltipBase(),{
    formatter:function(ps){var d=new Date(ps[0].value[0]);
      var s=esc(fmtDate(d))+'<br>';
      ps.forEach(function(p){s+=markDot(p.color)+esc(p.seriesName)+': <b>'+fmtDur(p.value[1])+'</b><br>';});
      return s;}}),
    xAxis:timeAxis(),yAxis:valAxis({axisLabel:{color:MUTED,formatter:function(v){return fmtNum(v)+'m';}}}),
    series:[{name:'Texting minutes',type:'line',showSymbol:false,
      data:b.starts.map(function(s,i){return [b.ts[i],Math.round(b.rows[i].texting_minutes)];}),
      lineStyle:{width:1.5,color:COLORS.a},itemStyle:{color:COLORS.a},
      areaStyle:{color:COLORS.a,opacity:.22}}]});
}
function renderConnBursts(b){
  if(!b.starts.length){ noData('cxBursts'); return; }
  ensureCanvas('cxBursts');
  setChart('cxBursts',{grid:baseGrid(),tooltip:tooltipBase(),
    xAxis:timeAxis(),yAxis:valAxis({}),
    series:[{name:'Bursts',type:'bar',barMaxWidth:14,
      data:b.starts.map(function(s,i){return [b.ts[i],b.rows[i].bursts];}),
      itemStyle:{color:COLORS.a}}]});
}
function renderConnBurstDur(){
  var mb=(state.connected.monthly||{}).bursts||{};
  var ms=connMonthKeys(mb);
  if(!ms.length){ noData('cxBurstDur'); return; }
  ensureCanvas('cxBurstDur');
  setChart('cxBurstDur',{grid:baseGrid(),tooltip:Object.assign(tooltipBase(),{
    formatter:function(ps){var d=new Date(ps[0].value[0]);
      var s=esc(String(d.getUTCFullYear())+'-'+pad(d.getUTCMonth()+1))+'<br>';
      ps.forEach(function(p){s+=markDot(p.color)+esc(p.seriesName)+': <b>'
        +(p.seriesName==='Bursts'?fmtNum(p.value[1]):fmtDur(p.value[1]))+'</b><br>';});
      return s;}}),
    legend:legend(['Median duration','Bursts']),
    xAxis:timeAxis(),
    yAxis:[valAxis({axisLabel:{color:MUTED,formatter:function(v){return fmtNum(v)+'m';}}}),
           valAxis({splitLine:{show:false}})],
    series:[
      {name:'Median duration',type:'line',showSymbol:false,yAxisIndex:0,
        data:ms.map(function(m){return [parseYMD(m+'-01').getTime(),mb[m].median_min];}),
        lineStyle:{width:2,color:COLORS.a},itemStyle:{color:COLORS.a}},
      {name:'Bursts',type:'bar',yAxisIndex:1,barMaxWidth:12,
        data:ms.map(function(m){return [parseYMD(m+'-01').getTime(),mb[m].count];}),
        itemStyle:{color:'rgba(158,158,158,.45)'}}]});
}
function renderConnFocus(){
  var att=state.connected.attention||{};
  var focus=att.focus_index, frag=att.fragmentation_index;
  if(focus==null){ noData('cxFocus'); return; }
  ensureCanvas('cxFocus');
  var sw=att.chat_switch||{};
  setChart('cxFocus',{grid:{left:100,right:60,top:26,bottom:30},
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){return esc(p.name)+': <b>'+fmtPct(p.value,1)+'</b>';}},
    xAxis:valAxis({max:1,axisLabel:{color:MUTED,formatter:function(v){return fmtPct(v);}}}),
    yAxis:{type:'category',data:['Juggling ≥2 chats','Single-chat focus'],
      axisLabel:{color:MUTED},axisLine:{lineStyle:{color:GRID}}},
    series:[{type:'bar',barMaxWidth:26,data:[
      {value:frag,itemStyle:{color:'#E4A11B'}},
      {value:focus,itemStyle:{color:COLORS.a}}],
      label:{show:true,position:'right',color:MUTED,
        formatter:function(p){return fmtPct(p.value,1);}}}],
    graphic:[{type:'text',left:'center',top:2,style:{
      text:'chat switches: '+fmtNum(sw.switches_per_active_hour)+' / active hour · '
        +fmtPct(sw.switch_fraction,1)+' of quick follow-ups change chat',
      fill:MUTED,fontSize:11}}]});
}
function renderConnTypeMix(){
  var tm=(state.connected.monthly||{}).type_mix||{};
  var ms=connMonthKeys(tm);
  if(!ms.length){ noData('cxTypeMix'); return; }
  ensureCanvas('cxTypeMix');
  var series=CONN_TYPES.map(function(t){
    return {name:CONN_TYPE_LBL[t],type:'bar',stack:'mix',barMaxWidth:22,
      data:ms.map(function(m){return [parseYMD(m+'-01').getTime(),(tm[m]||{})[t]||0];}),
      itemStyle:{color:CONN_TYPE_COLORS[t]}};
  });
  setChart('cxTypeMix',{grid:baseGrid(),legend:legend(CONN_TYPES.map(function(t){return CONN_TYPE_LBL[t];})),
    tooltip:tooltipBase(),xAxis:timeAxis(),yAxis:valAxis({}),series:series});
}
function renderConnDeep(){
  var dw=(state.connected.weekly||{}).deep_talk||{};
  var ks=connWeekKeys(dw);
  if(!ks.length){ noData('cxDeep'); return; }
  ensureCanvas('cxDeep');
  setChart('cxDeep',{grid:baseGrid(),tooltip:tooltipBase(),
    xAxis:timeAxis(),yAxis:valAxis({minInterval:1}),
    series:[{name:'Deep talks',type:'bar',barMaxWidth:10,
      data:ks.map(function(k){return [isoWeekStartDate(k).getTime(),dw[k]];}),
      itemStyle:{color:CONN_TYPE_COLORS.deep_talk}}]});
}

/* horizontal leaderboard bars: rows = [{name,v,tip}] descending */
function connHBar(id,rows,fmt){
  if(!rows||!rows.length){ noData(id); return; }
  ensureCanvas(id);
  var arr=rows.slice(0,12).reverse();  // ascending -> biggest on top
  setChart(id,{grid:{left:150,right:64,top:8,bottom:24},
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){var r=arr[p.dataIndex];
        return esc(r.name)+': <b>'+fmt(r.v)+'</b>'+(r.tip?'<br>'+esc(r.tip):'');}},
    xAxis:valAxis({}),
    yAxis:{type:'category',data:arr.map(function(r){return r.name;}),
      axisLabel:{color:MUTED,width:135,overflow:'truncate'},axisLine:{lineStyle:{color:GRID}}},
    series:[{type:'bar',barMaxWidth:16,
      data:arr.map(function(r){return {value:r.v,itemStyle:{color:r.c||COLORS.a}};}),
      label:{show:true,position:'right',color:MUTED,
        formatter:function(p){return fmt(p.value);}}}]});
}
function renderConnLeaderboards(){
  var c=state.connected, lb=c.leaderboards||{};
  // Where your messages go — top 12 + Others (share of all sent).
  var bs=(lb.by_sent_share||[]).slice(0,12);
  var covered=0; bs.forEach(function(r){covered+=r.sent;});
  var totSent=(c.totals||{}).messages_sent||0;
  var rows=bs.map(function(r){return {name:connLabel(r),v:r.share,tip:fmtNum(r.sent)+' messages'};});
  if(totSent>covered) rows.push({name:'Others',v:(totSent-covered)/totSent,
    tip:fmtNum(totSent-covered)+' messages',c:OTHERS_COLOR});
  rows.sort(function(a,b){return b.v-a.v;});
  connHBar('cxSentL',rows,function(v){return fmtPct(v,1);});
  // Attention hierarchy — fastest first (ascending latency).
  var ah=(lb.attention_hierarchy||[]).slice(0,12).map(function(r){
    return {name:connLabel(r),v:r.reply_latency_median_min,tip:fmtNum(r.reply_n)+' replies (≥50 gate)'};});
  ah.reverse(); // connHBar re-reverses: fastest ends up on top
  connHBar('cxLatL',ah,function(v){return fmtDur(v);});
  // Initiation asymmetry.
  connHBar('cxInitL',(lb.initiation||[]).slice(0,12).map(function(r){
    return {name:connLabel(r),v:r.initiation_share,tip:fmtNum(r.sessions)+' sessions'};}),
    function(v){return fmtPct(v);});
  // Night ownership.
  connHBar('cxNightL',(lb.night||[]).slice(0,12).map(function(r){
    return {name:connLabel(r),v:r.night_share,tip:fmtNum(r.night_msgs)+' night messages'};}),
    function(v){return fmtPct(v,1);});
  // Openness (words per turn).
  connHBar('cxOpenL',(lb.openness||[]).slice(0,12).map(function(r){
    return {name:connLabel(r),v:r.words_per_turn,
      tip:'questions '+fmtPct(r.question_rate,1)+' · I-words '+fmtPct(r.i_word_rate,1)
        +' · positivity '+fmtPct(r.pos_rate,1)};}),
    function(v){return fmtNum(v);});
  // Style mirroring box.
  var cs=c.code_switching||{}, pc=(cs.per_contact||[]).slice();
  pc.sort(function(a,b){return (b.mirror_score||0)-(a.mirror_score||0);});
  var h='<div class="nlp-label">You mirror most</div>';
  pc.slice(0,6).forEach(function(r){
    h+='<span class="tag hot">'+esc(connLabel(r))+'<span class="n">'+fmtPct(r.mirror_score,0)+'</span></span>';});
  h+='<div class="nlp-label">Style variance across contacts</div>'
    +'<div class="vocab-line">emoji rate '+fmtNum(cs.emoji_rate_variance)
    +' · word length '+fmtNum(cs.avg_word_len_variance)
    +' · language mix '+fmtNum(cs.lang_variance)+'</div>'
    +'<div class="vocab-line faint">Higher variance = you change voice more between people (code-switching).</div>';
  var box=el('connMirrorBox'); if(box) box.innerHTML=h;
}

function renderConnGini(){
  var g=(state.connected.monthly||{}).gini||{};
  var ms=connMonthKeys(g);
  if(!ms.length){ noData('cxGini'); return; }
  ensureCanvas('cxGini');
  setChart('cxGini',{grid:baseGrid(),tooltip:tooltipBase(),
    xAxis:timeAxis(),yAxis:valAxis({min:0,max:1}),
    series:[{name:'Gini',type:'line',showSymbol:false,
      data:ms.map(function(m){return [parseYMD(m+'-01').getTime(),g[m]];}),
      lineStyle:{width:2,color:COLORS.a},itemStyle:{color:COLORS.a},
      areaStyle:{color:COLORS.a,opacity:.15}}]});
}
function renderConnDyn(){
  var mo=state.connected.monthly||{};
  var ac=mo.active_contacts||{}, ch=mo.churned||{}, re=mo.reactivated||{};
  var ms=connMonthKeys(ac);
  if(!ms.length){ noData('cxDyn'); return; }
  ensureCanvas('cxDyn');
  function ser(name,src,color){
    return {name:name,type:'line',showSymbol:false,
      data:ms.map(function(m){return [parseYMD(m+'-01').getTime(),src[m]||0];}),
      lineStyle:{width:1.5,color:color},itemStyle:{color:color}};
  }
  setChart('cxDyn',{grid:baseGrid(),legend:legend(['Active','Churned','Reactivated']),
    tooltip:tooltipBase(),xAxis:timeAxis(),yAxis:valAxis({minInterval:1}),
    series:[ser('Active',ac,COLORS.a),ser('Churned',ch,'#E02F44'),
            ser('Reactivated',re,'#73BF69')]});
}
function renderConnRecip(){
  var c=state.connected, r=c.reciprocity||{}, lb=c.leaderboards||{};
  var h='<div class="vocab-line">Overall: you sent <b>'+fmtNum(r.sent_total)
    +'</b> · received <b>'+fmtNum(r.received_total)+'</b> · ratio <b>'
    +(r.ratio==null?'—':fmtNum(r.ratio))+'</b></div>';
  function rows(list,label){
    var s='<div class="nlp-label">'+esc(label)+'</div>';
    (list||[]).slice(0,5).forEach(function(x){
      s+='<div class="vocab-line">'+esc(connLabel(x))+' — ratio '+fmtNum(x.reciprocity)
        +' <span class="faint">(sent '+fmtNum(x.sent)+' / recv '+fmtNum(x.received)+')</span></div>';});
    return s;
  }
  h+=rows(lb.reciprocity_surplus,'You over-invest (send ≫ receive)');
  h+=rows(lb.reciprocity_deficit,'You under-invest (receive ≫ send)');
  var box=el('connRecipBox'); if(box) box.innerHTML=h;
}

function renderConnFunnel(){
  var f=state.connected.funnel||{}, st=f.stages||{}, rt=f.retention||{};
  if(!st.met){ noData('cxFunnel'); return; }
  ensureCanvas('cxFunnel');
  var cats=['Met','Talked again','Recurring (3+ sessions)','Still active 30d+','Still active 90d+'];
  var vals=[st.met,st.talked_again,st.recurring,rt.active_30d,rt.active_90d];
  setChart('cxFunnel',{grid:{left:170,right:60,top:8,bottom:24},
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){return esc(p.name)+': <b>'+fmtNum(p.value)+'</b>'
        +(st.met?' ('+fmtPct(p.value/st.met,0)+' of met)':'');}},
    xAxis:valAxis({}),
    yAxis:{type:'category',data:cats.slice().reverse(),
      axisLabel:{color:MUTED,width:160,overflow:'truncate'},axisLine:{lineStyle:{color:GRID}}},
    series:[{type:'bar',barMaxWidth:20,
      data:vals.slice().reverse().map(function(v,i){
        return {value:v,itemStyle:{color:COLORS.a,opacity:.45+.55*(v/(st.met||1))}};}),
      label:{show:true,position:'right',color:MUTED,
        formatter:function(p){return fmtNum(p.value);}}}]});
}
function renderConnNewContacts(){
  var np=(state.connected.funnel||{}).new_per_month||{};
  var ms=connMonthKeys(np);
  if(!ms.length){ noData('cxNewC'); return; }
  ensureCanvas('cxNewC');
  setChart('cxNewC',{grid:baseGrid(),legend:legend(['You texted first','They texted first']),
    tooltip:tooltipBase(),xAxis:timeAxis(),yAxis:valAxis({minInterval:1}),
    series:[
      {name:'You texted first',type:'bar',stack:'n',barMaxWidth:18,
        data:ms.map(function(m){return [parseYMD(m+'-01').getTime(),np[m].owner_first||0];}),
        itemStyle:{color:COLORS.a}},
      {name:'They texted first',type:'bar',stack:'n',barMaxWidth:18,
        data:ms.map(function(m){return [parseYMD(m+'-01').getTime(),np[m].contact_first||0];}),
        itemStyle:{color:'#9E9E9E'}}]});
}
function renderConnGroups(){
  var g=state.connected.groups||{}, box=el('connGroupsBox');
  if(!box) return;
  if(!g.count){ box.innerHTML='<div class="placeholder" style="height:60px">No group chats</div>'; return; }
  var h='<div class="vocab-line">'+fmtNum(g.count)+' groups · you sent <b>'+fmtNum(g.messages_owner)
    +'</b> of '+fmtNum(g.messages_total)+' messages · '+fmtDur(g.texting_minutes)+' of group texting</div>'
    +'<table class="lt-table"><tr><th>Group</th><th>Members</th><th>Your msgs</th><th>Total</th><th>Time</th></tr>';
  (g.per_group||[]).slice(0,10).forEach(function(x){
    h+='<tr><td>'+esc(connLabel(x))+'</td><td class="num">'+fmtNum(x.members)
      +'</td><td class="num">'+fmtNum(x.messages_owner)+'</td><td class="num">'+fmtNum(x.messages_total)
      +'</td><td class="num">'+fmtDur(x.texting_minutes)+'</td></tr>';});
  h+='</table>';
  box.innerHTML=h;
}

/* ============================================================ *
 * CONTROLS
 * ============================================================ */
function buildPresets(){
  var chips=[{k:'all',lbl:'All time'},{k:'30',lbl:'Last 30d'},{k:'90',lbl:'Last 90d'},
    {k:'180',lbl:'Last 6mo'},{k:'365',lbl:'Last 1y'}];
  var years=calendarYears();
  years.forEach(function(y){chips.push({k:'y'+y,lbl:String(y)});});
  chips.push({k:'reset',lbl:'⟲ Reset',reset:true});
  var host=el('presetChips'); host.innerHTML='';
  chips.forEach(function(c){
    var d=document.createElement('div');
    d.className='chip'+(c.reset?' reset':'')+(state.preset===c.k?' active':'');
    d.textContent=c.lbl; d.setAttribute('data-k',c.k);
    d.onclick=function(){applyPreset(c.k);};
    host.appendChild(d);
  });
}
function calendarYears(){
  if(!state.fullStart) return [];
  var ys=[]; for(var y=state.fullStart.getUTCFullYear();y<=state.fullEnd.getUTCFullYear();y++) ys.push(y);
  return ys;
}

/* ---- fast month picker ---- */
var MONTH_NAMES=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function monthBounds(ym){ // 'YYYY-MM' -> [Date first, Date last] clamped to data
  var y=+ym.slice(0,4), m=+ym.slice(5,7)-1;
  var first=new Date(Date.UTC(y,m,1));
  var last=new Date(Date.UTC(y,m+1,0));
  return [maxD(first,state.fullStart), minD(last,state.fullEnd)];
}
function buildMonthPicker(){
  var sel=el('monthSel'); if(!sel) return;
  while(sel.options.length>1) sel.remove(1);
  if(!state.fullStart) return;
  var cur=new Date(Date.UTC(state.fullStart.getUTCFullYear(),state.fullStart.getUTCMonth(),1));
  var end=new Date(Date.UTC(state.fullEnd.getUTCFullYear(),state.fullEnd.getUTCMonth(),1));
  var opts=[];
  while(cur.getTime()<=end.getTime()){
    opts.push(cur.getUTCFullYear()+'-'+pad(cur.getUTCMonth()+1));
    cur=new Date(Date.UTC(cur.getUTCFullYear(),cur.getUTCMonth()+1,1));
  }
  opts.reverse(); // newest first — fastest to reach
  opts.forEach(function(ym){
    var o=document.createElement('option');
    o.value=ym;
    o.textContent=MONTH_NAMES[+ym.slice(5,7)-1]+' '+ym.slice(0,4);
    sel.appendChild(o);
  });
  sel.value='';
}
function applyMonth(ym){
  if(!ym) return;
  var bnd=monthBounds(ym);
  state.start=bnd[0]; state.end=bnd[1]; state.preset=null;
  syncControls(); rerender();
}
function activeMonth(){ // 'YYYY-MM' when the active range is exactly one (clamped) month
  var s=ymd(state.start), e=ymd(state.end);
  if(s.slice(0,7)!==e.slice(0,7)) return '';
  var bnd=monthBounds(s.slice(0,7));
  return (ymd(bnd[0])===s && ymd(bnd[1])===e) ? s.slice(0,7) : '';
}
function applyPreset(k){
  state.preset=k;
  if(k==='all'||k==='reset'){ state.start=new Date(state.fullStart.getTime()); state.end=new Date(state.fullEnd.getTime()); if(k==='reset') state.preset='all'; }
  else if(k[0]==='y'){ var y=+k.slice(1);
    state.start=maxD(new Date(Date.UTC(y,0,1)),state.fullStart);
    state.end=minD(new Date(Date.UTC(y,11,31)),state.fullEnd); }
  else { var n=+k; state.end=new Date(state.fullEnd.getTime());
    state.start=maxD(addDays(state.fullEnd,-(n-1)),state.fullStart); }
  syncControls(); rerender();
}
function maxD(a,b){return a.getTime()>b.getTime()?a:b;}
function minD(a,b){return a.getTime()<b.getTime()?a:b;}
function syncControls(){
  el('dFrom').value=ymd(state.start); el('dTo').value=ymd(state.end);
  var msel=el('monthSel'); if(msel) msel.value=activeMonth();
  var chips=el('presetChips').children;
  for(var i=0;i<chips.length;i++){
    var k=chips[i].getAttribute('data-k');
    chips[i].className='chip'+(k==='reset'?' reset':'')+(state.preset===k?' active':'');
  }
}
function applyCustomRange(){
  var f=el('dFrom').value, t=el('dTo').value;
  if(!f||!t) return;
  var fs=parseYMD(f), ts=parseYMD(t);
  if(fs.getTime()>ts.getTime()){ var tmp=fs; fs=ts; ts=tmp; }
  // clamp INTO the data extent so an out-of-data range can never invert
  state.start=minD(maxD(fs,state.fullStart),state.fullEnd);
  state.end=maxD(minD(ts,state.fullEnd),state.fullStart);
  state.preset=null; syncControls(); rerender();
}

/* ---------- platform filter ---------- */
/* selectedPlatforms: null/empty Set => ALL. Otherwise only listed platforms. */
var selectedPlatforms = null;
function pfOf(m){ return m.platform||'instagram'; }
function pfBadge(p){ return p==='telegram'?'✈️':'📸'; }
function pfLabel(p){ return p==='telegram'?'✈️ Telegram':(p==='instagram'?'📸 Instagram':p); }
function platformVisible(m){
  return !(selectedPlatforms&&selectedPlatforms.size)||selectedPlatforms.has(pfOf(m));
}
function visibleManifest(){ return MANIFEST.filter(platformVisible); }
function buildPlatformFilter(){
  var present={}; MANIFEST.forEach(function(m){present[pfOf(m)]=1;});
  var plats=Object.keys(present).sort();
  var ctrl=el('platformControl'), seg=el('platformSeg');
  if(!ctrl||!seg) return;
  if(plats.length<2){ ctrl.style.display='none'; return; }
  ctrl.style.display='';
  seg.innerHTML='';
  plats.forEach(function(p){
    var chip=document.createElement('span');
    var on=!(selectedPlatforms&&selectedPlatforms.size)||selectedPlatforms.has(p);
    chip.className='chip'+(on?' active':'');
    chip.textContent=pfLabel(p);
    chip.onclick=function(){ togglePlatform(p); };
    seg.appendChild(chip);
  });
}
function togglePlatform(p){
  if(!selectedPlatforms) selectedPlatforms=new Set();
  if(selectedPlatforms.has(p)) selectedPlatforms.delete(p);
  else selectedPlatforms.add(p);
  // Empty selection => back to ALL.
  if(selectedPlatforms.size===0) selectedPlatforms=null;
  buildPlatformFilter();
  buildChatDropdown(el('chatSearch')?el('chatSearch').value:'');
  // In connected mode the platform chips pick the CONNECTED variant instead of
  // filtering the chat list — reload the matching variant in place.
  if(state.isConnected){ selectConnected(); return; }
  // If the current chat is now filtered out, jump to the first visible one.
  var vis=visibleManifest();
  if(vis.length && !vis.some(function(m){return m.id===state.chatId;})){
    selectChat(vis[0].id);
  }
}

/* ---------- chat selector ---------- */
function buildChatDropdown(filter){
  var list=el('chatList'); list.innerHTML='';
  var q=(filter||'').toLowerCase();
  // Pinned owner entry — always on top, immune to platform filter and search.
  var you=document.createElement('div');
  you.className='dd-item connected'+(state.isConnected?' active':'');
  var yn=document.createElement('span'); yn.textContent='👤 You — Connected';
  var yd=document.createElement('span'); yd.className='n'; yd.textContent='all chats';
  you.appendChild(yn); you.appendChild(yd);
  you.onclick=function(){ selectConnected(); closeDD(); };
  list.appendChild(you);
  visibleManifest().forEach(function(m){
    if(q && m.name.toLowerCase().indexOf(q)<0) return;
    var item=document.createElement('div');
    item.className='dd-item'+(m.id===state.chatId?' active':'');
    var name=document.createElement('span');
    name.textContent=pfBadge(pfOf(m))+' '+m.name;
    var n=document.createElement('span'); n.className='n';
    n.textContent=(m.is_group?('👥 '+(m.members||'')+' · '):'')+fmtNum(m.messages)+' msgs';
    item.appendChild(name); item.appendChild(n);
    item.onclick=function(){ selectChat(m.id); closeDD(); };
    list.appendChild(item);
  });
  if(list.children.length<=1){ var e=document.createElement('div');
    e.className='dd-item faint'; e.textContent='No matches'; list.appendChild(e); }
}
function openDD(){ el('chatPanel').classList.add('open'); el('chatSearch').focus(); }
function closeDD(){ el('chatPanel').classList.remove('open'); }
function selectChat(id){
  var m=MANIFEST.filter(function(x){return x.id===id;})[0];
  if(!m) return;
  txt(el('chatBtnLabel'), m.name);
  state.chatId=id;
  if(DATA[id]){ onChatLoaded(id); return; }
  var s=document.createElement('script');
  s.src=m.file;
  s.onload=function(){ onChatLoaded(id); };
  s.onerror=function(){ el('app').innerHTML='<div class="placeholder" style="height:200px">Failed to load chat data.</div>'; };
  document.body.appendChild(s);
}
/* ---------- connected (owner) mode entry ---------- */
var CONNECTED_ID='__connected';
var CONN_VARIANT_LBL={all:'All platforms',instagram:'Instagram',telegram:'Telegram'};
/* Variant is driven by the existing platform filter chips while in connected
   mode: no filter / both platforms -> 'all'; only Instagram -> 'instagram';
   only Telegram -> 'telegram'. */
function connectedVariant(){
  if(!selectedPlatforms||!selectedPlatforms.size) return 'all';
  if(selectedPlatforms.size===1){
    if(selectedPlatforms.has('telegram')) return 'telegram';
    if(selectedPlatforms.has('instagram')) return 'instagram';
  }
  return 'all';
}
function selectConnected(){
  txt(el('chatBtnLabel'),'👤 You — Connected');
  state.chatId=CONNECTED_ID;
  loadConnectedVariant(connectedVariant());
}
function loadConnectedVariant(v){
  window.CONNECTED_V=window.CONNECTED_V||{};
  if(window.CONNECTED_V[v]){ onConnectedLoaded(v); return; }
  var s=document.createElement('script');
  s.src='data/connected_'+v+'.js';
  s.onload=function(){ onConnectedLoaded(v); };
  s.onerror=function(){ connectedMissing(v); };
  document.body.appendChild(s);
}
function connectedMissing(v){
  disposeCharts();
  state.isConnected=true; state.connected=null; state.chat=null;
  state.connectedVariant=v;
  var lbl=CONN_VARIANT_LBL[v]||v;
  el('app').innerHTML='<div class="card" style="margin-top:26px;text-align:center;padding:40px 20px">'
    +'<h3 style="margin-bottom:8px">👤 You — Connected · '+esc(lbl)+' is not built yet</h3>'
    +'<div class="sub" style="font-size:13px">This view merges your chats into one owner profile.<br>'
    +'Generate it once with:<br><br>'
    +'<code style="background:var(--panel-2);border:1px solid var(--border);border-radius:6px;padding:6px 12px;display:inline-block">python build_connected.py</code>'
    +'<br><br>…then rebuild or just reload this page.<br>'
    +'<span class="faint">(Switch the Platform filter to pick a different variant.)</span></div></div>';
}
function onConnectedLoaded(v){
  var c=(window.CONNECTED_V||{})[v];
  if(!c||!c.daily){ connectedMissing(v); return; }
  disposeCharts();
  state.connectedVariant=v;
  state.connected=c; state.isConnected=true;
  state.chat=null; state.isGroup=false; state.users=[c.owner||'You',null];
  var dates=Object.keys(c.daily).sort();
  if(dates.length){ state.fullStart=parseYMD(dates[0]); state.fullEnd=parseYMD(dates[dates.length-1]); }
  else { var t=new Date(); state.fullStart=t; state.fullEnd=t; }
  state.start=new Date(state.fullStart.getTime()); state.end=new Date(state.fullEnd.getTime());
  state.preset='all';
  renderSkeletonConnected();
  buildPresets(); buildMonthPicker(); syncControls();
  loadAndRenderFindings('connected:'+v);
  if(!dates.length){ el('kpiRow').innerHTML='<div class="kpi"><div class="placeholder">No data</div></div>'; return; }
  renderAllConnected();
}

function onChatLoaded(id){
  var chat=DATA[id];
  if(!chat){ return; }
  disposeCharts();
  state.isConnected=false; state.connected=null;
  state.chat=chat;
  state.isGroup=!!chat.is_group;
  state.users=(chat.participants&&chat.participants.length>=2)?
    [chat.participants[0],chat.participants[1]]:[chat.participants&&chat.participants[0]||'A','B'];
  var dates=Object.keys(chat.daily).sort();
  if(dates.length){ state.fullStart=parseYMD(dates[0]); state.fullEnd=parseYMD(dates[dates.length-1]); }
  else { var t=new Date(); state.fullStart=t; state.fullEnd=t; }
  state.start=new Date(state.fullStart.getTime()); state.end=new Date(state.fullEnd.getTime());
  state.preset='all';
  if(state.isGroup) renderSkeletonGroup(); else renderSkeleton();
  buildPresets(); buildMonthPicker(); syncControls();
  if(!dates.length){ el('app').querySelectorAll('.chart').forEach(function(n){n.innerHTML='<div class="placeholder">No data in this chat</div>';});
    el('kpiRow').innerHTML='<div class="kpi"><div class="placeholder">No data</div></div>';
    var lt0=el('ltCards'); if(lt0) lt0.innerHTML=''; return; }
  if(state.isGroup){ renderAllGroup(); return; }
  renderAll();
  renderLifetime();
  safe(renderTurnHist,'turnhist');
  loadAndRenderFindings(id);
}

/* ---------- init ---------- */
function init(){
  if(!MANIFEST.length){ el('app').innerHTML='<div class="placeholder" style="height:240px">No chats found. Run build_dashboard.py first.</div>'; return; }
  el('chatBtn').onclick=function(){ var p=el('chatPanel');
    if(p.classList.contains('open')) closeDD(); else { buildChatDropdown(el('chatSearch').value); openDD(); } };
  el('chatSearch').oninput=function(){ buildChatDropdown(this.value); };
  document.addEventListener('click',function(e){
    if(!el('chatDD').contains(e.target)) closeDD(); });
  el('gran').onchange=function(){ state.gran=this.value; if(state.chat||state.isConnected) rerender(); };
  el('monthSel').onchange=function(){ if(state.chat||state.isConnected) applyMonth(this.value); };
  el('applyRange').onclick=applyCustomRange;
  el('dFrom').onchange=function(){}; el('dTo').onchange=function(){};
  buildPlatformFilter();
  buildChatDropdown('');
  selectChat(MANIFEST[0].id);
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init);
else init();
</script>
</body>
</html>
'''
