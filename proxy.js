/**
 * FIFA World Cup 2026 Tracker — Local Proxy Server
 * ─────────────────────────────────────────────────
 * Two jobs:
 *   1. Serves matchdata.json at /local-data so the tracker can
 *      load scores, scorers and stats without any API subscription.
 *   2. Forwards /api/* requests to football-data.org for live scores.
 *
 * REQUIRES: Node.js (v14+) — no npm install needed, uses built-ins only.
 *
 * HOW TO RUN:
 *   node proxy.js
 *
 * Then open worldcup2026.html in your browser.
 * Keep this terminal open while using the tracker.
 * Press Ctrl+C to stop.
 */

const http  = require('http');
const https = require('https');
const url   = require('url');
const fs    = require('fs');
const path  = require('path');

const DATA_FILE = path.join(__dirname, 'matchdata.json');

const PORT      = 3001;
const API_TOKEN = '9d424744f5934fbc9ec3b8a4cae44749';
const API_HOST  = 'api.football-data.org';
const API_BASE  = '/v4';

const server = http.createServer((req, res) => {
  // ── CORS headers — allow any local origin ──
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Auth-Token');

  // Handle preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // Only allow GET requests
  if (req.method !== 'GET') {
    res.writeHead(405, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Method not allowed' }));
    return;
  }

  const parsed   = url.parse(req.url);
  const pathname = parsed.pathname || '';

  // ── /local-data — serve matchdata.json ──
  if (pathname === '/local-data') {
    try {
      const data = fs.readFileSync(DATA_FILE, 'utf8');
      res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
      res.end(data);
    } catch (e) {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'matchdata.json not found' }));
    }
    return;
  }

  // ── Health check ──
  if (pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', message: 'WC2026 proxy running' }));
    return;
  }

  // ── Serve the tracker page itself over http (avoids file:// quirks) ──
  if (pathname === '/' || pathname === '/index.html' || pathname === '/worldcup2026.html') {
    try {
      const html = fs.readFileSync(path.join(__dirname, 'worldcup2026.html'), 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(html);
    } catch (e) {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'worldcup2026.html not found' }));
    }
    return;
  }

  // Must start with /api for football-data.org forwarding
  if (!pathname.startsWith('/api')) {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found. Use /api/... or /local-data' }));
    return;
  }

  // Strip /api prefix, forward the rest to football-data.org
  const forwardPath = API_BASE + pathname.replace('/api', '') + (parsed.search || '');

  const options = {
    hostname: API_HOST,
    port:     443,
    path:     forwardPath,
    method:   'GET',
    headers:  {
      'X-Auth-Token': API_TOKEN,
      'Accept':       'application/json',
    },
  };

  console.log(`[${new Date().toLocaleTimeString()}] → https://${API_HOST}${forwardPath}`);

  const proxyReq = https.request(options, (proxyRes) => {
    let body = '';
    proxyRes.on('data', chunk => { body += chunk; });
    proxyRes.on('end', () => {
      console.log(`[${new Date().toLocaleTimeString()}] ← ${proxyRes.statusCode} (${body.length} bytes)`);
      res.writeHead(proxyRes.statusCode, {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      });
      res.end(body);
    });
  });

  proxyReq.on('error', (err) => {
    console.error(`[ERROR] ${err.message}`);
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Proxy error: ' + err.message }));
  });

  proxyReq.end();
});

server.listen(PORT, '127.0.0.1', () => {
  console.log('');
  console.log('  ⚽  FIFA World Cup 2026 Proxy Server');
  console.log('  ─────────────────────────────────────');
  console.log(`  Running at: http://localhost:${PORT}`);
  console.log(`  Proxying:   https://${API_HOST}${API_BASE}`);
  console.log('');
  console.log('  Open worldcup2026.html in your browser.');
  console.log('  Press Ctrl+C to stop.');
  console.log('');
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`\n  ✗ Port ${PORT} is already in use.`);
    console.error(`  Stop the other process or change PORT at the top of this file.\n`);
  } else {
    console.error('\n  ✗ Server error:', err.message, '\n');
  }
  process.exit(1);
});
