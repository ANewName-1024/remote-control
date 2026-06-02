// HTTP REST API Tests - /api/status, /api/agent/ping, /api/verify-password,
//   /api/agents, /api/agents/:id/auth, /api/files, /api/download, /api/files DELETE
// Run: node test_http_api.js
// Covers test_design.md §A (HTTP REST API)

const http = require('http');
const path = require('path');
const fs = require('fs');

const PORT = 21996;
const PASSWORD = 'test-pw-http-' + Date.now();

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

let passed = 0, failed = 0;
function check(name, ok, detail) {
    if (ok) { console.log(`  PASS  ${name}`); passed++; }
    else { console.log(`  FAIL  ${name} ${detail || ''}`); failed++; }
}

(async () => {
    console.log(`Starting server on :${PORT}...`);
    await startServer();

    try {
        console.log('\n[1] GET /api/status (A1)');
        const r1 = await request('GET', '/api/status', null, {});
        check('status 200', r1.status === 200, `got ${r1.status}`);
        const status = JSON.parse(r1.body);
        check('status has uptime', typeof status.uptime === 'number', JSON.stringify(status));
        check('status reports 0 agents', status.agents === 0);
        check('status reports 0 clients', status.clients === 0);
        check('status has hasPassword=true', status.hasPassword === true);

        console.log('\n[2] GET /api/agent/ping (A2)');
        const r2a = await request('GET', '/api/agent/ping', null, {});
        check('no agentId -> 400', r2a.status === 400, `got ${r2a.status}`);
        const r2b = await request('GET', '/api/agent/ping?agentId=nonexistent', null, {});
        check('unknown agent -> 404', r2b.status === 404, `got ${r2b.status}`);

        console.log('\n[3] POST /api/verify-password (A3)');
        const r3a = await request('POST', '/api/verify-password',
            JSON.stringify({}), { 'Content-Type': 'application/json' });
        check('no password -> 400', r3a.status === 400, `got ${r3a.status}`);
        const r3b = await request('POST', '/api/verify-password',
            JSON.stringify({ password: 'wrong' }), { 'Content-Type': 'application/json' });
        check('wrong password -> 401', r3b.status === 401, `got ${r3b.status}`);
        const r3c = await request('POST', '/api/verify-password',
            JSON.stringify({ password: PASSWORD }), { 'Content-Type': 'application/json' });
        check('correct password -> 200', r3c.status === 200, `got ${r3c.status}`);
        const tokenResp = JSON.parse(r3c.body);
        check('response has success=true', tokenResp.success === true);
        check('response has token (uuid)', /^[0-9a-f-]{36}$/.test(tokenResp.token),
              `token=${tokenResp.token}`);

        console.log('\n[4] GET /api/agents (A4)');
        const r4a = await request('GET', '/api/agents', null, {});
        check('no auth -> 401', r4a.status === 401, `got ${r4a.status}`);
        const r4b = await request('GET', '/api/agents', null, {
            'Authorization': 'Bearer ' + Buffer.from('wrong').toString('base64')
        });
        check('wrong auth -> 401', r4b.status === 401, `got ${r4b.status}`);
        const r4c = await request('GET', '/api/agents', null, authHeader());
        check('correct auth -> 200', r4c.status === 200, `got ${r4c.status}`);
        const agents = JSON.parse(r4c.body);
        check('agents is empty array', Array.isArray(agents.agents) && agents.agents.length === 0,
              `body=${r4c.body}`);

        console.log('\n[5] POST /api/agents/:id/auth (A5)');
        const fakeId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
        const r5a = await request('POST', `/api/agents/${fakeId}/auth`,
            JSON.stringify({ secret: 'x' }), { 'Content-Type': 'application/json' });
        check('offline agent -> 404', r5a.status === 404, `got ${r5a.status}`);

        console.log('\n[6] GET /api/files (A6)');
        const r6 = await request('GET', '/api/files', null, {});
        check('files list -> 200', r6.status === 200, `got ${r6.status}`);
        const filesResp = JSON.parse(r6.body);
        check('files is array', Array.isArray(filesResp.files));

        console.log('\n[7] GET /api/download/:name (A8)');
        // First upload a file
        const uploadDir = path.join(__dirname, 'server', 'uploads');
        const testFile = path.join(uploadDir, 'http_api_test.txt');
        fs.writeFileSync(testFile, 'download test content');
        const r7 = await request('GET', '/api/download/http_api_test.txt', null, {});
        check('download existing file -> 200', r7.status === 200, `got ${r7.status}`);
        check('downloaded body matches', r7.body === 'download test content');
        const r7b = await request('GET', '/api/download/does_not_exist.txt', null, {});
        check('download missing -> 404', r7b.status === 404, `got ${r7b.status}`);
        // Path traversal on download — path.basename() in handler should prevent escape
        const r7c = await request('GET', '/api/download/..%2f..%2fpackage.json', null, {});
        check('download traversal -> 404 (not 200)', r7c.status === 404, `got ${r7c.status}`);

        console.log('\n[8] DELETE /api/files/:name (A9)');
        const r8a = await request('DELETE', '/api/files/does_not_exist.txt', null, {});
        check('delete missing -> 404', r8a.status === 404, `got ${r8a.status}`);
        const r8b = await request('DELETE', '/api/files/http_api_test.txt', null, {});
        check('delete existing -> 200', r8b.status === 200, `got ${r8b.status}`);
        check('file actually deleted', !fs.existsSync(testFile));

        console.log('\n[9] Async I/O under load (G5)');
        // Create 50 files quickly, then list — should not block
        for (let i = 0; i < 50; i++) {
            fs.writeFileSync(path.join(uploadDir, `load_${i}.txt`), `content ${i}`);
        }
        const t0 = Date.now();
        const r9 = await request('GET', '/api/files', null, {});
        const t1 = Date.now();
        check('list 50+ files -> 200', r9.status === 200, `got ${r9.status}`);
        const files = JSON.parse(r9.body);
        check('list includes load_0.txt', files.files.some(f => f.name === 'load_0.txt'));
        check('list response < 500ms', (t1 - t0) < 500, `${t1 - t0}ms`);
        // cleanup
        for (let i = 0; i < 50; i++) {
            try { fs.unlinkSync(path.join(uploadDir, `load_${i}.txt`)); } catch (e) {}
        }

    } catch (err) {
        console.error('Test error:', err);
        failed++;
    } finally {
        stopServer();
        console.log(`\n=== ${passed} passed, ${failed} failed ===`);
        process.exit(failed > 0 ? 1 : 0);
    }
})();
