/**
 * Remote Control Relay Server
 * 
 * Architecture:
 * - HTTP server: serves web control interface + REST API
 * - WebSocket server: relays data between agents and browser clients
 *   - /agent  - Windows Agent connections (outbound from agent)
 *   - /client - Browser Client connections
 */

const express = require('express');
const http = require('http');
const path = require('path');
const fs = require('fs');
const { WebSocketServer } = require('ws');
const { v4: uuidv4 } = require('uuid');
const multer = require('multer');

// ============================================================
// Config
// ============================================================

const PORT = process.env.PORT || 21112;
const UPLOAD_DIR = path.join(__dirname, 'uploads');
// Diag dump dir: the Flutter App proactively uploads its on-device
// log file to /client (via the 'app_diag' WS message). Server
// writes each upload to DIAG_DIR/<agentId-or-_noagent>/<ts>-<trigger>.log
// so the operator can `tail -f` recent activity without needing
// USB access to the phone. Same access password as the rest of
// the API -- these logs may contain the user's host/agent id and
// shouldn't be world-readable.
const DIAG_DIR = process.env.DIAG_DIR || path.join(__dirname, 'agent_logs');
const DIAG_MAX_BYTES = 1024 * 1024;  // 1MB per upload -- sanity cap; 256KB typical
if (!fs.existsSync(DIAG_DIR)) {
    fs.mkdirSync(DIAG_DIR, { recursive: true });
}
const ACCESS_PASSWORD = process.env.ACCESS_PASSWORD || 'Ops@2024!';  // 默认密码，可通过环境变量修改
const AGENTS = new Map();   // agentId -> { ws, info, lastSeen }
const CLIENTS = new Map();  // clientId -> { ws, agentId, info }
const SESSIONS = new Map();  // sessionId -> { agentId, clientId, type, data }
const PASSWORD_TOKENS = new Map();  // passwordToken -> true (one-time or timed)

// Process-wide relay stats. Per-socket state is per-ws, but the
// 30s health snapshot needs cumulative counters and active counts.
// We count 'recv' on every message parse, 'fwd' on every successful
// relay. PONGs are NOT counted (they'd dwarf everything).
const STATS = { totalRecv: 0, totalFwd: 0 };
// Throttle for [wsraw] raw-receive logs (one per client per 5s).
const _clientRawLogAt = new Map();

// Ensure upload dir exists
if (!fs.existsSync(UPLOAD_DIR)) {
    fs.mkdirSync(UPLOAD_DIR, { recursive: true });
}

// ============================================================
// HTTP Server (Express)
// ============================================================

const app = express();
const server = http.createServer(app);

// Serve static files (web control interface) — disable cache for hot dev
app.use(express.static(path.join(__dirname, 'static'), {
    etag: false,
    lastModified: false,
    setHeaders: (res) => res.setHeader('Cache-Control', 'no-store, must-revalidate'),
}));

// === Static Deploy API ===
const DEPLOY_DIR = path.join(__dirname, 'static', 'app');
const DEPLOY_MAX_BYTES = 50 * 1024 * 1024; // 50MB per file
if (!fs.existsSync(DEPLOY_DIR)) {
    fs.mkdirSync(DEPLOY_DIR, { recursive: true });
}

// Auth helper for deploy endpoints: require base64(password) == ACCESS_PASSWORD
function requireDeployAuth(req, res, next) {
    const auth = req.headers['authorization'] || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    let password = '';
    try { password = Buffer.from(token, 'base64').toString('utf8'); } catch {}
    if (password !== ACCESS_PASSWORD) {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    next();
}

// Resolve a user-supplied deploy path safely inside DEPLOY_DIR.
// Returns the absolute path or null if the path tries to escape.
function resolveSafeDeployPath(filepath) {
    if (typeof filepath !== 'string' || filepath.length === 0) return null;
    // Reject NUL bytes and absolute paths outright.
    if (filepath.includes('\0') || path.isAbsolute(filepath)) return null;
    const resolved = path.resolve(DEPLOY_DIR, filepath);
    // Ensure resolved path is inside DEPLOY_DIR (with trailing separator to avoid prefix trickery).
    const rootWithSep = DEPLOY_DIR.endsWith(path.sep) ? DEPLOY_DIR : DEPLOY_DIR + path.sep;
    if (resolved !== DEPLOY_DIR && !resolved.startsWith(rootWithSep)) return null;
    return resolved;
}

// PUT /api/deploy/:filepath(*) - Deploy static file to static/app/
app.put('/api/deploy/:filepath(*)', requireDeployAuth, express.raw({
    type: () => true,
    limit: DEPLOY_MAX_BYTES
}), async (req, res) => {
    const safePath = resolveSafeDeployPath(req.params.filepath);
    if (!safePath) {
        return res.status(403).json({ error: 'Invalid path' });
    }
    try {
        await fs.promises.mkdir(path.dirname(safePath), { recursive: true });
        await fs.promises.writeFile(safePath, req.body || Buffer.alloc(0));
        res.json({ success: true, path: `/app/${req.params.filepath}` });
    } catch (err) {
        console.error('[Deploy] write failed:', err);
        res.status(500).json({ error: 'Upload failed' });
    }
});

// Serve deployed app at /app/
app.use('/app', express.static(DEPLOY_DIR));

// GET /api/deploy/list - List deployed files (iterative, async, capped depth)
app.get('/api/deploy/list', requireDeployAuth, async (req, res) => {
    const MAX_DEPTH = 8;
    const files = [];
    try {
        // Iterative BFS walk to avoid stack overflow on deep trees.
        const queue = [{ dir: DEPLOY_DIR, rel: '', depth: 0 }];
        while (queue.length > 0) {
            const { dir, rel, depth } = queue.shift();
            if (depth > MAX_DEPTH) continue;
            let entries;
            try {
                entries = await fs.promises.readdir(dir, { withFileTypes: true });
            } catch (err) {
                continue; // skip unreadable subdirs
            }
            for (const entry of entries) {
                const childRel = rel ? `${rel}/${entry.name}` : entry.name;
                if (entry.isDirectory()) {
                    queue.push({ dir: path.join(dir, entry.name), rel: childRel, depth: depth + 1 });
                } else if (entry.isFile()) {
                    files.push(childRel);
                }
            }
        }
        res.json({ files });
    } catch (err) {
        console.error('[Deploy] list failed:', err);
        res.status(500).json({ error: 'List failed' });
    }
});
app.use(express.json());

// ============================================================
// REST API
// ============================================================

// GET /api/status - Server status
app.get('/api/status', (req, res) => {
    res.json({
        status: 'online',
        uptime: process.uptime(),
        agents: AGENTS.size,
        clients: CLIENTS.size,
        version: '1.0.0',
        hasPassword: !!ACCESS_PASSWORD,
        // Diag-only: server's wall clock (Date.now). Used to detect
        // clock skew between server and agent. The agent can call
        // this and compare to its own time.time()*1000 to measure
        // skew. (Real "network RTT" excludes the skew term, but
        // Date.now()-msg.ts on the keepalive handler measures
        // skew + 1-way RTT together, which is what the existing
        // /api/agents.lastRttMs reports. We do not fix the skew
        // in code — NTP is the proper fix — but we expose the
        // raw clocks so the skew is observable.)
        serverNowMs: Date.now(),
        nodeVersion: process.version,
    });
});

// GET /api/agent/ping - HTTP heartbeat from agent (fallback when WS send fails)
// Agent calls this every 30s to stay alive even if screen capture is failing
app.get('/api/agent/ping', (req, res) => {
    const { agentId } = req.query;
    if (!agentId) {
        return res.status(400).json({ error: 'agentId required' });
    }
    const agent = AGENTS.get(agentId);
    if (agent) {
        agent.lastSeen = Date.now();
        res.json({ ok: true, agentId });
    } else {
        res.status(404).json({ error: 'agent not found' });
    }
});

// POST /api/verify-password - Verify server access password
app.post('/api/verify-password', (req, res) => {
    const { password } = req.body;
    if (!password) {
        return res.status(400).json({ error: 'Password required' });
    }
    if (password !== ACCESS_PASSWORD) {
        return res.status(401).json({ error: 'Invalid password' });
    }
    // Generate a session token valid for 1 hour
    const token = uuidv4();
    PASSWORD_TOKENS.set(token, { createdAt: Date.now(), expiresAt: Date.now() + 3600000 });
    res.json({ success: true, token });
});

// GET /api/agents - List online agents (password protected)
app.get('/api/agents', (req, res) => {
    const auth = req.headers['authorization'] || '';
    const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    // Decode base64 password
    let password = '';
    try { password = Buffer.from(token, 'base64').toString('utf8'); } catch {}
    if (password !== ACCESS_PASSWORD) {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    const agents = Array.from(AGENTS.values()).map(a => {
        // Three metric families, all from the keepalive handler's
        // rolling windows (<=20 samples each):
        //
        //   rttSamples / rttAvgMs / rttMaxMs  (oneWayRttMs):
        //     Date.now() - msg.ts*1000, i.e. clock skew + one-way
        //     RTT. A large value here (e.g. 600ms when ICMP ping
        //     is 16ms) is the NTP drift signal — see
        //     lastClockSkewMs to disambiguate.
        //
        //   skewSamples / skewAvgMs / skewMaxMs  (clockSkewMs):
        //     Same number rounded separately so the dashboard
        //     can color the skew term red on its own.
        //
        //   procSamples / procAvgMs / procMaxMs  (serverProcMs):
        //     process.hrtime.bigint() delta between
        //     keepalive-received and ack-sent. Monotonic, not
        //     subject to wall clock drift. Should be <5ms on a
        //     healthy node. If this creeps up the node is the
        //     bottleneck, not the network.
        //
        // The legacy oneWayRttMs field is kept under
        // `lastRttMs` / `rttAvgMs` / `rttMaxMs` for backward
        // compat — operators who already know the units of
        // `rttAvgMs` see the same number they used to.
        const rtts = a.rttSamples || [];
        const rttAvg = rtts.length ? Math.round(rtts.reduce((s, v) => s + v, 0) / rtts.length) : null;
        const rttMax = rtts.length ? Math.max(...rtts) : null;
        const skews = a.skewSamples || [];
        const skewAvg = skews.length ? Math.round(skews.reduce((s, v) => s + v, 0) / skews.length) : null;
        const skewMax = skews.length ? Math.max(...skews) : null;
        const procs = a.procSamples || [];
        const procAvg = procs.length ? Math.round((procs.reduce((s, v) => s + v, 0) / procs.length) * 1000) / 1000 : null;
        const procMax = procs.length ? Math.max(...procs) : null;
        return {
            agentId: a.info.agentId,
            hostname: a.info.hostname,
            os: a.info.os,
            lastSeen: a.lastSeen,
            lastKeepaliveAt: a.lastKeepaliveAt || null,
            // Legacy / one-way RTT (includes clock skew)
            lastRttMs: a.lastRttMs || null,
            rttAvgMs: rttAvg,
            rttMaxMs: rttMax,
            rttSamples: rtts.length,
            // New: clock skew term (wall clock diff, monotonic-free)
            lastClockSkewMs: a.lastClockSkewMs || null,
            skewAvgMs: skewAvg,
            skewMaxMs: skewMax,
            skewSamples: skews.length,
            // New: server processing time (monotonic, ms, 3dp)
            lastServerProcMs: a.lastServerProcMs || null,
            procAvgMs: procAvg,
            procMaxMs: procMax,
            procSamples: procs.length,
            online: a.ws && a.ws.readyState === 1
        };
    });
    res.json({ agents });
});

// POST /api/agents/:agentId/auth - Authenticate agent
app.post('/api/agents/:agentId/auth', (req, res) => {
    const { agentId } = req.params;
    const { secret } = req.body;
    
    const agent = AGENTS.get(agentId);
    if (!agent) {
        return res.status(404).json({ error: 'Agent not found or offline' });
    }
    if (agent.info.secret !== secret) {
        return res.status(401).json({ error: 'Invalid secret' });
    }
    
    // Generate access token for browser clients
    const accessToken = uuidv4();
    SESSIONS.set(accessToken, { agentId, type: 'access' });
    
    res.json({ 
        success: true, 
        accessToken,
        agentInfo: {
            hostname: agent.info.hostname,
            os: agent.info.os,
            agentId: agent.info.agentId
        }
    });
});

// GET /api/files - List uploaded files
app.get('/api/files', (req, res) => {
    const files = fs.readdirSync(UPLOAD_DIR).map(f => {
        const stat = fs.statSync(path.join(UPLOAD_DIR, f));
        return {
            name: f,
            size: stat.size,
            modified: stat.mtime
        };
    });
    res.json({ files });
});

// File upload configuration
// Sanitize the original name to strip path separators/parent refs so the
// stored filename can't smuggle "../" segments (defense in depth — the file
// is already confined to UPLOAD_DIR, but downstream consumers of the name
// should not see traversal sequences).
function sanitizeFilename(name) {
    if (typeof name !== 'string') return 'file';
    // Strip NUL bytes and control chars FIRST so path.basename doesn't choke
    // (Windows path APIs reject NUL bytes in filenames).
    const cleaned = name.replace(/[\x00-\x1f]/g, '');
    // Then strip any path components.
    const base = path.basename(cleaned);
    return base.length > 0 ? base : 'file';
}

const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, UPLOAD_DIR),
    filename: (req, file, cb) => cb(null, `${Date.now()}-${sanitizeFilename(file.originalname)}`)
});
const upload = multer({ storage, limits: { fileSize: 500 * 1024 * 1024 } }); // 500MB max

// POST /api/upload - Upload file
app.post('/api/upload', upload.single('file'), (req, res) => {
    if (!req.file) {
        return res.status(400).json({ error: 'No file uploaded' });
    }
    
    const { agentId } = req.body;
    const agent = AGENTS.get(agentId);
    
    // Notify agent about available file
    if (agent && agent.ws.readyState === 1) {
        agent.ws.send(JSON.stringify({
            type: 'file_available',
            filename: req.file.filename,
            originalName: req.file.originalname,
            size: req.file.size,
            path: req.body.targetPath || ''
        }));
    }
    
    res.json({ 
        success: true, 
        filename: req.file.filename,
        originalName: req.file.originalname,
        size: req.file.size
    });
});

// GET /api/download/:filename - Download file from server
app.get('/api/download/:filename', (req, res) => {
    const filename = path.basename(req.params.filename);
    const filepath = path.join(UPLOAD_DIR, filename);
    
    if (!fs.existsSync(filepath)) {
        return res.status(404).json({ error: 'File not found' });
    }
    
    res.download(filepath, filename);
});

// DELETE /api/files/:filename - Delete file
app.delete('/api/files/:filename', (req, res) => {
    const filename = path.basename(req.params.filename);
    const filepath = path.join(UPLOAD_DIR, filename);
    
    if (!fs.existsSync(filepath)) {
        return res.status(404).json({ error: 'File not found' });
    }
    
    fs.unlinkSync(filepath);
    res.json({ success: true });
});

// ============================================================
// Diag dump API (Flutter App -> server -> DIAG_DIR)
// ============================================================
// Password-protected (same as /api/agents). Lists / downloads the
// on-device log dumps the App proactively uploads. Each dump is
// a `<agentId>/<ts>-<trigger>.log` pair with a sidecar `.json`.
//
// Layout example:
//   DIAG_DIR/
//     WEI3216/
//       2026-06-05T07-34-12-123Z-auto.log
//       2026-06-05T07-34-12-123Z-auto.json
//       2026-06-05T07-39-12-456Z-periodic.log
//       ...
//     _noagent/                    # user clicked Upload before binding
//       2026-06-05T08-01-00-000Z-manual.log
//
// The 'trigger' suffix lets `ls DIAG_DIR/agent/ | sort` surface
// error dumps first (lexically 'error' < 'manual' < 'periodic').

// GET /api/diag - List all diag dumps, optionally filtered by agentId
// Returns: { agents: [{ agentId, files: [{ name, bytes, mtime, meta? }] }] }
app.get('/api/diag', requireDeployAuth, async (req, res) => {
    try {
        const filter = req.query.agentId ? _safeAgentDirName(req.query.agentId) : null;
        const agents = [];
        const entries = await fs.promises.readdir(DIAG_DIR, { withFileTypes: true });
        for (const e of entries) {
            if (!e.isDirectory()) continue;
            if (filter && e.name !== filter) continue;
            const dir = path.join(DIAG_DIR, e.name);
            const files = [];
            let names;
            try { names = await fs.promises.readdir(dir); } catch (err) { continue; }
            for (const n of names) {
                if (!n.endsWith('.log')) continue;
                const stat = await fs.promises.stat(path.join(dir, n));
                const metaPath = path.join(dir, n.replace(/\.log$/, '.json'));
                let meta = null;
                try { meta = JSON.parse(await fs.promises.readFile(metaPath, 'utf8')); } catch (err) { /* sidecar missing is fine */ }
                files.push({
                    name: n,
                    bytes: stat.size,
                    mtime: stat.mtime.toISOString(),
                    meta,
                });
            }
            files.sort((a, b) => b.mtime.localeCompare(a.mtime));
            agents.push({ agentId: e.name, files });
        }
        agents.sort((a, b) => a.agentId.localeCompare(b.agentId));
        res.json({ agents, totalFiles: agents.reduce((s, a) => s + a.files.length, 0) });
    } catch (err) {
        console.error('[Diag] list failed:', err);
        res.status(500).json({ error: 'list failed' });
    }
});

// GET /api/diag/latest?agentId=xxx - Get the most recent .log
// for an agent, plus its sidecar meta. Returns 404 if no uploads
// yet for that agent.
app.get('/api/diag/latest', requireDeployAuth, async (req, res) => {
    try {
        const agentId = _safeAgentDirName(req.query.agentId);
        const dir = path.join(DIAG_DIR, agentId);
        const names = await fs.promises.readdir(dir).catch(() => []);
        const logs = names.filter(n => n.endsWith('.log')).sort().reverse();
        if (logs.length === 0) return res.status(404).json({ error: 'no diag files' });
        const latest = logs[0];
        const stat = await fs.promises.stat(path.join(dir, latest));
        const meta = JSON.parse(await fs.promises.readFile(path.join(dir, latest.replace(/\.log$/, '.json')), 'utf8').catch(() => 'null'));
        res.json({ agentId, name: latest, bytes: stat.size, mtime: stat.mtime.toISOString(), meta });
    } catch (err) {
        console.error('[Diag] latest failed:', err);
        res.status(500).json({ error: 'latest failed' });
    }
});

// GET /api/diag/download?agentId=xxx&name=yyy - Stream the raw .log
// file. name is path.basename'd twice (once in the query parser, once
// in the agentId sanitizer) to ensure the resulting path stays
// inside DIAG_DIR/<agentId>/. We don't allow directory traversal to
// leak files outside the per-agent folder.
app.get('/api/diag/download', requireDeployAuth, async (req, res) => {
    try {
        const agentId = _safeAgentDirName(req.query.agentId);
        const name = path.basename(String(req.query.name || ''));
        if (!name || !name.endsWith('.log')) {
            return res.status(400).json({ error: 'name (.log) required' });
        }
        const filePath = path.join(DIAG_DIR, agentId, name);
        // Defense in depth: confirm filePath is still under the per-agent dir.
        const agentDir = path.join(DIAG_DIR, agentId);
        const rootWithSep = agentDir.endsWith(path.sep) ? agentDir : agentDir + path.sep;
        if (filePath !== agentDir && !filePath.startsWith(rootWithSep)) {
            return res.status(403).json({ error: 'path traversal blocked' });
        }
        if (!fs.existsSync(filePath)) {
            return res.status(404).json({ error: 'file not found' });
        }
        res.download(filePath, name);
    } catch (err) {
        console.error('[Diag] download failed:', err);
        res.status(500).json({ error: 'download failed' });
    }
});

// ============================================================
// WebSocket Server (Socket.IO compatible)
// ============================================================

const wss = new WebSocketServer({ server });

// Heartbeat interval - also sends websocket pings to agents as keepalive
setInterval(() => {
    const now = Date.now();

    AGENTS.forEach((agent, id) => {
        // Send websocket ping to keep connection alive
        if (agent.ws && agent.ws.readyState === 1) {
            try { agent.ws.ping(); } catch (e) {}
        }
        // Check timeout (2 minutes for agents) -- pass-through
        // detection: if the agent has been silent for 2 minutes,
        // give up on it. NOT a 30s flash-disconnect -- 2 minutes
        // is long enough that any legitimate drop (sleep, network
        // blip, OS hibernation) will have self-recovered. We do
        // NOT close on smaller gaps because mid-test the user is
        // actively working and we don't want a 1-2s blip on the
        // App side to drop their in-progress drag.
        if (now - agent.lastSeen > 120000) {
            console.log(`[Agent] ${id} heartbeat timeout (no signal in 120s), removing`);
            AGENTS.delete(id);
        }
        // INPUT_SEQ_GAP: log only, do NOT force reconnect. We
        // discovered that any proactive close mid-session causes
        // the App's coordinate mapping / scale reference to
        // reset, and the next user click lands in the wrong
        // place. Better to keep the half-dead socket and let
        // the user restart the App if it gets really stuck.
        const sent = agent.inputSeq || 0;
        const acked = agent.lastInputAck || 0;
        const gap = sent - acked;
        if (gap > 50) {
            console.log(`[Agent] ${id} input seq gap: sent=${sent} acked=${acked} gap=${gap} (no auto-reconnect to avoid coordinate-mapping reset)`);
        }
    });

    CLIENTS.forEach((client, id) => {
        if (now - client.lastSeen > 120000) {
            console.log(`[Client] ${id} heartbeat timeout, removing`);
            CLIENTS.delete(id);
        }
    });
}, 5000);

// Sanitize an agentId for use as a subdirectory name. The agentId
// is set by the agent itself, so a malicious or buggy client
// could submit "../etc" or "foo/bar" -- strip path separators
// and any traversal pattern. Falls back to '_noagent' if empty
// (e.g. user clicked Upload before binding to an agent).
function _safeAgentDirName(agentId) {
    if (typeof agentId !== 'string' || agentId.length === 0) return '_noagent';
    // Strip NUL + control chars first so path.join doesn't choke.
    const cleaned = agentId.replace(/[\x00-\x1f]/g, '');
    // Replace any character that could break a path component
    // with '_'. Allows [A-Za-z0-9._-] which covers the normal
    // hostname + UUID-style ids the agent generates.
    const safe = cleaned.replace(/[^A-Za-z0-9._-]/g, '_');
    return safe.length > 0 ? safe : '_noagent';
}

// Sanitize a 'trigger' string for use as part of a filename.
function _safeTriggerName(trigger) {
    if (typeof trigger !== 'string' || trigger.length === 0) return 'unknown';
    return trigger.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 32) || 'unknown';
}

// Save an app_diag upload to disk. Layout:
//   DIAG_DIR/<agentId>/<timestamp>-<trigger>.log   -- the log text
//   DIAG_DIR/<agentId>/<timestamp>-<trigger>.json  -- metadata sidecar
// Returns { ok, path, error? }. Always acks the client with
// { type: 'diag_ack', ok, path } so the App's UI can surface a
// 'uploaded' / 'failed' toast (App only logs "queued" today;
// ack is wired so we can upgrade later without a wire change).
async function _handleAppDiag(ws, client, msg) {
    try {
        const agentId = _safeAgentDirName(client.agentId);
        const trigger = _safeTriggerName(msg.trigger || 'unknown');
        const ts = new Date().toISOString().replace(/[:.]/g, '-');
        const dir = path.join(DIAG_DIR, agentId);
        await fs.promises.mkdir(dir, { recursive: true });
        const base = `${ts}-${trigger}`;
        const logPath = path.join(dir, `${base}.log`);
        const metaPath = path.join(dir, `${base}.json`);

        const logs = typeof msg.logs === 'string' ? msg.logs : '';
        if (logs.length === 0) {
            // Empty upload is rejected -- otherwise a buggy client
            // could flood DIAG_DIR with empty files. The App's
            // logger should always have *something* by the time
            // the user can click Upload.
            console.warn(`[Diag] rejected empty upload from client ${client.id || '?'}`);
            try { ws.send(JSON.stringify({ type: 'diag_ack', ok: false, error: 'empty' })); } catch (e) {}
            return;
        }
        if (logs.length > DIAG_MAX_BYTES) {
            // Truncate to last DIAG_MAX_BYTES bytes (newline-aligned
            // where possible so we don't cut a log line in half).
            // Better to keep the most recent activity than to
            // reject outright -- the periodic 5min timer is the
            // main case that could grow this; it dumps the full
            // file log so on a busy session we may exceed.
            const overflow = logs.length - DIAG_MAX_BYTES;
            let start = overflow;
            const nl = logs.indexOf('\n', start);
            if (nl >= 0 && nl < overflow + 200) start = nl + 1;
            console.warn(`[Diag] truncated: ${logs.length} > ${DIAG_MAX_BYTES} bytes (kept tail)`);
            const truncated = logs.slice(start);
            await fs.promises.writeFile(logPath, truncated, 'utf8');
        } else {
            await fs.promises.writeFile(logPath, logs, 'utf8');
        }
        const meta = {
            receivedAt: new Date().toISOString(),
            agentId: client.agentId || null,
            clientId: client.id || null,
            trigger,
            appVersion: msg.appVersion || null,
            platform: msg.platform || null,
            capturedAt: msg.capturedAt || null,
            bytes: logs.length,
            context: msg.context || null,
        };
        await fs.promises.writeFile(metaPath, JSON.stringify(meta, null, 2), 'utf8');
        console.log(`[Diag] saved ${logPath} (${logs.length} bytes, trigger=${trigger})`);
        try { ws.send(JSON.stringify({ type: 'diag_ack', ok: true, path: logPath, bytes: logs.length })); } catch (e) {}
    } catch (err) {
        console.error('[Diag] save failed:', err.message);
        try { ws.send(JSON.stringify({ type: 'diag_ack', ok: false, error: err.message })); } catch (e) {}
    }
}

// ============================================================
// Agent WebSocket Handler
// ============================================================
// Agents connect to: ws://host/agent
// Message types: auth, screen, output, file_chunk

wss.on('connection', (ws, req) => {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const path = url.pathname;
    
    // Skip non-websocket paths
    if (path !== '/agent' && path !== '/client') return;
    
    console.log(`[WS] New connection: ${path} from ${req.socket.remoteAddress} ua="${(req.headers['user-agent'] || '').slice(0, 80)}"`);
    
    let authenticated = false;
    let agentId = null;
    let clientId = null;
    
    ws.on('message', (data) => {
        try {
            const msg = JSON.parse(data.toString());

            // Raw-receive log for /client connections: any message that
            // reaches ws.onmessage will be logged here, BEFORE any
            // try/catch swallowing or auth gating. This is the
            // "did it ever arrive" checkpoint for "input goes nowhere"
            // debugging. Throttled to one line per 5s per client to
            // avoid flooding on mouse move streams.
            if (path === '/client') {
                const now = Date.now();
                const last = _clientRawLogAt.get(clientId) || 0;
                if (now - last > 5000) {
                    _clientRawLogAt.set(clientId, now);
                    console.log(`[wsraw] client ${clientId || '<unauth>'} type=${msg.type} agentId=${msg.agentId || (clientId ? (CLIENTS.get(clientId) || {}).agentId : null)} keys=${Object.keys(msg).join(',')}`);
                }
            }

            // ----- AGENT CONNECTION -----
            if (path === '/agent') {
                if (msg.type === 'auth') {
                    // Agent registers with agentId + secret
                    const { agentId: aid, secret, hostname, os } = msg;
                    
                    // TODO: Validate secret against stored secrets
                    // For now, accept any new agent
                    
                    agentId = aid;
                    authenticated = true;  // Mark as authenticated so pong/screen messages are processed
                    AGENTS.set(agentId, {
                        ws,
                        info: { agentId: aid, hostname, os, secret },
                        lastSeen: Date.now(),
                        connectedAt: Date.now(),
                        remoteIp: req.socket.remoteAddress,
                        userAgent: req.headers['user-agent'] || ''
                    });
                    
                    ws.send(JSON.stringify({ type: 'auth_ok', agentId: aid }));
                    console.log(`[Agent] Registered: ${aid} (${hostname} ${os}) from ${req.socket.remoteAddress}`);
                    return;
                }
                
                if (!authenticated) {
                    ws.send(JSON.stringify({ type: 'error', message: 'Not authenticated' }));
                    return;
                }

                // Update lastSeen for ALL messages from authenticated agents
                const agent = AGENTS.get(agentId);
                if (agent) agent.lastSeen = Date.now();

                // Handle heartbeat/pong from agent (keepalive)
                if (msg.type === 'pong') {
                    const agent = AGENTS.get(agentId);
                    if (agent) agent.lastSeen = Date.now();
                    console.log(`[PONG] from ${agentId}, lastSeen updated`);
                    return;
                }

                // Business-level keepalive from the agent. Refreshes
                // lastSeen on the AGENTS map (same effect as PONG), so
                // the AGENT_TIMEOUT_CLEANUP loop won't reap an agent
                // that is actively sending keepalives. Pair this with
                // the inbound liveness check in the client->agent
                // relay path (see _isAgentLive) so we never write
                // mouse/key into a half-dead socket.
                //
                // We also send back a {'type':'keepalive_ack'} so the
                // agent gets a round-trip signal: if the underlying
                // WS is half-dead on the outbound direction (server
                // can't actually deliver to agent), the agent won't
                // see the ack and can close + reconnect on its own.
                // Without this, a server-side silent half-close would
                // freeze the agent's _ws.recv() until 3600s timeout.
                if (msg.type === 'keepalive') {
                    const agent = AGENTS.get(agentId);
                    if (agent) {
                        agent.lastSeen = Date.now();
                        // Clock + RTT bookkeeping. Three numbers:
                        //
                        //   * serverProcMs  — how long server spent
                        //     parsing the keepalive, computing the
                        //     RTT/skew, and pushing the ack into the
                        //     WS outgoing queue. Measured with
                        //     process.hrtime.bigint() (monotonic) so
                        //     it is wall-clock-skew free.
                        //     Expected ~0.1-1ms on a healthy node.
                        //
                        //   * clockSkewMs   — Date.now() - msg.ts*1000.
                        //     This is the diff between server's wall
                        //     clock and the agent's wall clock at the
                        //     moment server received the keepalive, MINUS
                        //     one-way network RTT. With a 16ms ICMP
                        //     ping and a 600ms skew, this reads ~616ms
                        //     (skew dominates, network RTT is small).
                        //     Catching a >100ms skew here is the
                        //     signal that VPS NTP is broken or that
                        //     something is wrong with one of the
                        //     clocks. The fix is `apt install chrony`
                        //     (or whatever the VPS distro uses), not
                        //     anything in this codebase.
                        //
                        //   * oneWayRttMs   — the legacy single
                        //     number, kept for backward compat with
                        //     any caller reading /api/agents.lastRttMs.
                        //     = clockSkewMs + (real one-way RTT).
                        //     The agent side computes the *real*
                        //     round-trip RTT in its own clock
                        //     (typically 22-50ms for this deployment,
                        //     see ws_bridge._rtt_samples_ms) so the
                        //     discrepancy between server's oneWayRttMs
                        //     and agent's rtt_avg is the skew signal.
                        //
                        // All three are pushed into their own rolling
                        // window of <=20 samples for /api/agents.
                        const recvMonoNs = process.hrtime.bigint();
                        const recvAtMs = Date.now();
                        if (typeof msg.ts === 'number') {
                            const oneWayRtt = Math.round((recvAtMs / 1000 - msg.ts) * 1000);
                            const clockSkew = Math.round(recvAtMs - msg.ts * 1000);
                            agent.lastRttMs = oneWayRtt;          // legacy name
                            agent.lastClockSkewMs = clockSkew;    // new: wall-clock skew term
                            agent.rttSamples = (agent.rttSamples || []);
                            agent.rttSamples.push(oneWayRtt);
                            if (agent.rttSamples.length > 20) agent.rttSamples.shift();
                            agent.skewSamples = (agent.skewSamples || []);
                            agent.skewSamples.push(clockSkew);
                            if (agent.skewSamples.length > 20) agent.skewSamples.shift();
                        }
                        agent.lastKeepaliveAt = recvAtMs;
                        try {
                            if (agent.ws.readyState === 1) {
                                // CONTRACT: keepalive_ack MUST echo seq back to
                                // the agent. Older server versions only sent
                                // ts, which caused the agent's seq-based probe
                                // matcher to always read 0 and force-reconnect
                                // every 5s. The agent still falls back to a
                                // ts-window match for safety, but this field is
                                // the canonical signal. We additionally
                                // echo `serverRecvAtMs` so the agent can
                                // observe the server's wall clock and
                                // compute clock skew on its side (a
                                // simple `serverRecvAtMs - msg.ts*1000`
                                // gives the same number as
                                // lastClockSkewMs above, exposed two
                                // ways for cross-checking).
                                const ack = JSON.stringify({
                                    type: 'keepalive_ack',
                                    seq: msg.seq,
                                    ts: msg.ts,
                                    serverRecvAtMs: recvAtMs,
                                });
                                agent.ws.send(ack);
                                // Measure server processing time
                                // between recv and ack-pushed-to-ws.
                                const sendMonoNs = process.hrtime.bigint();
                                const procMs = Number(sendMonoNs - recvMonoNs) / 1e6;
                                agent.lastServerProcMs = Math.round(procMs * 1000) / 1000; // 3 dp
                                agent.procSamples = (agent.procSamples || []);
                                agent.procSamples.push(agent.lastServerProcMs);
                                if (agent.procSamples.length > 20) agent.procSamples.shift();
                                console.log(`[keepalive] from ${agentId} seq=${msg.seq} clockSkew=${agent.lastClockSkewMs}ms oneWayRtt=${agent.lastRttMs}ms proc=${agent.lastServerProcMs}ms ack_sent`);
                            }
                        } catch (e) {}
                    }
                    return;
                }
                if (msg.type === 'keepalive_ack') {
                    // Diagnostic: the server-side _send might appear to
                    // succeed but the agent never sees the ack. Log the
                    // ack arrival here as the other half of the round
                    // trip so a half-dead socket is observable in logs.
                    const agent = AGENTS.get(agentId);
                    if (agent) agent.lastSeen = Date.now();
                    console.log(`[keepalive_ack] from ${agentId} seq=${msg.seq}`);
                    return;
                }
                if (msg.type === 'input_ack') {
                    // The agent tells us the highest input message seq
                    // it actually processed. We use this to detect a
                    // server->agent half-close: if the agent is still
                    // acking (proving the ws is alive in the inbound
                    // direction) but the seq it's reporting is far
                    // behind what we sent, the outbound direction is
                    // dropping message frames.
                    const agent = AGENTS.get(agentId);
                    if (agent) {
                        agent.lastSeen = Date.now();
                        agent.lastInputAck = msg.lastSeenSeq || 0;
                    }
                    return;
                }

                // Handle screen frame
                if (msg.type === 'screen') {

                    // Relay to all connected clients viewing this agent.
                    // The agent's screen message may be a full keyframe
                    // ({fmt:'kf', data:base64(jpeg), w, h}) or a delta
                    // ({fmt:'df', data:base64(pixel_data), regions:[[x,y,w,h],...]}).
                    // Forward all fields; the browser client decides how to render.
                    const relay = {
                        type: 'screen',
                        data: msg.data,
                        quality: msg.quality,
                        timestamp: msg.timestamp,
                        ...(msg.fmt     !== undefined && { fmt: msg.fmt }),
                        ...(msg.regions !== undefined && { regions: msg.regions }),
                        ...(msg.w       !== undefined && { w: msg.w }),
                        ...(msg.h       !== undefined && { h: msg.h }),
                        ...(msg.ts      !== undefined && { src_ts: msg.ts }),
                        ...(msg.seq     !== undefined && { seq: msg.seq }),
                    };
                    CLIENTS.forEach((client) => {
                        if (client.agentId === agentId && client.ws.readyState === 1) {
                            client.ws.send(JSON.stringify(relay));
                        }
                    });
                    return;
                }
                
                // Handle command output
                if (msg.type === 'output') {
                    const agent = AGENTS.get(agentId);
                    if (agent) agent.lastSeen = Date.now();
                    
                    // Relays output to the client that initiated this session
                    if (msg.session) {
                        const session = SESSIONS.get(msg.session);
                        if (session && session.clientId) {
                            const client = CLIENTS.get(session.clientId);
                            if (client && client.ws.readyState === 1) {
                                client.ws.send(JSON.stringify({
                                    type: 'output',
                                    session: msg.session,
                                    data: msg.data,
                                    done: msg.done
                                }));
                            }
                        }
                    }
                    return;
                }
                
                // Handle file chunk from agent
                if (msg.type === 'file_chunk') {
                    if (msg.session) {
                        const session = SESSIONS.get(msg.session);
                        if (session && session.clientId) {
                            const client = CLIENTS.get(session.clientId);
                            if (client && client.ws.readyState === 1) {
                                client.ws.send(JSON.stringify({
                                    type: 'file_chunk',
                                    session: msg.session,
                                    chunk: msg.chunk,
                                    done: msg.done,
                                    filename: msg.filename
                                }));
                            }
                        }
                    }
                    return;
                }

                // Handle clipboard response from agent
                // (clipboard set/get — no sessionId; the agent's
                //  response goes to ALL clients viewing this agent.)
                if (msg.type === 'clipboard') {
                    CLIENTS.forEach((client) => {
                        if (client.agentId === agentId && client.ws.readyState === 1) {
                            client.ws.send(JSON.stringify({
                                type: 'clipboard',
                                action: msg.action,
                                ok: msg.ok,
                                content: msg.content,
                                bytes: msg.bytes,
                                error: msg.error
                            }));
                        }
                    });
                    return;
                }
            }
            
            // ----- CLIENT CONNECTION -----
            if (path === '/client') {
                if (msg.type === 'auth') {
                    // Client authenticates with server password + agentId
                    const { password, agentId: targetAgentId } = msg;
                    
                    // Step 1: Verify server access password
                    if (!password || password !== ACCESS_PASSWORD) {
                        ws.send(JSON.stringify({ type: 'auth_failed', message: 'Invalid server password' }));
                        ws.close();
                        console.log(`[Client] Failed auth attempt from ${req.socket.remoteAddress}`);
                        return;
                    }
                    
                    // Step 2: Verify agent exists and is online
                    const targetAgent = AGENTS.get(targetAgentId);
                    if (!targetAgent) {
                        ws.send(JSON.stringify({ type: 'agent_offline' }));
                        ws.close();
                        return;
                    }
                    
                    clientId = uuidv4();
                    CLIENTS.set(clientId, {
                        ws,
                        agentId: targetAgentId,
                        info: { connectedAt: Date.now() },
                        lastSeen: Date.now()
                    });
                    
                    ws.send(JSON.stringify({ 
                        type: 'auth_ok',
                        clientId,
                        agentInfo: {
                            hostname: targetAgent.info.hostname,
                            os: targetAgent.info.os,
                            agentId: targetAgentId
                        }
                    }));
                    
                    console.log(`[Client] ${clientId} authenticated for agent ${targetAgentId} (hostname=${targetAgent.info.hostname} os=${targetAgent.info.os})`);
                    // Also report the underlying ip for client -> agent debugging
                    console.log(`[Client]   client_ip=${req.socket.remoteAddress} agent_online=true frame_buffered=${targetAgent._buffered ? 'yes' : 'no'}`);
                    return;
                }
                
                if (!clientId) {
                    ws.send(JSON.stringify({ type: 'error', message: 'Not authenticated' }));
                    return;
                }
                
                // Update last seen
                const client = CLIENTS.get(clientId);
                if (client) client.lastSeen = Date.now();

                // ---- App diagnostic log upload (Flutter App -> server) ----
                // NOT forwarded to the agent: the agent is the Windows
                // desktop, the diag is the phone's log file. The agent
                // has no use for it; the server is the natural
                // collector. Save to DIAG_DIR/<agentId>/<ts>-<trigger>.log
                // (or <_noagent>/ if the user hasn't bound to an
                // agent yet -- e.g. they hit "Upload Logs" right
                // after the auth_ok landing screen). Metadata goes
                // into a sidecar <same-stem>.json so the operator
                // can see trigger / appVersion / context without
                // opening the log file.
                if (msg.type === 'app_diag') {
                    // Fire-and-forget: _handleAppDiag acks the
                    // client itself and writes to disk async. The
                    // outer 'message' handler is sync (Node ws
                    // doesn't deliver messages in async order
                    // without explicit queuing), so we just kick
                    // off the work and return. Errors inside
                    // _handleAppDiag are caught and turned into
                    // a diag_ack, so nothing escapes.
                    _handleAppDiag(ws, client, msg).catch(err => {
                        console.error('[Diag] unhandled:', err.message);
                    });
                    return;
                }

                // Forward commands to agent
                // Also forward 'req_kf' (keyframe request from client) so
                // the agent can immediately push a fresh kf instead of
                // waiting for its 3-second keyframe interval.
                if (['mouse', 'key', 'exec', 'file_request', 'clipboard', 'req_kf', 'subscribe', 'ping'].includes(msg.type)) {
                    STATS.totalRecv += 1;
                    const targetAgent = AGENTS.get(client.agentId);
                    // Liveness gate for input-bearing messages. The agent
                    // sends a business-level keepalive (see ws.onmessage
                    // 'keepalive' handler) every 25s once authed. If we
                    // haven't seen one in 30s, the WS socket is almost
                    // certainly half-dead (server side still believes it's
                    // OPEN because Node's ws.send() buffers successfully
                    // into a dead socket). Drop the message and tell the
                    // client to re-subscribe, instead of silently
                    // consuming events that the agent will never see.
                    if (targetAgent && (msg.type === 'mouse' || msg.type === 'key')) {
                        const ageMs = Date.now() - (targetAgent.lastSeen || 0);
                        if (ageMs > 30000) {
                            console.log(`[relay] DROPPED ${msg.type}: agent ${client.agentId} not live (lastSeen ${Math.round(ageMs/1000)}s ago, no keepalive in window)`);
                            // Intentionally don't bump totalFwd -- this never
                            // reached the agent. Tell the client to give up
                            // and let the user retry instead of pretending
                            // the message was forwarded.
                            try { ws.send(JSON.stringify({ type: 'agent_offline', reason: 'keepalive_timeout' })); } catch (e) {}
                            return;
                        }
                        // Check the underlying TCP socket. Node's `ws`
                        // exposes `readyState=1` for a long time after
                        // the OS has actually half-closed the socket:
                        // PING/PONG control frames still flow (the ws
                        // library handles those at a lower layer than
                        // send()'s message queue) but application
                        // message frames stop being delivered. The
                        // signature is: send queue grows unbounded
                        // (`ws.bufferedAmount`) while agent-side
                        // `recv()` shows nothing. Inspect both the
                        // socket fd and the bufferedAmount to catch
                        // this before sending the next message.
                        // Check the underlying TCP socket. Node's `ws`
                        // exposes `readyState=1` for a long time after
                        // the OS has actually half-closed the socket:
                        // PING/PONG control frames still flow (the ws
                        // library handles those at a lower layer than
                        // send()'s message queue) but application
                        // message frames stop being delivered. The
                        // signature is: send queue grows unbounded
                        // (`ws.bufferedAmount`) while agent-side
                        // `recv()` shows nothing. Inspect both the
                        // socket fd and the bufferedAmount to catch
                        // this -- but DO NOT force-close: any proactive
                        // close mid-session resets the App's coordinate
                        // mapping / scale reference and the next user
                        // click lands in the wrong place. Drop this
                        // single message and let the next one try.
                        const sock = targetAgent.ws._socket;
                        if (!sock || sock.destroyed || !sock.writable || !sock.readable) {
                            console.log(`[relay] DROPPED ${msg.type}: agent ${client.agentId} socket fd looks dead (destroyed=${sock && sock.destroyed} writable=${sock && sock.writable} readable=${sock && sock.readable}) -- dropping message, NOT closing (avoid coordinate-mapping reset)`);
                            STATS.totalFwd -= 1;
                            return;
                        }
                        if (targetAgent.ws.bufferedAmount > 1024 * 1024) {
                            console.log(`[relay] DROPPED ${msg.type}: agent ${client.agentId} send queue backed up (bufferedAmount=${targetAgent.ws.bufferedAmount} bytes) -- dropping message, NOT closing (avoid coordinate-mapping reset)`);
                            STATS.totalFwd -= 1;
                            return;
                        }
                    }
                    // Per-relay visibility log. The agent is the one that
                    // actually executes these, so server-side we just need
                    // to confirm we received it from the client and
                    // forwarded it. Helps diagnose "input goes nowhere"
                    // cases where the client sends something but it gets
                    // dropped before reaching the helper.
                    if (msg.type === 'mouse') {
                        console.log(`[relay] mouse ${msg.action} (${msg.x},${msg.y}) ${msg.button} -> agent ${client.agentId}`);
                    } else if (msg.type === 'key') {
                        console.log(`[relay] key ${msg.action} '${msg.key}' -> agent ${client.agentId}`);
                    } else if (msg.type === 'exec') {
                        // Truncate command for log readability
                        const cmd = (msg.command || '').toString();
                        const cmdTrunc = cmd.length > 60 ? cmd.slice(0, 60) + '...' : cmd;
                        console.log(`[relay] exec '${cmdTrunc}' (cwd=${msg.cwd || '-'}) -> agent ${client.agentId}`);
                    } else if (msg.type === 'file_request') {
                        console.log(`[relay] file_request op=${msg.op || msg.action || '?'} path='${msg.path || msg.target || '?'}' -> agent ${client.agentId}`);
                    } else if (msg.type === 'clipboard') {
                        const text = (msg.text || '').toString();
                        const txtTrunc = text.length > 60 ? text.slice(0, 60) + '...' : text;
                        console.log(`[relay] clipboard ${msg.action || 'set'} '${txtTrunc}' -> agent ${client.agentId}`);
                    } else if (msg.type === 'req_kf' || msg.type === 'subscribe') {
                        console.log(`[relay] ${msg.type} -> agent ${client.agentId}`);
                    } else if (msg.type === 'ping') {
                        // No log per ping -- 10s heartbeats would flood.
                    }
                    if (targetAgent && targetAgent.ws.readyState === 1) {
                        // Create session for commands that need a server-side session
                        // so the agent's subsequent file_chunk/output can be routed back.
                        // - exec: server generates sessionId (cmd → output)
                        // - file_request: reuse client-provided sessionId (file_request → file_chunk)
                        //   The client (index.html doDownload) already generates
                        //   'dl_' + Date.now() as the session id, so we can keep it.
                        STATS.totalFwd += 1;
                        // Stamp every input-bearing message (mouse/key/exec/
                        // file_request/clipboard) with a monotonic input seq
                        // and remember the last seq we sent. The agent will
                        // echo back the last seq it actually processed
                        // (input_ack). If the gap (sent - acked) grows
                        // beyond a small window we know the outbound
                        // direction is half-dead: PONGs still flow but
                        // message frames are being swallowed. This is the
                        // only signal that reliably catches a silent
                        // half-close at interactive latencies, since TCP
                        // backpressure / bufferedAmount / readyState all
                        // happily lie about a half-closed socket.
                        if (['mouse', 'key', 'exec', 'file_request', 'clipboard'].includes(msg.type)) {
                            targetAgent.inputSeq = (targetAgent.inputSeq || 0) + 1;
                            msg.seq = targetAgent.inputSeq;
                            msg.lastAck = targetAgent.lastInputAck || 0;
                        }
                        if (msg.type === 'exec' && msg.cmd) {
                            const sessionId = uuidv4();
                            SESSIONS.set(sessionId, { agentId: client.agentId, clientId, type: 'exec' });
                            targetAgent.ws.send(JSON.stringify({ ...msg, session: sessionId }));
                        } else if (msg.type === 'file_request' && msg.session) {
                            // Register the client-supplied sessionId so file_chunk
                            // (sent later by the agent) can be routed back to this client.
                            SESSIONS.set(msg.session, {
                                agentId: client.agentId,
                                clientId,
                                type: 'file_request'
                            });
                            targetAgent.ws.send(JSON.stringify(msg));
                        } else {
                            targetAgent.ws.send(JSON.stringify(msg));
                        }
                    } else {
                        // 'agent_offline' here is the routing-failure
                        // signal, not the heartbeat-timeout one. The
                        // client hasn't bound itself to a target via
                        // 'subscribe' yet, OR the agent is down. Log
                        // the distinction so the operator can tell
                        // them apart from the journal alone.
                        if (!client.agentId) {
                            console.log(`[relay] DROPPED ${msg.type} from client ${clientId}: not subscribed to any agent yet`);
                        } else {
                            console.log(`[relay] DROPPED ${msg.type} -> agent ${client.agentId}: agent not connected`);
                        }
                        ws.send(JSON.stringify({ type: 'agent_offline' }));
                    }
                    return;
                }
            }
            
        } catch (err) {
            console.error('[WS] Parse error:', err.message);
        }
    });
    
    ws.on('close', (code, reason) => {
        const reasonStr = reason ? reason.toString().slice(0, 80) : '';
        if (agentId) {
            const entry = AGENTS.get(agentId);
            const uptime = entry && entry.connectedAt ? ((Date.now() - entry.connectedAt) / 1000).toFixed(0) : '?';
            console.log(`[Agent] Disconnected: ${agentId} (uptime=${uptime}s code=${code} reason="${reasonStr}")`);
            AGENTS.delete(agentId);
        }
        if (clientId) {
            const entry = CLIENTS.get(clientId);
            const dur = entry && entry.connectedAt ? ((Date.now() - entry.connectedAt) / 1000).toFixed(0) : '?';
            console.log(`[Client] Disconnected: ${clientId} (dur=${dur}s code=${code} reason="${reasonStr}")`);
            CLIENTS.delete(clientId);
        }
    });
    
    ws.on('error', (err) => {
        console.error(`[WS] Error (${path}):`, err.message);
    });
});

// ============================================================
// Start Server
// ============================================================

server.listen(PORT, () => {
    const startTime = new Date().toISOString();
    console.log(`
╔══════════════════════════════════════════════════════╗
║       Remote Control Relay Server v1.0              ║
╠══════════════════════════════════════════════════════╣
║  HTTP/WebSocket Port: ${PORT}                          ║
║  Web Interface:      http://localhost:${PORT}          ║
║  Agent Endpoint:     ws://host:${PORT}/agent            ║
║  Client Endpoint:    ws://host:${PORT}/client           ║
║  Started:            ${startTime}      ║
║  Node:               ${process.version}                  ║
║  PID:                ${process.pid}                       ║
╚══════════════════════════════════════════════════════╝
    `);
    // Aggregate stats every 30s. Mirrors the agent's heartbeat but
    // for the relay itself: total messages, unique agents/clients,
    // peak ws count, dropped/forwards.
    let lastStats = { up: 0, recv: 0, fwd: 0, drop: 0 };
    setInterval(() => {
        const ws = global.wss ? global.wss.clients.size : 0;
        console.log(`[Stats] uptime=${process.uptime().toFixed(0)}s agents=${AGENTS.size} clients=${CLIENTS.size} ws_open=${ws} total_recv=${STATS.totalRecv} total_fwd=${STATS.totalFwd}`);
    }, 30000);
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\nShutting down (SIGINT)...');
    _gracefulShutdown('SIGINT');
});

// SIGTERM (systemctl restart / stop) is the one that actually
// matters in production. Without this, systemd's restart just
// hard-closes the listening socket; the open WebSockets get a TCP
// RST instead of a WebSocket close frame, so the agent's
// _ws.recv() blocks forever in its 3600s timeout and the agent
// never reconnects. systemd's Stop=6s+SIGKILL policy means we
// have very little time to do this cleanly -- so we don't wait for
// the agent to ack, we just fire the close and exit.
process.on('SIGTERM', () => {
    console.log('Shutting down (SIGTERM)...');
    _gracefulShutdown('SIGTERM');
});

function _gracefulShutdown(signal) {
    let count = 0;
    try {
        for (const a of AGENTS.values()) {
            try { a.ws.close(1001, 'server ' + signal); } catch (e) {}
            count++;
        }
        for (const c of CLIENTS.values()) {
            try { c.ws.close(1001, 'server ' + signal); } catch (e) {}
            count++;
        }
    } catch (e) {}
    console.log(`Sent WebSocket close to ${count} peers; exiting.`);
    try { wss.close(); } catch (e) {}
    try { server.close(); } catch (e) {}
    // Force exit after a brief grace period even if close()
    // doesn't trigger the listening socket close (which is the
    // typical Node.js behavior on Linux).
    setTimeout(() => process.exit(0), 500).unref();
}
