import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  base: "/", // 自定义域 + 根路径
  build: {
    outDir: ".",        // 构建产物输出到仓库根目录（给 Pages 用）
    assetsDir: "assets",
    emptyOutDir: false  // 不要清空根目录，避免删掉 CNAME / 源码
  }
});