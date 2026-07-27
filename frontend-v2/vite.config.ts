import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '../', '')
  const host = env.BACKEND_HOST || '127.0.0.1'
  const port = env.BACKEND_PORT || '8000'
  const target = `http://${host}:${port}`

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5174,
      proxy: {
        '/api': target,
        '/health': target,
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      css: true,
    },
  }
})
