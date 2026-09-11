<script setup>
import {
    nextTick,
    onBeforeUnmount,
    onMounted,
    ref,
    watch
} from "vue";

import * as echarts from "echarts";


const props = defineProps({
    option: {
        type: Object,
        required: true
    },

    height: {
        type: String,
        default: "340px"
    }
});


const emit = defineEmits([
    "chart-click"
]);


const host = ref(null);

let instance = null;
let resizeObserver = null;


function render() {

    if (!instance || !props.option) {
        return;
    }


    instance.setOption(
        props.option,
        {
            notMerge: false,
            lazyUpdate: false,
            replaceMerge: ["series"]
        }
    );
}


function resize() {

    if (instance) {
        instance.resize();
    }
}


watch(
    () => props.option,
    async () => {

        await nextTick();

        render();
    },
    {
        deep: true
    }
);


onMounted(
    async () => {

        await nextTick();


        instance = echarts.init(
            host.value,
            null,
            {
                renderer: "canvas"
            }
        );


        instance.on(
            "click",
            params => {
                emit("chart-click", params);
            }
        );


        render();


        resizeObserver = new ResizeObserver(resize);

        resizeObserver.observe(host.value);

        window.addEventListener(
            "resize",
            resize
        );
    }
);


onBeforeUnmount(
    () => {

        window.removeEventListener(
            "resize",
            resize
        );


        if (resizeObserver) {
            resizeObserver.disconnect();
        }


        if (instance) {

            instance.dispose();

            instance = null;
        }
    }
);
</script>


<template>
    <div
        ref="host"
        class="nmtg-echart"
        :style="{ height }"
    ></div>
</template>