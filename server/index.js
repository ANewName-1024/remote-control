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
        hasPassword: !!ACCESS_PASSWORD
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
    const agents = Array.from(AGENTS.values()).map(a => ({
        agentId: a.info.agentId,
        hostname: a.info.hostname,
        os: a.info.os,
        lastSeen: a.lastSeen,
        online: a.ws && a.ws.readyState === 1
    }));
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
        // Check timeout (2 minutes for agents)
        if (now - agent.lastSeen > 120000) {
            console.log(`[Agent] ${id} heartbeat timeout, removing`);
            AGENTS.delete(id);
        }
    });
    
    CLIENTS.forEach((client, id) => {
        if (now - client.lastSeen > 120000) {
            console.log(`[Client] ${id} heartbeat timeout, removing`);
            CLIENTS.delete(id);
        }
    });
}, 30000);

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
                
                // Forward commands to agent
                // Also forward 'req_kf' (keyframe request from client) so
                // the agent can immediately push a fresh kf instead of
                // waiting for its 3-second keyframe interval.
                if (['mouse', 'key', 'exec', 'file_request', 'clipboard', 'req_kf', 'subscribe', 'ping'].includes(msg.type)) {
                    STATS.totalRecv += 1;
                    const targetAgent = AGENTS.get(client.agentId);
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
    console.log('\nShutting down...');
    wss.close();
    server.close();
    process.exit(0);
});
