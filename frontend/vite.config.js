import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Gelistirmede /api istekleri backend'e (uvicorn, 8000) proxy'lenir.
const target = process.env.BETODDS_API || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target,
        changeOrigin: true,
        // SSE akisinin tamponlanmamasi icin
        configure: (proxy) => {
          proxy.on('proxyRes', (res) => { res.headers['cache-control'] = 'no-cache' })
        },
      },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
