<script setup>
import Progress from "@/components/ui/Progress.vue";

const props = defineProps({
  label: String,
  unit: String,
  value: Number,
  target: { type: Number, default: null },
});

const pct = () => (props.target ? (props.value / props.target) * 100 : 0);
const over = () => props.target != null && props.value > props.target;
</script>

<template>
  <div class="rounded-lg border bg-card p-3">
    <div class="flex items-baseline justify-between">
      <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">{{ label }}</span>
      <span v-if="target" class="text-xs tabular text-muted-foreground">/{{ Math.round(target) }}</span>
    </div>
    <div class="mt-1 text-2xl font-semibold tabular" :class="over() ? 'text-destructive' : 'text-foreground'">
      {{ Math.round(value) }}<span class="ml-0.5 text-sm font-normal text-muted-foreground">{{ unit }}</span>
    </div>
    <Progress
      v-if="target"
      class="mt-2"
      :value="pct()"
      :indicator-class="over() ? 'bg-destructive' : 'bg-primary'"
    />
  </div>
</template>
