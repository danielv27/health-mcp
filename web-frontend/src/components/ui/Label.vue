<script setup>
import { cn } from "@/lib/utils";
defineProps({ class: { type: String, default: "" } });
</script>

<template>
  <label :class="cn('text-xs font-medium uppercase tracking-wide text-muted-foreground', $props.class)">
    <slot />
  </label>
</template>
