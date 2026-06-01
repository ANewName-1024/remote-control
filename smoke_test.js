// Smoke test for Static Deploy API fixes
// Run with: node smoke_test.js
const http = require('http');
const path = require('path');
const fs = require('fs');

const PORT = 21999; // avoid conflict with main server
const PASSWORD = 'SmokeTest!2026';

let serverProcess = null;

function startServer() {
    return new Promise((resolve, reject) => {
        serverProcess = require('child_process').spawn('node', ['server/index.js'], {
            cwd: __dirname,
            env: { ...process.env, PORT: String(PORT), ACCESS_PASSWORD: PASSWORD },
            stdio: ['ignore', 'pipe', 'pipe']
        });
        serverProcess.stdout.on('data', d => {
            if (d.toString().includes('listening')) resolve();
        });
        serverProcess.stderr.on('data', d => process.stderr.write(d));
        setTimeout(() => resolve(), 1500); // fallback
    });
}

function stopServer() {
    if (serverProcess) serverProcess.kill();
}

function request(method, urlPath, body, headers = {}) {
    return new Promise((resolve, reject) => {
        const req = http.request({
            hostname: '127.0.0.1',
            port: PORT,
            method,
            path: urlPath,
            headers: { 'Content-Length': body ? Buffer.byteLength(body) : 0, ...headers }
        }, res => {
            const chunks = [];
            res.on('data', c => chunks.push(c));
            res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() }));
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
    console.log('Starting server...');
    await startServer();

    try {
        console.log('\n[1] Auth requirement');
        const r1 = await request('PUT', '/api/deploy/hello.txt', 'data', {});
        check('PUT without auth -> 401', r1.status === 401, `got ${r1.status}`);

        const r2 = await request('PUT', '/api/deploy/hello.txt', 'data', { 'Authorization': 'Bearer ' + Buffer.from('wrong').toString('base64') });
        check('PUT with wrong auth -> 401', r2.status === 401, `got ${r2.status}`);

        console.log('\n[2] Normal deploy works');
        const r3 = await request('PUT', '/api/deploy/hello.txt', 'hello world', authHeader());
        check('PUT with auth -> 200', r3.status === 200, `got ${r3.status} body=${r3.body}`);
        const deployedPath = path.join(__dirname, 'server', 'static', 'app', 'hello.txt');
        check('File written to disk', fs.existsSync(deployedPath));
        if (fs.existsSync(deployedPath)) {
            check('Content matches', fs.readFileSync(deployedPath, 'utf8') === 'hello world');
        }

        console.log('\n[3] Path traversal blocked');
        const r4 = await request('PUT', '/api/deploy/../../etc/passwd_evil', 'evil', authHeader());
        check('Traversal with .. -> 403', r4.status === 403, `got ${r4.status} body=${r4.body}`);

        const r5 = await request('PUT', '/api/deploy/..%2f..%2fescape.txt', 'evil', authHeader());
        check('Traversal with URL-encoded ..%2f -> 403', r5.status === 403, `got ${r5.status} body=${r5.body}`);

        const r6 = await request('PUT', '/api/deploy/' + encodeURIComponent('..\\windows.txt'), 'evil', authHeader());
        check('Traversal with ..\\ -> 403', r6.status === 403, `got ${r6.status} body=${r6.body}`);

        // Absolute path injection (Express will receive the literal /etc/passwd)
        const r6b = await request('PUT', '/api/deploy/' + encodeURIComponent('/etc/passwd_evil'), 'evil', authHeader());
        check('Absolute path /etc/... -> 403', r6b.status === 403, `got ${r6b.status} body=${r6b.body}`);

        console.log('\n[4] Size limit enforced');
        const big = Buffer.alloc(60 * 1024 * 1024, 'A'); // 60MB > 50MB limit
        const r7 = await request('PUT', '/api/deploy/big.bin', big, authHeader());
        check('60MB upload -> 413', r7.status === 413, `got ${r7.status}`);

        console.log('\n[5] List endpoint works');
        const r8 = await request('GET', '/api/deploy/list', null, authHeader());
        check('GET list with auth -> 200', r8.status === 200, `got ${r8.status}`);
        const listBody = JSON.parse(r8.body);
        check('List contains hello.txt', listBody.files.includes('hello.txt'),
              `files=${JSON.stringify(listBody.files)}`);

        const r9 = await request('GET', '/api/deploy/list', null, {});
        check('GET list without auth -> 401', r9.status === 401, `got ${r9.status}`);

        console.log('\n[6] Deployed file served via /app/');
        const r10 = await request('GET', '/app/hello.txt', null, {});
        check('GET /app/hello.txt -> 200', r10.status === 200, `got ${r10.status}`);
        check('Content matches', r10.body === 'hello world');

    } catch (err) {
        console.error('Test error:', err);
        failed++;
    } finally {
        stopServer();
        // cleanup
        try { fs.unlinkSync(path.join(__dirname, 'server', 'static', 'app', 'hello.txt')); } catch {}
        console.log(`\n=== ${passed} passed, ${failed} failed ===`);
        process.exit(failed > 0 ? 1 : 0);
    }
})();
