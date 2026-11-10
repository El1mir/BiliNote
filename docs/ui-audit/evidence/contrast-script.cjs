// Recomputes WCAG contrast from the real token source (BillNote_frontend/src/ember/tokens.css).
// Values are parsed from the `@theme` block so the report can never drift from the shipped CSS.
const fs = require('fs');
const path = require('path');
const tokensPath = path.join(__dirname, '../../../BillNote_frontend/src/ember/tokens.css');
const css = fs.readFileSync(tokensPath, 'utf8');
const theme = css.slice(css.indexOf('@theme'), css.indexOf('/* Semantic aliases'));
const read = (name) => {
  const m = theme.match(new RegExp('--color-' + name + ':\\s*(#[0-9a-fA-F]{6})'));
  if (!m) throw new Error('token not found: ' + name);
  return m[1].toLowerCase();
};
const hex = (h) => h.replace('#', '').match(/../g).map((x) => parseInt(x, 16) / 255);
const lin = (c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const L = (h) => { const [r, g, b] = hex(h).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const cr = (a, b) => { const [x, y] = [L(a), L(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const c = {};
for (const n of ['canvas','surface','raised','raised-hover','line','ink','ink-soft','ink-mute','ok','warn','danger','ember']) c[n] = read(n);
const pairs = [
  ['line','canvas',3.0],['line','surface',3.0],
  ['warn','surface',4.5],['ok','surface',4.5],['danger','surface',4.5],
  ['ink-mute','surface',4.5],['ink-mute','raised',4.5],
  ['ink','canvas',4.5],['ink-soft','surface',4.5],['ember','canvas',4.5],['ink-mute','canvas',4.5],
];
let failed = 0;
console.log('source:', path.relative(process.cwd(), tokensPath));
console.log('palette:', JSON.stringify(c));
for (const [a, b, min] of pairs) {
  const v = cr(c[a], c[b]);
  const ok = v >= min;
  if (!ok) failed++;
  console.log((a + '/' + b).padEnd(20), v.toFixed(2), '>= ' + min.toFixed(1), ok ? 'PASS' : 'FAIL');
}
// Chip hover direction: the raised controls must get darker on hover, never lighter.
console.log('raised luminance      ', L(c['raised']).toFixed(4));
console.log('raised-hover luminance', L(c['raised-hover']).toFixed(4), L(c['raised-hover']) < L(c['raised']) ? 'DARKER (hover darkens) PASS' : 'LIGHTER FAIL');
console.log(failed === 0 ? 'ALL CONTRAST CHECKS PASS' : failed + ' CHECK(S) FAILED');
process.exit(failed === 0 ? 0 : 1);