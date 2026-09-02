import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { env } from 'node:process'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': env.VITE_API_PROXY_TARGET || 'http://localhost:5000'
    }
  }
})
