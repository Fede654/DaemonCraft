/**
 * research-dashboard/server.js
 *
 * Live dashboard for the hermes `researcher` profile. Mirrors the
 * architecture of bot/server.js: HTTP + WebSocket, broadcastDashboard()
 * pushing typed events to all connected clients, a /dashboard endpoint
 * that serves dashboard.html, and a /ws endpoint for the WebSocket
 * upgrade.
 *
 * Difference vs the bot dashboard: the researcher kanban-worker is a
 * transient process (lives one run, dies). It cannot host a WS server.
 * So this dashboard does NOT receive push events from a single producer
 * — instead, it watches the data sources directly (session JSONL,
 * kanban DB, workspace STATE.json, results dir) and self-emits the
 * same typed events the bot dashboard would emit.
 *
 *   POST /agent/log     → still accepted, for future push-style producers
 *   GET  /dashboard     → serves dashboard.html
 *   GET  /ws            → WebSocket upgrade
 *   GET  /health        → JSON status
 *   GET  /status        → current snapshot (latest broadcast payload)
 *
 * Event types broadcast (mirroring bot/server.js conventions):
 *   status            { task_id, status, run_id, run_state, elapsed_s }
 *   agent             [{ ts, role, tool_calls:[{name, args_short}], content_preview }, ...]
 *   heartbeat         { last_note, last_ts, runs_count }
 *   kanban_event      { kind, payload, ts, run_id }
 *   state             (contents of workspace/STATE.json)
 *   metrics           [{ experiment, variant_means, overall }, ...]
 *   files             [{ path, size, mtime }, ...]
 *
 * Env:
 *   PORT                   default 9120
 *   HERMES_HOME            ~/.hermes/profiles/researcher
 *   KANBAN_TASK_ID         t_xxxxxxxx (the task to focus on; if unset, latest active)
 *   POLL_MS                default 3000
 */

import http from 'http';
import { readFileSync, existsSync, readdirSync, statSync, watch } from 'fs';
import path from 'path';
import os from 'os';
import { WebSocketServer } from 'ws';
import { execSync } from 'child_process';

// ── Config ────────────────────────────────────────────────────────────────
const PORT          = parseInt(process.env.PORT || '9120', 10);
const HERMES_HOME   = process.env.HERMES_HOME || path.join(os.homedir(), '.hermes/profiles/researcher');
const PROFILE_NAME  = path.basename(HERMES_HOME);
const SESSIONS_DIR  = path.join(HERMES_HOME, 'sessions');
const KANBAN_DB     = path.join(HERMES_HOME, 'kanban.db');
const WORKSPACES    = path.join(os.homedir(), '.hermes/kanban/workspaces');
const RESULTS_GLOB  = process.env.RESULTS_DIR_GLOB || path.join(
  os.homedir(),
  'REPOS/daemoncraft/agents/embodied-service/primitives_lab/results',
);
const TASK_ID_ENV   = process.env.KANBAN_TASK_ID || '';
const POLL_MS       = parseInt(process.env.POLL_MS || '3000', 10);

// ── State (mirrors bot/server.js style: small global state, broadcast on change) ─
let lastBroadcast = {
  status: null,
  agent: [],
  heartbeat: null,
  kanban_events: [],
  state: null,
  metrics: null,
  files: [],
};
const dashboardClients = new Set();

function broadcastDashboard(type, data) {
  if (dashboardClients.size === 0) return;
  const msg = JSON.stringify({ type, data });
  for (const ws of dashboardClients) {
    try { ws.send(msg); } catch { dashboardClients.delete(ws); }
  }
}

function log(...args) {
  console.log(`[${new Date().toISOString()}]`, ...args);
}

// ── Source watchers ───────────────────────────────────────────────────────

/** Latest session_*.json by mtime — the active worker run's transcript. */
function latestSessionPath() {
  try {
    const entries = readdirSync(SESSIONS_DIR)
      .filter(f => f.startsWith('session_') && f.endsWith('.json'))
      .map(f => ({ f, m: statSync(path.join(SESSIONS_DIR, f)).mtimeMs }));
    if (entries.length === 0) return null;
    entries.sort((a, b) => b.m - a.m);
    return path.join(SESSIONS_DIR, entries[0].f);
  } catch { return null; }
}

/** Reduce a session JSON to a compact list of recent turns (~50 latest). */
function summarizeSession(sessionPath) {
  if (!sessionPath || !existsSync(sessionPath)) return [];
  let d;
  try { d = JSON.parse(readFileSync(sessionPath, 'utf8')); } catch { return []; }
  const msgs = Array.isArray(d?.messages) ? d.messages : [];
  const out = [];
  for (let i = Math.max(0, msgs.length - 80); i < msgs.length; i++) {
    const m = msgs[i];
    if (!m) continue;
    const tcs = (m.tool_calls || []).map(tc => {
      const fn = tc.function || {};
      let args = fn.arguments;
      try { args = typeof args === 'string' ? JSON.parse(args) : args; } catch {}
      const args_short = typeof args === 'object'
        ? JSON.stringify(args).slice(0, 160)
        : String(args || '').slice(0, 160);
      return { name: fn.name || '?', args_short };
    });
    let content = m.content;
    if (Array.isArray(content)) {
      content = content.map(c => c?.text || '').join('\n');
    }
    content = (content || '').toString();
    out.push({
      idx: i,
      role: m.role || '?',
      tool_calls: tcs,
      content_preview: content.length > 600 ? content.slice(0, 600) + '…' : content,
      has_content: content.trim().length > 0,
    });
  }
  return out;
}

/** Query kanban DB via the `hermes kanban` CLI — mimics bot's HTTP-state polling. */
function queryKanban(taskId) {
  // List active tasks if no task id pinned
  let resolvedId = taskId;
  if (!resolvedId) {
    try {
      const out = execSync(
        `HERMES_HOME='${HERMES_HOME}' hermes kanban list --json 2>/dev/null`,
        { encoding: 'utf8', timeout: 6000 },
      );
      const arr = JSON.parse(out);
      const running = arr.find(t => t.status === 'running' || t.status === 'blocked');
      if (running) resolvedId = running.id;
    } catch (e) { /* fall through */ }
  }
  if (!resolvedId) return { task: null, events: [], runs: [], comments: [] };
  try {
    const out = execSync(
      `HERMES_HOME='${HERMES_HOME}' hermes kanban show '${resolvedId}' --json 2>/dev/null`,
      { encoding: 'utf8', timeout: 6000 },
    );
    return JSON.parse(out);
  } catch (e) {
    return { task: null, events: [], runs: [], comments: [], error: String(e).slice(0, 200) };
  }
}

/** Read workspace/STATE.json if it exists for this task. */
function loadWorkspaceState(taskId) {
  if (!taskId) return null;
  const p = path.join(WORKSPACES, taskId, 'STATE.json');
  if (!existsSync(p)) return null;
  try { return JSON.parse(readFileSync(p, 'utf8')); }
  catch (e) { return { error: `failed to parse STATE.json: ${String(e).slice(0,120)}` }; }
}

/** Walk results directories, return per-experiment summary. */
function summarizeResults() {
  const out = [];
  let dirs;
  try { dirs = readdirSync(RESULTS_GLOB).filter(d => {
    try { return statSync(path.join(RESULTS_GLOB, d)).isDirectory(); }
    catch { return false; }
  }); } catch { return []; }
  for (const d of dirs) {
    const dirPath = path.join(RESULTS_GLOB, d);
    let files;
    try { files = readdirSync(dirPath).filter(f => f.endsWith('.json')); }
    catch { continue; }
    const variants = [];
    for (const f of files) {
      const fp = path.join(dirPath, f);
      let data;
      try { data = JSON.parse(readFileSync(fp, 'utf8')); }
      catch { continue; }
      const results = Array.isArray(data?.results) ? data.results : [];
      const rates = results.map(r => r?.metrics?.success_rate).filter(v => v != null);
      const mean = rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null;
      variants.push({
        file: f,
        n_variants: results.length,
        success_rates: rates,
        mean,
        mtime: statSync(fp).mtimeMs,
      });
    }
    if (variants.length === 0) continue;
    const groupMean = (() => {
      const allRates = variants.flatMap(v => v.success_rates);
      return allRates.length ? allRates.reduce((a, b) => a + b, 0) / allRates.length : null;
    })();
    out.push({ run: d, variants, mean: groupMean });
  }
  return out.sort((a, b) => a.run.localeCompare(b.run));
}

/** List workspace artifact files for the focused task. */
function listWorkspaceFiles(taskId) {
  if (!taskId) return [];
  const dir = path.join(WORKSPACES, taskId);
  if (!existsSync(dir)) return [];
  try {
    return readdirSync(dir).map(f => {
      const fp = path.join(dir, f);
      const s = statSync(fp);
      return { name: f, size: s.size, mtime: s.mtimeMs, is_dir: s.isDirectory() };
    }).sort((a, b) => b.mtime - a.mtime);
  } catch { return []; }
}

// ── Poll loop — emits typed events on change ──────────────────────────────

let activeTaskId = TASK_ID_ENV || '';
let lastSessionMtime = 0;
let lastStateMtime = 0;
let lastResultsSig = '';

function pollAndBroadcast() {
  // 1. Kanban state (events, runs, heartbeats)
  const k = queryKanban(activeTaskId);
  const task = k?.task || null;
  if (task) {
    activeTaskId = task.id;
    const eventsSnap = (k.events || []).slice(-30);
    if (JSON.stringify(eventsSnap) !== JSON.stringify(lastBroadcast.kanban_events)) {
      lastBroadcast.kanban_events = eventsSnap;
      broadcastDashboard('kanban_event', eventsSnap);
    }
    const heartbeats = (k.events || []).filter(e => e.kind === 'heartbeat');
    const lastHb = heartbeats.length ? heartbeats[heartbeats.length - 1] : null;
    const hbPayload = {
      last_note: lastHb?.payload?.note || null,
      last_ts:   lastHb?.created_at || null,
      runs_count: (k.runs || []).length,
    };
    if (JSON.stringify(hbPayload) !== JSON.stringify(lastBroadcast.heartbeat)) {
      lastBroadcast.heartbeat = hbPayload;
      broadcastDashboard('heartbeat', hbPayload);
    }
    const statusPayload = {
      task_id: task.id,
      title: task.title,
      status: task.status,
      current_run_id: task.current_run_id,
      assignee: task.assignee,
      profile: PROFILE_NAME,
      runs: (k.runs || []).map(r => ({
        id: r.id, status: r.status, outcome: r.outcome,
        summary: r.summary, started_at: r.started_at, ended_at: r.ended_at,
      })),
      comments: (k.comments || []).slice(-5).map(c => ({
        author: c.author, body: c.body, created_at: c.created_at,
      })),
    };
    if (JSON.stringify(statusPayload) !== JSON.stringify(lastBroadcast.status)) {
      lastBroadcast.status = statusPayload;
      broadcastDashboard('status', statusPayload);
    }
  }

  // 2. Workspace STATE.json
  if (activeTaskId) {
    const statePath = path.join(WORKSPACES, activeTaskId, 'STATE.json');
    let mtime = 0;
    try { mtime = statSync(statePath).mtimeMs; } catch {}
    if (mtime > 0 && mtime !== lastStateMtime) {
      lastStateMtime = mtime;
      const state = loadWorkspaceState(activeTaskId);
      lastBroadcast.state = state;
      broadcastDashboard('state', state);
    }
    // Workspace files
    const files = listWorkspaceFiles(activeTaskId);
    if (JSON.stringify(files) !== JSON.stringify(lastBroadcast.files)) {
      lastBroadcast.files = files;
      broadcastDashboard('files', files);
    }
  }

  // 3. Latest session JSONL → agent turns
  const sp = latestSessionPath();
  if (sp) {
    let mtime = 0;
    try { mtime = statSync(sp).mtimeMs; } catch {}
    if (mtime !== lastSessionMtime) {
      lastSessionMtime = mtime;
      const turns = summarizeSession(sp);
      lastBroadcast.agent = turns;
      broadcastDashboard('agent', turns);
    }
  }

  // 4. Experiment results → metrics trajectory
  const results = summarizeResults();
  const sig = JSON.stringify(results.map(r => [r.run, r.mean, r.variants.length]));
  if (sig !== lastResultsSig) {
    lastResultsSig = sig;
    lastBroadcast.metrics = results;
    broadcastDashboard('metrics', results);
  }

  // 5. Heartbeat tick so the UI can show "last refresh" even when
  //    no other source changed. Always emit.
  broadcastDashboard('tick', { ts: Date.now(), poll_ms: POLL_MS });
}

// ── HTTP server (mirrors bot/server.js endpoint shape) ────────────────────

const httpServer = http.createServer((req, res) => {
  // CORS-friendly
  res.setHeader('Access-Control-Allow-Origin', '*');
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

  if (req.method === 'GET' && url.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({
      ok: true, service: 'research-dashboard', version: '0.1.0',
      port: PORT, profile: PROFILE_NAME, task_id: activeTaskId,
      ws_clients: dashboardClients.size,
    }));
  }

  if (req.method === 'GET' && url.pathname === '/status') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify(lastBroadcast));
  }

  if (req.method === 'GET' && url.pathname === '/dashboard') {
    const htmlPath = new URL('dashboard.html', import.meta.url).pathname;
    try {
      let html = readFileSync(htmlPath, 'utf8');
      html = html.replace('<span id="profile-name">researcher</span>',
                          `<span id="profile-name">${PROFILE_NAME}</span>`);
      res.writeHead(200, { 'Content-Type': 'text/html' });
      return res.end(html);
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ ok: false, error: 'dashboard.html not found', details: String(e) }));
    }
  }

  if (req.method === 'POST' && url.pathname === '/agent/log') {
    // Push-style producer support — mirrors bot/server.js /agent/log.
    // Any external producer can push a turn-shaped payload and we'll
    // broadcast it. For the consumer-side watcher loop, this is unused.
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const payload = JSON.parse(body);
        broadcastDashboard('agent', [payload]);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ ok: true }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ ok: false, error: String(e) }));
      }
    });
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  return res.end(JSON.stringify({ ok: false, error: 'not found', path: url.pathname }));
});

// ── WebSocket server ──────────────────────────────────────────────────────
const wss = new WebSocketServer({ server: httpServer, path: '/ws' });

wss.on('connection', (ws) => {
  dashboardClients.add(ws);
  log(`ws client connected (total=${dashboardClients.size})`);
  // Send current snapshot immediately
  try {
    for (const [type, data] of Object.entries(lastBroadcast)) {
      if (data == null) continue;
      ws.send(JSON.stringify({ type: type === 'kanban_events' ? 'kanban_event' : type, data }));
    }
  } catch {}
  ws.on('close', () => {
    dashboardClients.delete(ws);
    log(`ws client disconnected (total=${dashboardClients.size})`);
  });
  ws.on('error', () => {
    dashboardClients.delete(ws);
  });
});

httpServer.listen(PORT, () => {
  log(`research-dashboard listening on http://localhost:${PORT}/dashboard`);
  log(`  profile: ${PROFILE_NAME}`);
  log(`  task:    ${activeTaskId || '(auto-detect)'}`);
  log(`  sources: sessions=${SESSIONS_DIR}, kanban=${KANBAN_DB}, results=${RESULTS_GLOB}`);
});

// Initial poll + interval
pollAndBroadcast();
setInterval(pollAndBroadcast, POLL_MS);

// Graceful shutdown
for (const sig of ['SIGTERM', 'SIGINT']) {
  process.on(sig, () => {
    log(`received ${sig}, shutting down`);
    httpServer.close(() => process.exit(0));
  });
}
