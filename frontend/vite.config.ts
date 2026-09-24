import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // Every backend router prefix must be listed here, or the tab that
      // calls it gets a 404 from the dev server and renders empty.
      '/health': 'http://127.0.0.1:8000',
      '/devices': 'http://127.0.0.1:8000',
      '/apps': 'http://127.0.0.1:8000',
      '/library': 'http://127.0.0.1:8000',
      '/sync': 'http://127.0.0.1:8000',
      '/backup': 'http://127.0.0.1:8000',
      '/files': 'http://127.0.0.1:8000',
      '/photos': 'http://127.0.0.1:8000',
      '/storage': 'http://127.0.0.1:8000',
      '/diagnostics': 'http://127.0.0.1:8000',
      '/tools': 'http://127.0.0.1:8000',
      '/firmware': 'http://127.0.0.1:8000',
      '/flash': 'http://127.0.0.1:8000',
      '/screen': 'http://127.0.0.1:8000'
    }
  }
})
