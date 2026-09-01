<script setup>
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const props = defineProps({
  variant: { type: String, default: "default" },
  class: { type: String, default: "" },
});

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium tabular",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary/10 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "text-foreground",
        success: "border-transparent bg-success/10 text-success",
        warning: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400",
        destructive: "border-transparent bg-destructive/10 text-destructive",
      },
    },
    defaultVariants: { variant: "default" },
  }
);
</script>

<template>
  <span :class="cn(badgeVariants({ variant }), props.class)"><slot /></span>
</template>
