import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the Python backend on 127.0.0.1:8000, so the
// browser only ever talks to one origin and no CORS or base-URL configuration
// is needed while developing. Change the target here if you run the backend on
// another port (python server.py --port 9000).
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  plugins: [react()],
})
