import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  base: "/", // 自定义域根路径
  build: {
    outDir: "dist",
    emptyOutDir: true
  }
});