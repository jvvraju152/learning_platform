import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import path from "path"

// Build output goes to ../frontend_dist, which the Python server picks up automatically.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: { outDir: "../frontend_dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
})
