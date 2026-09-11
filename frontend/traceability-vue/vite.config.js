import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

import {
    dirname,
    resolve
} from "path";

import {
    fileURLToPath
} from "url";


const __filename =
    fileURLToPath(
        import.meta.url
    );

const __dirname =
    dirname(__filename);


export default defineConfig({

    plugins: [
        vue()
    ],

    build: {

        outDir:
            resolve(
                __dirname,
                "../../static/vue/traceability"
            ),

        emptyOutDir: true,

        sourcemap: false,

        rollupOptions: {

            input:
                resolve(
                    __dirname,
                    "src/main.js"
                ),

            output: {

                entryFileNames:
                    "traceability.js",

                chunkFileNames:
                    "traceability-[name].js",

                assetFileNames:
                    assetInfo => {

                        if (
                            assetInfo.name &&
                            assetInfo.name.endsWith(".css")
                        ) {
                            return "traceability.css";
                        }

                        return "traceability-[name][extname]";
                    }
            }
        }
    }
});