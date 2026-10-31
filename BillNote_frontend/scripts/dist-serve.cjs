/**
 * Production-artifact harness.
 *
 * `pnpm build` output assumes a reverse proxy maps /api and /static onto the
 * backend (that is what nginx does in docker-compose). Serving dist with a plain
 * static server therefore shows the boot screen, not the app — so this script
 * serves dist AND proxies the two backend prefixes, which is the only way to
 * screenshot the real built bundle against the real backend.
 */
const http = require('http')
const fs = require('fs')
const path = require('path')

const DIST = path.join(__dirname, '..', 'dist')
const BACKEND = { host: '127.0.0.1', port: 8483 }
const PORT = Number(process.env.PORT || 4174)

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json; charset=utf-8',
  '.woff2': 'font/woff2',
}

const proxy = (req, res) => {
  const upstream = http.request(
    {
      host: BACKEND.host,
      port: BACKEND.port,
      path: req.url,
      method: req.method,
      headers: req.headers,
    },
    up => {
      res.writeHead(up.statusCode || 502, up.headers)
      up.pipe(res)
    }
  )
  upstream.on('error', () => {
    res.writeHead(502)
    res.end('bad gateway')
  })
  req.pipe(upstream)
}

http
  .createServer((req, res) => {
    if (req.url.startsWith('/api') || req.url.startsWith('/static')) return proxy(req, res)
    const rel = req.url.split('?')[0] === '/' ? '/index.html' : req.url.split('?')[0]
    const file = path.join(DIST, rel)
    if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(200, { 'content-type': TYPES['.html'] })
      return res.end(fs.readFileSync(path.join(DIST, 'index.html')))
    }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' })
    res.end(fs.readFileSync(file))
  })
  .listen(PORT, '127.0.0.1', () => console.log('dist harness on http://127.0.0.1:' + PORT))
