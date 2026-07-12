import { defineConfig } from "vite";

export default defineConfig(async () => {
  // Dynamically import the ESM‑only plugin
  const { default: react } = await import("@vitejs/plugin-react");

  return {
    plugins: [react()],
    // Prevent Vite from attempting to load/parse postcss.config.*
    // (set to an empty string to satisfy Vite typing)
    css: { postcss: {} },
    // Do not force-map/include optional map deps during dev startup.
    // MapGL is not part of the current UI; avoiding these prevents blank screen.
    optimizeDeps: {},
    server: {
      proxy: {
        "/api": {
          target: "http://backend:8000",
          changeOrigin: true,
        },
      },
    },
  };
});



