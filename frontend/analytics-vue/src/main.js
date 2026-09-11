import { createApp } from "vue";

import PrimeVue from "primevue/config";
import Aura from "@primeuix/themes/aura";

import "primeicons/primeicons.css";

import App from "./App.vue";
import "./style.css";


const app =
    createApp(App);


app.use(
    PrimeVue,
    {
        ripple: true,

        theme: {

            preset: Aura,

            options: {

                darkModeSelector:
                    ".jms-dark-theme",

                cssLayer: false
            }
        }
    }
);


app.mount(
    "#analytics-vue"
);