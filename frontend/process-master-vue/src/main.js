import { createApp } from "vue";

import PrimeVue from "primevue/config";
import Aura from "@primeuix/themes/aura";

import "primeicons/primeicons.css";

import App from "./App.vue";
import "./style.css";


const app = createApp(App);


app.use(PrimeVue, {

    ripple: true,

    theme: {

        preset: Aura,

        options: {

            /*
             * Uses the SAME dark-theme class
             * already used by JMS.
             */
            darkModeSelector:
                ".jms-dark-theme",

            cssLayer: false
        }
    }
});


app.mount("#process-master-vue");
