"""The embedded editor UI: a single self-contained HTML/CSS/JS page served
at `GET /`. Copied verbatim from the original script (down to escaping
quirks in the inline JS onclick handlers) - this project only changed
*where* this constant lives, not its content. See server.py for the routes
it talks to (/upload-temp, /process, /progress/<id>, /push, /projects...).
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Clip Editor</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, sans-serif;
  background: #0d0d0d; color: #ccc;
  height: 100vh; display: flex; flex-direction: column; overflow: hidden;
}
button { font-family: inherit; cursor: pointer; }
input, select { font-family: inherit; }

/* ── Shared components ───────────────────────────────────────────────────── */
.ibtn {
  display:inline-flex; align-items:center; gap:5px; padding:5px 10px;
  border-radius:5px; border:1px solid #1e1e1e; background:#141414;
  color:#555; font-size:.75rem; cursor:pointer; white-space:nowrap;
  transition:color .12s,border-color .12s;
}
.ibtn:hover { color:#ccc; border-color:#333; }
.ibtn.active { background:#0d2040; border-color:#2a5090; color:#7eb8ff; }
.ibtn.ok { background:#14452a; color:#6effc0; border-color:#1e6040; }
.bar-bg { height:4px; background:#1a1a1a; border-radius:2px; overflow:hidden; }
.bar-fg { height:100%; background:#4a7fcb; width:0%; transition:width .08s; }

/* ── Top bar ─────────────────────────────────────────────────────────────── */
#top-bar {
  display:flex; align-items:center; gap:8px; padding:7px 12px;
  border-bottom:1px solid #1e1e1e; background:#0f0f0f; flex-shrink:0;
}
#top-title { font-size:.65rem; letter-spacing:.14em; color:#2a2a2a; text-transform:uppercase; }
#proj-name-wrap { flex:1; display:flex; align-items:center; position:relative; max-width:340px; }
#proj-name {
  width:100%; background:transparent; border:1px solid transparent;
  border-radius:4px; color:#555; font-size:.82rem; padding:4px 22px 4px 8px;
  transition:border-color .15s,color .15s;
}
#proj-name:hover { border-color:#222; color:#aaa; }
#proj-name:focus { outline:none; border-color:#4a7fcb; color:#ccc; }
#proj-dirty {
  position:absolute; right:7px; top:50%; transform:translateY(-50%);
  width:6px; height:6px; border-radius:50%; background:#4a7fcb; opacity:0; transition:opacity .2s; pointer-events:none;
}
#proj-dirty.visible { opacity:1; }
.ibtn:disabled { opacity:.28; cursor:not-allowed; pointer-events:none; }
@keyframes shake {
  0%,100%{transform:translateX(0)} 20%{transform:translateX(-5px)}
  40%{transform:translateX(5px)} 60%{transform:translateX(-4px)} 80%{transform:translateX(3px)}
}
.shake { animation:shake .3s ease; border-color:#a04040!important; }

/* ── Workspace ───────────────────────────────────────────────────────────── */
#workspace { display:flex; flex:1; min-height:0; overflow:hidden; }

/* Media bin */
#bin {
  width:210px; flex-shrink:0; display:flex; flex-direction:column;
  background:#0f0f0f; border-right:1px solid #1e1e1e; overflow:hidden;
}
#bin-hdr {
  display:flex; align-items:center; justify-content:space-between;
  padding:7px 10px; border-bottom:1px solid #1e1e1e; flex-shrink:0;
}
#bin-title { font-size:.65rem; letter-spacing:.1em; text-transform:uppercase; color:#333; }
#bin-add-btn { background:none; border:none; color:#444; font-size:1.3rem; cursor:pointer; padding:0 2px; line-height:1; }
#bin-add-btn:hover { color:#7eb8ff; }
#bin-list { flex:1; overflow-y:auto; padding:4px; }
#bin-list::-webkit-scrollbar { width:4px; }
#bin-list::-webkit-scrollbar-thumb { background:#222; border-radius:2px; }
.bin-item {
  display:flex; align-items:center; gap:6px; padding:7px 8px;
  border-radius:5px; cursor:pointer; border:1px solid transparent; transition:background .1s;
}
.bin-item:hover { background:#161616; border-color:#1e1e1e; }
.bin-item-icon { font-size:1rem; opacity:.45; flex-shrink:0; }
.bin-item-info { flex:1; min-width:0; }
.bin-item-name { font-size:.75rem; color:#888; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.bin-item-meta { font-size:.65rem; color:#3a3a3a; }
#bin-hint { padding:24px 12px; text-align:center; color:#222; font-size:.78rem; line-height:1.7; }
#bin-input { display:none; }

/* Preview */
#preview-area {
  flex:1; min-width:0; display:flex; flex-direction:column;
  align-items:center; justify-content:center; padding:12px 16px; gap:8px; overflow:hidden;
  position:relative;
}
#preview-placeholder {
  position:absolute; display:flex; flex-direction:column; align-items:center; gap:8px;
  color:#2a2a2a; pointer-events:none;
}
#preview-placeholder .ph-icon { font-size:2.2rem; }
#preview-placeholder .ph-lbl { font-size:.82rem; }
#preview-placeholder .ph-sub { font-size:.7rem; color:#1a1a1a; }
#preview-vid {
  max-width:100%; max-height:calc(100% - 46px); object-fit:contain;
  border-radius:6px; background:#000; display:none;
}
#preview-vid.visible { display:block; }
#transport { display:flex; align-items:center; gap:7px; }
.tp-btn {
  background:#141414; border:1px solid #1e1e1e; border-radius:5px;
  color:#555; padding:5px 10px; font-size:.9rem; cursor:pointer; transition:color .1s;
}
.tp-btn:hover { color:#ccc; border-color:#333; }
#tc-disp { font-size:.78rem; color:#444; font-family:monospace; min-width:126px; text-align:center; }

/* ── Timeline section ────────────────────────────────────────────────────── */
#tl-section { display:flex; flex-direction:column; flex-shrink:0; border-top:1px solid #1e1e1e; }

/* Toolbar */
#tl-toolbar {
  display:flex; align-items:center; gap:6px; padding:5px 10px;
  border-bottom:1px solid #1e1e1e; flex-shrink:0; background:#0f0f0f;
}
.tb-sep { width:1px; height:14px; background:#1e1e1e; margin:0 2px; }
#zoom-lbl { font-size:.7rem; color:#3a3a3a; font-family:monospace; min-width:50px; text-align:center; }

/* Timeline canvas wrapper */
#tl-wrap { overflow-x:auto; overflow-y:hidden; flex-shrink:0; }
#tl-wrap::-webkit-scrollbar { height:5px; }
#tl-wrap::-webkit-scrollbar-thumb { background:#1e1e1e; border-radius:3px; }
#tl-canvas { display:block; cursor:default; }

/* ── Bottom bar ──────────────────────────────────────────────────────────── */
#bot-bar {
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:7px 12px; border-top:1px solid #1e1e1e; background:#0f0f0f; flex-shrink:0;
}
.sg { display:flex; align-items:center; gap:7px; }
.s-lbl { font-size:.72rem; color:#444; white-space:nowrap; }
input[type=range] { accent-color:#4a7fcb; cursor:pointer; width:80px; }
.s-val { font-size:.72rem; color:#888; min-width:30px; }
.s-note { font-size:.68rem; color:#2a2a2a; }
.s-inp { background:#0d0d0d; border:1px solid #222; border-radius:4px; color:#aaa; font-size:.78rem; padding:3px 6px; width:58px; }
.s-inp:focus { outline:none; border-color:#4a7fcb; }
select.s-sel { background:#0d0d0d; border:1px solid #222; border-radius:4px; color:#aaa; font-size:.78rem; padding:3px 6px; cursor:pointer; }
.mute-btn { padding:3px 9px; border-radius:4px; border:1px solid #1e1e1e; background:#141414; color:#555; font-size:.72rem; cursor:pointer; }
.mute-btn.on { background:#2a1010; color:#f07070; border-color:#4a1515; }
.bot-sep { width:1px; height:16px; background:#1e1e1e; }
.btn-exp { padding:7px 16px; background:#1e3a5f; color:#7eb8ff; border:none; border-radius:6px; font-size:.82rem; font-weight:500; cursor:pointer; }
.btn-exp:hover { background:#254d80; }
.btn-exp-up { padding:7px 16px; background:#1c3a22; color:#7effa0; border:none; border-radius:6px; font-size:.82rem; font-weight:500; cursor:pointer; }
.btn-exp-up:hover { background:#255030; }

/* ── Overlays ────────────────────────────────────────────────────────────── */
.overlay {
  display:none; position:fixed; inset:0; background:rgba(0,0,0,.75);
  align-items:center; justify-content:center; z-index:100;
}
.overlay.on { display:flex; }
.ov-card {
  background:#111; border:1px solid #1e1e1e; border-radius:10px;
  padding:24px 32px; min-width:260px; display:flex; flex-direction:column; gap:10px; align-items:center;
}
.ov-lbl { font-size:.82rem; color:#888; }

/* Result dialog */
#result-dlg {
  display:none; position:fixed; inset:0; background:rgba(0,0,0,.8);
  align-items:center; justify-content:center; z-index:200;
}
#result-dlg.on { display:flex; }
.result-card {
  background:#111; border:1px solid #1e1e1e; border-radius:12px;
  padding:20px; width:min(620px,92vw); display:flex; flex-direction:column; gap:12px;
}
#result-vid { width:100%; border-radius:6px; background:#000; max-height:340px; }
#result-info { font-size:.75rem; color:#555; }
#result-url { background:#0d0d0d; border:1px solid #1a1a1a; border-radius:6px; padding:10px 12px; font-size:.78rem; color:#7eb8ff; word-break:break-all; font-family:monospace; line-height:1.5; display:none; }
.res-btns { display:flex; gap:8px; flex-wrap:wrap; }
.btn-copy { background:#1a3558; color:#7eb8ff; border:none; border-radius:6px; padding:8px 14px; font-size:.8rem; cursor:pointer; }
.btn-copy:hover { background:#234a7a; }
.btn-copy.ok { background:#14452a; color:#6effc0; }
#btn-push-only { background:#1c3a22; color:#7effa0; border:none; border-radius:6px; padding:8px 14px; font-size:.8rem; cursor:pointer; display:none; }
.btn-dismiss { background:#161616; color:#555; border:none; border-radius:6px; padding:8px 14px; font-size:.8rem; cursor:pointer; }

/* Projects dropdown */
#proj-panel {
  display:none; position:fixed; top:40px; right:12px; z-index:50;
  background:#111; border:1px solid #1e1e1e; border-radius:8px;
  width:300px; max-height:380px; overflow-y:auto;
  padding:6px; flex-direction:column; gap:4px;
  box-shadow:0 8px 32px rgba(0,0,0,.6);
}
#proj-panel.on { display:flex; }
.proj-item { display:flex; align-items:center; gap:8px; padding:8px 10px; background:#141414; border:1px solid #1a1a1a; border-radius:5px; cursor:pointer; transition:border-color .12s; }
.proj-item:hover { border-color:#2a4a7f; }
.proj-iname { flex:1; font-size:.8rem; color:#888; }
.proj-imeta { font-size:.68rem; color:#333; white-space:nowrap; }
.proj-idel { background:none; border:none; color:#333; font-size:1rem; cursor:pointer; padding:1px 5px; }
.proj-idel:hover { color:#c55; }
#proj-empty { font-size:.75rem; color:#333; text-align:center; padding:16px; }

/* Error bar */
#err-bar { display:none; padding:7px 14px; background:#1f0a0a; border-top:1px solid #4a1010; color:#f08080; font-size:.78rem; flex-shrink:0; }
#err-bar.on { display:block; }

/* Global drop overlay */
#drop-over {
  display:none; position:fixed; inset:0; z-index:300;
  background:rgba(10,20,40,.7); border:3px dashed #4a7fcb; border-radius:12px;
  align-items:center; justify-content:center; color:#7eb8ff; font-size:1.1rem; pointer-events:none;
}
#drop-over.on { display:flex; }
</style>
</head>
<body>

<!-- Top bar -->
<div id="top-bar">
  <span id="top-title">Clip Editor</span>
  <div id="proj-name-wrap">
    <input type="text" id="proj-name" placeholder="Untitled project" maxlength="80">
    <span id="proj-dirty"></span>
  </div>
  <button class="ibtn" id="btn-undo" onclick="undo()" title="Undo (Ctrl+Z)" disabled>&#8630;</button>
  <button class="ibtn" id="btn-redo" onclick="redo()" title="Redo (Ctrl+Y)" disabled>&#8631;</button>
  <button class="ibtn" id="btn-save" onclick="saveProject()">
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.2"/><rect x="3.5" y="1" width="4" height="3.5" rx=".5" fill="currentColor" opacity=".7"/><rect x="2.5" y="7" width="7" height="3.5" rx=".5" fill="currentColor" opacity=".5"/></svg>
    Save
  </button>
  <button class="ibtn" id="btn-projects" onclick="toggleProjPanel()">&#9776; Projects</button>
</div>
<div id="proj-panel"></div>

<!-- Workspace -->
<div id="workspace">
  <!-- Media bin -->
  <div id="bin">
    <div id="bin-hdr">
      <span id="bin-title">Media</span>
      <button id="bin-add-btn" title="Add files" onclick="document.getElementById('bin-input').click()">+</button>
      <input type="file" id="bin-input" accept="video/*" multiple onchange="handleFiles(this.files)">
    </div>
    <div id="bin-list"><div id="bin-hint">Drop videos anywhere<br>or click + to add<br><span style="color:#1a1a1a">Double-click to add to timeline</span></div></div>
  </div>
  <!-- Preview -->
  <div id="preview-area">
    <div id="preview-placeholder">
      <div class="ph-icon">&#127916;</div>
      <div class="ph-lbl">Add videos to get started</div>
      <div class="ph-sub">Double-click a file in the bin to add it to the timeline</div>
    </div>
    <video id="preview-vid"></video>
    <div id="transport">
      <button class="tp-btn" onclick="skipStart()" title="Go to start">&#9646;&#9664;</button>
      <button class="tp-btn" id="play-btn" onclick="togglePlay()" title="Play / Pause [Space]">&#9654;</button>
      <button class="tp-btn" onclick="skipEnd()" title="Go to end">&#9654;&#9646;</button>
      <span id="tc-disp">0:00.0 / 0:00.0</span>
    </div>
  </div>
</div>

<!-- Timeline -->
<div id="tl-section">
  <div id="tl-toolbar">
    <button class="ibtn active" id="tool-select" onclick="setTool('select')" title="Select &amp; Trim [V]">
      <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2 1l8 5-3.5 1L5 11z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
      Select
    </button>
    <button class="ibtn" id="tool-razor" onclick="setTool('razor')" title="Razor: split clip [R]">
      <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><line x1="4" y1="1" x2="8" y2="11" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><line x1="1" y1="6" x2="11" y2="6" stroke="currentColor" stroke-width="1" stroke-dasharray="2,2" opacity=".5"/></svg>
      Razor
    </button>
    <button class="ibtn" id="tool-delete" onclick="setTool('delete')" title="Delete clip [E]">
      <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      Delete
    </button>
    <div class="tb-sep"></div>
    <button class="ibtn" onclick="zoomTl(-1)">&#8722;</button>
    <span id="zoom-lbl">60px/s</span>
    <button class="ibtn" onclick="zoomTl(1)">+</button>
    <button class="ibtn" onclick="fitTl()">Fit</button>
    <div class="tb-sep"></div>
    <button class="ibtn" id="btn-add-more" style="display:none" onclick="document.getElementById('bin-input').click()">+ Add clips</button>
  </div>
  <div id="tl-wrap"><canvas id="tl-canvas" height="90"></canvas></div>
</div>

<!-- Bottom bar -->
<div id="bot-bar">
  <div class="sg">
    <span class="s-lbl">Quality</span>
    <input type="range" id="q-sl" min="1" max="100" value="70" oninput="onQ()">
    <span class="s-val" id="q-val">70%</span>
    <span class="s-note" id="crf-n">CRF 24</span>
  </div>
  <div class="bot-sep"></div>
  <div class="sg">
    <span class="s-lbl">Size</span>
    <input type="number" class="s-inp" id="tmb" placeholder="MB" min="1" step="1">
  </div>
  <div class="bot-sep"></div>
  <div class="sg">
    <span class="s-lbl">Volume</span>
    <input type="range" id="v-sl" min="0" max="200" value="100" oninput="onV()">
    <span class="s-val" id="v-val">100%</span>
    <button class="mute-btn" id="mute-btn" onclick="toggleMute()">Mute</button>
  </div>
  <div class="bot-sep"></div>
  <div class="sg">
    <span class="s-lbl">Preset</span>
    <select class="s-sel" id="preset-sel">
      <option value="veryfast">veryfast</option>
      <option value="fast">fast</option>
      <option value="medium">medium</option>
      <option value="slow">slow</option>
    </select>
  </div>
  <div class="bot-sep"></div>
  <button class="btn-exp" onclick="doProcess(false)">&#9654; Export</button>
  <button class="btn-exp-up" onclick="doProcess(true)">&#9654;&#8593; Export &amp; Upload</button>
</div>

<!-- Upload overlay -->
<div id="up-overlay" class="overlay">
  <div class="ov-card">
    <div class="ov-lbl" id="up-lbl">Uploading...</div>
    <div class="bar-bg" style="width:220px"><div class="bar-fg" id="up-fg"></div></div>
  </div>
</div>

<!-- Process overlay -->
<div id="proc-overlay" class="overlay">
  <div class="ov-card">
    <div class="ov-lbl" id="proc-lbl">Processing...</div>
    <div class="bar-bg" style="width:220px"><div class="bar-fg" id="proc-fg"></div></div>
  </div>
</div>

<!-- Result dialog -->
<div id="result-dlg">
  <div class="result-card">
    <video id="result-vid" controls></video>
    <div id="result-info"></div>
    <div id="result-url"></div>
    <div class="res-btns">
      <button class="btn-copy" id="copy-btn" style="display:none" onclick="doCopy()">Copy link</button>
      <button id="btn-push-only" onclick="doPush()">&#8593; Upload to server</button>
      <button class="btn-dismiss" onclick="document.getElementById('result-dlg').classList.remove('on')">Done</button>
    </div>
  </div>
</div>

<!-- Drop overlay -->
<div id="drop-over">Drop videos to add to bin</div>

<!-- Error bar -->
<div id="err-bar"></div>

<script>
// ── State ─────────────────────────────────────────────────────────────────────
let mediaFiles = [];  // [{fileId, name, dur, hasAudio, width, height, size}]
let tClips = [];      // [{id, fileId, name, dur, hasAudio, inPoint, outPoint}]
let tCtr = 0;
let pxPerSec = 60;
let playheadT = 0;
let activeTool = 'select';
let dragState = null;
let previewClipIdx = -1;
let isPlaying = false;
let processedId = null, resultUrl = null;
let isMuted = false;
let currentProjectId = null;
let _dirty = false;
let _projOpen = false;
let _autoSaveTimer = null;
let _undoStack = [];
let _redoStack = [];

const HANDLE = 8;
const RULER_H = 22;
const TRACK_Y = RULER_H + 4;
const TRACK_H = 52;
const CLIP_COLORS = ['#1a3d66','#3d1a66','#66401a','#1a663d','#56601a','#1a5566','#661a3d','#1a4055'];

const vid = document.getElementById('preview-vid');
const tlCanvas = document.getElementById('tl-canvas');
const tlCtx = tlCanvas.getContext('2d');
const tlWrap = document.getElementById('tl-wrap');

// ── Helpers ───────────────────────────────────────────────────────────────────
function totalDur() { return tClips.reduce((s,c) => s+(c.outPoint-c.inPoint), 0); }
function clipStart(i) { let t=0; for(let j=0;j<i;j++) t+=tClips[j].outPoint-tClips[j].inPoint; return t; }
function timeToClip(t) {
  let off=0;
  for(let i=0;i<tClips.length;i++){
    const dur=tClips[i].outPoint-tClips[i].inPoint;
    if(t<off+dur||i===tClips.length-1) return {idx:i, srcT:tClips[i].inPoint+(t-off)};
    off+=dur;
  }
  return {idx:-1, srcT:0};
}
function clipColor(i) { return CLIP_COLORS[i%CLIP_COLORS.length]; }
function fmtSecs(s) {
  s=Math.max(0,s||0); let m=Math.floor(s/60), ss=(s%60).toFixed(1);
  if(ss==='60.0'){m++;ss='00.0';} return m+':'+ss.padStart(4,'0');
}
function fmtBytes(b) { if(!b)return''; return b<1048576?(b/1024).toFixed(0)+' KB':(b/1048576).toFixed(1)+' MB'; }
function esc(s){return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function showErr(msg){const e=document.getElementById('err-bar');e.textContent=msg;e.classList.toggle('on',!!msg);}
function markDirty(){_dirty=true;document.getElementById('proj-dirty').classList.add('visible');}
function clearDirty(){_dirty=false;document.getElementById('proj-dirty').classList.remove('visible');}

// ── Undo / Redo ───────────────────────────────────────────────────────────────
function _snapClips(){return tClips.map(c=>({...c}));}
function _updateUndoUI(){
  document.getElementById('btn-undo').disabled=!_undoStack.length;
  document.getElementById('btn-redo').disabled=!_redoStack.length;
}
function pushUndo(){
  _redoStack=[];
  _undoStack.push(_snapClips());
  if(_undoStack.length>100)_undoStack.shift();
  _updateUndoUI();
}
function _applySnapshot(snap){
  tClips=snap;
  tCtr=tClips.reduce((m,c)=>Math.max(m,c.id+1),tCtr);
  previewClipIdx=Math.min(Math.max(previewClipIdx,tClips.length?0:-1),tClips.length-1);
  if(!tClips.length){previewClipIdx=-1;vid.src='';vid.classList.remove('visible');document.getElementById('preview-placeholder').style.display='flex';}
  markDirty(); resizeTl(); _updateUndoUI();
}
function undo(){
  if(!_undoStack.length)return;
  _redoStack.push(_snapClips());
  _applySnapshot(_undoStack.pop());
}
function redo(){
  if(!_redoStack.length)return;
  _undoStack.push(_snapClips());
  _applySnapshot(_redoStack.pop());
}

// ── Timeline drawing ──────────────────────────────────────────────────────────
const ZOOM_LEVELS=[8,12,20,30,40,60,80,100,150,200,300,500];
function tToX(t){ return t*pxPerSec+4; }
function xToT(x){ return Math.max(0,(x-4)/pxPerSec); }

function tlTotalW(){
  return Math.max((tlWrap.clientWidth||800), totalDur()*pxPerSec+120);
}
function resizeTl(){ tlCanvas.width=tlTotalW(); drawTl(); }
window.addEventListener('resize',resizeTl);

function drawTl(razorX){
  const W=tlCanvas.width, H=tlCanvas.height;
  tlCtx.clearRect(0,0,W,H);

  // backgrounds
  tlCtx.fillStyle='#0d0d0d'; tlCtx.fillRect(0,0,W,H);
  tlCtx.fillStyle='#0f0f0f'; tlCtx.fillRect(0,0,W,RULER_H);
  tlCtx.fillStyle='#141414'; tlCtx.fillRect(0,TRACK_Y,W,TRACK_H);

  // ruler ticks
  const minPx=55;
  const steps=[0.1,0.25,0.5,1,2,5,10,15,30,60,120,300,600];
  const step=steps.find(s=>s*pxPerSec>=minPx)||600;
  const dur=Math.max(totalDur(),1);
  tlCtx.font='9px monospace'; tlCtx.textBaseline='alphabetic';
  for(let t=0;t<=dur+step;t+=step){
    const x=tToX(t);
    tlCtx.fillStyle='#1e1e1e'; tlCtx.fillRect(x,RULER_H,1,TRACK_H);
    tlCtx.fillStyle='#333'; tlCtx.fillRect(x,RULER_H-5,1,5);
    if(x>4&&x<W-28){tlCtx.fillStyle='#444'; tlCtx.fillText(fmtTick(t),x+2,RULER_H-7);}
  }

  // clips
  tClips.forEach((clip,i)=>{
    const ts=clipStart(i), x1=tToX(ts);
    const w=Math.max((clip.outPoint-clip.inPoint)*pxPerSec,2);
    const y=TRACK_Y+2, h=TRACK_H-4;
    tlCtx.fillStyle=clipColor(i);
    rr(tlCtx,x1,y,w,h,3); tlCtx.fill();
    // label
    if(w>36){
      tlCtx.save(); tlCtx.beginPath(); tlCtx.rect(x1+3,y+1,w-6,h-2); tlCtx.clip();
      tlCtx.fillStyle='rgba(255,255,255,.5)'; tlCtx.font='10px system-ui,sans-serif';
      tlCtx.textBaseline='top'; tlCtx.fillText(clip.name,x1+5,y+4); tlCtx.restore();
    }
    // handles
    tlCtx.fillStyle='rgba(255,255,255,.25)';
    tlCtx.fillRect(x1,y,3,h); tlCtx.fillRect(x1+w-3,y,3,h);
    // border
    tlCtx.strokeStyle='rgba(255,255,255,.1)'; tlCtx.lineWidth=1;
    rr(tlCtx,x1,y,w,h,3); tlCtx.stroke();
  });

  // razor line
  if(razorX!==undefined){
    tlCtx.save(); tlCtx.strokeStyle='rgba(255,160,50,.9)'; tlCtx.lineWidth=1.5;
    tlCtx.setLineDash([3,3]); tlCtx.beginPath();
    tlCtx.moveTo(razorX,RULER_H); tlCtx.lineTo(razorX,H); tlCtx.stroke(); tlCtx.restore();
  }

  // playhead
  const phX=tToX(playheadT);
  tlCtx.setLineDash([]); tlCtx.strokeStyle='rgba(255,255,255,.8)'; tlCtx.lineWidth=1.5;
  tlCtx.beginPath(); tlCtx.moveTo(phX,2); tlCtx.lineTo(phX,H); tlCtx.stroke();
  tlCtx.fillStyle='rgba(255,255,255,.8)';
  tlCtx.beginPath(); tlCtx.moveTo(phX-5,2); tlCtx.lineTo(phX+5,2); tlCtx.lineTo(phX,RULER_H-3); tlCtx.fill();

  // timecode
  document.getElementById('tc-disp').textContent=fmtSecs(playheadT)+' / '+fmtSecs(totalDur());
}

function rr(ctx,x,y,w,h,r){
  r=Math.min(r,w/2,h/2);
  ctx.beginPath(); ctx.moveTo(x+r,y);
  ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath();
}

function fmtTick(t){
  if(t<1) return t.toFixed(1)+'s';
  const m=Math.floor(t/60),s=Math.floor(t%60);
  return m>0?m+':'+String(s).padStart(2,'0'):s+'s';
}

// ── Zoom ──────────────────────────────────────────────────────────────────────
function zoomTl(dir){
  let i=ZOOM_LEVELS.findIndex(z=>z>=pxPerSec);
  if(i===-1)i=ZOOM_LEVELS.length-1;
  i=Math.max(0,Math.min(ZOOM_LEVELS.length-1,i+dir));
  pxPerSec=ZOOM_LEVELS[i];
  document.getElementById('zoom-lbl').textContent=pxPerSec+'px/s';
  resizeTl();
}
function fitTl(){
  const total=totalDur(); if(!total)return;
  const avail=(tlWrap.clientWidth||800)-40;
  const ideal=avail/total;
  const level=ZOOM_LEVELS.slice().reverse().find(z=>z<=ideal)||ZOOM_LEVELS[0];
  pxPerSec=level;
  document.getElementById('zoom-lbl').textContent=pxPerSec+'px/s';
  resizeTl();
}
tlWrap.addEventListener('wheel',e=>{e.preventDefault();zoomTl(e.deltaY<0?1:-1);},{passive:false});

// ── Timeline mouse ────────────────────────────────────────────────────────────
function hitClip(x){
  for(let i=0;i<tClips.length;i++){
    const ts=clipStart(i), x1=tToX(ts), w=(tClips[i].outPoint-tClips[i].inPoint)*pxPerSec;
    if(x>=x1-2&&x<=x1+w+2){
      let zone='body';
      if(Math.abs(x-x1)<=HANDLE)zone='left';
      else if(Math.abs(x-(x1+w))<=HANDLE)zone='right';
      return{clip:tClips[i],idx:i,zone};
    }
  }
  return null;
}

tlCanvas.addEventListener('mousemove',e=>{
  const x=e.offsetX;
  if(dragState){
    const dt=(x-dragState.ox)/pxPerSec;
    if(dragState.type==='left'){
      dragState.clip.inPoint=Math.max(0,Math.min(dragState.clip.outPoint-0.05,dragState.origIn+dt));
      markDirty(); resizeTl();
    } else if(dragState.type==='right'){
      dragState.clip.outPoint=Math.max(dragState.clip.inPoint+0.05,Math.min(dragState.clip.dur,dragState.origOut+dt));
      markDirty(); resizeTl();
    } else if(dragState.type==='head'){
      playheadT=Math.max(0,Math.min(totalDur(),xToT(x)));
      seekTo(playheadT); drawTl();
    }
    return;
  }
  if(activeTool==='select'){
    const h=hitClip(x);
    tlCanvas.style.cursor=h?(h.zone==='body'?'default':'ew-resize'):'default';
  } else if(activeTool==='razor'){
    tlCanvas.style.cursor='col-resize'; drawTl(x); return;
  } else if(activeTool==='delete'){
    tlCanvas.style.cursor='pointer';
  }
  drawTl();
});

tlCanvas.addEventListener('mouseleave',()=>{ if(!dragState)drawTl(); });

tlCanvas.addEventListener('mousedown',e=>{
  const x=e.offsetX, t=xToT(x);
  if(activeTool==='select'){
    const phX=tToX(playheadT);
    if(e.offsetY<TRACK_Y&&Math.abs(x-phX)<=8){
      dragState={type:'head',ox:x}; return;
    }
    const h=hitClip(x);
    if(!h){
      playheadT=Math.max(0,Math.min(totalDur(),t));
      seekTo(playheadT); dragState={type:'head',ox:x}; drawTl(); return;
    }
    if(h.zone==='left'){pushUndo();dragState={type:'left',clip:h.clip,idx:h.idx,ox:x,origIn:h.clip.inPoint,origOut:h.clip.outPoint};}
    else if(h.zone==='right'){pushUndo();dragState={type:'right',clip:h.clip,idx:h.idx,ox:x,origIn:h.clip.inPoint,origOut:h.clip.outPoint};}
    else {
      playheadT=clipStart(h.idx)+Math.max(0,t-clipStart(h.idx));
      seekTo(playheadT); dragState={type:'head',ox:x};
    }
    drawTl();
  } else if(activeTool==='razor'){
    const h=hitClip(x);
    if(h&&h.clip.outPoint-h.clip.inPoint>0.1){
      pushUndo();
      const srcT=h.clip.inPoint+(t-clipStart(h.idx));
      const origOut=h.clip.outPoint;
      h.clip.outPoint=srcT;
      tClips.splice(h.idx+1,0,{id:tCtr++,fileId:h.clip.fileId,name:h.clip.name,
        dur:h.clip.dur,hasAudio:h.clip.hasAudio,inPoint:srcT,outPoint:origOut});
      markDirty(); resizeTl();
    }
  } else if(activeTool==='delete'){
    const h=hitClip(x);
    if(h){
      pushUndo();
      tClips.splice(h.idx,1);
      if(!tClips.length){previewClipIdx=-1;vid.src='';vid.classList.remove('visible');document.getElementById('preview-placeholder').style.display='flex';}
      markDirty(); resizeTl();
    }
  }
});

document.addEventListener('mouseup',()=>{
  if(dragState){
    if((dragState.type==='left'||dragState.type==='right')&&
       dragState.clip.inPoint===dragState.origIn&&dragState.clip.outPoint===dragState.origOut){
      _undoStack.pop(); _updateUndoUI();
    }
    dragState=null; drawTl();
  }
});

// ── Playback ──────────────────────────────────────────────────────────────────
function togglePlay(){
  if(!tClips.length)return;
  if(isPlaying)pause(); else play();
}
function play(){
  isPlaying=true;
  document.getElementById('play-btn').innerHTML='&#9646;&#9646;';
  const {idx,srcT}=timeToClip(playheadT);
  if(idx<0){isPlaying=false;return;}
  loadClip(idx,srcT,true);
}
function pause(){
  isPlaying=false;
  document.getElementById('play-btn').innerHTML='&#9654;';
  vid.pause();
}
function loadClip(idx,srcT,autoplay){
  const clip=tClips[idx]; if(!clip)return;
  previewClipIdx=idx;
  const url='/preview/'+clip.fileId;
  const needLoad=vid.getAttribute('data-fid')!==clip.fileId;
  vid.setAttribute('data-fid',clip.fileId);
  const doSeek=()=>{
    vid.currentTime=Math.max(clip.inPoint,Math.min(clip.outPoint-0.01,srcT));
    if(autoplay)vid.play().catch(()=>{});
  };
  if(needLoad){vid.src=url;vid.load();vid.addEventListener('loadedmetadata',doSeek,{once:true});}
  else doSeek();
  vid.classList.add('visible');
  document.getElementById('preview-placeholder').style.display='none';
}
function seekTo(t){
  if(!tClips.length)return;
  const {idx,srcT}=timeToClip(Math.max(0,Math.min(totalDur(),t)));
  if(idx<0)return;
  loadClip(idx,srcT,isPlaying);
}
function skipStart(){playheadT=0;seekTo(0);drawTl();}
function skipEnd(){playheadT=totalDur();seekTo(playheadT);drawTl();}

vid.addEventListener('timeupdate',()=>{
  if(previewClipIdx<0||previewClipIdx>=tClips.length)return;
  const clip=tClips[previewClipIdx];
  const localT=vid.currentTime-clip.inPoint;
  playheadT=clipStart(previewClipIdx)+Math.max(0,localT);
  if(isPlaying&&vid.currentTime>=clip.outPoint-0.05){
    if(previewClipIdx+1<tClips.length){
      const next=tClips[++previewClipIdx];
      if(vid.getAttribute('data-fid')!==next.fileId){vid.setAttribute('data-fid',next.fileId);vid.src='/preview/'+next.fileId;}
      vid.currentTime=next.inPoint; vid.play().catch(()=>{});
    } else {
      pause(); playheadT=totalDur();
    }
  }
  drawTl();
});

// ── Tools ─────────────────────────────────────────────────────────────────────
function setTool(t){
  activeTool=t;
  document.querySelectorAll('#tl-toolbar .ibtn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tool-'+t)?.classList.add('active');
  tlCanvas.style.cursor=t==='razor'?'col-resize':t==='delete'?'pointer':'default';
}

// ── Media bin ─────────────────────────────────────────────────────────────────
function renderBin(){
  const list=document.getElementById('bin-list');
  if(!mediaFiles.length){list.innerHTML='<div id="bin-hint">Drop videos anywhere<br>or click + to add<br><span style="color:#1a1a1a">Double-click to add to timeline</span></div>';return;}
  list.innerHTML='';
  mediaFiles.forEach(f=>{
    const d=document.createElement('div'); d.className='bin-item';
    d.title='Double-click to add to timeline';
    d.innerHTML='<span class="bin-item-icon">&#127916;</span>'+
      '<div class="bin-item-info"><div class="bin-item-name">'+esc(f.name)+'</div>'+
      '<div class="bin-item-meta">'+fmtSecs(f.dur)+'&nbsp;&nbsp;'+fmtBytes(f.size)+'</div></div>';
    d.addEventListener('dblclick',()=>addToTimeline(f));
    list.appendChild(d);
  });
}

function addToTimeline(f){
  pushUndo();
  tClips.push({id:tCtr++,fileId:f.fileId,name:f.name,dur:f.dur,hasAudio:f.hasAudio,inPoint:0,outPoint:f.dur});
  markDirty();
  document.getElementById('btn-add-more').style.display='';
  if(tClips.length===1) loadClip(0,0,false);
  resizeTl();
}

// ── Upload ────────────────────────────────────────────────────────────────────
function handleFiles(files){
  const arr=Array.from(files); if(!arr.length)return;
  let done=0;
  document.getElementById('up-overlay').classList.add('on');
  document.getElementById('up-lbl').textContent=arr.length>1?'Uploading '+arr.length+' files...':'Uploading...';
  arr.forEach(file=>{
    const fd=new FormData(); fd.append('file',file);
    const xhr=new XMLHttpRequest(); xhr.open('POST','/upload-temp');
    xhr.upload.onprogress=e=>{
      if(arr.length>1||!e.lengthComputable)return;
      document.getElementById('up-fg').style.width=Math.round(e.loaded/e.total*100)+'%';
    };
    xhr.onload=()=>{
      done++; if(arr.length>1)document.getElementById('up-fg').style.width=Math.round(done/arr.length*100)+'%';
      if(done===arr.length)document.getElementById('up-overlay').classList.remove('on');
      const d=JSON.parse(xhr.responseText);
      if(xhr.status!==200){showErr(d.error||xhr.responseText);return;}
      const mf={fileId:d.fileId,name:d.filename,dur:d.duration,hasAudio:d.hasAudio,width:d.width||0,height:d.height||0,size:d.size||0};
      mediaFiles.push(mf); renderBin(); addToTimeline(mf);
    };
    xhr.onerror=()=>{done++;if(done===arr.length)document.getElementById('up-overlay').classList.remove('on');showErr('Upload failed: '+file.name);};
    xhr.send(fd);
  });
}

document.addEventListener('dragover',e=>{e.preventDefault();document.getElementById('drop-over').classList.add('on');});
document.addEventListener('dragleave',e=>{if(!e.relatedTarget||!document.body.contains(e.relatedTarget))document.getElementById('drop-over').classList.remove('on');});
document.addEventListener('drop',e=>{e.preventDefault();document.getElementById('drop-over').classList.remove('on');if(e.dataTransfer.files.length)handleFiles(e.dataTransfer.files);});

// ── Settings ──────────────────────────────────────────────────────────────────
function onQ(){const q=parseInt(document.getElementById('q-sl').value);document.getElementById('q-val').textContent=q+'%';document.getElementById('crf-n').textContent='CRF '+Math.max(18,Math.min(40,Math.round(40-q*22/100)));}
function onV(){document.getElementById('v-val').textContent=document.getElementById('v-sl').value+'%';}
function toggleMute(){isMuted=!isMuted;const b=document.getElementById('mute-btn');b.classList.toggle('on',isMuted);b.textContent=isMuted?'Unmute':'Mute';}

// ── Process ───────────────────────────────────────────────────────────────────
function doProcess(autoUpload){
  if(!tClips.length){showErr('Add clips to the timeline first.');return;}
  showErr('');
  document.getElementById('proc-overlay').classList.add('on');
  document.getElementById('proc-fg').style.width='0%';
  document.getElementById('proc-lbl').textContent='Starting FFmpeg...';
  const body={
    clips:tClips.map(c=>({fileId:c.fileId,segments:[{start:c.inPoint,end:c.outPoint}]})),
    settings:{
      quality:parseInt(document.getElementById('q-sl').value),
      targetMb:parseFloat(document.getElementById('tmb').value)||null,
      volume:parseInt(document.getElementById('v-sl').value),
      muted:isMuted,
      preset:document.getElementById('preset-sel').value,
    }
  };
  fetch('/process',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{if(d.error)throw new Error(d.error);listenJob(d.jobId,autoUpload);})
    .catch(e=>{document.getElementById('proc-overlay').classList.remove('on');showErr(e.message);});
}
function listenJob(jobId,autoUpload){
  const es=new EventSource('/progress/'+jobId);
  es.onmessage=e=>{
    const d=JSON.parse(e.data);
    const pct=Math.round((d.progress||0)*100);
    document.getElementById('proc-fg').style.width=pct+'%';
    document.getElementById('proc-lbl').textContent=d.status==='processing'?'Encoding... '+pct+'%':d.status==='done'?'Done!':'Error: '+d.error;
    if(d.status==='done'){es.close();processedId=d.output_id;document.getElementById('proc-overlay').classList.remove('on');showResult(d,autoUpload);}
    else if(d.status==='error'){es.close();document.getElementById('proc-overlay').classList.remove('on');showErr('FFmpeg: '+d.error);}
  };
  es.onerror=()=>{es.close();document.getElementById('proc-overlay').classList.remove('on');showErr('Lost connection');};
}
function showResult(job,autoUpload){
  const dlg=document.getElementById('result-dlg'); dlg.classList.add('on');
  document.getElementById('result-vid').src='/preview/'+job.output_id;
  document.getElementById('result-info').textContent='Processed: '+fmtBytes(job.size);
  document.getElementById('result-url').style.display='none';
  document.getElementById('copy-btn').style.display='none';
  document.getElementById('btn-push-only').style.display='none';
  resultUrl=null;
  if(autoUpload)doPush(); else document.getElementById('btn-push-only').style.display='';
}
function doPush(){
  document.getElementById('btn-push-only').style.display='none';
  document.getElementById('result-info').textContent+='  |  Uploading...';
  fetch('/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fileId:processedId})})
    .then(r=>r.json()).then(d=>{
      if(d.error||d.detail)throw new Error(d.detail||d.error);
      resultUrl=d.url;
      const u=document.getElementById('result-url'); u.textContent=d.url; u.style.display='block';
      document.getElementById('copy-btn').style.display=''; document.getElementById('result-info').textContent='Uploaded';
    }).catch(e=>showErr('Upload failed: '+e.message));
}
function doCopy(){
  navigator.clipboard.writeText(resultUrl).then(()=>{
    const b=document.getElementById('copy-btn'); b.textContent='Copied!'; b.classList.add('ok');
    setTimeout(()=>{b.textContent='Copy link';b.classList.remove('ok');},2000);
  });
}

// ── Projects ──────────────────────────────────────────────────────────────────
document.getElementById('proj-name').addEventListener('input',()=>{
  if(!tClips.length)return; markDirty(); clearTimeout(_autoSaveTimer); _autoSaveTimer=setTimeout(saveProject,800);
});

async function saveProject(){
  if(!tClips.length){showErr('Add clips before saving.');return;}
  const nameEl=document.getElementById('proj-name'); const name=nameEl.value.trim();
  if(!name){nameEl.focus();nameEl.classList.remove('shake');void nameEl.offsetWidth;nameEl.classList.add('shake');setTimeout(()=>nameEl.classList.remove('shake'),350);return;}
  const body={
    projectId:currentProjectId, name,
    clips:tClips.map(c=>({fileId:c.fileId,name:c.name,dur:c.dur,hasAudio:c.hasAudio,width:0,height:0,size:0,segs:[{s:c.inPoint,e:c.outPoint}]})),
    settings:{quality:parseInt(document.getElementById('q-sl').value),targetMb:parseFloat(document.getElementById('tmb').value)||null,
      volume:parseInt(document.getElementById('v-sl').value),muted:isMuted,preset:document.getElementById('preset-sel').value}
  };
  try{
    const data=await(await fetch('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(data.error)throw new Error(data.error);
    currentProjectId=data.projectId; clearDirty();
    const btn=document.getElementById('btn-save'); const orig=btn.innerHTML;
    btn.innerHTML='&#10003; Saved'; btn.classList.add('ok'); setTimeout(()=>{btn.innerHTML=orig;btn.classList.remove('ok');},2000);
  }catch(e){showErr('Save failed: '+e.message);}
}

function toggleProjPanel(){
  const panel=document.getElementById('proj-panel');
  if(_projOpen){panel.classList.remove('on');_projOpen=false;return;}
  _projOpen=true; panel.classList.add('on');
  panel.innerHTML='<div id="proj-empty">Loading...</div>';
  fetch('/projects').then(r=>r.json()).then(list=>{
    panel.innerHTML=''; if(!list.length){panel.innerHTML='<div id="proj-empty">No saved projects</div>';return;}
    list.forEach(p=>{
      const div=document.createElement('div'); div.className='proj-item';
      const date=(p.updated||p.created||'').substring(0,16).replace('T',' ');
      div.innerHTML='<div style="flex:1"><div class="proj-iname">'+esc(p.name)+'</div><div class="proj-imeta">'+p.clipCount+' clip'+(p.clipCount!==1?'s':'')+' &middot; '+date+'</div></div>'+
        '<button class="proj-idel" onclick="event.stopPropagation();deleteProjById(\\''+p.projectId+'\\')">&times;</button>';
      div.addEventListener('click',()=>loadProjById(p.projectId)); panel.appendChild(div);
    });
  }).catch(e=>{panel.innerHTML='<div id="proj-empty">Error: '+esc(e.message)+'</div>';});
}

async function loadProjById(projectId){
  try{
    const data=await(await fetch('/projects/'+projectId)).json();
    if(data.error)throw new Error(data.error);
    tClips=[]; mediaFiles=[]; processedId=null; resultUrl=null; _undoStack=[]; _redoStack=[]; _updateUndoUI();
    document.getElementById('proj-panel').classList.remove('on'); _projOpen=false; showErr('');
    const seen=new Set();
    for(const cl of data.clips){
      if(!seen.has(cl.fileId)){seen.add(cl.fileId);mediaFiles.push({fileId:cl.fileId,name:cl.name,dur:cl.dur,hasAudio:cl.hasAudio,width:cl.width||0,height:cl.height||0,size:cl.size||0});}
      const segs=cl.segs||[]; const inP=segs.length?segs[0].s:0; const outP=segs.length?segs[segs.length-1].e:cl.dur;
      tClips.push({id:tCtr++,fileId:cl.fileId,name:cl.name,dur:cl.dur,hasAudio:cl.hasAudio,inPoint:inP,outPoint:outP});
    }
    renderBin();
    const s=data.settings||{};
    if(s.quality!=null){document.getElementById('q-sl').value=s.quality;onQ();}
    if(s.volume!=null){document.getElementById('v-sl').value=s.volume;onV();}
    if(s.preset)document.getElementById('preset-sel').value=s.preset;
    document.getElementById('tmb').value=s.targetMb||'';
    isMuted=!!s.muted; const mb=document.getElementById('mute-btn'); mb.classList.toggle('on',isMuted); mb.textContent=isMuted?'Unmute':'Mute';
    currentProjectId=data.projectId; document.getElementById('proj-name').value=data.name; clearDirty();
    if(tClips.length){document.getElementById('btn-add-more').style.display='';loadClip(0,0,false);fitTl();}
  }catch(e){showErr('Load failed: '+e.message);}
}

async function deleteProjById(projectId){
  if(!confirm('Delete this project?'))return;
  try{
    const d=await(await fetch('/projects/'+projectId,{method:'DELETE'})).json();
    if(d.error)throw new Error(d.error);
    if(projectId===currentProjectId){currentProjectId=null;document.getElementById('proj-name').value='';}
    _projOpen=false; toggleProjPanel();
  }catch(e){showErr('Delete failed: '+e.message);}
}

document.addEventListener('click',e=>{
  if(_projOpen){
    const panel=document.getElementById('proj-panel'), btn=document.getElementById('btn-projects');
    if(!panel.contains(e.target)&&!btn.contains(e.target)){panel.classList.remove('on');_projOpen=false;}
  }
});

// ── Keyboard ──────────────────────────────────────────────────────────────────
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();saveProject();return;}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!e.shiftKey){e.preventDefault();undo();return;}
  if((e.ctrlKey||e.metaKey)&&(e.key.toLowerCase()==='y'||(e.key.toLowerCase()==='z'&&e.shiftKey))){e.preventDefault();redo();return;}
  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
  const k=e.key.toLowerCase();
  if(k===' '){e.preventDefault();togglePlay();}
  else if(k==='v')setTool('select');
  else if(k==='r')setTool('razor');
  else if(k==='e')setTool('delete');
});

// ── Init ──────────────────────────────────────────────────────────────────────
resizeTl();
</script>
</body>
</html>""".encode("utf-8")

