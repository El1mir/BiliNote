// Self-hosted faces (W0). Imported for their side effect: each file ships the
// woff2 and the @font-face rule, so first paint never waits on a CDN.
//
// Latin subsets only: CJK glyphs are far larger than the UI budget and the
// system stack in tokens.css paints them immediately.
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'
import '@fontsource/source-serif-4/latin-400.css'
import '@fontsource/source-serif-4/latin-600.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'