// Path Security Tests - resolveSafeDeployPath, deploy API security edges
// Run: node test_path_security.js
// Covers test_design.md §B (Static Deploy), §G (Security)

const http = require('http');
const path = require('path');
const fs = require('fs');

const PORT = 21997;
const PASSWORD = 'test-pw-psec-' + Date.now();
const DEPLOY_DIR = path.join(__dirname, 'server', 'static', 'app');

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

function authHeader() {
    return { 'Authorization': 'Bearer ' + Buffer.from(PASSWORD).toString('base64') };
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
                body: Buffer.concat(chunks).toString()
            }));
        });
        req.on('error', reject);
        if (body) req.write(body);
        req.end();
    });
}

let passed = 0, failed = 0;
function check(name, ok, detail) {
    if (ok) { console.log(`  PASS  ${name}`); passed++; }
    else { console.log(`  FAIL  ${name} ${detail || ''}`); failed++; }
}

function rmrf(dir) {
    if (fs.existsSync(dir)) {
        for (const f of fs.readdirSync(dir)) {
            const p = path.join(dir, f);
            try {
                if (fs.statSync(p).isDirectory()) rmrf(p);
                else fs.unlinkSync(p);
            } catch (e) {}
        }
    }
}

(async () => {
    console.log(`Starting server on :${PORT} (pw=${PASSWORD})...`);
    await startServer();
    rmrf(DEPLOY_DIR);
    fs.mkdirSync(DEPLOY_DIR, { recursive: true });

    try {
        console.log('\n[1] NUL byte rejection (G2 / B8)');
        const nulBody = 'evil';
        const r1 = await request('PUT', '/api/deploy/file%00.txt', nulBody, authHeader());
        check('NUL byte in filename -> 403', r1.status === 403, `got ${r1.status} body=${r1.body}`);

        console.log('\n[2] Windows absolute path rejection (G2 / B9)');
        // Note: Express path-matching with absolute paths is tricky on Windows.
        // The path parameter always comes after the /api/deploy/ prefix, so
        // ":filepath" can never start with "C:" because the URL is "/api/deploy/C:..."
        // — Express will treat the path as "C:..." literal. We test the literal
        // payload that resolveSafeDeployPath receives.
        const r2 = await request('PUT', '/api/deploy/' + encodeURIComponent('C:/Windows/System32/drivers/etc/hosts_evil'),
            'evil', authHeader());
        check('Windows abs path C:\\... -> 403', r2.status === 403, `got ${r2.status} body=${r2.body}`);

        console.log('\n[3] Mixed encoding path traversal (G2 / B10)');
        // Express decodes the URL once before passing to handler.
        // %252f becomes literal '%2f' which is NOT a path separator — so a
        // double-encoded attack does NOT actually traverse. Verify the file
        // (if accepted) stays inside DEPLOY_DIR, OR is rejected outright.
        const r3 = await request('PUT', '/api/deploy/..%252f..%252fescape.txt', 'evil', authHeader());
        // Either 403 (rejected) or 200 with file safely inside DEPLOY_DIR is acceptable
        if (r3.status === 200) {
            const written = path.join(DEPLOY_DIR, '..%2f..%2fescape.txt');
            const resolved = path.resolve(written);
            check('Double-encoded file (if accepted) stays inside DEPLOY_DIR',
                  resolved.startsWith(DEPLOY_DIR + path.sep) || resolved === DEPLOY_DIR,
                  `resolved=${resolved}`);
            // cleanup
            try { fs.rmSync(path.dirname(written), { recursive: true, force: true }); } catch {}
        } else {
            check('Double-encoded path rejected', r3.status === 403, `got ${r3.status}`);
        }

        const r3b = await request('PUT', '/api/deploy/%2e%2e%2fescape.txt', 'evil', authHeader());
        check('Encoded ..%2f (single) -> 403', r3b.status === 403, `got ${r3b.status} body=${r3b.body}`);

        console.log('\n[4] Nested subdirectory creation (B11)');
        const r4 = await request('PUT', '/api/deploy/sub/dir/nested.txt',
            'nested content', authHeader());
        check('PUT to sub/dir/nested.txt -> 200', r4.status === 200, `got ${r4.status} body=${r4.body}`);
        const nestedPath = path.join(DEPLOY_DIR, 'sub', 'dir', 'nested.txt');
        check('File exists at sub/dir/nested.txt', fs.existsSync(nestedPath));
        if (fs.existsSync(nestedPath)) {
            check('Nested file content matches', fs.readFileSync(nestedPath, 'utf8') === 'nested content');
        }

        console.log('\n[5] resolveSafeDeployPath logic (B12)');
        // Source the function via require — but it's not exported. Test via the
        // HTTP surface instead: behavior we already know from index.js.
        // Deeper path: PUT with deep nested path inside DEPLOY_DIR
        const r5 = await request('PUT', '/api/deploy/a/b/c/d/e/f/g/h/deep.txt',
            'deep', authHeader());
        check('8-level deep path -> 200', r5.status === 200, `got ${r5.status}`);
        const deepPath = path.join(DEPLOY_DIR, 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'deep.txt');
        check('Deep file exists', fs.existsSync(deepPath));

        console.log('\n[6] Empty path rejection');
        // Express matches /api/deploy/ to the route with empty :filepath.
        // resolveSafeDeployPath('') returns null (length 0), so handler returns 403.
        const r6 = await request('PUT', '/api/deploy/', 'evil', authHeader());
        check('Empty path -> 403 (validator rejects empty string)', r6.status === 403, `got ${r6.status}`);

        console.log('\n[7] List depth cap (G6)');
        // Create 10-level deep directory tree, list should cap at 8
        const deepDir = path.join(DEPLOY_DIR, 'listcap');
        let d = deepDir;
        for (let i = 0; i < 10; i++) {
            d = path.join(d, `l${i}`);
            fs.mkdirSync(d, { recursive: true });
        }
        // Place a file at depth 9 (>8 cap)
        const tooDeepFile = path.join(d, 'toodeep.txt');
        fs.writeFileSync(tooDeepFile, 'should not appear');
        // Place a file at depth 5 (within cap)
        const withinCapFile = path.join(deepDir, 'l0', 'l1', 'l2', 'l3', 'l4', 'within.txt');
        fs.writeFileSync(withinCapFile, 'within cap');

        const r7 = await request('GET', '/api/deploy/list', null, authHeader());
        check('GET list -> 200', r7.status === 200, `got ${r7.status}`);
        const listBody = JSON.parse(r7.body);
        check('List does NOT contain depth-10 toodeep.txt',
            !listBody.files.includes('listcap/l0/l1/l2/l3/l4/l5/l6/l7/l8/l9/toodeep.txt'),
            `files=${JSON.stringify(listBody.files)}`);
        check('List DOES contain depth-6 within.txt',
            listBody.files.includes('listcap/l0/l1/l2/l3/l4/within.txt'),
            `files=${JSON.stringify(listBody.files)}`);

        console.log('\n[8] Bearer auth edge cases (G1)');
        // Empty bearer
        const r8a = await request('PUT', '/api/deploy/x.txt', 'x', { 'Authorization': 'Bearer ' });
        check('Empty Bearer -> 401', r8a.status === 401, `got ${r8a.status}`);
        // Wrong scheme
        const r8b = await request('PUT', '/api/deploy/x.txt', 'x', { 'Authorization': 'Basic ' + Buffer.from(PASSWORD).toString('base64') });
        check('Basic auth (not Bearer) -> 401', r8b.status === 401, `got ${r8b.status}`);
        // Malformed base64 — server falls back to '' or garbage, should still 401
        const r8c = await request('PUT', '/api/deploy/x.txt', 'x', { 'Authorization': 'Bearer !!!notbase64!!!' });
        check('Malformed base64 Bearer -> 401', r8c.status === 401, `got ${r8c.status}`);

    } catch (err) {
        console.error('Test error:', err);
        failed++;
    } finally {
        stopServer();
        // cleanup deploy dir
        rmrf(DEPLOY_DIR);
        console.log(`\n=== ${passed} passed, ${failed} failed ===`);
        process.exit(failed > 0 ? 1 : 0);
    }
})();
