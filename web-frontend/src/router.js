import { createRouter, createWebHistory } from "vue-router";
import TodayView from "@/views/TodayView.vue";
import TrendsView from "@/views/TrendsView.vue";
import ChatView from "@/views/ChatView.vue";
import SettingsView from "@/views/SettingsView.vue";

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "today", component: TodayView },
    { path: "/trends", name: "trends", component: TrendsView },
    { path: "/chat", name: "chat", component: ChatView },
    { path: "/settings", name: "settings", component: SettingsView },
  ],
});
