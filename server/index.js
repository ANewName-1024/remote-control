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
const CLIENTS = new Map();   // clientId -> { ws, agentId, info }
const SESSIONS = new Map();  // sessionId -> { agentId, clientId, type, data }
const PASSWORD_TOKENS = new Map();  // passwordToken -> true (one-time or timed)

// Ensure upload dir exists
if (!fs.existsSync(UPLOAD_DIR)) {
    fs.mkdirSync(UPLOAD_DIR, { recursive: true });
}

// ============================================================
// HTTP Server (Express)
// ============================================================

const app = express();
const server = http.createServer(app);

// Serve static files (web control interface)
app.use(express.static(path.join(__dirname, 'static')));
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
const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, UPLOAD_DIR),
    filename: (req, file, cb) => cb(null, `${Date.now()}-${file.originalname}`)
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
    
    console.log(`[WS] New connection: ${path} from ${req.socket.remoteAddress}`);
    
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
                        lastSeen: Date.now()
                    });
                    
                    ws.send(JSON.stringify({ type: 'auth_ok', agentId: aid }));
                    console.log(`[Agent] Registered: ${aid} (${hostname})`);
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
                    
                    // Relay to all connected clients viewing this agent
                    CLIENTS.forEach((client) => {
                        if (client.agentId === agentId && client.ws.readyState === 1) {
                            client.ws.send(JSON.stringify({
                                type: 'screen',
                                data: msg.data,
                                quality: msg.quality,
                                timestamp: msg.timestamp
                            }));
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
                    
                    console.log(`[Client] ${clientId} authenticated for agent ${targetAgentId}`);
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
                if (['mouse', 'key', 'exec', 'file_request', 'clipboard'].includes(msg.type)) {
                    const targetAgent = AGENTS.get(client.agentId);
                    if (targetAgent && targetAgent.ws.readyState === 1) {
                        // Create session for commands
                        if (msg.type === 'exec' && msg.cmd) {
                            const sessionId = uuidv4();
                            SESSIONS.set(sessionId, { agentId: client.agentId, clientId, type: 'exec' });
                            targetAgent.ws.send(JSON.stringify({ ...msg, session: sessionId }));
                        } else {
                            targetAgent.ws.send(JSON.stringify(msg));
                        }
                    } else {
                        ws.send(JSON.stringify({ type: 'agent_offline' }));
                    }
                    return;
                }
            }
            
        } catch (err) {
            console.error('[WS] Parse error:', err.message);
        }
    });
    
    ws.on('close', () => {
        if (agentId) {
            console.log(`[Agent] Disconnected: ${agentId}`);
            AGENTS.delete(agentId);
        }
        if (clientId) {
            console.log(`[Client] Disconnected: ${clientId}`);
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
    console.log(`
╔══════════════════════════════════════════════════════╗
║       Remote Control Relay Server v1.0              ║
╠══════════════════════════════════════════════════════╣
║  HTTP/WebSocket Port: ${PORT}                          ║
║  Web Interface:      http://localhost:${PORT}          ║
║  Agent Endpoint:     ws://host:${PORT}/agent            ║
║  Client Endpoint:    ws://host:${PORT}/client           ║
╚══════════════════════════════════════════════════════╝
    `);
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\nShutting down...');
    wss.close();
    server.close();
    process.exit(0);
});
