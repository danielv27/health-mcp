<script setup>
import { cn } from "@/lib/utils";

const props = defineProps({
  value: { type: Number, default: 0 },
  class: { type: String, default: "" },
  indicatorClass: { type: String, default: "bg-primary" },
});
const pct = () => Math.min(100, Math.max(0, props.value));
</script>

<template>
  <div :class="cn('relative h-2 w-full overflow-hidden rounded-full bg-secondary', props.class)">
    <div
      class="h-full rounded-full transition-all duration-500"
      :class="indicatorClass"
      :style="{ width: pct() + '%' }"
    />
  </div>
</template>
