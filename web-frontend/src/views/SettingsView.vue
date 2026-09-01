<script setup>
import { onMounted, reactive, ref } from "vue";
import { toast } from "vue-sonner";
import { RefreshCw } from "lucide-vue-next";
import Card from "@/components/ui/Card.vue";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import Label from "@/components/ui/Label.vue";
import Switch from "@/components/ui/Switch.vue";

const targets = reactive({ kcal: 0, protein: 0, carbs: 0, fat: 0 });
const targetsLoading = ref(true);

const autoSync = ref(false);
const syncStatus = ref({ last_run_at: null, last_status: null, last_error: null });
const syncing = ref(false);

async function loadTargets() {
  const res = await fetch("/api/targets");
  const t = await res.json();
  if (t) Object.assign(targets, t);
  targetsLoading.value = false;
}

async function saveTargets() {
  await fetch("/api/targets", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(targets),
  });
  toast("Targets saved");
}

async function loadSettings() {
  const res = await fetch("/api/settings");
  const s = await res.json();
  autoSync.value = s.hevy_auto_sync;
}

async function loadSyncStatus() {
  const res = await fetch("/api/sync/status");
  syncStatus.value = await res.json();
}

async function onToggleAutoSync(value) {
  autoSync.value = value;
  await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hevy_auto_sync: value }),
  });
  toast(value ? "Background Hevy sync enabled — runs every 30 min" : "Background Hevy sync disabled");
}

async function syncNow() {
  syncing.value = true;
  try {
    const res = await fetch("/api/sync/hevy", { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      toast.error(body.detail || "Sync failed");
    } else {
      toast("Hevy sync complete");
    }
  } finally {
    syncing.value = false;
    await loadSyncStatus();
  }
}

function relativeTime(iso) {
  if (!iso) return "Never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

onMounted(() => {
  loadTargets();
  loadSettings();
  loadSyncStatus();
});
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-lg font-semibold tracking-tight">Settings</h1>

    <Card class="p-4">
      <h2 class="mb-3 text-sm font-medium">Hevy sync</h2>
      <div class="flex items-center justify-between gap-4">
        <div>
          <p class="text-sm">Background auto-sync</p>
          <p class="text-xs text-muted-foreground">Pulls new Hevy workouts automatically every 30 minutes.</p>
        </div>
        <Switch :model-value="autoSync" @update:model-value="onToggleAutoSync" />
      </div>
      <div class="mt-4 flex items-center justify-between gap-4 border-t pt-4">
        <div class="text-xs text-muted-foreground">
          <p>Last run: {{ relativeTime(syncStatus.last_run_at) }}</p>
          <p v-if="syncStatus.last_status" class="mt-0.5 capitalize">
            Status: {{ syncStatus.last_status }}
            <span v-if="syncStatus.last_error" class="text-destructive"> — {{ syncStatus.last_error }}</span>
          </p>
        </div>
        <Button size="sm" variant="outline" :disabled="syncing" @click="syncNow">
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': syncing }" />
          Sync now
        </Button>
      </div>
    </Card>

    <Card v-if="!targetsLoading" class="p-4">
      <h2 class="mb-3 text-sm font-medium">Daily targets</h2>
      <div class="grid grid-cols-2 gap-3">
        <div class="flex flex-col gap-1.5"><Label>kcal</Label><Input type="number" v-model.number="targets.kcal" /></div>
        <div class="flex flex-col gap-1.5"><Label>protein (g)</Label><Input type="number" v-model.number="targets.protein" /></div>
        <div class="flex flex-col gap-1.5"><Label>carbs (g)</Label><Input type="number" v-model.number="targets.carbs" /></div>
        <div class="flex flex-col gap-1.5"><Label>fat (g)</Label><Input type="number" v-model.number="targets.fat" /></div>
      </div>
      <Button class="mt-4" @click="saveTargets">Save targets</Button>
    </Card>
  </div>
</template>
