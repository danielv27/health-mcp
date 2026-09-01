<script setup>
import { RouterLink, RouterView, useRoute } from "vue-router";
import { Toaster } from "vue-sonner";
import { UtensilsCrossed, LineChart, MessageCircle, Settings } from "lucide-vue-next";

const route = useRoute();
const tabs = [
  { to: "/", label: "Today", icon: UtensilsCrossed },
  { to: "/trends", label: "Trends", icon: LineChart },
  { to: "/chat", label: "Chat", icon: MessageCircle },
  { to: "/settings", label: "Settings", icon: Settings },
];
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <a
      href="#main"
      class="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
    >
      Skip to content
    </a>

    <header class="sticky top-0 z-40 hidden border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:block">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <span class="text-sm font-semibold tracking-tight">Ledger</span>
        <nav class="flex items-center gap-1">
          <RouterLink
            v-for="tab in tabs"
            :key="tab.to"
            :to="tab.to"
            class="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            :class="{ 'bg-accent text-foreground': route.path === tab.to }"
          >
            <component :is="tab.icon" class="h-4 w-4" />
            {{ tab.label }}
          </RouterLink>
        </nav>
      </div>
    </header>

    <header class="sticky top-0 z-40 flex items-center justify-center border-b bg-background/95 py-3 backdrop-blur sm:hidden">
      <span class="text-sm font-semibold tracking-tight">Ledger</span>
    </header>

    <main id="main" class="mx-auto max-w-6xl px-4 pb-24 pt-4 sm:px-6 sm:pb-10">
      <RouterView />
    </main>

    <nav
      class="fixed inset-x-0 bottom-0 z-40 flex border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 sm:hidden"
      style="padding-bottom: env(safe-area-inset-bottom)"
    >
      <RouterLink
        v-for="tab in tabs"
        :key="tab.to"
        :to="tab.to"
        class="flex flex-1 flex-col items-center gap-1 py-2.5 text-xs font-medium text-muted-foreground"
        :class="{ 'text-primary': route.path === tab.to }"
      >
        <component :is="tab.icon" class="h-5 w-5" />
        {{ tab.label }}
      </RouterLink>
    </nav>

    <Toaster position="top-center" rich-colors close-button />
  </div>
</template>
