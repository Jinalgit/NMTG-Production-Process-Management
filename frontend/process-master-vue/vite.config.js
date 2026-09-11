import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

import {
    fileURLToPath
} from "url";

import {
    dirname,
    resolve
} from "path";


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

    base:
        "/static/vue/process-master/",


    build: {

        outDir:
            resolve(
                __dirname,
                "../../static/vue/process-master"
            ),

        emptyOutDir: true,

        cssCodeSplit: false,


        rollupOptions: {

            input:
                resolve(
                    __dirname,
                    "src/main.js"
                ),


            output: {

                entryFileNames:
                    "process-master.js",

                chunkFileNames:
                    "assets/[name]-[hash].js",


                assetFileNames:
                    function (assetInfo) {

                        const name =
                            assetInfo.name || "";


                        if (
                            name.endsWith(".css")
                        ) {

                            return "process-master.css";

                        }


                        return (
                            "assets/" +
                            "[name]-[hash][extname]"
                        );

                    }

            }

        }

    }

});
