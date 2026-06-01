// Multer upload smoke test (verifies the 1.x -> 2.x upgrade)
const http = require('http');
const path = require('path');
const fs = require('fs');

const PORT = 21998;
const PASSWORD = process.env.TEST_PASSWORD || 'test-pw-' + Date.now();
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
    return { 'Authorization': '***' + Buffer.from(PASSWORD).toString('base64') };
}

// Build a multipart/form-data body
function buildMultipart(fields, files) {
    const boundary = '----formboundary' + Math.random().toString(36).slice(2);
    const parts = [];
    for (const [name, value] of Object.entries(fields)) {
        parts.push(Buffer.from(
            `--${boundary}\r\n` +
            `Content-Disposition: form-data; name="${name}"\r\n\r\n` +
            `${value}\r\n`
        ));
    }
    for (const file of files) {
        parts.push(Buffer.from(
            `--${boundary}\r\n` +
            `Content-Disposition: form-data; name="${file.field}"; filename="${file.name}"\r\n` +
            `Content-Type: ${file.contentType || 'application/octet-stream'}\r\n\r\n`
        ));
        parts.push(file.content);
        parts.push(Buffer.from('\r\n'));
    }
    parts.push(Buffer.from(`--${boundary}--\r\n`));
    const body = Buffer.concat(parts);
    return { body, headers: {
        'Content-Type': `multipart/form-data; boundary=${boundary}`,
        'Content-Length': body.length
    }};
}

function request(method, urlPath, body, headers) {
    return new Promise((resolve, reject) => {
        const req = http.request({
            hostname: '127.0.0.1', port: PORT, method, path: urlPath,
            headers: { ...headers }
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

let passed = 0, failed = 0;
function check(name, ok, detail) {
    if (ok) { console.log(`  PASS  ${name}`); passed++; }
    else { console.log(`  FAIL  ${name} ${detail || ''}`); failed++; }
}

(async () => {
    console.log('Starting server...');
    await startServer();

    try {
        console.log('\n[1] Multer 2.x file upload');
        const small = Buffer.from('test file content');
        const mp = buildMultipart({ agentId: 'fake-agent' }, [
            { field: 'file', name: 'test.txt', contentType: 'text/plain', content: small }
        ]);
        const r1 = await request('POST', '/api/upload', mp.body, mp.headers);
        check('POST /api/upload -> 200', r1.status === 200, `got ${r1.status} body=${r1.body}`);
        const resp = JSON.parse(r1.body);
        check('Response has filename', resp.filename && resp.filename.includes('test.txt'),
              `filename=${resp.filename}`);
        check('Response size matches', resp.size === small.length, `size=${resp.size}`);
        // Verify file actually written
        const uploadedPath = path.join(__dirname, 'server', 'uploads', resp.filename);
        check('File exists on disk', fs.existsSync(uploadedPath));
        if (fs.existsSync(uploadedPath)) {
            check('Content matches', fs.readFileSync(uploadedPath).equals(small));
            fs.unlinkSync(uploadedPath); // cleanup
        }

        console.log('\n[2] Multipart missing file field');
        const mp2 = buildMultipart({}, []);
        const r2 = await request('POST', '/api/upload', mp2.body, mp2.headers);
        check('Missing file -> 400', r2.status === 400, `got ${r2.status}`);

        console.log('\n[3] Filename sanitization');
        const evil = Buffer.from('x');
        const mp3 = buildMultipart({}, [
            { field: 'file', name: '../../../etc/passwd_evil.txt', content: evil }
        ]);
        const r3 = await request('POST', '/api/upload', mp3.body, mp3.headers);
        check('Evil filename -> 200', r3.status === 200, `got ${r3.status}`);
        if (r3.status === 200) {
            const resp3 = JSON.parse(r3.body);
            const evilPath = path.join(__dirname, 'server', 'uploads', resp3.filename);
            check('Stored under uploads/', evilPath.includes('uploads'), `path=${evilPath}`);
            check('Filename has no ../ segments', !resp3.filename.includes('..'),
                  `filename=${resp3.filename}`);
            check('Filename has no path separator', !/[\/\\]/.test(resp3.filename.replace(/^\d+-/, '')),
                  `filename=${resp3.filename}`);
            if (fs.existsSync(evilPath)) fs.unlinkSync(evilPath);
        }

        console.log('\n[4] Path-only filename');
        const evil2 = Buffer.from('y');
        const mp4 = buildMultipart({}, [
            { field: 'file', name: '../../justdir', content: evil2 }
        ]);
        const r4 = await request('POST', '/api/upload', mp4.body, mp4.headers);
        check('Path-only name -> 200', r4.status === 200, `got ${r4.status}`);
        if (r4.status === 200) {
            const resp4 = JSON.parse(r4.body);
            const stored = resp4.filename.replace(/^\d+-/, '');
            check('Stored name is basename only', stored === 'justdir',
                  `stored=${stored}, full=${resp4.filename}`);
            const p = path.join(__dirname, 'server', 'uploads', resp4.filename);
            if (fs.existsSync(p)) fs.unlinkSync(p);
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
