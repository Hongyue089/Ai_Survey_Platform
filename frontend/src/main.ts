import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import "./style.css";
import App from "./App.vue";
import Projects from "./Projects.vue";
import Editor from "./Editor.vue";
import Preview from "./Preview.vue";
import PreviewData from "./PreviewData.vue";
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: Projects },
    { path: "/survey/:id/preview", component: Preview },
    { path: "/survey/:id/preview-data", component: PreviewData },
    { path: "/survey/:id/:module(builder|flow|options)", component: Editor },
    {
      path: "/survey/:id/:module(distribution|analysis|report)",
      component: Editor,
    },
  ],
});
createApp(App).use(router).use(ElementPlus).mount("#app");
