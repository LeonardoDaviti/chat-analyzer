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
.findings-block{margin-bottom:14px}
.findings-block:last-child{margin-bottom:0}
.findings-header{font-size:11px;text-transform:uppercase;letter-spacing:.6px;
  color:var(--faint);font-weight:600;margin:2px 0 8px;
  border-bottom:1px solid var(--border);padding-bottom:4px}
/* findings-under-charts: compact strips inside a chart card */
.find-under{display:grid;gap:6px;margin-top:10px}
.find-under:empty{display:none;margin:0}
.fstrip{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;
  border-left:3px solid var(--border);padding:5px 10px;border-radius:6px;
  background:var(--panel-2);font-size:12px;line-height:1.45}
.fstrip.sev-signal{border-left-color:var(--accent)}
.fstrip.sev-notable{border-left-color:var(--b)}
.fstrip.sev-fun{border-left-color:var(--faint)}
.fstrip .f-chip{font-size:9px;text-transform:uppercase;letter-spacing:.5px;
  padding:1px 6px;border-radius:9px;border:1px solid var(--border);color:var(--muted)}
.fstrip.sev-signal .f-chip{border-color:var(--accent);color:var(--accent)}
.fstrip-tag{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--faint)}
.fstrip-text{flex:1;color:var(--text);min-width:180px}
.fstrip .f-evidence{font-size:10.5px;color:var(--faint);font-variant-numeric:tabular-nums}
/* chat-picker hide controls + hidden section */
.dd-item .dd-hide{color:var(--faint);cursor:pointer;padding:0 4px;font-size:12px;
  border-radius:4px;flex:0 0 auto}
.dd-item .dd-hide:hover{color:var(--bad)}
.dd-hidden-head{font-size:11px;text-transform:uppercase;letter-spacing:.6px;
  color:var(--faint);cursor:pointer;padding:8px 9px 4px;margin-top:6px;
  border-top:1px solid var(--border)}
.dd-hidden-note{font-size:10.5px;color:var(--faint);padding:0 9px 6px;font-style:italic}
.dd-item .dd-unhide{color:var(--a);cursor:pointer;padding:0 4px;font-size:12px;flex:0 0 auto}
.dd-item.pinned-compare{border:1px solid var(--b);background:rgba(158,158,158,.08);
  font-weight:600;margin-bottom:6px}
.dd-item.pinned-compare:hover,.dd-item.pinned-compare.active{background:rgba(158,158,158,.16)}
/* compare mode */
.cmp-pick{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
.cmp-opt{display:flex;align-items:center;gap:6px;padding:5px 10px;border-radius:14px;
  border:1px solid var(--border);background:var(--panel);cursor:pointer;font-size:12px;user-select:none}
.cmp-opt.on{border-color:var(--a)}
.cmp-opt .swatch{width:9px;height:9px;border-radius:2px;display:inline-block}
.cmp-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.cmp-chip{font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid var(--border);
  color:var(--muted);background:var(--panel-2)}
.cmp-dyad-row{margin:8px 0}
.cmp-dyad-name{font-size:12px;font-weight:600;margin-bottom:2px;display:flex;align-items:center;gap:6px}
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
  connSentMode:'msgs', connRecipMode:'msgs', // msgs/words toggle on the volume-flow cards
  isCompare:false, compareIds:[],   // "⚖ Compare" mode — selected dyad chat ids
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
  edits:0,calls:0,call_answered:0,call_missed:0,call_seconds:0};}
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
  el('app').innerHTML = injectStripHosts(
  section('Pulse','<div class="grid kpis" id="kpiRow"></div>')
  + section('Story timeline',
      card('Message volume','A above the line, partner mirrored below',
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
  + callsSection()
  + section('Shifts vs previous period',
      card('What changed','Every metric that moved, current range compared to the previous window of equal length',
        '<div class="diff" id="shiftList"></div>'))
  + findingsSection()
  + section('All-time lifetime metrics',
      '<div class="grid cols-2" id="ltCards"></div>'));
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
    + card('Voice notes','How many voice notes each person sends and how long they run (all-time)','<div class="chart" id="cTgVoice"></div>')
    + card('Reaction speed','Median time from a message to each person’s reaction — how fast they’re watching (all-time)','<div class="chart" id="cTgReactLat"></div>')
    + card('Signature reactions','Each person’s most-used reaction emoji and how concentrated it is (all-time)','<div id="tgSigBox" style="min-height:120px"></div>')
    + card('Edit latency','When edits happen after sending — quick typo fixes vs later reconsideration (all-time)','<div class="chart" id="cTgEditLat"></div>')
    + card('Stickers','Sticker use per person, top stickers and how much the two vocabularies overlap (all-time)','<div id="tgStickerBox" style="min-height:120px"></div>')
    + '</div>');
}
/* Calls — platform-neutral; rendered whenever the chat carries any call events
   (Telegram is call-rich, Instagram sparse). */
function callsSection(){
  if(!state.chat||!state.chat.calls) return '';
  return section('Calls',
    '<div class="grid cols-2">'
    + card('Calls over time','Calls in range, split by who started the call','<div class="chart" id="cCallsTime"></div>')
    + card('Answered vs missed','Answered = the call connected (talk time > 0) · in range','<div class="chart" id="cCallsMix"></div><div id="callsBox" style="min-height:60px;margin-top:8px"></div>')
    + card('Call outcomes','How calls ended · the call is credited to its initiator, so this is the outcome mix, not who literally hung up (all-time)','<div class="chart" id="cCallsOutcome"></div>')
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
  // ---- Voice notes: count + median duration (all-time) ---- #
  var vn=tg.voice_notes||{}, va=vn[A]||{}, vb=vn[B]||{};
  if((va.n||0)+(vb.n||0)>0){
    setChart('cTgVoice',{grid:baseGrid(),legend:legend(['count','median length']),
      tooltip:{trigger:'axis',backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
        formatter:function(ps){var s=esc(ps[0].axisValue)+'<br>';
          s+=markDot(COLORS.a)+'count: <b>'+fmtNum(ps[0].value)+'</b><br>';
          if(ps[1])s+=markDot(COLORS.b)+'median: <b>'+fmtDur((ps[1].value||0)/60)+'</b>';return s;}},
      xAxis:{type:'category',data:names,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
      yAxis:[valAxis({name:'count',nameTextStyle:{color:MUTED}}),
        valAxis({name:'sec',nameTextStyle:{color:MUTED},position:'right',axisLabel:{color:MUTED}})],
      series:[{name:'count',type:'bar',yAxisIndex:0,barMaxWidth:50,
        data:[va.n||0,vb.n||0],itemStyle:{color:COLORS.a}},
        {name:'median length',type:'bar',yAxisIndex:1,barMaxWidth:50,
          data:[va.median_s||0,vb.median_s||0],itemStyle:{color:COLORS.b}}]});
  } else noData('cTgVoice');
  // ---- Reaction latency: median seconds per person (all-time) ---- #
  var rl=tg.reaction_latency||{}, ra=rl[A]||{}, rb=rl[B]||{};
  if((ra.n||0)+(rb.n||0)>0){
    setChart('cTgReactLat',{grid:baseGrid(),
      tooltip:{trigger:'axis',backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
        formatter:function(ps){var i=ps[0].dataIndex;var o=i===0?ra:rb;
          return esc(names[i])+'<br>median: <b>'+fmtDur((o.median_s||0)/60)+'</b><br>'+fmtNum(o.n||0)+' reactions';}},
      xAxis:{type:'category',data:names,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
      yAxis:valAxis({name:'sec',nameTextStyle:{color:MUTED}}),
      series:[{type:'bar',barMaxWidth:60,
        data:[{value:ra.median_s||0,itemStyle:{color:COLORS.a}},
              {value:rb.median_s||0,itemStyle:{color:COLORS.b}}],
        label:{show:true,position:'top',color:TEXT,formatter:function(o){return fmtDur((o.value||0)/60);}}}]});
  } else noData('cTgReactLat');
  // ---- Signature reactions: top emoji + concentration ---- #
  var se=tg.signature_emoji||{}, seA=se[A]||{}, seB=se[B]||{};
  (function(){
    function line(u,o){
      var top=(o.top||[]);
      if(!top.length) return '<div class="nlp-label">'+esc(u)+'</div><div class="vocab-line faint">no reactions</div>';
      var tags=top.slice(0,6).map(function(t){return '<span class="tag">'+esc(t[0])+'<span class="n">'+fmtNum(t[1])+'</span></span>';}).join('');
      return '<div class="nlp-label">'+esc(u)+' · top '+esc(top[0][0])+' is '+fmtPct(o.concentration||0,0)+' of reactions</div>'+tags;
    }
    var box=el('tgSigBox'); if(box) box.innerHTML=line(A,seA)+line(B,seB);
  })();
  // ---- Edit latency buckets per person ---- #
  var elt=tg.edit_latency||{}, elA=elt[A]||{}, elB=elt[B]||{};
  if((elA.n||0)+(elB.n||0)>0){
    var eord=['<1m','1-10m','10-60m','>1h'];
    setChart('cTgEditLat',{grid:baseGrid(),legend:legend(names),
      tooltip:{trigger:'axis',backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT}},
      xAxis:{type:'category',data:eord,axisLine:{lineStyle:{color:GRID}},axisLabel:{color:MUTED}},
      yAxis:valAxis({}),
      series:[{name:A,type:'bar',itemStyle:{color:COLORS.a},
        data:eord.map(function(k){return (elA.buckets||{})[k]||0;})},
        {name:B,type:'bar',itemStyle:{color:COLORS.b},
          data:eord.map(function(k){return (elB.buckets||{})[k]||0;})}]});
  } else noData('cTgEditLat');
  // ---- Stickers: counts, top, overlap ---- #
  var st=tg.stickers||{}, spu=st.per_user||{}, stA=spu[A]||{}, stB=spu[B]||{};
  (function(){
    function line(u,o){
      var top=(o.top||[]);
      var tags=top.slice(0,8).map(function(t){return '<span class="tag">'+esc(t[0])+'<span class="n">'+fmtNum(t[1])+'</span></span>';}).join('');
      return '<div class="nlp-label">'+esc(u)+' · '+fmtNum(o.n||0)+' stickers</div>'+(tags||'<div class="vocab-line faint">none</div>');
    }
    var h=line(A,stA)+line(B,stB);
    if(st.overlap!=null){
      h+='<div class="vocab-line">Vocabulary overlap: <b>'+fmtPct(st.overlap,0)+'</b>'
        +(st.shared&&st.shared.length?' · shared: '+st.shared.map(function(e){return esc(e);}).join(' '):'')+'</div>';
    }
    var box=el('tgStickerBox'); if(box) box.innerHTML=h;
  })();
}
/* Calls — windowed timeline + answered/missed (from the daily table) plus an
   all-time outcome mix. Platform-neutral (renders for IG chats with calls). */
function renderCalls(b,rt){
  if(!state.chat||!state.chat.calls) return;
  var A=state.users[0],B=state.users[1], cl=state.chat.calls;
  // Timeline: calls per bucket, stacked by who started the call.
  var sa=[],sb=[];
  for(var i=0;i<b.starts.length;i++){var ts=b.ts[i];
    sa.push([ts,b.rows[i].A.calls||0]); sb.push([ts,b.rows[i].B.calls||0]);}
  setChart('cCallsTime',{grid:baseGrid(),legend:legend([A,B]),
    tooltip:Object.assign(tooltipBase(),{formatter:function(ps){
      var d=new Date(ps[0].value[0]);var s=esc(fmtDate(d))+'<br>';
      ps.forEach(function(p){s+=markDot(p.color)+esc(p.seriesName)+': <b>'+fmtNum(p.value[1])+'</b><br>';});return s;}}),
    xAxis:timeAxis(), yAxis:valAxis({}),
    series:[{name:A,type:'bar',stack:'calls',data:sa,itemStyle:{color:COLORS.a}},
      {name:B,type:'bar',stack:'calls',data:sb,itemStyle:{color:COLORS.b}}]});
  // Answered vs missed (windowed).
  var ans=(rt.tot.A.call_answered||0)+(rt.tot.B.call_answered||0);
  var mis=(rt.tot.A.call_missed||0)+(rt.tot.B.call_missed||0);
  if(ans+mis>0){
    setChart('cCallsMix',{tooltip:{trigger:'item',backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT}},
      series:[{type:'pie',radius:['45%','70%'],center:['50%','52%'],
        label:{color:TEXT,formatter:'{b}: {c}'},labelLine:{lineStyle:{color:GRID}},
        data:[{name:'Answered',value:ans,itemStyle:{color:COLORS.a}},
              {name:'Missed',value:mis,itemStyle:{color:COLORS.b}}]}]});
  } else noData('cCallsMix');
  // Talk-time + who-initiates box.
  var secs=(rt.tot.A.call_seconds||0)+(rt.tot.B.call_seconds||0);
  var box=el('callsBox');
  if(box) box.innerHTML='<div class="vocab-line">Talk time in range: <b>'+fmtDur(secs/60)
    +'</b> · median answered call: <b>'+fmtDur((cl.median_talk_s||0)/60)+'</b> (all-time)</div>'
    +'<div class="vocab-line">Started calls in range: '+esc(A)+' <b>'+fmtNum(rt.tot.A.calls||0)
    +'</b> · '+esc(B)+' <b>'+fmtNum(rt.tot.B.calls||0)+'</b></div>';
  // Outcome mix (all-time).
  var outs=cl.outcomes||{};
  var oc={missed:'#8892a6',hangup:COLORS.a,busy:'#E0A23F',disconnect:COLORS.b};
  var od=Object.keys(outs).map(function(k){return {name:k,value:outs[k],itemStyle:{color:oc[k]||'#7A6FF0'}};});
  if(od.length){
    setChart('cCallsOutcome',{tooltip:{trigger:'item',backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT}},
      series:[{type:'pie',radius:['45%','70%'],center:['50%','52%'],
        label:{color:TEXT,formatter:'{b}: {c}'},labelLine:{lineStyle:{color:GRID}},data:od}]});
  } else noData('cCallsOutcome');
}
function section(title,inner){return '<div class="section"><div class="section-title">'+esc(title)+'</div>'+inner+'</div>';}
function card(title,sub,inner){return '<div class="card"><h3>'+esc(title)+'</h3>'
  +(sub?'<div class="sub">'+esc(sub)+'</div>':'')+inner+'</div>';}
function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}

/* ============================================================ *
 * FINDINGS ("Insights") — lazy-loaded from data/insights.js.
 * Precomputed all-time findings (Tier 1). Graceful when absent.
 * Windowed recompute for daily-table rules (docs/INSIGHTS.md §3.3).
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
  // Wrapped in an addressable section so it can be hidden entirely when it has
  // no content (empty "Other findings" box disappears — Part 4b).
  return '<div class="section" id="findingsSection" style="display:none">'
    +'<div class="section-title">'+esc('📋 Other findings')+'</div>'
    +'<div id="findingsBox"></div></div>';
}
/* Anchor ids that findings attach to. Each gets a strip host (id "fu-<anchor>")
   injected right after its chart/box in the skeleton, so an anchored finding can
   render as a compact strip UNDER the chart it belongs to (M2.2). Any finding
   whose anchor is not present on the current page falls back to the "Other
   findings" box. */
var ANCHOR_IDS=['cVolume','cCal','cInit','cQ','cDepth','cTurns','cEmoji','cMedia',
  'cNight','cEnd','cRestart','cWait','cWe','cSent','cLSM','courtesyBox','cTgEdit',
  'cCallsTime','cTgVoice','cTgReactLat','tgSigBox','cTgEditLat','tgStickerBox',
  'cxFunnel','cxDyn','cxLatL','cxFocus','cxTypeMix','cxNightL','cxInitL','cxGini',
  'cxBurstDur','connRecipBox','connMirrorBox'];
var ANCHOR_SET={}; (function(){for(var i=0;i<ANCHOR_IDS.length;i++)ANCHOR_SET[ANCHOR_IDS[i]]=1;})();
/* Inject a strip host after each anchor-target's (empty) div in a skeleton HTML
   string. Targets are always empty divs ending in `></div>`. */
function injectStripHosts(html){
  return html.replace(/id="([A-Za-z][\w]*)"[^>]*><\/div>/g, function(m,id){
    return ANCHOR_SET[id] ? m+'<div class="find-under" id="fu-'+id+'"></div>' : m;
  });
}
function clearStripHosts(){
  for(var i=0;i<ANCHOR_IDS.length;i++){ var h=el('fu-'+ANCHOR_IDS[i]); if(h) h.innerHTML=''; }
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
function fCard(f){
  var sev=(f.severity==='signal'||f.severity==='notable'||f.severity==='fun')?f.severity:'notable';
  var anchor=f.anchor&&el(f.anchor)?f.anchor:null;
  return '<div class="finding sev-'+sev+'" data-rid="'+esc(f.id||'')+'">'
    +'<div class="f-head"><span class="f-chip">'+esc(f.severity||'')+'</span>'
    +'<span class="f-title">'+esc(f.title||'')+'</span></div>'
    +'<div class="f-sentence">'+esc(f.sentence||'')+'</div>'
    +'<div class="f-foot">'
    +'<span class="f-evidence">'+fEvidenceLine(f)+'</span>'
    +(anchor?'<button class="f-showme" data-anchor="'+esc(anchor)+'">show me →</button>':'')
    +'</div></div>';
}
/* Compact strip for a finding rendered directly under its chart (M2.2):
   severity chip + a "in this window"/"all-time" tag + sentence + evidence,
   no card chrome. */
function fStrip(f,tag){
  var sev=(f.severity==='signal'||f.severity==='notable'||f.severity==='fun')?f.severity:'notable';
  var ev=fEvidenceLine(f);
  return '<div class="fstrip sev-'+sev+'" data-rid="'+esc(f.id||'')+'">'
    +'<span class="f-chip">'+esc(f.severity||'')+'</span>'
    +(tag?'<span class="fstrip-tag">'+esc(tag)+'</span>':'')
    +'<span class="fstrip-text">'+esc(f.sentence||'')+'</span>'
    +(ev?'<span class="f-evidence">'+ev+'</span>':'')
    +'</div>';
}
/* PARITY-BEGIN — windowed daily-table findings engine.
 *
 * Mirrors a subset of Python's WINDOWABLE_RULE_IDS (see src/insights_engine.py).
 * Self-contained on purpose: tests/test_parity.py extracts the code between the
 * PARITY-BEGIN / PARITY-END markers and runs it under node against the same
 * synthetic daily tables the Python engine sees, so the two agree at the full
 * range (where the proportional gate scale == 1). Keep this block free of DOM /
 * `state` references — renderFindings (below the markers) is the only bridge to
 * the page.
 *
 * JS-mirrored rules — pure within-window aggregates over the daily table:
 *   question-imbalance, gottman-ratio, courtesy-asymmetry, media-reciprocity-gap,
 *   depth-mismatch, eager-waiter, left-on-react, unanswered-bids.
 * NOT mirrored (stay all-time only, from Python lifetime/extras or a
 * first-half-vs-second-half-of-LIFE comparison that is meaningless in a short
 * sub-window): monologue-drift, night-migration, we-ness-shift, feast-and-famine,
 * steady-drumbeat, and every non-windowable rule. See docs/INSIGHTS.md
 * "Window-awareness".
 */
var JS_MIN_BASE_RATE = 0.02;   // ratios only when both base rates >= 2%
var JS_MIN_SESSIONS = 60;      // depth-mismatch session gate (full)
var JS_MIN_MSGS = 500;         // global gate (mirrors Python MIN_MSGS)

function _wParseYMD(s){var p=s.split('-');return Date.UTC(+p[0],+p[1]-1,+p[2]);}
function _wFmtDay(ms){var d=new Date(ms);function p(n){return (n<10?'0':'')+n;}
  return d.getUTCFullYear()+'-'+p(d.getUTCMonth()+1)+'-'+p(d.getUTCDate());}
function _wPct(v){return (v*100).toFixed(0)+'%';}
function _wX(r){return r.toFixed(1)+'×';}

/* Fields the mirrored rules read; summed per user over the window (and over the
   window's first/second active-day halves for depth-mismatch stability). */
var _WIN_FIELDS = ['msgs','words','questions','questions_answered','pos_words',
  'neg_words','gratitude','apology','photos','videos','voice','turns',
  'reacted_leave','wait_reply_sum_min','wait_reply_n','initiations'];
function _wZero(){var o={};for(var i=0;i<_WIN_FIELDS.length;i++)o[_WIN_FIELDS[i]]=0;return o;}
function _wAdd(acc,cell){for(var i=0;i<_WIN_FIELDS.length;i++){var f=_WIN_FIELDS[i];acc[f]+=(cell[f]||0);}}

/* Build the window context in [sdMs,edMs]. The active-day halves (mid =
   floor(nDays/2)) match Python ChatCtx.h1/h2 exactly, so depth-mismatch's
   stability check ports 1:1. `fullDays` is the whole-history span; the gate
   scale = clamp(rangeDays/fullDays, 0.25, 1) so short windows get proportionally
   lower volume gates (25% floor) and the full range gets scale 1. */
function buildWinCtx(daily, users, sdMs, edMs, fullDays){
  var a=users[0], b=users[1];
  var days=[];
  for(var dk in daily){ var t=_wParseYMD(dk); if(t>=sdMs&&t<=edMs) days.push(dk); }
  days.sort();
  var tot={}, h1={}, h2={}, months={};
  tot[a]=_wZero(); tot[b]=_wZero(); h1[a]=_wZero(); h1[b]=_wZero(); h2[a]=_wZero(); h2[b]=_wZero();
  var mid=Math.floor(days.length/2);
  for(var di=0; di<days.length; di++){
    var c=daily[days[di]]; months[days[di].slice(0,7)]=1;
    var half=(di<mid)?h1:h2;
    for(var ui=0; ui<2; ui++){ var u=users[ui], cell=c[u]; if(!cell) continue;
      _wAdd(tot[u],cell); _wAdd(half[u],cell); }
  }
  var rangeDays=Math.round((edMs-sdMs)/86400000)+1;
  var fd=fullDays||rangeDays;
  return {users:users, tot:tot, h1:h1, h2:h2,
    nMsgs:tot[a].msgs+tot[b].msgs,
    nSessions:tot[a].initiations+tot[b].initiations,
    nMonths:Object.keys(months).length,
    gateScale:Math.max(0.25, Math.min(rangeDays/fd, 1))};
}
function wGate(ctx, fullGate){ return fullGate*ctx.gateScale; }  // floored at 25% of the full gate

function _mkFinding(id,category,severity,title,sentence,evidence,anchor){
  return {id:id,scope:'chat',category:category,severity:severity,
    title:title,sentence:sentence,evidence:evidence,anchor:anchor};
}

/* --- Rule ports. Ratio/rate thresholds are effect sizes (never scaled); only
   count/volume gates pass through wGate(). --- */
function jsQuestionImbalance(ctx){   // who ASKS more (asking-rate ratio >= 2x)
  var u=ctx.users,a=u[0],b=u[1],t=ctx.tot;
  if(t[a].msgs < wGate(ctx,100) || t[b].msgs < wGate(ctx,100)) return null;
  var qa=t[a].msgs?t[a].questions/t[a].msgs:0, qb=t[b].msgs?t[b].questions/t[b].msgs:0;
  var cand=[[a,qa,qb],[b,qb,qa]];
  for(var i=0;i<2;i++){ var X=cand[i][0],qx=cand[i][1],qy=cand[i][2];
    if(qx<JS_MIN_BASE_RATE||qy<JS_MIN_BASE_RATE) continue;
    if(qx>=2*qy){ var ratio=qx/qy;
      return _mkFinding('question-imbalance','dynamics','notable','One asks, one answers',
        X+' asks '+_wX(ratio)+' more questions per message.',
        {asker:X,q_rate:Math.round(qx*1e4)/1e4,partner_q_rate:Math.round(qy*1e4)/1e4,ratio:Math.round(ratio*100)/100},'cQ'); } }
  return null;
}
function jsGottmanRatio(ctx){
  var u=ctx.users,a=u[0],b=u[1],t=ctx.tot;
  var pos=t[a].pos_words+t[b].pos_words, neg=t[a].neg_words+t[b].neg_words;
  if(pos+neg < wGate(ctx,300) || neg < wGate(ctx,5)) return null;
  var ratio=pos/neg;
  if(ratio>=5 && ratio<=8) return null;
  var below=ratio<5, effect=below?(5-ratio)/5:Math.min((ratio-8)/8,1);
  if(effect<=0) return null;
  return _mkFinding('gottman-ratio','language','signal','Positivity balance',
    'Warm words outnumber cold ones '+ratio.toFixed(1)+':1 — '+(below?'below':'above')+' the 5:1 line.',
    {pos_neg_ratio:Math.round(ratio*100)/100,pos_words:pos,neg_words:neg},'cSent');
}
function jsCourtesyAsymmetry(ctx){
  var u=ctx.users,a=u[0],b=u[1],t=ctx.tot;
  var ca=t[a].gratitude+t[a].apology, cb=t[b].gratitude+t[b].apology;
  if(ca+cb < wGate(ctx,40)) return null;
  var ra=t[a].msgs?ca/t[a].msgs:0, rb=t[b].msgs?cb/t[b].msgs:0;
  var cand=[[a,ra,rb],[b,rb,ra]];
  for(var i=0;i<2;i++){ var X=cand[i][0],rx=cand[i][1],ry=cand[i][2];
    if(ry<=0) continue;
    if(rx>=2.5*ry){ var ratio=rx/ry;
      return _mkFinding('courtesy-asymmetry','language','notable','Courtesy gap',
        X+' says thanks or sorry '+_wX(ratio)+' more often.',
        {polite:X,rate:Math.round(rx*1e4)/1e4,partner_rate:Math.round(ry*1e4)/1e4,ratio:Math.round(ratio*100)/100},'courtesyBox'); } }
  return null;
}
function jsMediaReciprocity(ctx){
  var u=ctx.users,a=u[0],b=u[1],t=ctx.tot;
  var ma=t[a].photos+t[a].videos+t[a].voice, mb=t[b].photos+t[b].videos+t[b].voice;
  if(ma+mb < wGate(ctx,60)) return null;
  var cand=[[a,b,ma,mb],[b,a,mb,ma]];
  for(var i=0;i<2;i++){ var X=cand[i][0],Y=cand[i][1],mx=cand[i][2],my=cand[i][3];
    if(my<=0) continue;
    if(mx>=3*my){ var ratio=mx/my;
      return _mkFinding('media-reciprocity-gap','rhythm','fun','One sends the media',
        X+' sends the photos and voice notes; '+Y+' answers in text ('+Math.round(mx)+' vs '+Math.round(my)+').',
        {sender:X,media:Math.round(mx),partner_media:Math.round(my),ratio:Math.round(ratio*100)/100},'cMedia'); } }
  return null;
}
function jsDepthMismatch(ctx){
  var u=ctx.users,a=u[0],b=u[1],t=ctx.tot;
  if(ctx.nSessions < wGate(ctx,JS_MIN_SESSIONS)) return null;
  function wpt(cell){return cell.turns?cell.words/cell.turns:0;}
  var da=wpt(t[a]), db=wpt(t[b]);
  var cand=[[a,b,da,db],[b,a,db,da]];
  for(var i=0;i<2;i++){ var X=cand[i][0],Y=cand[i][1],dx=cand[i][2],dy=cand[i][3];
    if(dy<=0) continue;
    if(dx>=1.8*dy){
      var h1y=wpt(ctx.h1[Y]), h2y=wpt(ctx.h2[Y]);
      var r1=h1y?wpt(ctx.h1[X])/h1y:0, r2=h2y?wpt(ctx.h2[X])/h2y:0;
      if(Math.min(r1,r2) < 1.5) continue;   // stability: both halves keep the gap
      var ratio=dx/dy;
      return _mkFinding('depth-mismatch','dynamics','notable','Essays vs one-liners',
        X+' writes '+_wX(ratio)+' more per turn — one sends essays, the other sends lines.',
        {writer:X,words_per_turn:Math.round(dx*10)/10,partner_words_per_turn:Math.round(dy*10)/10,ratio:Math.round(ratio*100)/100},'cDepth'); } }
  return null;
}
function jsEagerWaiter(ctx){
  var u=ctx.users,a=u[0],b=u[1],t=ctx.tot;
  var na=t[a].wait_reply_n, nb=t[b].wait_reply_n;
  if(na < wGate(ctx,30) || nb < wGate(ctx,30)) return null;
  var ma=na?t[a].wait_reply_sum_min/na:0, mb=nb?t[b].wait_reply_sum_min/nb:0;
  var cand=[[a,ma,mb],[b,mb,ma]];
  for(var i=0;i<2;i++){ var X=cand[i][0],mx=cand[i][1],my=cand[i][2];
    if(mx<=5.0 && my>0 && mx<=0.5*my){
      return _mkFinding('eager-waiter','dynamics','notable','Waiting by the phone',
        X+' answers within ~'+mx.toFixed(0)+' min after long silences (vs ~'+my.toFixed(0)+' min) — keeps the chat open.',
        {waiter:X,reply_min:Math.round(mx*10)/10,partner_reply_min:Math.round(my*10)/10,n_waits:Math.round(Math.min(na,nb))},'cWait'); } }
  return null;
}
function jsLeftOnReact(ctx){
  var u=ctx.users,a=u[0],b=u[1],t=ctx.tot;
  var ra=t[a].reacted_leave, rb=t[b].reacted_leave;
  if(ra+rb < wGate(ctx,40)) return null;
  var cand=[[a,b,ra,rb],[b,a,rb,ra]];
  for(var i=0;i<2;i++){ var X=cand[i][0],Y=cand[i][1],rx=cand[i][2],ry=cand[i][3];
    if(ry<=0) continue;
    if(rx>=2*ry && rx>=wGate(ctx,20)){ var ratio=rx/ry;
      return _mkFinding('left-on-react','dynamics','notable','Exit by reaction',
        'When '+X+' exits a conversation, it’s often with just a reaction — '+Math.round(rx)+' times vs '+Math.round(ry)+'.',
        {leaver:X,reacted_leaves:Math.round(rx),partner_reacted_leaves:Math.round(ry),ratio:Math.round(ratio*100)/100},'cRestart'); } }
  return null;
}
function jsUnansweredBids(ctx){   // who gets ANSWERED less (answer-rate <= 0.6x)
  var u=ctx.users,a=u[0],b=u[1],t=ctx.tot;
  var qa=t[a].questions, qb=t[b].questions;
  if(qa < wGate(ctx,40) || qb < wGate(ctx,40)) return null;
  var ra=qa?t[a].questions_answered/qa:0, rb=qb?t[b].questions_answered/qb:0;
  var cand=[[a,b,ra,rb],[b,a,rb,ra]];
  for(var i=0;i<2;i++){ var X=cand[i][0],Y=cand[i][1],rx=cand[i][2],ry=cand[i][3];
    if(ry<=0) continue;
    if(rx<=0.6*ry){ var hang=1-rx;
      return _mkFinding('unanswered-bids','dynamics','signal','Questions left hanging',
        Y+' leaves '+_wPct(hang)+' of '+X+'’s questions hanging — answered far less than the other way round.',
        {asker:X,answer_rate:Math.round(rx*1e3)/1e3,partner_answer_rate:Math.round(ry*1e3)/1e3,n_questions:Math.round(qa+qb)},'cQ'); } }
  return null;
}

/* Registry — the exact set tests/test_parity.py checks against the Python
   engine. Keep in sync with PARITY_RULES there. */
var JS_WINDOWABLE_RULES = {
  'question-imbalance': jsQuestionImbalance,
  'gottman-ratio': jsGottmanRatio,
  'courtesy-asymmetry': jsCourtesyAsymmetry,
  'media-reciprocity-gap': jsMediaReciprocity,
  'depth-mismatch': jsDepthMismatch,
  'eager-waiter': jsEagerWaiter,
  'left-on-react': jsLeftOnReact,
  'unanswered-bids': jsUnansweredBids
};

/* Run all mirrored rules over [sd,ed]. `fullStart/fullEnd` bound the chat's
   whole history; when the selected window equals it the gate scale is 1 and the
   output matches the Python engine. Windowed findings carry no `score` (v1):
   ordering is severity, then rule id — deterministic. sd/ed/fullStart/fullEnd
   accept Date objects or epoch-ms. */
function computeWindowedFindings(daily, users, sd, ed, fullStart, fullEnd){
  if(!daily || !users || users.length!==2) return [];
  var sdMs=(sd instanceof Date)?sd.getTime():sd, edMs=(ed instanceof Date)?ed.getTime():ed;
  var fs=fullStart!=null?((fullStart instanceof Date)?fullStart.getTime():fullStart):sdMs;
  var fe=fullEnd!=null?((fullEnd instanceof Date)?fullEnd.getTime():fullEnd):edMs;
  var fullDays=Math.round((fe-fs)/86400000)+1;
  var ctx=buildWinCtx(daily, users, sdMs, edMs, fullDays);
  if(ctx.nMsgs < wGate(ctx,JS_MIN_MSGS)) return [];
  var out=[];
  for(var rid in JS_WINDOWABLE_RULES){
    var f=null;
    try{ f=JS_WINDOWABLE_RULES[rid](ctx); }
    catch(e){ if(typeof console!=='undefined'&&console.error) console.error('windowed rule '+rid+' failed:',e); }
    if(f){ f.window={from:_wFmtDay(sdMs),to:_wFmtDay(edMs)}; out.push(f); }
  }
  var sev={signal:0,notable:1,fun:2};
  out.sort(function(x,y){var sx=(x.severity in sev)?sev[x.severity]:1, sy=(y.severity in sev)?sev[y.severity]:1;
    return sx-sy || x.id.localeCompare(y.id);});
  return out;
}
/* PARITY-END */

/* Render findings for the current scope into #findingsBox.
   scopeKey: a chat id, or 'connected:<variant>'. Two blocks:
     - "In this window (…)": windowed daily-table rules, recomputed for the
       selected range. Rendered only when the range is NARROWER than the full
       history (full range => all-time is the same story, so it is skipped).
     - "All-time (full history)": from insights.js. A rule id already shown in
       the window block is skipped here (dedup) — the all-time story is implied.
   Connected scope is all-time only (windowed is out of scope this wave). */
function renderFindings(scopeKey){
  var box=el('findingsBox');
  clearStripHosts();
  var isConnected = scopeKey.indexOf('connected:')===0;
  var winIds={};                 // rule ids shown in a window strip
  var hostHtml={};               // 'fu-<anchor>' -> accumulated strip HTML
  var other=[];                  // strips with no resolvable on-page anchor
  var placedAnchored=false;
  function place(f,tag){
    var anchor=f.anchor;
    var host = anchor ? el('fu-'+anchor) : null;
    if(host){ var k='fu-'+anchor; hostHtml[k]=(hostHtml[k]||'')+fStrip(f,tag); placedAnchored=true; }
    else { other.push(fStrip(f,tag)); }
  }
  // 1) Windowed daily-table findings (chat scope, only when the range is
  //    narrower than the full history). These get the "in this window" tag and
  //    replace any all-time finding of the same rule id.
  if(!isConnected && state.chat && state.users && state.users.length===2){
    var full = state.fullStart && state.fullEnd && state.start && state.end &&
      state.start.getTime()<=state.fullStart.getTime() &&
      state.end.getTime()>=state.fullEnd.getTime();
    if(!full){
      var wf=computeWindowedFindings(state.chat.daily||{}, state.users,
        state.start, state.end, state.fullStart, state.fullEnd);
      for(var i=0;i<wf.length;i++){ winIds[wf[i].id]=1; place(wf[i],'in this window'); }
    }
  }
  // 2) All-time findings from insights.js (deduped against the window block).
  var all=window.INSIGHTS||{}, allList;
  if(isConnected){ var v=scopeKey.slice('connected:'.length); allList=((all.connected||{})[v])||[]; }
  else { allList=all[scopeKey]||[]; }
  for(var j=0;j<allList.length;j++){ if(winIds[allList[j].id]) continue; place(allList[j],'all-time'); }
  // 3) Write strips into their chart-card hosts.
  for(var hid in hostHtml){ var h=el(hid); if(h) h.innerHTML=hostHtml[hid]; }
  // 4) "Other findings" box holds only findings with no chart on this page.
  //    When there are none, the whole section is hidden (Part 4b) — no empty box.
  var sec=el('findingsSection');
  if(box){
    if(other.length){
      var note = isConnected ? '<div class="findings-note">Connected findings are all-time (data honesty — the insights engine is lifetime here).</div>' : '';
      box.innerHTML=note+'<div class="findings">'+other.join('')+'</div>';
      if(sec) sec.style.display='';
    } else {
      box.innerHTML='';
      if(sec) sec.style.display='none';
    }
  }
}
function loadAndRenderFindings(scopeKey){
  ensureInsights(function(){ try{ renderFindings(scopeKey); }catch(e){ try{console.error('renderFindings failed:',e);}catch(_){} } });
  /* Windowed findings render even before insights.js resolves. */
  if(scopeKey.indexOf('connected:')!==0){
    try{ renderFindings(scopeKey); }catch(e){}
  }
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
  safe(function(){renderCalls(b,rt);},'calls');
  safe(function(){renderShifts(rt);},'shifts');
  // Findings: windowed recompute for daily-table rules + all-time from insights.js.
  safe(function(){
    if(el('findingsBox')&&state.chat&&state.users&&state.users.length===2){
      try{renderFindings(state.chatId);}catch(e){}
    }
  },'findings');
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
      areaSeries(A,sa,COLORS.a),
      areaSeries(B,sb,COLORS.b)
    ]
  };
  setChart('cVolume',opt);
  var c=charts['cVolume'];
  c.off('datazoom'); c.on('datazoom',onVolumeZoom);
}
function areaSeries(name,data,color){
  return {name:name,type:'line',data:data,showSymbol:false,smooth:false,
    lineStyle:{width:1.5,color:color},itemStyle:{color:color},
    areaStyle:{color:color,opacity:.22}};
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
  safe(function(){renderTelegram(rt);},'telegram');
  safe(function(){renderCalls(b,rt);},'calls');
  safe(function(){renderShifts(rt);},'shifts');
  // Findings: windowed recompute for daily-table rules.
  safe(function(){
    if(el('findingsBox')&&state.chat&&state.users&&state.users.length===2){
      try{renderFindings(state.chatId);}catch(e){}
    }
  },'findings');
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
  if(state.isCompare) renderCompare();
  else if(state.isConnected) renderAllConnected();
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

/* ---- windowed per-contact recompute layer (contact_monthly) ----
   Every connected leaderboard/card recomputes from contact_monthly clipped to
   the selected range: months whose 'YYYY-MM' falls between the range's first
   and last month (same convention as the other monthly-clipped charts). */
function connMonthsInRange(){
  return {sm:ymd(state.start).slice(0,7), em:ymd(state.end).slice(0,7)};
}
function connContactAgg(){ // {chat_id: {summed counters}} over the active range
  var cm=(state.connected&&state.connected.contact_monthly)||{};
  var r=connMonthsInRange(), out={};
  for(var mon in cm){ if(mon<r.sm||mon>r.em) continue;
    var month=cm[mon];
    for(var cid in month){ var cell=month[cid], acc=out[cid]||(out[cid]={});
      for(var k in cell) acc[k]=(acc[k]||0)+cell[k]; }
  }
  return out;
}
function connContactMeta(){ // chat_id -> contact record (name / platform / dates)
  var m={}; ((state.connected&&state.connected.contacts)||[]).forEach(function(c){m[c.chat_id]=c;});
  return m;
}
function connGates(){
  var g=(state.connected&&state.connected.gates)||{};
  return {min_msgs:g.min_msgs||0, min_replies:g.min_replies||0, react_min:g.react_min||0};
}
/* Population variance (matches Python _variance): sum((v-mean)^2)/n. */
function connVar(vals){
  var n=vals.length; if(n<2) return 0;
  var mean=0; vals.forEach(function(v){mean+=v;}); mean/=n;
  var s=0; vals.forEach(function(v){s+=(v-mean)*(v-mean);}); return s/n;
}

function renderSkeletonConnected(){
  var owner=state.connected.owner||'You';
  el('app').innerHTML = injectStripHosts(
  '<div class="section" style="padding-bottom:0"><div id="connVariantNote" class="sub" style="font-size:13px"></div></div>'
  + section('Pulse — '+owner+' across every chat','<div class="grid kpis" id="kpiRow"></div>')
  + section('Attention & texting span',
      '<div class="grid cols-2">'
      + card('Time spent texting','Sum of conversation-session minutes you took part in, any chat (per bucket, in range)','<div class="chart" id="cxTexting"></div>')
      + card('Engagement bursts','Runs of your messages across ALL chats with gaps under 15 min (bursts started per bucket, in range)','<div class="chart" id="cxBursts"></div>')
      + card('Burst length trend','Median burst duration per month, minutes (monthly, in range)','<div class="chart" id="cxBurstDur"></div>')
      + card('Focus vs juggling','Your active 10-min windows: one chat vs several at once · plus chat-switch rate (in range)','<div class="chart" id="cxFocus"></div>')
      + '</div>')
  + section('Session portfolio',
      '<div class="grid cols-2">'
      + card('Conversation type mix','ping / exchange / hangout / deep talk per month (all chats, in range)','<div class="chart" id="cxTypeMix"></div>')
      + card('Deep talks per week','Long sessions with long turns + questions or self-disclosure (in range)','<div class="chart" id="cxDeep"></div>')
      + '</div>')
  + section('Contact leaderboards',
      '<div class="grid cols-2">'
      + card('Where your messages go','Share of everything you sent · top 12 + others · 👥 groups included (in range)','<div class="chips" id="cxSentToggle"></div><div class="chart tall" id="cxSentL"></div>')
      + card('Attention hierarchy','Your mean reply latency per contact, fastest first · monthly sums pooled (means weighted by volume) · only contacts with ≥50 replies in range · 1:1 chats only','<div class="chart tall" id="cxLatL"></div>')
      + card('Initiation asymmetry — you start','Share of conversations YOU started with each contact (in range, volume-gated) · 1:1 chats only','<div class="chart tall" id="cxInitL"></div>')
      + card('Initiation asymmetry — they start toward you','Share of conversations THEY started (1 − your share) with each contact (in range, volume-gated) · 1:1 chats only','<div class="chart tall" id="cxInitRevL"></div>')
      + card('Night ownership','Who receives your 00:00–06:00 messages · 👥 groups included (in range)','<div class="chart tall" id="cxNightL"></div>')
      + card('Openness','Your words per turn with each contact — where you talk in paragraphs vs monosyllables (in range, volume-gated) · 1:1 chats only','<div class="chart tall" id="cxOpenL"></div>')
      + card('You react fastest to','Mean time from their message to your reaction, fastest first · ≥30 reactions in range · 1:1 chats only','<div class="chart tall" id="cxReactYou"></div>')
      + card('Reacts to you fastest','Mean time from your message to their reaction, fastest first · ≥30 reactions in range · 1:1 chats only','<div class="chart tall" id="cxReactThem"></div>')
      + card('Style mirroring & code-switching','How much your texting style shape-shifts between contacts (in range) · 1:1 chats only','<div id="connMirrorBox" style="min-height:200px"></div>')
      + '</div>')
  + section('Social portfolio dynamics',
      '<div class="grid cols-2">'
      + card('Attention concentration (Gini)','0 = attention spread evenly · 1 = one contact gets everything (monthly, in range)','<div class="chart" id="cxGini"></div>')
      + card('Active · churned · reactivated contacts','Monthly counts (churn = silent for the next two months; in range)','<div class="chart" id="cxDyn"></div>')
      + card('Reciprocity','You send vs receive — biggest surpluses (you over-invest) and deficits, log₂(sent/received) · 👥 groups: you vs the rest of the group combined (in range)','<div class="chips" id="cxRecipToggle"></div><div id="connRecipBox" style="min-height:40px"></div><div class="chart tall" id="cxRecip"></div>')
      + '</div>')
  + section('New-contact funnel',
      '<div class="grid cols-2">'
      + card('Met → talked again → recurring','New contacts whose first message falls in range · only accepted, still-existing chats are visible (survivorship bias)','<div class="chart" id="cxFunnel"></div>')
      + card('New contacts per month','A chat’s first-ever message · split by who texted first (in range)','<div class="chart" id="cxNewC"></div>')
      + '</div>')
  + findingsSection()
  + section('Groups lane',
      card('Group chats','Kept separate so groups never pollute the contact rankings (in range)','<div id="connGroupsBox" style="min-height:80px"></div>'))
  + '<div class="section" id="connMergePanel" style="display:none"><div class="card">'
    + '<h3>⧉ Merge contacts</h3>'
    + '<div class="sub" style="font-size:13px">Map the same person across Instagram &amp; Telegram into one entity. '
    + 'Manual only — nothing is auto-matched. Applies to this “All platforms” view after you re-run analysis.</div>'
    + '<div id="connMergeBody"></div>'
    + '<div id="connMergeStatus" class="sub" style="font-size:12px;margin-top:8px"></div>'
    + '</div></div>');
}

/* Prepend the platform badge to a leaderboard/contact row name in the merged
   ('all') variant, matching the chat-picker badges (📸 / ✈️). */
function connLabel(r){
  return (state.connectedVariant==='all'&&r&&r.platform)
    ? pfBadge(r.platform)+' '+r.name : (r?r.name:'');
}
/* Per-platform split for a merged (⧉) entity, e.g. "📸 120 · ✈️ 340". Empty
   string for non-merged rows. Used in tooltips where a platform badge appears. */
function connSplit(r){
  if(!r||!r.merged||!r.platforms) return '';
  var out=[]; for(var p in r.platforms) out.push(pfBadge(p)+' '+fmtNum(r.platforms[p]));
  return out.length?(' · '+out.join(' · ')):'';
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
  safe(renderConnMerge,'cmerge');
  safe(function(){renderConnKPIs(rt,has);},'ckpi');
  safe(function(){renderConnTexting(b);},'ctexting');
  safe(function(){renderConnBursts(b);},'cbursts');
  safe(renderConnBurstDur,'cburstdur');
  safe(renderConnFocus,'cfocus');
  safe(renderConnTypeMix,'ctypemix');
  safe(renderConnDeep,'cdeep');
  safe(renderConnLeaderboards,'clead');
  safe(renderConnInitRev,'cinitrev');
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
  // Windowed attention (parallel-texting + mean burst span) from monthly.attention.
  var am=(c.monthly||{}).attention||{}, msA=connMonthKeys(am);
  var wActive=0,wJug=0,wBurstDur=0,wBurstCnt=0;
  msA.forEach(function(m){var a=am[m];wActive+=a.active_windows;wJug+=a.juggle_windows;
    wBurstDur+=a.burst_dur_sum_min;wBurstCnt+=a.burst_count;});
  var parallelR=wActive?wJug/wActive:null;
  var meanSpan=wBurstCnt?wBurstDur/wBurstCnt:null;

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
    kpi('Mean burst span',meanSpan==null?'—':fmtDur(meanSpan),null,
      '<span class="split faint">per burst · in range</span>'),
    kpi('Parallel texting',parallelR==null?'—':fmtPct(parallelR,1),null,
      '<span class="split faint">windows with ≥2 chats · in range</span>'),
    kpi('Active contacts',fmtNum(activeContacts),null,
      '<span class="split faint">span overlaps range · '+fmtNum((c.totals||{}).contacts)+' total</span>'),
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
  // Windowed from monthly.attention: sum window/switch counts over range months.
  var am=(state.connected.monthly||{}).attention||{}, ms=connMonthKeys(am);
  var active=0,juggle=0,adjacent=0,switches=0,hours=0;
  ms.forEach(function(m){var a=am[m];active+=a.active_windows;juggle+=a.juggle_windows;
    adjacent+=a.adjacent;switches+=a.switches;hours+=a.active_hours;});
  if(!active){ noData('cxFocus'); return; }
  ensureCanvas('cxFocus');
  var frag=juggle/active, focus=1-frag;
  var sw={switches_per_active_hour:hours?switches/hours:0,
          switch_fraction:adjacent?switches/adjacent:0};
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
/* msgs/words toggle chips on the volume-flow cards (share + reciprocity). The
   default is 'msgs'; flipping to 'words' re-renders the card from the word
   counters in contact_monthly (words_sent / words_recv). */
function renderConnModeChips(id,key,setter){
  var box=el(id); if(!box) return;
  var mode=state[key]; box.innerHTML='';
  [['msgs','Messages'],['words','Words']].forEach(function(m){
    var chip=document.createElement('span');
    chip.className='chip'+(mode===m[0]?' active':'');
    chip.textContent=m[1];
    chip.setAttribute('data-mode',m[0]);
    chip.onclick=function(){ window[setter](m[0]); };
    box.appendChild(chip);
  });
}
function connSetSentMode(m){ if(state.connSentMode===m) return;
  state.connSentMode=m; safe(renderConnLeaderboards,'clead'); }
function connSetRecipMode(m){ if(state.connRecipMode===m) return;
  state.connRecipMode=m; safe(renderConnRecip,'crecip'); }

/* Every contact leaderboard recomputes from contact_monthly clipped to the
   active range. Volume gates are absolute WITHIN the window (≥ N in range). */
function renderConnLeaderboards(){
  var agg=connContactAgg(), meta=connContactMeta(), g=connGates();
  var cids=Object.keys(agg);
  function isGroup(cid){ return !!(meta[cid]&&meta[cid].is_group); }
  // Volume-flow label — prepend a 👥 badge for groups (kept on top of any
  // platform badge connLabel adds in the merged 'all' view).
  function lbl(cid){ return (isGroup(cid)?'👥 ':'')+connLabel(meta[cid]||{}); }
  function meget(cid){ return meta[cid]||{}; }
  // Dyadic-behaviour boards are 1:1 only — groups never carry those semantics.
  var dyadCids=cids.filter(function(cid){return !isGroup(cid);});

  // Where your messages go — top 12 + Others (share of everything sent IN RANGE).
  // Groups ARE destinations of your messages, so they join this board (👥). The
  // msgs/words toggle switches the metric between message and word counts.
  renderConnModeChips('cxSentToggle','connSentMode','connSetSentMode');
  var sWords=state.connSentMode==='words';
  function sMetric(cid){ return sWords?(agg[cid].words_sent||0):(agg[cid].sent||0); }
  var totSent=0; cids.forEach(function(cid){totSent+=sMetric(cid);});
  var sentRows=cids.filter(function(cid){return sMetric(cid)>0;})
    .sort(function(a,b){return sMetric(b)-sMetric(a);});
  var top=sentRows.slice(0,12), covered=0;
  var sUnit=sWords?' words':' messages';
  var rows=top.map(function(cid){covered+=sMetric(cid);
    return {name:lbl(cid),v:totSent?sMetric(cid)/totSent:0,
      tip:fmtNum(sMetric(cid))+sUnit+connSplit(meget(cid))};});
  if(totSent>covered) rows.push({name:'Others',v:(totSent-covered)/totSent,
    tip:fmtNum(totSent-covered)+sUnit,c:OTHERS_COLOR});
  rows.sort(function(a,b){return b.v-a.v;});
  connHBar('cxSentL',rows,function(v){return fmtPct(v,1);});

  // Attention hierarchy — mean reply latency (pooled monthly sums), fastest first.
  var lat=dyadCids.filter(function(cid){return (agg[cid].reply_lat_n||0)>=g.min_replies;})
    .map(function(cid){var a=agg[cid];
      return {name:lbl(cid),v:a.reply_lat_sum_min/a.reply_lat_n,tip:fmtNum(a.reply_lat_n)+' replies (≥'+g.min_replies+' in range)'};})
    .sort(function(a,b){return a.v-b.v;});           // fastest first -> top
  connHBar('cxLatL',lat,function(v){return fmtDur(v);});

  // Initiation asymmetry — you start (share of sessions you opened).
  var init=dyadCids.filter(function(cid){return (agg[cid].sent||0)>=g.min_msgs&&(agg[cid].sessions||0)>0;})
    .map(function(cid){var a=agg[cid];
      return {name:lbl(cid),v:a.initiations/a.sessions,tip:fmtNum(a.sessions)+' sessions'};})
    .sort(function(a,b){return b.v-a.v;});
  connHBar('cxInitL',init,function(v){return fmtPct(v);});

  // Night ownership — share of your 00:00–06:00 messages (groups included, 👥).
  var totNight=0; cids.forEach(function(cid){totNight+=agg[cid].night_sent||0;});
  var night=cids.filter(function(cid){return (agg[cid].night_sent||0)>0;})
    .map(function(cid){var a=agg[cid];
      return {name:lbl(cid),v:totNight?a.night_sent/totNight:0,tip:fmtNum(a.night_sent)+' night messages'};})
    .sort(function(a,b){return b.v-a.v;});
  connHBar('cxNightL',night,function(v){return fmtPct(v,1);});

  // Openness — your words per turn (words / owner turns) in range.
  var open=dyadCids.filter(function(cid){return (agg[cid].sent||0)>=g.min_msgs&&(agg[cid].turns_sent||0)>0;})
    .map(function(cid){var a=agg[cid];
      return {name:lbl(cid),v:a.words_sent/a.turns_sent,tip:fmtNum(a.turns_sent)+' turns · '+fmtNum(a.words_sent)+' words'};})
    .sort(function(a,b){return b.v-a.v;});
  connHBar('cxOpenL',open,function(v){return fmtNum(v);});

  // Reaction-latency leaderboards (both directions), fastest first (mean seconds).
  var ry=dyadCids.filter(function(cid){return (agg[cid].react_you_n||0)>=g.react_min;})
    .map(function(cid){var a=agg[cid];
      return {name:lbl(cid),v:(a.react_you_sum_s/a.react_you_n)/60,tip:fmtNum(a.react_you_n)+' reactions (≥'+g.react_min+' in range)'};})
    .sort(function(a,b){return a.v-b.v;});
  connHBar('cxReactYou',ry,function(v){return fmtDur(v);});
  var rm=dyadCids.filter(function(cid){return (agg[cid].react_them_n||0)>=g.react_min;})
    .map(function(cid){var a=agg[cid];
      return {name:lbl(cid),v:(a.react_them_sum_s/a.react_them_n)/60,tip:fmtNum(a.react_them_n)+' reactions (≥'+g.react_min+' in range)'};})
    .sort(function(a,b){return a.v-b.v;});
  connHBar('cxReactThem',rm,function(v){return fmtDur(v);});

  // Style mirroring & code-switching — recompute style + variance over the range.
  var ung=dyadCids.filter(function(cid){return (agg[cid].sent||0)>=g.min_msgs;});
  var emojiRates=[],wlenVals=[],geoVals=[],mirror=[];
  ung.forEach(function(cid){var a=agg[cid];
    var er=a.sent?(a.emoji_sent||0)/a.sent:0;
    var wl=a.words_sent?(a.o_wlen||0)/a.words_sent:0;
    var geo=a.lang_total?(a.lang_geo||0)/a.lang_total:0;
    var cer=a.recv?(a.recv_emoji||0)/a.recv:0;
    emojiRates.push(er); wlenVals.push(wl); geoVals.push(geo);
    mirror.push({name:lbl(cid),score:1-Math.min(1,Math.abs(er-cer))});
  });
  mirror.sort(function(a,b){return b.score-a.score;});
  var h='<div class="nlp-label">You mirror most</div>';
  if(mirror.length) mirror.slice(0,6).forEach(function(r){
    h+='<span class="tag hot">'+esc(r.name)+'<span class="n">'+fmtPct(r.score,0)+'</span></span>';});
  else h+='<div class="vocab-line faint">No contacts clear the volume gate in range.</div>';
  h+='<div class="nlp-label">Style variance across contacts</div>'
    +'<div class="vocab-line">emoji rate '+fmtNum(connVar(emojiRates))
    +' · word length '+fmtNum(connVar(wlenVals))
    +' · language mix '+fmtNum(connVar(geoVals))+'</div>'
    +'<div class="vocab-line faint">Higher variance = you change voice more between people (code-switching). In range.</div>';
  var box=el('connMirrorBox'); if(box) box.innerHTML=h;
}

/* Reversed initiation twin: share of conversations THEY started toward you
   (1 − your initiation share), recomputed windowed. */
function renderConnInitRev(){
  var agg=connContactAgg(), meta=connContactMeta(), g=connGates();
  var rows=Object.keys(agg)
    .filter(function(cid){return !(meta[cid]&&meta[cid].is_group)
      &&(agg[cid].sent||0)>=g.min_msgs&&(agg[cid].sessions||0)>0;})
    .map(function(cid){var a=agg[cid];
      return {name:connLabel(meta[cid]||{}),v:1-(a.initiations/a.sessions),tip:fmtNum(a.sessions)+' sessions'};})
    .sort(function(a,b){return b.v-a.v;});
  connHBar('cxInitRevL',rows,function(v){return fmtPct(v);});
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
/* Reciprocity — a diverging horizontal bar of log₂(sent/received) per contact
   over the selected range: top ~8 surpluses (you over-invest) and top ~8
   deficits, volume-gated, with in-range headline totals above. */
function renderConnRecip(){
  var agg=connContactAgg(), meta=connContactMeta(), g=connGates();
  // msgs/words toggle: reciprocity in messages (default) or words. For a group,
  // "received" is every message/word from the rest of the group combined.
  renderConnModeChips('cxRecipToggle','connRecipMode','connSetRecipMode');
  var wMode=state.connRecipMode==='words';
  function sM(a){ return wMode?(a.words_sent||0):(a.sent||0); }
  function rM(a){ return wMode?(a.words_recv||0):(a.recv||0); }
  var unit=wMode?'words':'messages';
  var sentTot=0,recvTot=0,rows=[];
  for(var cid in agg){ var a=agg[cid];
    var s=sM(a), rv=rM(a);
    sentTot+=s; recvTot+=rv;
    // Volume gate stays on message count (unchanged) so the same ties qualify
    // regardless of the toggle; only the plotted metric switches.
    if((a.sent||0)>=g.min_msgs && rv>0 && s>0){
      rows.push({name:(meta[cid]&&meta[cid].is_group?'👥 ':'')+connLabel(meta[cid]||{}),
        l2:Math.log(s/rv)/Math.LN2, sent:s, recv:rv});
    }
  }
  var head=el('connRecipBox');
  if(head) head.innerHTML='<div class="vocab-line">In range ('+unit+'): you sent <b>'+fmtNum(sentTot)
    +'</b> · received <b>'+fmtNum(recvTot)+'</b> · ratio <b>'
    +(recvTot?fmtNum(sentTot/recvTot):'—')+'</b></div>';
  var pos=rows.filter(function(r){return r.l2>0;}).sort(function(a,b){return b.l2-a.l2;}).slice(0,8);
  var neg=rows.filter(function(r){return r.l2<0;}).sort(function(a,b){return a.l2-b.l2;}).slice(0,8);
  var arr=pos.concat(neg).sort(function(a,b){return a.l2-b.l2;}); // deficits bottom, surpluses top
  if(!arr.length){ noData('cxRecip'); return; }
  ensureCanvas('cxRecip');
  setChart('cxRecip',{grid:{left:150,right:64,top:8,bottom:24},
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){var r=arr[p.dataIndex];
        return esc(r.name)+': log₂ <b>'+(r.l2>=0?'+':'')+r.l2.toFixed(2)+'</b><br>'
          +'sent '+fmtNum(r.sent)+' / received '+fmtNum(r.recv)+' '+unit+' (ratio '+fmtNum(r.sent/r.recv)+')';}},
    xAxis:valAxis({axisLabel:{color:MUTED,formatter:function(v){return (v>0?'+':'')+v;}}}),
    yAxis:{type:'category',data:arr.map(function(r){return r.name;}),
      axisLabel:{color:MUTED,width:135,overflow:'truncate'},axisLine:{lineStyle:{color:GRID}}},
    series:[{type:'bar',barMaxWidth:16,
      data:arr.map(function(r){return {value:r.l2,itemStyle:{color:r.l2>=0?COLORS.a:'#E02F44'}};}),
      label:{show:true,position:'right',color:MUTED,
        formatter:function(p){return (p.value>=0?'+':'')+p.value.toFixed(2);}}}]});
}

/* New-contact funnel, windowed: contacts whose FIRST message falls in range →
   met, talked again (≥2 sessions in range), recurring (≥3 sessions in range). */
function renderConnFunnel(){
  var agg=connContactAgg(), meta=connContactMeta(), r=connMonthsInRange();
  var met=0,talked=0,recurring=0;
  for(var cid in meta){ var m=meta[cid];
    if(!m.first_day) continue;
    var fm=m.first_day.slice(0,7);
    if(fm<r.sm||fm>r.em) continue;      // first message not in the window
    met++;
    var sess=(agg[cid]&&agg[cid].sessions)||0;
    if(sess>=2) talked++;
    if(sess>=3) recurring++;
  }
  if(!met){ noData('cxFunnel'); return; }
  ensureCanvas('cxFunnel');
  var cats=['Met (new in range)','Talked again (2+ sessions)','Recurring (3+ sessions)'];
  var vals=[met,talked,recurring];
  setChart('cxFunnel',{grid:{left:200,right:60,top:8,bottom:24},
    tooltip:{backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
      formatter:function(p){return esc(p.name)+': <b>'+fmtNum(p.value)+'</b>'
        +(met?' ('+fmtPct(p.value/met,0)+' of met)':'');}},
    xAxis:valAxis({}),
    yAxis:{type:'category',data:cats.slice().reverse(),
      axisLabel:{color:MUTED,width:190,overflow:'truncate'},axisLine:{lineStyle:{color:GRID}}},
    series:[{type:'bar',barMaxWidth:20,
      data:vals.slice().reverse().map(function(v,i){
        return {value:v,itemStyle:{color:COLORS.a,opacity:.45+.55*(v/(met||1))}};}),
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
/* Groups lane, windowed: recompute per-group owner/total/minutes from
   groups.monthly clipped to the active range. */
function renderConnGroups(){
  var g=state.connected.groups||{}, box=el('connGroupsBox');
  if(!box) return;
  var mon=g.monthly||{}, meta=g.meta||{}, r=connMonthsInRange();
  var agg={}, tOwner=0,tTotal=0,tMin=0;
  for(var m in mon){ if(m<r.sm||m>r.em) continue;
    for(var cid in mon[m]){ var c=mon[m][cid], acc=agg[cid]||(agg[cid]={owner:0,total:0,minutes:0});
      acc.owner+=c.owner; acc.total+=c.total; acc.minutes+=c.minutes;
      tOwner+=c.owner; tTotal+=c.total; tMin+=c.minutes; }
  }
  var ids=Object.keys(agg);
  if(!ids.length){ box.innerHTML='<div class="placeholder" style="height:60px">No group chats in range</div>'; return; }
  ids.sort(function(a,b){return agg[b].owner-agg[a].owner;});
  var h='<div class="vocab-line">'+fmtNum(ids.length)+' groups · you sent <b>'+fmtNum(tOwner)
    +'</b> of '+fmtNum(tTotal)+' messages · '+fmtDur(tMin)+' of group texting (in range)</div>'
    +'<table class="lt-table"><tr><th>Group</th><th>Members</th><th>Your msgs</th><th>Total</th><th>Time</th></tr>';
  ids.slice(0,10).forEach(function(cid){ var mt=meta[cid]||{name:cid}, x=agg[cid];
    h+='<tr><td>'+esc(connLabel({name:mt.name,platform:mt.platform}))+'</td><td class="num">'+fmtNum(mt.members)
      +'</td><td class="num">'+fmtNum(x.owner)+'</td><td class="num">'+fmtNum(x.total)
      +'</td><td class="num">'+fmtDur(x.minutes)+'</td></tr>';});
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
function pfBadge(p){ return p==='merged'?'⧉':(p==='telegram'?'✈️':'📸'); }
function pfLabel(p){ return p==='telegram'?'✈️ Telegram':(p==='instagram'?'📸 Instagram':p); }
function platformVisible(m){
  return !(selectedPlatforms&&selectedPlatforms.size)||selectedPlatforms.has(pfOf(m));
}
/* ---------- hidden chats (M1.4) ----------
   Persisted to Dashboard/data/hidden.json via the launcher's /hidden route when
   served over http, AND to localStorage as a file:// fallback. On load we read
   BOTH and union them. build_connected.py / build_insights.py read the same
   hidden.json and drop those chats on the next re-analyze. */
var HIDDEN={};                     // id -> 1
function isHidden(m){ return !!HIDDEN[m.id]; }
function hiddenManifest(){ return MANIFEST.filter(isHidden); }
function hiddenIds(){ var a=[]; for(var k in HIDDEN) a.push(k); return a; }
function loadHidden(cb){
  // localStorage fallback (works on file://)
  try{ if(typeof localStorage!=='undefined'){
    var ls=JSON.parse(localStorage.getItem('hiddenChats')||'[]');
    if(ls&&ls.length) ls.forEach(function(id){HIDDEN[id]=1;});
  }}catch(e){}
  // launcher route (http only) — union in whatever it has, then refresh UI
  try{ if(typeof XMLHttpRequest!=='undefined'){
    var x=new XMLHttpRequest(); x.open('GET','/hidden',true);
    x.onreadystatechange=function(){ if(x.readyState===4){
      if(x.status===200){ try{ var arr=JSON.parse(x.responseText);
        if(arr&&arr.length){ arr.forEach(function(id){HIDDEN[id]=1;}); if(cb) cb(); } }catch(e){} }
    }};
    x.send();
  }}catch(e){}
}
function persistHidden(){
  var arr=hiddenIds();
  try{ if(typeof localStorage!=='undefined') localStorage.setItem('hiddenChats',JSON.stringify(arr)); }catch(e){}
  try{ if(typeof XMLHttpRequest!=='undefined'){
    var x=new XMLHttpRequest(); x.open('POST','/hidden',true);
    x.setRequestHeader('Content-Type','application/json'); x.send(JSON.stringify(arr));
  }}catch(e){}
}
function hideChat(id){
  HIDDEN[id]=1; persistHidden();
  buildChatDropdown(el('chatSearch')?el('chatSearch').value:'');
  // If the hidden chat was showing, jump to the first still-visible chat.
  if(state.chatId===id && !state.isConnected && !state.isCompare){
    var vis=visibleManifest();
    if(vis.length) selectChat(vis[0].id);
  }
  // Keep compare selection consistent.
  if(state.compareIds&&state.compareIds.length){
    state.compareIds=state.compareIds.filter(function(x){return x!==id;});
    if(state.isCompare) renderCompare();
  }
}
function unhideChat(id){
  delete HIDDEN[id]; persistHidden();
  buildChatDropdown(el('chatSearch')?el('chatSearch').value:'');
}

/* ---------- cross-platform identity merges (M3.2) ----------
   Persisted to Dashboard/data/identities.json via the launcher's /identities
   route (http only) AND to localStorage as a file:// remember-only fallback.
   build_connected.py reads identities.json and merges the mapped contacts into
   ONE entity in the 'all' variant on the next re-analyze. Member keys are
   "<platform>:<chat_id>" — the same pair every connected row already carries. */
var IDENTITIES={identities:[]};
function loadIdentities(cb){
  try{ if(typeof localStorage!=='undefined'){
    var ls=JSON.parse(localStorage.getItem('identities')||'null');
    if(ls&&ls.identities) IDENTITIES=ls;
  }}catch(e){}
  try{ if(typeof XMLHttpRequest!=='undefined'){
    var x=new XMLHttpRequest(); x.open('GET','/identities',true);
    x.onreadystatechange=function(){ if(x.readyState===4&&x.status===200){
      try{ var o=JSON.parse(x.responseText);
        if(o&&o.identities){ IDENTITIES=o; if(cb) cb(); } }catch(e){} } };
    x.send();
  }}catch(e){}
}
function persistIdentities(){
  try{ if(typeof localStorage!=='undefined') localStorage.setItem('identities',JSON.stringify(IDENTITIES)); }catch(e){}
  // Writing to disk only works when the launcher serves the page (http). On
  // file:// the POST can't reach a server and builders can't read localStorage,
  // so no-op with a visible hint (same UX class as hide-chats).
  if(typeof location!=='undefined' && location.protocol==='file:'){
    connMergeStatus('Served from file:// — remembered in this browser only. Open via the launcher to save merges for analysis.',true);
    return false;
  }
  try{ if(typeof XMLHttpRequest!=='undefined'){
    var x=new XMLHttpRequest(); x.open('POST','/identities',true);
    x.setRequestHeader('Content-Type','application/json'); x.send(JSON.stringify(IDENTITIES));
  }}catch(e){}
  return true;
}
function connMergeStatus(msg,warn){
  var s=el('connMergeStatus'); if(!s) return;
  s.innerHTML='<span style="color:'+(warn?'#E4A11B':'var(--muted)')+'">'+esc(msg)+'</span>';
}
function renderConnMerge(){
  var panel=el('connMergePanel'); if(!panel) return;
  if(state.connectedVariant!=='all'){ panel.style.display='none'; return; }
  panel.style.display='';
  var body=el('connMergeBody'); if(!body) return;
  // Offer only UNMERGED contacts as checkboxes (already-merged ⧉ entities are
  // the result of an existing identity and are managed via unmerge below).
  var contacts=((state.connected&&state.connected.contacts)||[]).filter(function(x){return x.platform!=='merged';});
  var h='<div class="merge-pick" style="max-height:180px;overflow:auto;margin:8px 0;display:flex;flex-wrap:wrap;gap:6px">';
  contacts.forEach(function(x){
    var key=x.platform+':'+x.chat_id;
    h+='<label class="cmp-opt" style="cursor:pointer"><input type="checkbox" class="cmerge-cb" data-key="'+esc(key)+'"> '
      +pfBadge(x.platform)+' '+esc(x.name)+'</label>';
  });
  if(!contacts.length) h+='<span class="faint">No contacts available to merge.</span>';
  h+='</div><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
    +'<input id="connMergeName" placeholder="Display name for the merged person" '
    +'style="flex:1;min-width:180px;padding:6px 10px;background:var(--panel-2);border:1px solid var(--border);border-radius:6px;color:var(--text)">'
    +'<button class="chip" onclick="connMergeSelected()">⧉ Merge selected as…</button></div>';
  var ids=(IDENTITIES.identities||[]);
  if(ids.length){
    h+='<div style="margin-top:12px;margin-bottom:4px"><b>Existing merges</b> <span class="faint">(applied on next re-analyze)</span></div>';
    ids.forEach(function(it,i){
      h+='<div class="vocab-line" style="display:flex;justify-content:space-between;align-items:center">'
        +'<span>⧉ '+esc(it.name)+' <span class="faint">('+((it.members||[]).length)+' members)</span></span>'
        +'<span class="dd-unhide" style="cursor:pointer" onclick="connUnmerge('+i+')">↺ unmerge</span></div>';
    });
  }
  body.innerHTML=h;
}
function connMergeSelected(){
  var boxes=(typeof document!=='undefined'&&document.querySelectorAll)?document.querySelectorAll('.cmerge-cb'):[];
  var members=[]; for(var i=0;i<boxes.length;i++){ if(boxes[i].checked) members.push(boxes[i].getAttribute('data-key')); }
  var name=((el('connMergeName')&&el('connMergeName').value)||'').trim();
  if(members.length<2){ connMergeStatus('Select at least 2 contacts to merge.',true); return; }
  if(!name){ connMergeStatus('Enter a display name for the merged person.',true); return; }
  IDENTITIES.identities.push({name:name,members:members});
  var ok=persistIdentities();
  renderConnMerge();
  if(ok) connMergeStatus('Saved “'+name+'”. Re-run analysis to apply the merge.',false);
}
function connUnmerge(i){
  var it=IDENTITIES.identities[i]; if(!it) return;
  IDENTITIES.identities.splice(i,1);
  var ok=persistIdentities();
  renderConnMerge();
  if(ok) connMergeStatus('Removed “'+it.name+'”. Re-run analysis to apply.',false);
}
function visibleManifest(){ return MANIFEST.filter(function(m){return platformVisible(m)&&!isHidden(m);}); }
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
  // Pinned "⚖ Compare" entry — always on top, next to You — Connected.
  var cmp=document.createElement('div');
  cmp.className='dd-item pinned-compare'+(state.isCompare?' active':'');
  var cn=document.createElement('span'); cn.textContent='⚖ Compare contacts';
  var cd=document.createElement('span'); cd.className='n'; cd.textContent='2–5 dyads';
  cmp.appendChild(cn); cmp.appendChild(cd);
  cmp.onclick=function(){ selectCompare(); closeDD(); };
  list.appendChild(cmp);
  var shownRows=0;
  visibleManifest().forEach(function(m){
    if(q && m.name.toLowerCase().indexOf(q)<0) return;
    shownRows++;
    var item=document.createElement('div');
    item.className='dd-item'+(m.id===state.chatId?' active':'');
    var name=document.createElement('span');
    name.textContent=pfBadge(pfOf(m))+' '+m.name;
    var n=document.createElement('span'); n.className='n';
    n.textContent=(m.is_group?('👥 '+(m.members||'')+' · '):'')+fmtNum(m.messages)+' msgs';
    var hide=document.createElement('span'); hide.className='dd-hide';
    hide.textContent='✕'; hide.title='Hide this chat';
    hide.onclick=function(e){ if(e&&e.stopPropagation) e.stopPropagation(); hideChat(m.id); };
    item.appendChild(name); item.appendChild(n); item.appendChild(hide);
    item.onclick=function(){ selectChat(m.id); closeDD(); };
    list.appendChild(item);
  });
  if(!shownRows){ var e=document.createElement('div');
    e.className='dd-item faint'; e.textContent='No matches'; list.appendChild(e); }
  // Collapsed "Hidden (n)" section at the bottom, with per-chat unhide.
  var hid=hiddenManifest();
  if(hid.length){
    var head=document.createElement('div'); head.className='dd-hidden-head';
    head.textContent=(HIDDEN_OPEN?'▾ ':'▸ ')+'Hidden ('+hid.length+')';
    head.onclick=function(){ HIDDEN_OPEN=!HIDDEN_OPEN; buildChatDropdown(el('chatSearch')?el('chatSearch').value:''); };
    list.appendChild(head);
    if(HIDDEN_OPEN){
      var note=document.createElement('div'); note.className='dd-hidden-note';
      note.textContent='Excluded from Connected & Insights on next re-analyze.';
      list.appendChild(note);
      hid.forEach(function(m){
        var item=document.createElement('div'); item.className='dd-item faint';
        var name=document.createElement('span'); name.textContent=pfBadge(pfOf(m))+' '+m.name;
        var un=document.createElement('span'); un.className='dd-unhide';
        un.textContent='↺ unhide'; un.title='Unhide this chat';
        un.onclick=function(e){ if(e&&e.stopPropagation) e.stopPropagation(); unhideChat(m.id); };
        item.appendChild(name); item.appendChild(un);
        list.appendChild(item);
      });
    }
  }
}
var HIDDEN_OPEN=false;
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
  state.connected=c; state.isConnected=true; state.isCompare=false;
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
  state.isConnected=false; state.connected=null; state.isCompare=false;
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

/* ============================================================ *
 * COMPARE (⚖) mode — side-by-side of 2–5 dyads, every metric shown
 * BOTH directions (you → them vs them → you), computed from the
 * already-loaded per-chat daily tables over the CURRENT range.
 * ============================================================ */
var COMPARE_ID='__compare';
/* Deterministic colour per contact name (stable across renders). */
function cmpColor(name){ var h=0,s=String(name||'');
  for(var i=0;i<s.length;i++){ h=(h*31+s.charCodeAt(i))>>>0; }
  return GROUP_PAL[h%GROUP_PAL.length]; }

/* Metric specs. `f(o,c,days)` returns [ownerValue, contactValue] from the
   owner/contact range totals; `pct` renders the y-axis as a percentage. */
var CMP_METRICS=[
  {id:'cmpMsgs',title:'Messages / day',sub:'Average messages sent each direction per day (in range)',
   f:function(o,c,days){ return [days?o.msgs/days:0, days?c.msgs/days:0]; },
   fmt:function(v){return fmtNum(Math.round(v*10)/10);}},
  {id:'cmpInit',title:'Initiation share',sub:'Who opens conversations (share of initiations)',pct:true,
   f:function(o,c){ var t=o.initiations+c.initiations; return [t?o.initiations/t:0, t?c.initiations/t:0]; }},
  {id:'cmpLat',title:'Reply latency (min)',sub:'Mean in-session reply latency each direction',
   f:function(o,c){ return [o.resp_lat_n?o.resp_lat_sum_min/o.resp_lat_n:0,
                            c.resp_lat_n?c.resp_lat_sum_min/c.resp_lat_n:0]; },
   fmt:function(v){return fmtNum(Math.round(v*10)/10);}},
  {id:'cmpDepth',title:'Words per turn',sub:'Depth of each turn, each direction',
   f:function(o,c){ return [o.turns?o.words/o.turns:0, c.turns?c.words/c.turns:0]; },
   fmt:function(v){return fmtNum(Math.round(v));}},
  {id:'cmpQ',title:'Question rate',sub:'Questions per message, each direction',pct:true,
   f:function(o,c){ return [o.msgs?o.questions/o.msgs:0, c.msgs?c.questions/c.msgs:0]; }},
  {id:'cmpNight',title:'Night share',sub:'Share of messages 23:00–02:59, each direction',pct:true,
   f:function(o,c){ return [o.msgs?o.night_msgs/o.msgs:0, c.msgs?c.night_msgs/c.msgs:0]; }},
  {id:'cmpLaugh',title:'Laugh share',sub:'Messages with laughter per message, each direction',pct:true,
   f:function(o,c){ return [o.msgs?o.laughs/o.msgs:0, c.msgs?c.laughs/c.msgs:0]; }},
  {id:'cmpReact',title:'Left-on-react',sub:'Conversations ended with just a reaction, each direction',
   f:function(o,c){ return [o.reacted_leave, c.reacted_leave]; },
   fmt:function(v){return fmtNum(v);}}
];

/* Owner = the participant common to the selected dyads (most frequent). */
function compareOwnerName(chats){
  var counts={};
  chats.forEach(function(c){ (c.participants||[]).forEach(function(p){ counts[p]=(counts[p]||0)+1; }); });
  var best=null,bn=-1;
  for(var p in counts){ if(counts[p]>bn){ bn=counts[p]; best=p; } }
  return best;
}
/* Owner/contact totals for one chat over [sD,eD]. */
function cmpChatTotals(chat, ownerName, sD, eD){
  var contact=null;
  (chat.participants||[]).forEach(function(p){ if(p!==ownerName) contact=p; });
  if(contact==null) contact=(chat.participants&&chat.participants[1])||'them';
  var o=blank(), c=blank(), d=chat.daily||{};
  for(var ds in d){ var t=parseYMD(ds).getTime(); if(t<sD.getTime()||t>eD.getTime()) continue;
    var cell=d[ds]; if(cell[ownerName]) addInto(o,cell[ownerName]); if(cell[contact]) addInto(c,cell[contact]); }
  return {contact:contact, o:o, c:c};
}
function selectCompare(){
  txt(el('chatBtnLabel'),'⚖ Compare');
  disposeCharts();
  state.isCompare=true; state.isConnected=false; state.connected=null;
  state.chat=null; state.isGroup=false; state.chatId=COMPARE_ID;
  if(!state.compareIds || state.compareIds.length<2){
    var dyads=visibleManifest().filter(function(m){return !m.is_group;});
    state.compareIds=dyads.slice(0,Math.min(3,dyads.length)).map(function(m){return m.id;});
  }
  state.preset='all';
  renderCompareShell();
  loadCompareData(function(){ buildPresets(); buildMonthPicker(); syncControls(); renderCompare(); });
}
function loadCompareData(cb){
  var need=state.compareIds.filter(function(id){
    return !DATA[id] && MANIFEST.some(function(x){return x.id===id;}); });
  var remaining=need.length;
  function finish(){ setCompareRange(); cb&&cb(); }
  if(!remaining){ finish(); return; }
  need.forEach(function(id){
    var m=MANIFEST.filter(function(x){return x.id===id;})[0];
    var s=document.createElement('script'); s.src=m.file;
    s.onload=function(){ if(--remaining<=0) finish(); };
    s.onerror=function(){ if(--remaining<=0) finish(); };
    document.body.appendChild(s);
  });
}
function setCompareRange(){
  var lo=null,hi=null;
  state.compareIds.forEach(function(id){ var c=DATA[id]; if(!c||!c.daily) return;
    var ks=Object.keys(c.daily).sort(); if(!ks.length) return;
    var a=parseYMD(ks[0]), b=parseYMD(ks[ks.length-1]);
    if(!lo||a.getTime()<lo.getTime()) lo=a;
    if(!hi||b.getTime()>hi.getTime()) hi=b;
  });
  if(!lo){ var t=new Date(); lo=t; hi=t; }
  state.fullStart=lo; state.fullEnd=hi;
  if(!state.start||state.preset==='all'){ state.start=new Date(lo.getTime()); state.end=new Date(hi.getTime()); }
  state.start=minD(maxD(state.start,state.fullStart),state.fullEnd);
  state.end=maxD(minD(state.end,state.fullEnd),state.fullStart);
}
function toggleCompare(id){
  var i=state.compareIds.indexOf(id);
  if(i>=0){ state.compareIds.splice(i,1); }
  else { if(state.compareIds.length>=5) return; state.compareIds.push(id); }
  renderComparePicker();
  loadCompareData(function(){ syncControls(); renderCompare(); });
}
function renderCompareShell(){
  var chartsHtml='';
  CMP_METRICS.forEach(function(mt){
    chartsHtml+=card(mt.title, mt.sub, '<div class="chart" id="'+mt.id+'"></div>');
  });
  el('app').innerHTML=
    section('⚖ Compare contacts',
      '<div class="sub" style="margin-bottom:8px">Pick 2–5 direct chats. Every metric is shown BOTH '
      +'directions — <span class="dotA"></span> you → them and <span class="dotB"></span> them → you — '
      +'over the selected time range. Groups are excluded; newly selected chats load on demand.</div>'
      +'<div class="cmp-pick" id="cmpPick"></div>')
    + section('Side-by-side metrics','<div class="grid cols-2">'+chartsHtml+'</div>')
    + section('Findings per contact','<div id="cmpFindings"><div class="findings-empty">…</div></div>');
  renderComparePicker();
}
function renderComparePicker(){
  var box=el('cmpPick'); if(!box) return;
  box.innerHTML='';
  var dyads=visibleManifest().filter(function(m){return !m.is_group;});
  dyads.forEach(function(m){
    var on=state.compareIds.indexOf(m.id)>=0;
    var opt=document.createElement('span'); opt.className='cmp-opt'+(on?' on':'');
    var sw=document.createElement('span'); sw.className='swatch'; sw.style.background=cmpColor(m.name);
    var lab=document.createElement('span'); lab.textContent=(on?'☑ ':'☐ ')+pfBadge(pfOf(m))+' '+m.name;
    opt.appendChild(sw); opt.appendChild(lab);
    opt.onclick=function(){ toggleCompare(m.id); };
    box.appendChild(opt);
  });
}
function renderCompare(){
  if(!state.isCompare) return;
  renderComparePicker();
  var ids=state.compareIds.filter(function(id){return DATA[id]&&DATA[id].daily;});
  if(ids.length<2){
    CMP_METRICS.forEach(function(mt){ var n=el(mt.id);
      if(n){ var c=charts[mt.id]; if(c){try{c.clear();}catch(e){}} n.innerHTML='<div class="placeholder">Pick at least 2 contacts</div>'; charts[mt.id]=null; } });
    var fb0=el('cmpFindings'); if(fb0) fb0.innerHTML='<div class="findings-empty">Pick at least 2 contacts to compare.</div>';
    return;
  }
  var chatsSel=ids.map(function(id){return DATA[id];});
  var owner=compareOwnerName(chatsSel)||'You';
  var days=dayDiff(state.start,state.end)+1;
  var rows=ids.map(function(id){
    var t=cmpChatTotals(DATA[id],owner,state.start,state.end);
    var m=MANIFEST.filter(function(x){return x.id===id;})[0]||{};
    return {id:id,name:m.name||t.contact,badge:pfBadge(pfOf(m)),o:t.o,c:t.c}; });
  var cats=rows.map(function(r){return r.badge+' '+r.name;});
  CMP_METRICS.forEach(function(mt){
    ensureCanvas(mt.id);
    var oData=[], cData=[];
    rows.forEach(function(r){ var pair=mt.f(r.o,r.c,days);
      oData.push(+(pair[0]||0));
      cData.push({value:+(pair[1]||0), itemStyle:{color:cmpColor(r.name)}}); });
    var fmt = mt.fmt || (mt.pct?function(v){return fmtPct(v,1);}:function(v){return fmtNum(v);});
    setChart(mt.id,{grid:baseGrid(),legend:legend(['You →','→ You']),
      tooltip:{trigger:'axis',backgroundColor:PANEL,borderColor:GRID,textStyle:{color:TEXT},
        valueFormatter:function(v){return fmt(v);}},
      xAxis:{type:'category',data:cats,axisLine:{lineStyle:{color:GRID}},
        axisLabel:{color:MUTED,interval:0,rotate:cats.length>3?18:0}},
      yAxis: mt.pct?valAxis({axisLabel:{color:MUTED,formatter:function(v){return (v*100).toFixed(0)+'%';}}}):valAxis({}),
      series:[
        {name:'You →',type:'bar',data:oData,itemStyle:{color:COLORS.a},barMaxWidth:26,
          label:{show:cats.length<=4,position:'top',color:MUTED,fontSize:9,formatter:function(o){return fmt(o.value);}}},
        {name:'→ You',type:'bar',data:cData,barMaxWidth:26,
          label:{show:cats.length<=4,position:'top',color:MUTED,fontSize:9,formatter:function(o){return fmt(o.value);}}}
      ]});
  });
  renderCompareFindings(rows);
}
function renderCompareFindings(rows){
  var box=el('cmpFindings'); if(!box) return;
  ensureInsights(function(){
    var ins=window.INSIGHTS||{}, h='';
    rows.forEach(function(r){
      var list=ins[r.id]||[];
      h+='<div class="cmp-dyad-row"><div class="cmp-dyad-name">'
        +'<span class="swatch" style="display:inline-block;width:9px;height:9px;border-radius:2px;background:'
        +cmpColor(r.name)+'"></span>'+esc(r.badge+' '+r.name)+'</div>';
      if(list.length){ h+='<div class="cmp-chips">';
        list.forEach(function(f){ h+='<span class="cmp-chip" title="'+esc(f.sentence||'')+'">'+esc(f.id)+'</span>'; });
        h+='</div>'; }
      else { h+='<div class="findings-empty">No findings.</div>'; }
      h+='</div>';
    });
    box.innerHTML=h;
  });
}

/* ---------- init ---------- */
function init(){
  if(!MANIFEST.length){ el('app').innerHTML='<div class="placeholder" style="height:240px">No chats found. Run build_dashboard.py first.</div>'; return; }
  el('chatBtn').onclick=function(){ var p=el('chatPanel');
    if(p.classList.contains('open')) closeDD(); else { buildChatDropdown(el('chatSearch').value); openDD(); } };
  el('chatSearch').oninput=function(){ buildChatDropdown(this.value); };
  document.addEventListener('click',function(e){
    if(!el('chatDD').contains(e.target)) closeDD(); });
  el('gran').onchange=function(){ state.gran=this.value; if(state.chat||state.isConnected||state.isCompare) rerender(); };
  el('monthSel').onchange=function(){ if(state.chat||state.isConnected||state.isCompare) applyMonth(this.value); };
  el('applyRange').onclick=applyCustomRange;
  el('dFrom').onchange=function(){}; el('dTo').onchange=function(){};
  // Load identity-merge map (localStorage + launcher /identities); refresh the
  // merge panel if the connected 'all' view is already showing.
  loadIdentities(function(){ if(state.isConnected) safe(renderConnMerge,'cmerge'); });
  // Load hidden-chat state (localStorage + launcher /hidden) before first paint.
  loadHidden(function(){ buildChatDropdown(el('chatSearch')?el('chatSearch').value:'');
    // If the currently-shown chat just got hidden by a synced list, jump away.
    if(state.chatId&&HIDDEN[state.chatId]&&!state.isConnected&&!state.isCompare){
      var v=visibleManifest(); if(v.length) selectChat(v[0].id); } });
  buildPlatformFilter();
  buildChatDropdown('');
  var firstVis=visibleManifest();
  selectChat((firstVis[0]||MANIFEST[0]).id);
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init);
else init();
</script>
</body>
</html>
'''
