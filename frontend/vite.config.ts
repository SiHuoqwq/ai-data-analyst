import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const projectRoot = fileURLToPath(new URL('../', import.meta.url))
  const env = loadEnv(mode, projectRoot, '')
  const backendHost = env.BACKEND_HOST || '127.0.0.1'
  const backendPort = env.BACKEND_PORT || '8000'
  const backendUrl = `http://${backendHost}:${backendPort}`

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': backendUrl,
        '/storage': backendUrl,
      },
    },
  }
})
