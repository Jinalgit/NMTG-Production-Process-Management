import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "node:path";
import { fileURLToPath } from "node:url";

const currentDir =
  path.dirname(
    fileURLToPath(import.meta.url)
  );

export default defineConfig({
  root: currentDir,

  plugins: [
    vue()
  ],

  build: {
    outDir:
      path.resolve(
        currentDir,
        "../../../static/vue/user-management"
      ),

    emptyOutDir: false,

    cssCodeSplit: false,

    rollupOptions: {
      input:
        path.resolve(
          currentDir,
          "src/main.js"
        ),

      output: {
        entryFileNames:
          "assets/app.js",

        chunkFileNames:
          "assets/[name].js",

        assetFileNames:
          (assetInfo) => {
            const name =
              assetInfo.name || "";

            if (
              name.endsWith(".css")
            ) {
              return "assets/app.css";
            }

            return "assets/[name][extname]";
          }
      }
    }
  }
});