<script setup>
import { Plus, Check } from "lucide-vue-next";
import Badge from "@/components/ui/Badge.vue";

defineProps({ food: Object, inCart: Boolean });
defineEmits(["toggle"]);
</script>

<template>
  <button
    type="button"
    class="flex w-full items-center justify-between gap-3 rounded-lg border p-3 text-left transition-colors"
    :class="inCart ? 'border-primary bg-primary/5' : 'bg-card hover:bg-accent/50'"
    @click="$emit('toggle', food)"
  >
    <span class="min-w-0">
      <span class="flex items-center gap-2">
        <span class="truncate text-sm font-medium">{{ food.name }}</span>
        <Badge :variant="food.source === 'verified' ? 'success' : 'warning'">{{ food.source }}</Badge>
      </span>
      <span class="mt-0.5 block text-xs tabular text-muted-foreground">
        {{ Math.round(food.last_grams) }}g last time
      </span>
    </span>
    <span
      class="flex h-8 w-8 flex-none items-center justify-center rounded-full"
      :class="inCart ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'"
    >
      <Check v-if="inCart" class="h-4 w-4" />
      <Plus v-else class="h-4 w-4" />
    </span>
  </button>
</template>
