import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Mirror Caddy routing for local dev
      '/servers': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/servers/, ''),
        ws: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api/, ''),
      },
      '/email': {
        target: 'http://localhost:8014',
        changeOrigin: true,
      },
      '/registry': {
        target: 'http://localhost:8012',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/registry/, ''),
      },
      '/vault': {
        target: 'http://localhost:8007',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/vault/, ''),
      },
      '/dns': {
        target: 'http://localhost:8006',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/dns/, ''),
      },
      '/notify': {
        target: 'http://localhost:8008',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/notify/, ''),
      },
      '/automation': {
        target: 'http://localhost:8013',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/automation/, ''),
      },
      '/pbx': {
        target: 'http://localhost:8011',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/pbx/, ''),
      },
      '/storage': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/storage/, ''),
      },
      '/monitor': {
        target: 'http://localhost:8004',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/monitor/, ''),
      },
    },
  },
})

