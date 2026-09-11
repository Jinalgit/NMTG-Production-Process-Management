import "./wip-summary-enhance.js";
import "./draft1-direct-fix.js";
import { createApp } from "vue";
import PrimeVue from "primevue/config";
import Aura from "@primeuix/themes/aura";

import "primeicons/primeicons.css";
import "./style.css";

import App from "./App.vue";

const app = createApp(App);

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

app.mount("#data-view-vue");