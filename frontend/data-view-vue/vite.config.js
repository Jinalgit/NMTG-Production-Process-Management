import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export default defineConfig({
  plugins: [
    vue()
  ],

  base: "/static/vue/data-view/",

  build: {
    outDir: resolve(
      __dirname,
      "../../static/vue/data-view"
    ),

    emptyOutDir: true,

    cssCodeSplit: false,

    rollupOptions: {
      input: resolve(
        __dirname,
        "src/main.js"
      ),

      output: {
        entryFileNames: "data-view.js",

        chunkFileNames:
          "assets/[name]-[hash].js",

        assetFileNames: (assetInfo) => {
          const name =
            assetInfo.name || "";

          if (name.endsWith(".css")) {
            return "data-view.css";
          }

          return "assets/[name]-[hash][extname]";
        }
      }
    }
  }
});