<script setup>
import { cn } from "@/lib/utils";

defineOptions({ inheritAttrs: false });
const props = defineProps({
  class: { type: String, default: "" },
  modelValue: { type: [String, Number], default: undefined },
});
defineEmits(["update:modelValue"]);
</script>

<template>
  <input
    v-bind="$attrs"
    :value="modelValue"
    @input="$emit('update:modelValue', $attrs.type === 'number' ? $event.target.valueAsNumber : $event.target.value)"
    :class="cn(
      'flex h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
      props.class
    )"
  />
</template>
