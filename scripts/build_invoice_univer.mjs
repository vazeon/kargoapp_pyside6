import { build } from 'esbuild'
import { mkdir, rm } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const entry = resolve(projectRoot, 'web/invoice_univer/main.js')
const outputDir = resolve(projectRoot, 'tabs/invoice_univer/vendor')

await mkdir(outputDir, { recursive: true })
await rm(resolve(outputDir, 'invoice_univer.js'), { force: true })
await rm(resolve(outputDir, 'invoice_univer.css'), { force: true })

await build({
  entryPoints: [entry],
  bundle: true,
  minify: true,
  sourcemap: false,
  target: ['chrome88'],
  platform: 'browser',
  format: 'iife',
  outfile: resolve(outputDir, 'invoice_univer.js'),
  assetNames: 'assets/[name]-[hash]',
  chunkNames: 'chunks/[name]-[hash]',
  loader: {
    '.woff': 'file',
    '.woff2': 'file',
    '.ttf': 'file',
    '.eot': 'file',
    '.png': 'file',
    '.jpg': 'file',
    '.jpeg': 'file',
    '.gif': 'file',
    '.svg': 'dataurl',
  },
  logLevel: 'info',
})

console.log('Univer Invoice bundle selesai dibuat di tabs/invoice_univer/vendor/.')
