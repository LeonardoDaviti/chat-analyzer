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
.kpi .split{font-size:13px;margin-top:4px;font-variant-numeric:tabular-nums}
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
var TEXT='#D8D9DA', MUTED='#8e9297', GRID='#2c3137', PANEL='#22262B';
var HEAT = ['#12233a','#173a5e','#1c5cab','#2a78d6','#5598e7','#86b6ef','#cde2fb'];
var WEEKDAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
var HOURS=[]; for(var h=0;h<24;h++) HOURS.push((h<10?'0':'')+h);

var MANIFEST = window.DASHBOARD_MANIFEST || [];
var DATA = window.DASHBOARD_DATA = window.DASHBOARD_DATA || {};

var state = {
  chatId:null, chat:null,
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
function blank(){return {msgs:0,words:0,chars:0,emoji:0,questions:0,night_msgs:0,
  reactions_given:0,reactions_received:0,media:0,resp_lat_sum_min:0,resp_lat_n:0,initiations:0};}
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
        '<div class="chart tall" id="cVolume"></div>'))
  + section('Balance',
      '<div class="grid cols-2">'
      + card('Initiation share','Who opens conversations (per bucket)','<div class="chart" id="cInit"></div>')
      + card('Question rate','Interrogatives per 100 messages','<div class="chart" id="cQ"></div>')
      + '</div>')
  + section('Responsiveness',
      card('Median in-session reply latency','Minutes · display capped near p95','<div class="chart" id="cLat"></div>'))
  + section('Affect',
      '<div class="grid cols-2">'
      + card('Reactions given','Acknowledgement channel','<div class="chart" id="cReact"></div>')
      + card('Emoji per 100 messages','Expressiveness channel','<div class="chart" id="cEmoji"></div>')
      + '</div>')
  + section('Rhythm',
      '<div class="grid cols-2">'
      + card('Activity clock · '+esc(A),'Messages by weekday × hour','<div class="chart" id="cHeatA"></div>')
      + card('Activity clock · '+esc(B),'Messages by weekday × hour','<div class="chart" id="cHeatB"></div>')
      + '</div>'
      + card('Night share','Share of messages during 23:00–02:59','<div class="chart short" id="cNight"></div>'))
  + section('All-time lifetime metrics',
      '<div class="grid cols-2" id="ltCards"></div>');
}
function section(title,inner){return '<div class="section"><div class="section-title">'+esc(title)+'</div>'+inner+'</div>';}
function card(title,sub,inner){return '<div class="card"><h3>'+esc(title)+'</h3>'
  +(sub?'<div class="sub">'+esc(sub)+'</div>':'')+inner+'</div>';}
function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}

/* ============================================================ *
 * RENDER: everything from active range
 * ============================================================ */
function renderAll(){
  if(!state.chat){return;}
  var b=buildBuckets();
  var rt=rangeTotals(state.start,state.end);
  var hasData=b.starts.length>0;
  renderKPIs(rt,hasData);
  renderVolume(b);
  renderBalance(b);
  renderResponsiveness(b);
  renderAffect(b);
  renderRhythm(rt,b);
  // Lifetime cards are range-independent; render once per chat.
}

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
function renderKPIs(rt,hasData){
  var A=state.users[0],B=state.users[1];
  var tot=rt.tot, days=dayDiff(state.start,state.end)+1;
  var totalMsgs=tot.A.msgs+tot.B.msgs;
  var perDay=days>0?totalMsgs/days:0;
  // previous equal-length window
  var prevEnd=addDays(state.start,-1), prevStart=addDays(state.start,-days);
  var prev=rangeTotals(prevStart,prevEnd);
  var prevTotal=prev.tot.A.msgs+prev.tot.B.msgs;
  var prevPerDay=days>0?prevTotal/days:0;
  var delta=prevPerDay>0?(perDay-prevPerDay)/prevPerDay:null;

  var latA=tot.A.resp_lat_n?tot.A.resp_lat_sum_min/tot.A.resp_lat_n:null;
  var latB=tot.B.resp_lat_n?tot.B.resp_lat_sum_min/tot.B.resp_lat_n:null;
  var initTot=tot.A.initiations+tot.B.initiations;
  var initA=initTot?tot.A.initiations/initTot:null;
  var nightTot=tot.A.night_msgs+tot.B.night_msgs;
  var nightShare=totalMsgs?nightTot/totalMsgs:null;

  var tiles=[];
  tiles.push(kpi('Messages', fmtNum(totalMsgs), null,
     '<span class="split"><span class="dotA"></span>'+fmtNum(tot.A.msgs)
     +' &nbsp;<span class="dotB"></span>'+fmtNum(tot.B.msgs)+'</span>'));
  tiles.push(kpi('Messages / day', fmtNum(perDay),
     delta==null?null:{v:delta}, '<span class="split faint">vs prev '+days+'d</span>'));
  tiles.push(kpi('Reply latency', fmtDur(latA==null&&latB==null?null:0), null,
     '<span class="split"><span class="dotA"></span>'+fmtDur(latA)
     +' &nbsp;<span class="dotB"></span>'+fmtDur(latB)+'</span>', true));
  tiles.push(kpi('Initiation', initA==null?'—':fmtPct(initA), null,
     '<span class="split"><span class="dotA"></span>'+fmtPct(initA)
     +' &nbsp;<span class="dotB"></span>'+(initA==null?'—':fmtPct(1-initA))+'</span>'));
  tiles.push(kpi('Reactions given', fmtNum(tot.A.reactions_given+tot.B.reactions_given), null,
     '<span class="split"><span class="dotA"></span>'+fmtNum(tot.A.reactions_given)
     +' &nbsp;<span class="dotB"></span>'+fmtNum(tot.B.reactions_given)+'</span>'));
  tiles.push(kpi('Night share', nightShare==null?'—':fmtPct(nightShare), null,
     '<span class="split faint">23:00–02:59</span>'));

  el('kpiRow').innerHTML = hasData ? tiles.join('')
     : '<div class="kpi"><div class="placeholder">No data in range</div></div>';
}
function kpi(label,value,delta,extra,hideValue){
  var d='';
  if(delta&&delta.v!=null){
    var up=delta.v>=0; d='<span class="delta '+(up?'up':'down')+'">'
      +(up?'▲ ':'▼ ')+fmtPct(Math.abs(delta.v),0)+'</span>';
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
  renderKPIs(rt,has); renderBalance(b); renderResponsiveness(b);
  renderAffect(b); renderRhythm(rt,b);
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
    var mh=(lt.circadian&&lt.circadian.overlap_coefficient!=null)?
      ('<tr><td>Circadian overlap</td><td class="num">'+pct(lt.circadian.overlap_coefficient)+'</td></tr>'):'';
    var half=(lt.half_life&&lt.half_life.median_half_life_minutes!=null)?
      ('<tr><td>Median half-life</td><td class="num">'+fmtDur(lt.half_life.median_half_life_minutes)+'</td></tr>'):'';
    return h+mh+half+'</tbody></table>';
  }
  el('ltCards').innerHTML =
    ltCard(A,'a',tableFor(A)) + ltCard(B,'b',tableFor(B));
}
function ltCard(user,cls,inner){
  return '<div class="card"><h3><span class="dot'+(cls==='a'?'A':'B')+'"></span> '+esc(user)
    +'</h3><div class="sub">All-time</div>'+inner+'</div>';
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
function applyPreset(k){
  state.preset=k;
  if(k==='all'||k==='reset'){ state.start=new Date(state.fullStart.getTime()); state.end=new Date(state.fullEnd.getTime()); if(k==='reset') state.preset='all'; }
  else if(k[0]==='y'){ var y=+k.slice(1);
    state.start=maxD(new Date(Date.UTC(y,0,1)),state.fullStart);
    state.end=minD(new Date(Date.UTC(y,11,31)),state.fullEnd); }
  else { var n=+k; state.end=new Date(state.fullEnd.getTime());
    state.start=maxD(addDays(state.fullEnd,-(n-1)),state.fullStart); }
  syncControls(); renderAll();
}
function maxD(a,b){return a.getTime()>b.getTime()?a:b;}
function minD(a,b){return a.getTime()<b.getTime()?a:b;}
function syncControls(){
  el('dFrom').value=ymd(state.start); el('dTo').value=ymd(state.end);
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
  state.start=maxD(fs,state.fullStart); state.end=minD(ts,state.fullEnd);
  state.preset=null; syncControls(); renderAll();
}

/* ---------- chat selector ---------- */
function buildChatDropdown(filter){
  var list=el('chatList'); list.innerHTML='';
  var q=(filter||'').toLowerCase();
  MANIFEST.forEach(function(m){
    if(q && m.name.toLowerCase().indexOf(q)<0) return;
    var item=document.createElement('div');
    item.className='dd-item'+(m.id===state.chatId?' active':'');
    var name=document.createElement('span'); name.textContent=m.name;
    var n=document.createElement('span'); n.className='n'; n.textContent=fmtNum(m.messages)+' msgs';
    item.appendChild(name); item.appendChild(n);
    item.onclick=function(){ selectChat(m.id); closeDD(); };
    list.appendChild(item);
  });
  if(!list.children.length){ var e=document.createElement('div');
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
function onChatLoaded(id){
  var chat=DATA[id];
  if(!chat){ return; }
  disposeCharts();
  state.chat=chat;
  state.users=(chat.participants&&chat.participants.length>=2)?
    [chat.participants[0],chat.participants[1]]:[chat.participants&&chat.participants[0]||'A','B'];
  var dates=Object.keys(chat.daily).sort();
  if(dates.length){ state.fullStart=parseYMD(dates[0]); state.fullEnd=parseYMD(dates[dates.length-1]); }
  else { var t=new Date(); state.fullStart=t; state.fullEnd=t; }
  state.start=new Date(state.fullStart.getTime()); state.end=new Date(state.fullEnd.getTime());
  state.preset='all';
  renderSkeleton();
  buildPresets(); syncControls();
  if(!dates.length){ el('app').querySelectorAll('.chart').forEach(function(n){n.innerHTML='<div class="placeholder">No data in this chat</div>';});
    el('kpiRow').innerHTML='<div class="kpi"><div class="placeholder">No data</div></div>';
    el('ltCards').innerHTML=''; return; }
  renderAll();
  renderLifetime();
}

/* ---------- init ---------- */
function init(){
  if(!MANIFEST.length){ el('app').innerHTML='<div class="placeholder" style="height:240px">No chats found. Run build_dashboard.py first.</div>'; return; }
  el('chatBtn').onclick=function(){ var p=el('chatPanel');
    if(p.classList.contains('open')) closeDD(); else { buildChatDropdown(el('chatSearch').value); openDD(); } };
  el('chatSearch').oninput=function(){ buildChatDropdown(this.value); };
  document.addEventListener('click',function(e){
    if(!el('chatDD').contains(e.target)) closeDD(); });
  el('gran').onchange=function(){ state.gran=this.value; if(state.chat) renderAll(); };
  el('applyRange').onclick=applyCustomRange;
  el('dFrom').onchange=function(){}; el('dTo').onchange=function(){};
  buildChatDropdown('');
  selectChat(MANIFEST[0].id);
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init);
else init();
</script>
</body>
</html>
'''
