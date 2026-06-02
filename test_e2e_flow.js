// End-to-End Tests - real client ⇄ real server ⇄ fake agent
// Verifies the full message routing chain.
// Uses Node 24's built-in WebSocket (Web API).
// Run: node test_e2e_flow.js
// Covers test_design.md §C (WebSocket), §F (Web Client behavior verified via server)

const PORT = 21994;
const PASSWORD = 'test-pw-e2e-' + Date.now();

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
        const t = setTimeout(() => { if (!opened) reject(new Error('open timeout')); }, 3000);
        ws.addEventListener('open', () => { opened = true; clearTimeout(t); resolve({ ws, messages }); });
        ws.addEventListener('message', evt => {
            try { messages.push(JSON.parse(evt.data)); } catch (e) {}
        });
        ws.addEventListener('error', e => { if (!opened) reject(e); });
        ws.addEventListener('close', () => messages.push({ type: '__closed__' }));
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

(async () => {
    console.log(`Starting server on :${PORT}...`);
    await startServer();

    // Set up fake agent
    console.log('\n[setup] Fake agent connecting...');
    const { ws: agentWs, messages: agentMsgs } = await openWs('/agent');
    agentWs.send(JSON.stringify({
        type: 'auth', agentId: 'e2e-agent-001', secret: 'e2e-sec',
        hostname: 'e2e-host', os: 'Windows 11'
    }));
    await waitFor(agentMsgs, m => m.type === 'auth_ok');
    console.log('  agent ready');

    // Set up client
    console.log('[setup] Fake client connecting...');
    const { ws: clientWs, messages: clientMsgs } = await openWs('/client');
    clientWs.send(JSON.stringify({
        type: 'auth', password: PASSWORD, agentId: 'e2e-agent-001'
    }));
    await waitFor(clientMsgs, m => m.type === 'auth_ok');
    console.log('  client ready\n');

    try {
        // ---------- T01: Agent → screen → Client ----------
        console.log('[T01] Agent screen → Client (C3)');
        agentWs.send(JSON.stringify({
            type: 'screen', data: 'base64jpegdata', quality: 75, timestamp: Date.now()
        }));
        const screen = await waitFor(clientMsgs, m => m.type === 'screen');
        check('client receives screen with data', screen.data === 'base64jpegdata', JSON.stringify(screen));
        check('client receives screen.quality', screen.quality === 75);
        check('client receives screen.timestamp', typeof screen.timestamp === 'number');

        // ---------- T02: Client → exec → Agent (with sessionId) ----------
        console.log('\n[T02] Client exec → Agent with sessionId (C11)');
        clientWs.send(JSON.stringify({ type: 'exec', cmd: 'echo hello' }));
        const execMsg = await waitFor(agentMsgs,
            m => m.type === 'exec' && m.session, 2000);
        check('agent receives exec', execMsg.cmd === 'echo hello', JSON.stringify(execMsg));
        check('agent receives exec with sessionId (uuid)',
              /^[0-9a-f-]{36}$/.test(execMsg.session),
              `session=${execMsg.session}`);

        // ---------- T03: Agent → output → Client (session routing) ----------
        console.log('\n[T03] Agent output → Client via session (C4)');
        agentWs.send(JSON.stringify({
            type: 'output', session: execMsg.session,
            data: 'hello\n', done: false
        }));
        const out = await waitFor(clientMsgs, m => m.type === 'output');
        check('client receives output with same session', out.session === execMsg.session, JSON.stringify(out));
        check('client receives output data', out.data === 'hello\n');
        check('client receives output done=false', out.done === false);

        // ---------- T04: Client → mouse → Agent ----------
        console.log('\n[T04] Client mouse → Agent (C9)');
        clientWs.send(JSON.stringify({
            type: 'mouse', action: 'click', x: 100, y: 200, button: 'left'
        }));
        const mouse = await waitFor(agentMsgs, m => m.type === 'mouse');
        check('agent receives mouse click', mouse.action === 'click' && mouse.x === 100 && mouse.y === 200,
              JSON.stringify(mouse));
        check('agent receives mouse button=left', mouse.button === 'left');

        // ---------- T05: Client → key → Agent ----------
        console.log('\n[T05] Client key → Agent (C10)');
        clientWs.send(JSON.stringify({ type: 'key', action: 'press', key: 'ctrl+alt+del' }));
        const key = await waitFor(agentMsgs, m => m.type === 'key');
        check('agent receives key press', key.action === 'press' && key.key === 'ctrl+alt+del',
              JSON.stringify(key));

        // ---------- T06: Client → file_request download → Agent ----------
        console.log('\n[T06] Client file_request download → Agent (C12)');
        clientWs.send(JSON.stringify({
            type: 'file_request', action: 'download',
            path: 'C:/Users/test/file.txt', filename: 'file.txt'
        }));
        const fdl = await waitFor(agentMsgs, m => m.type === 'file_request');
        check('agent receives file_request:download', fdl.action === 'download' && fdl.path === 'C:/Users/test/file.txt',
              JSON.stringify(fdl));

        // ---------- T07: Agent → file_chunk → Client ----------
        console.log('\n[T07] Agent file_chunk → Client (C5)');
        // Reuse the exec session from T02 (server only creates sessions for exec,
        // not for file_request). This verifies session-based routing.
        agentWs.send(JSON.stringify({
            type: 'file_chunk', session: execMsg.session,
            chunk: 'aGVsbG8=', done: false, filename: 'x'
        }));
        const chunk = await waitFor(clientMsgs, m => m.type === 'file_chunk');
        check('client receives file_chunk with same session',
              chunk.session === execMsg.session && chunk.chunk === 'aGVsbG8=' && !chunk.done,
              JSON.stringify(chunk));

        // ---------- T08: Client → clipboard → Agent ----------
        console.log('\n[T08] Client clipboard → Agent (C13)');
        clientWs.send(JSON.stringify({ type: 'clipboard', action: 'set', content: 'test' }));
        const clip = await waitFor(agentMsgs, m => m.type === 'clipboard');
        check('agent receives clipboard (forwarded by server, even if agent ignores it)',
              clip.action === 'set' && clip.content === 'test', JSON.stringify(clip));

        // ---------- T09: GAP-2 fix — file_request own session routing ----------
        console.log('\n[T09] file_request own session routes file_chunk back (GAP-2 fix)');
        // Client generates its own session id (like the real web client doDownload).
        const dlSid = 'dl_test_' + Date.now();
        clientWs.send(JSON.stringify({
            type: 'file_request', action: 'download',
            session: dlSid,
            path: 'C:/Users/test/file.txt', filename: 'file.txt'
        }));
        // Agent should receive the file_request WITH the same session id preserved.
        const fdl2 = await waitFor(agentMsgs,
            m => m.type === 'file_request' && m.action === 'download' && m.session === dlSid, 2000);
        check('agent receives file_request:download with client session id',
              fdl2.session === dlSid, JSON.stringify(fdl2));
        // Now agent sends back file_chunk using that same session id.
        // Server should route it back to the originating client (GAP-2 was: server
        // had no record of this session and dropped the chunk).
        agentWs.send(JSON.stringify({
            type: 'file_chunk', session: dlSid,
            chunk: 'aGVsbG8=', done: false, filename: 'file.txt'
        }));
        const chunk2 = await waitFor(clientMsgs,
            m => m.type === 'file_chunk' && m.session === dlSid, 2000);
        check('client receives file_chunk via own file_request session (GAP-2 fix)',
              chunk2.session === dlSid && chunk2.chunk === 'aGVsbG8=' && !chunk2.done,
              JSON.stringify(chunk2));

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
