// vite.config.js
//import { defineConfig } from 'vite'
//import react from '@vitejs/plugin-react'

//export default defineConfig({
//  plugins: [react()],
//  server: {
//    port: 5174,
//    host: true,
//    proxy: {
//      '/api': {
//        // FIX: usar localhost para mantener consistencia con pruebas/cURL
//        target: 'http://localhost:8001',
//        changeOrigin: true,
//        secure: false,
//        ws: true,
//      },
//    },
//  },
//})

// vite.config.js
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default ({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '') // carga .env.local
  return defineConfig({
    plugins: [react()],
    server: {
      port: 5174,
      host: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8001', // host -> contenedor (8001:8000)
          changeOrigin: true,
          secure: false,
          ws: true,
          // 👇 inyecta SIEMPRE la API Key en dev
          headers: {
            'X-API-Key': env.VITE_API_KEY,
          },
        },
      },
    },
  })
}