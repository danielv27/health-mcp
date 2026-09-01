<script setup>
import { nextTick, onMounted, ref } from "vue";
import { Send, MessageCircleOff } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import { cn } from "@/lib/utils";

const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const notConfigured = ref(false);
const listEl = ref(null);

async function send() {
  const text = draft.value.trim();
  if (!text || sending.value) return;
  messages.value.push({ role: "user", content: text });
  draft.value = "";
  sending.value = true;
  await scrollToBottom();
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: messages.value }),
    });
    if (res.status === 503) {
      notConfigured.value = true;
      messages.value.pop();
      return;
    }
    if (!res.ok) {
      messages.value.push({ role: "assistant", content: "Something went wrong — try again." });
      return;
    }
    const reply = await res.json();
    messages.value.push(reply);
  } finally {
    sending.value = false;
    await scrollToBottom();
  }
}

async function scrollToBottom() {
  await nextTick();
  listEl.value?.scrollTo({ top: listEl.value.scrollHeight, behavior: "smooth" });
}

function onKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}

onMounted(async () => {
  const res = await fetch("/api/chat/status").catch(() => null);
  const status = await res?.json().catch(() => null);
  notConfigured.value = !status?.configured;
});
</script>

<template>
  <div class="flex h-[calc(100vh-9.5rem)] flex-col sm:h-[calc(100vh-8rem)]">
    <h1 class="mb-4 text-lg font-semibold tracking-tight">Chat</h1>

    <div v-if="notConfigured" class="flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-center">
      <MessageCircleOff class="h-8 w-8 text-muted-foreground" />
      <p class="text-sm font-medium">Chat isn't configured yet</p>
      <p class="max-w-xs text-xs text-muted-foreground">
        Set HEALTH_MCP_ANTHROPIC_API_KEY on the server to let Claude answer questions about your training and eating history.
      </p>
    </div>

    <template v-else>
      <div ref="listEl" class="flex-1 space-y-3 overflow-y-auto pb-3">
        <div v-if="messages.length === 0" class="py-10 text-center text-sm text-muted-foreground">
          Ask about your training or eating history — e.g. "How's my protein this week?" or "Did I train more on high-calorie days?"
        </div>
        <div
          v-for="(m, i) in messages"
          :key="i"
          :class="cn('max-w-[85%] rounded-lg px-3 py-2 text-sm', m.role === 'user' ? 'ml-auto bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground')"
        >
          {{ m.content }}
        </div>
        <div v-if="sending" class="max-w-[85%] rounded-lg bg-secondary px-3 py-2 text-sm text-muted-foreground">
          Thinking…
        </div>
      </div>
      <div class="flex items-end gap-2 border-t pt-3">
        <Input
          v-model="draft"
          placeholder="Ask about your data…"
          class="flex-1"
          @keydown="onKeydown"
        />
        <Button size="icon" :disabled="sending || !draft.trim()" @click="send" aria-label="Send">
          <Send class="h-4 w-4" />
        </Button>
      </div>
    </template>
  </div>
</template>
