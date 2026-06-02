// WebSocket Protocol Tests - /agent and /client auth, message handling, robustness
// Uses Node 24's built-in WebSocket (Web API).
// Run: node test_ws_protocol.js
// Covers test_design.md §C (WebSocket protocol)

const http = require('http');

const PORT = 21995;
const PASSWORD = 'test-pw-ws-' + Date.now();

let serverProcess = null;

function startServer() {
    return new Promise(resolve => {
        serverProcess = require('child_process').spawn('node', ['server/index.js'], {
            cwd: __dirname,
            env: { ...process.env, PORT: String(PORT), ACCESS_PASSWORD: PASSWORD },
            stdio: ['ignore', 'pipe', 'pipe']
        });
        serverProcess.stderr.on('data', d => process.stderr.write(d));
        setTimeout(resolve, 1500);
    });
}

function stopServer() {
    if (serverProcess) serverProcess.kill();
}

let passed = 0, failed = 0;
function check(name, ok, detail) {
    if (ok) { console.log(`  PASS  ${name}`); passed++; }
    else { console.log(`  FAIL  ${name} ${detail || ''}`); failed++; }
}

function openWs(urlPath) {
    return new Promise((resolve, reject) => {
        const ws = new WebSocket(`ws://127.0.0.1:${PORT}${urlPath}`);
        const messages = [];
        let opened = false;
        const timeout = setTimeout(() => {
            if (!opened) reject(new Error(`WS ${urlPath} open timeout`));
        }, 3000);
        ws.addEventListener('open', () => { opened = true; clearTimeout(timeout); resolve({ ws, messages }); });
        ws.addEventListener('message', evt => {
            try { messages.push(JSON.parse(evt.data)); } catch (e) {}
        });
        ws.addEventListener('error', e => { if (!opened) reject(e); });
        ws.addEventListener('close', () => { messages.push({ type: '__closed__' }); });
    });
}

function waitFor(messages, predicate, timeoutMs = 2000) {
    return new Promise((resolve, reject) => {
        const start = Date.now();
        const check = () => {
            const found = messages.find(predicate);
            if (found) return resolve(found);
            if (Date.now() - start > timeoutMs) return reject(new Error('waitFor timeout'));
            setTimeout(check, 30);
        };
        check();
    });
}

function waitForClose(ws, timeoutMs = 2000) {
    return new Promise((resolve) => {
        if (ws.readyState === WebSocket.CLOSED) return resolve();
        const t = setTimeout(() => resolve(), timeoutMs);
        ws.addEventListener('close', () => { clearTimeout(t); resolve(); });
    });
}

(async () => {
    console.log(`Starting server on :${PORT}...`);
    await startServer();

    try {
        console.log('\n[1] Agent registration (C1)');
        const { ws: agentWs, messages: agentMsgs } = await openWs('/agent');
        agentWs.send(JSON.stringify({
            type: 'auth', agentId: 'ws-test-agent-001', secret: 'sec1',
            hostname: 'test-host', os: 'Windows 11'
        }));
        const authOk = await waitFor(agentMsgs, m => m.type === 'auth_ok');
        check('Agent receives auth_ok', authOk && authOk.agentId === 'ws-test-agent-001',
              JSON.stringify(authOk));

        console.log('\n[2] Agent appears in /api/agents (after WS auth)');
        const authHdr = 'Bearer ' + Buffer.from(PASSWORD).toString('base64');
        const agentsResp = await new Promise((resolve, reject) => {
            const req = http.request({
                hostname: '127.0.0.1', port: PORT, method: 'GET', path: '/api/agents',
                headers: { 'Authorization': authHdr }
            }, res => {
                const chunks = [];
                res.on('data', c => chunks.push(c));
                res.on('end', () => resolve(JSON.parse(Buffer.concat(chunks).toString())));
            });
            req.on('error', reject);
            req.end();
        });
        check('agent listed in /api/agents', agentsResp.agents.some(a => a.agentId === 'ws-test-agent-001'));

        console.log('\n[3] Agent not yet authed sending screen (C2)');
        const { ws: agent2Ws, messages: agent2Msgs } = await openWs('/agent');
        agent2Ws.send(JSON.stringify({
            type: 'screen', data: 'fake-jpeg-base64', quality: 60, timestamp: 123
        }));
        try {
            const err = await waitFor(agent2Msgs, m => m.type === 'error', 1000);
            check('Server sends error for unauthed screen', err && err.message === 'Not authenticated',
                  JSON.stringify(err));
        } catch (e) {
            check('Server sends error for unauthed screen', false, 'timeout waiting for error');
        }
        agent2Ws.close();

        console.log('\n[4] Agent pong updates lastSeen (C6)');
        // Hit /api/agent/ping to confirm agent is known
        const pingResp1 = await new Promise((resolve, reject) => {
            http.get(`http://127.0.0.1:${PORT}/api/agent/ping?agentId=ws-test-agent-001`, res => {
                const chunks = [];
                res.on('data', c => chunks.push(c));
                res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(Buffer.concat(chunks).toString()) }));
            }).on('error', reject);
        });
        check('ping returns ok', pingResp1.status === 200, JSON.stringify(pingResp1.body));
        // Now send pong from agent — server updates lastSeen (no error)
        agentWs.send(JSON.stringify({ type: 'pong' }));
        await new Promise(r => setTimeout(r, 200));
        check('Agent pong sent without error', agentWs.readyState === WebSocket.OPEN);

        console.log('\n[5] Client registration (C7)');
        const { ws: clientWs, messages: clientMsgs } = await openWs('/client');
        clientWs.send(JSON.stringify({
            type: 'auth', password: PASSWORD, agentId: 'ws-test-agent-001'
        }));
        const clientAuth = await waitFor(clientMsgs, m => m.type === 'auth_ok', 2000);
        check('Client receives auth_ok', clientAuth && clientAuth.clientId, JSON.stringify(clientAuth));
        check('auth_ok includes agentInfo.hostname',
              clientAuth.agentInfo && clientAuth.agentInfo.hostname === 'test-host',
              JSON.stringify(clientAuth));

        console.log('\n[6] Client wrong password is closed (C8)');
        const { ws: badWs, messages: badMsgs } = await openWs('/client');
        badWs.send(JSON.stringify({ type: 'auth', password: 'WRONG', agentId: 'ws-test-agent-001' }));
        try {
            const fail = await waitFor(badMsgs, m => m.type === 'auth_failed', 1500);
            check('Server sends auth_failed', fail && /Invalid/.test(fail.message), JSON.stringify(fail));
        } catch (e) {
            check('Server sends auth_failed', false, 'timeout');
        }
        await waitForClose(badWs, 1500);
        check('Bad-password client WS closed', badWs.readyState === WebSocket.CLOSED);

        console.log('\n[7] Client → offline agent → agent_offline (C14)');
        const { ws: offWs, messages: offMsgs } = await openWs('/client');
        offWs.send(JSON.stringify({ type: 'auth', password: PASSWORD, agentId: 'NONEXISTENT_AGENT' }));
        try {
            const offline = await waitFor(offMsgs, m => m.type === 'agent_offline', 1500);
            check('Server sends agent_offline for unknown agent', !!offline, JSON.stringify(offline));
        } catch (e) {
            check('Server sends agent_offline for unknown agent', false, 'timeout');
        }
        await waitForClose(offWs, 1500);

        console.log('\n[8] Malformed JSON does not crash server (C15)');
        const { ws: badJsonWs } = await openWs('/agent');
        badJsonWs.send('{not valid json');
        await new Promise(r => setTimeout(r, 300));
        check('Bad-JSON WS still open', badJsonWs.readyState === WebSocket.OPEN);
        badJsonWs.close();
        // Re-test status endpoint
        const statusAfter = await new Promise((resolve, reject) => {
            http.get(`http://127.0.0.1:${PORT}/api/status`, res => {
                const chunks = [];
                res.on('data', c => chunks.push(c));
                res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(Buffer.concat(chunks).toString()) }));
            }).on('error', reject);
        });
        check('Status endpoint still works', statusAfter.status === 200);

        console.log('\n[9] /api/agents/:id/auth against online agent with wrong/right secret (A5)');
        const authResp = await new Promise((resolve, reject) => {
            const req = http.request({
                hostname: '127.0.0.1', port: PORT, method: 'POST',
                path: '/api/agents/ws-test-agent-001/auth',
                headers: { 'Content-Type': 'application/json' }
            }, res => {
                const chunks = [];
                res.on('data', c => chunks.push(c));
                res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(Buffer.concat(chunks).toString()) }));
            });
            req.on('error', reject);
            req.write(JSON.stringify({ secret: 'WRONG' }));
            req.end();
        });
        check('Wrong secret -> 401', authResp.status === 401, JSON.stringify(authResp.body));

        const authResp2 = await new Promise((resolve, reject) => {
            const req = http.request({
                hostname: '127.0.0.1', port: PORT, method: 'POST',
                path: '/api/agents/ws-test-agent-001/auth',
                headers: { 'Content-Type': 'application/json' }
            }, res => {
                const chunks = [];
                res.on('data', c => chunks.push(c));
                res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(Buffer.concat(chunks).toString()) }));
            });
            req.on('error', reject);
            req.write(JSON.stringify({ secret: 'sec1' }));
            req.end();
        });
        check('Correct secret -> 200 + accessToken',
              authResp2.status === 200 && authResp2.body.success && authResp2.body.accessToken,
              JSON.stringify(authResp2.body));

        agentWs.close();
        clientWs.close();

    } catch (err) {
        console.error('Test error:', err);
        failed++;
    } finally {
        stopServer();
        console.log(`\n=== ${passed} passed, ${failed} failed ===`);
        process.exit(failed > 0 ? 1 : 0);
    }
})();
