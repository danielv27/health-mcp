<script setup>
import { DialogClose, DialogContent, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from "radix-vue";
import { X } from "lucide-vue-next";

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: "" },
});
const emit = defineEmits(["update:open"]);
</script>

<template>
  <DialogRoot :open="open" @update:open="(v) => emit('update:open', v)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=open]:fade-in data-[state=closed]:animate-out data-[state=closed]:fade-out" />
      <DialogContent
        class="fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[85vh] w-full max-w-lg flex-col gap-4 rounded-t-xl border bg-background p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-lg outline-none data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom data-[state=closed]:animate-out data-[state=closed]:slide-out-to-bottom"
      >
        <div class="flex items-center justify-between">
          <DialogTitle class="text-base font-semibold">{{ title }}</DialogTitle>
          <DialogClose class="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground" aria-label="Close">
            <X class="h-4 w-4" />
          </DialogClose>
        </div>
        <div class="overflow-y-auto">
          <slot />
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
