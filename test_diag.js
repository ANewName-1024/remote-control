// Diag dump tests - App-side log upload + server-side HTTP API
//   WS: client sends {type:'app_diag', ...} -> server writes file + ack
//   HTTP: GET /api/diag, /api/diag/latest, /api/diag/download
//   Path traversal protection on agentId and filename
// Run: node test_diag.js
// Covers test_design.md §D (Diag)

const http = require('http');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 21997;
const PASSWORD = 'test-pw-diag-' + Date.now();
// Use a temp dir under the system tmp so we don't pollute
// server/agent_logs/ and don't have to clean up after ourselves
// (the OS does it). Each test run is hermetic.
const DIAG_DIR = path.join(os.tmpdir(), 'rc-diag-test-' + Date.now());

let serverProcess = null;

function startServer() {
    return new Promise(resolve => {
        serverProcess = require('child_process').spawn('node', ['server/index.js'], {
            cwd: __dirname,
            env: { ...process.env, PORT: String(PORT), ACCESS_PASSWORD: PASSWORD, DIAG_DIR },
            stdio: ['ignore', 'pipe', 'pipe']
        });
        serverProcess.stderr.on('data', d => process.stderr.write(d));
        setTimeout(resolve, 1500);
    });
}

function stopServer() {
    if (serverProcess) serverProcess.kill();
}

function request(method, urlPath, body, headers = {}) {
    return new Promise((resolve, reject) => {
        const req = http.request({
            hostname: '127.0.0.1', port: PORT, method, path: urlPath,
            headers: { 'Content-Length': body ? Buffer.byteLength(body) : 0, ...headers }
        }, res => {
            const chunks = [];
            res.on('data', c => chunks.push(c));
            res.on('end', () => resolve({
                status: res.statusCode,
                body: Buffer.concat(chunks).toString(),
                headers: res.headers
            }));
        });
        req.on('error', reject);
        if (body) req.write(body);
        req.end();
    });
}

function authHeader() {
    return { 'Authorization': 'Bearer ' + Buffer.from(PASSWORD).toString('base64') };
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

let passed = 0, failed = 0;
function check(name, ok, detail) {
    if (ok) { console.log(`  PASS  ${name}`); passed++; }
    else { console.log(`  FAIL  ${name} ${detail || ''}`); failed++; }
}

function rmrf(dir) {
    if (!fs.existsSync(dir)) return;
    for (const e of fs.readdirSync(dir)) {
        const p = path.join(dir, e);
        if (fs.statSync(p).isDirectory()) rmrf(p);
        else try { fs.unlinkSync(p); } catch (err) {}
    }
    try { fs.rmdirSync(dir); } catch (err) {}
}

(async () => {
    console.log(`Starting server on :${PORT} (DIAG_DIR=${DIAG_DIR})...`);
    fs.mkdirSync(DIAG_DIR, { recursive: true });
    await startServer();

    try {
        // ---- Spin up a fake agent so the client has a target ----
        const AGENT_ID = 'diag-test-agent-001';
        const { ws: agentWs } = await openWs('/agent');
        agentWs.send(JSON.stringify({
            type: 'auth', agentId: AGENT_ID, secret: 's',
            hostname: 'diag-test-host', os: 'Windows 11'
        }));

        // ---- Spin up a client ----
        const { ws: clientWs, messages: clientMsgs } = await openWs('/client');
        clientWs.send(JSON.stringify({ type: 'auth', password: PASSWORD, agentId: AGENT_ID }));
        await waitFor(clientMsgs, m => m.type === 'auth_ok');
        clientWs.send(JSON.stringify({ type: 'subscribe', agentId: AGENT_ID }));
        await new Promise(r => setTimeout(r, 200));

        // ---- [D1] Client sends app_diag, server writes file + ack ----
        console.log('\n[1] WS app_diag round-trip (D1)');
        const SAMPLE_LOG = '[00:00:00.000] [INFO   ] [App] starting\n[00:00:00.001] [INFO   ] [Relay] Connecting to host:port\n[00:00:01.000] [INFO   ] [Relay] Auth success\n';
        clientWs.send(JSON.stringify({
            type: 'app_diag',
            trigger: 'manual',
            appVersion: '1.1-test',
            platform: 'android',
            capturedAt: '2026-06-05T07:34:00.000Z',
            context: { relayState: 'authenticated', agentId: AGENT_ID },
            logs: SAMPLE_LOG,
        }));
        const ack = await waitFor(clientMsgs, m => m.type === 'diag_ack');
        check('Server acks diag_ack with ok=true', ack && ack.ok === true, JSON.stringify(ack));
        check('diag_ack includes path', typeof ack.path === 'string' && ack.path.includes(AGENT_ID));
        check('diag_ack includes bytes', ack.bytes === SAMPLE_LOG.length);

        // Give the file a moment to flush
        await new Promise(r => setTimeout(r, 200));
        const files1 = fs.readdirSync(path.join(DIAG_DIR, AGENT_ID)).filter(n => n.endsWith('.log'));
        check('Log file written to disk', files1.length === 1, `files=${JSON.stringify(files1)}`);
        const log1 = fs.readFileSync(path.join(DIAG_DIR, AGENT_ID, files1[0]), 'utf8');
        check('Log file content matches what client sent', log1 === SAMPLE_LOG);
        // Sidecar JSON should exist
        const metaPath = path.join(DIAG_DIR, AGENT_ID, files1[0].replace(/\.log$/, '.json'));
        check('Sidecar meta JSON exists', fs.existsSync(metaPath));
        const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
        check('Sidecar has trigger=manual', meta.trigger === 'manual');
        check('Sidecar has appVersion=1.1-test', meta.appVersion === '1.1-test');
        check('Sidecar has agentId', meta.agentId === AGENT_ID);
        check('Sidecar has bytes', meta.bytes === SAMPLE_LOG.length);

        // ---- [D2] Different triggers sort + are preserved ----
        console.log('\n[2] Multiple uploads (different triggers) (D2)');
        clientWs.send(JSON.stringify({
            type: 'app_diag', trigger: 'periodic', appVersion: '1.1',
            capturedAt: '2026-06-05T07:35:00.000Z', context: {}, logs: 'periodic log content',
        }));
        const ack2 = await waitFor(clientMsgs, m => m.type === 'diag_ack' && m !== ack);
        check('Second upload acked', ack2 && ack2.ok === true, JSON.stringify(ack2));
        await new Promise(r => setTimeout(r, 200));
        const files2 = fs.readdirSync(path.join(DIAG_DIR, AGENT_ID)).filter(n => n.endsWith('.log'));
        check('Two log files now exist', files2.length === 2, `files=${JSON.stringify(files2)}`);
        const triggers = files2.map(f => {
            const m = fs.readFileSync(path.join(DIAG_DIR, AGENT_ID, f.replace(/\.log$/, '.json')), 'utf8');
            return JSON.parse(m).trigger;
        });
        check('Both triggers present', triggers.includes('manual') && triggers.includes('periodic'),
              `triggers=${JSON.stringify(triggers)}`);

        // ---- [D3] Empty upload rejected ----
        console.log('\n[3] Empty logs rejected (D3)');
        clientWs.send(JSON.stringify({
            type: 'app_diag', trigger: 'manual', appVersion: '1.1',
            capturedAt: '2026-06-05T07:36:00.000Z', context: {}, logs: '',
        }));
        const ack3 = await waitFor(clientMsgs, m => m.type === 'diag_ack' && m !== ack && m !== ack2);
        check('Empty upload ack has ok=false', ack3 && ack3.ok === false, JSON.stringify(ack3));
        check('Empty upload ack error=empty', ack3.error === 'empty');
        await new Promise(r => setTimeout(r, 200));
        const files3 = fs.readdirSync(path.join(DIAG_DIR, AGENT_ID)).filter(n => n.endsWith('.log'));
        check('No new file for empty upload', files3.length === 2, `files=${JSON.stringify(files3)}`);

        // ---- [D4] GET /api/diag lists agents and files ----
        console.log('\n[4] GET /api/diag lists files (D4)');
        const r4a = await request('GET', '/api/diag', null, {});
        check('no auth -> 401', r4a.status === 401, `got ${r4a.status}`);
        const r4b = await request('GET', '/api/diag', null, authHeader());
        check('with auth -> 200', r4b.status === 200, `got ${r4b.status}`);
        const list = JSON.parse(r4b.body);
        check('Response has agents array', Array.isArray(list.agents));
        check('Response has totalFiles=2', list.totalFiles === 2, `total=${list.totalFiles}`);
        const agent = list.agents.find(a => a.agentId === AGENT_ID);
        check('Our agent is in the list', !!agent);
        check('Agent has 2 files', agent && agent.files.length === 2, `len=${agent && agent.files.length}`);
        check('Each file has meta with trigger', agent && agent.files.every(f => f.meta && f.meta.trigger));

        // ---- [D5] GET /api/diag/latest returns most recent ----
        console.log('\n[5] GET /api/diag/latest (D5)');
        const r5 = await request('GET', `/api/diag/latest?agentId=${AGENT_ID}`, null, authHeader());
        check('latest -> 200', r5.status === 200, `got ${r5.status}`);
        const latest = JSON.parse(r5.body);
        check('latest returns the periodic one (most recent mtime)', latest.meta && latest.meta.trigger === 'periodic',
              `trigger=${latest.meta && latest.meta.trigger}`);
        const r5b = await request('GET', '/api/diag/latest?agentId=does_not_exist', null, authHeader());
        check('latest for unknown agent -> 404', r5b.status === 404, `got ${r5b.status}`);

        // ---- [D6] GET /api/diag/download streams the file ----
        console.log('\n[6] GET /api/diag/download streams file (D6)');
        const targetFile = files2.find(f => {
            const m = JSON.parse(fs.readFileSync(path.join(DIAG_DIR, AGENT_ID, f.replace(/\.log$/, '.json')), 'utf8'));
            return m.trigger === 'periodic';
        });
        const r6 = await request('GET',
            `/api/diag/download?agentId=${AGENT_ID}&name=${targetFile}`, null, authHeader());
        check('download -> 200', r6.status === 200, `got ${r6.status}`);
        check('downloaded body == "periodic log content"', r6.body === 'periodic log content',
              `body=${r6.body}`);

        // ---- [D7] Path traversal blocked on agentId ----
        console.log('\n[7] Path traversal blocked (D7)');
        // agentId ".." or "../etc" should be sanitized to "_" patterns
        // (the handler uses _safeAgentDirName which replaces /[^A-Za-z0-9._-]/_)
        const r7a = await request('GET', '/api/diag/latest?agentId=..%2Fetc%2Fpasswd', null, authHeader());
        // "..%2Fetc%2Fpasswd" decoded would be "../etc/passwd"; sanitized
        // to ".._etc_passwd" (slashes -> '_'). Should 404 since that
        // subdir doesn't exist.
        check('Traversal agentId -> 404 (not 200)', r7a.status === 404, `got ${r7a.status}`);
        const r7b = await request('GET',
            `/api/diag/download?agentId=..%2Fetc&name=passwd.log`, null, authHeader());
        check('Traversal download -> 404 or 403', r7b.status === 404 || r7b.status === 403,
              `got ${r7b.status}`);
        // Verify no file was created in DIAG_DIR's parent or sibling
        const before = fs.readdirSync(path.dirname(DIAG_DIR));
        check('No file leaked outside DIAG_DIR', !before.some(n => n === 'etc'),
              `siblings=${JSON.stringify(before)}`);

        // ---- [D8] /api/diag?agentId=X filters ----
        console.log('\n[8] /api/diag?agentId= filters (D8)');
        const r8 = await request('GET', `/api/diag?agentId=${AGENT_ID}`, null, authHeader());
        check('filter -> 200', r8.status === 200, `got ${r8.status}`);
        const filtered = JSON.parse(r8.body);
        check('filter returns 1 agent', filtered.agents.length === 1);
        check('filter returns our agent', filtered.agents[0].agentId === AGENT_ID);

        // ---- [D9] Client not authed -> app_diag rejected ----
        console.log('\n[9] app_diag from unauthed client rejected (D9)');
        // Open a new WS without auth, try to send app_diag
        const { ws: rogueWs, messages: rogueMsgs } = await openWs('/client');
        // We don't send auth. Just try to upload.
        rogueWs.send(JSON.stringify({
            type: 'app_diag', trigger: 'manual', logs: 'should not save',
        }));
        await new Promise(r => setTimeout(r, 500));
        // The server's auth check sends {type:'error', message:'Not authenticated'}
        // BEFORE the app_diag branch (see '!clientId' guard in /client handler)
        const errReply = rogueMsgs.find(m => m.type === 'error');
        check('Unauthed app_diag -> error message', !!errReply, `msgs=${JSON.stringify(rogueMsgs)}`);
        rogueWs.close();
        // Verify nothing landed in DIAG_DIR
        const files9 = fs.readdirSync(DIAG_DIR);
        check('No rogue subdir created', files9.length === 1 && files9[0] === AGENT_ID,
              `dirs=${JSON.stringify(files9)}`);

        clientWs.close();
        agentWs.close();
    } catch (err) {
        console.error('Test error:', err);
        failed++;
    } finally {
        stopServer();
        rmrf(DIAG_DIR);
        console.log(`\n=== ${passed} passed, ${failed} failed ===`);
        process.exit(failed > 0 ? 1 : 0);
    }
})();
