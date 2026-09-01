<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Line, Bar } from "vue-chartjs";
import Card from "@/components/ui/Card.vue";
import { cssVar } from "@/lib/chart-setup";

const RANGES = [
  { label: "4w", weeks: 4 },
  { label: "12w", weeks: 12 },
  { label: "26w", weeks: 26 },
  { label: "52w", weeks: 52 },
];
const weeks = ref(12);

const food = ref([]);
const workouts = ref([]);
const weight = ref([]);
const correlation = ref([]);
const loading = ref(true);

async function loadAll() {
  loading.value = true;
  const [f, w, wt, c] = await Promise.all([
    fetch(`/api/trends/food?weeks=${weeks.value}`).then((r) => r.json()),
    fetch(`/api/trends/workouts?weeks=${weeks.value}`).then((r) => r.json()),
    fetch(`/api/trends/weight?weeks=${weeks.value}`).then((r) => r.json()),
    fetch(`/api/trends/correlation?weeks=${weeks.value}`).then((r) => r.json()),
  ]);
  food.value = f;
  workouts.value = w;
  weight.value = wt;
  correlation.value = c;
  loading.value = false;
}

onMounted(loadAll);
watch(weeks, loadAll);

function short(d) {
  return new Date(d).toLocaleDateString([], { month: "short", day: "numeric" });
}

const baseOptions = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  plugins: { legend: { display: true, labels: { boxWidth: 10, usePointStyle: true } } },
  scales: {
    x: { grid: { display: false } },
    y: { grid: { color: "hsl(var(--border))" } },
  },
};

const macroData = computed(() => ({
  labels: food.value.map((r) => short(r.week_start)),
  datasets: [
    { label: "Calories (avg/day)", data: food.value.map((r) => r.kcal_avg), borderColor: cssVar("--chart-1"), backgroundColor: cssVar("--chart-1"), tension: 0.35, yAxisID: "y" },
  ],
}));

const macronutrientData = computed(() => ({
  labels: food.value.map((r) => short(r.week_start)),
  datasets: [
    { label: "Protein", data: food.value.map((r) => r.protein_avg), borderColor: cssVar("--chart-3"), backgroundColor: cssVar("--chart-3"), tension: 0.35 },
    { label: "Carbs", data: food.value.map((r) => r.carbs_avg), borderColor: cssVar("--chart-2"), backgroundColor: cssVar("--chart-2"), tension: 0.35 },
    { label: "Fat", data: food.value.map((r) => r.fat_avg), borderColor: cssVar("--chart-4"), backgroundColor: cssVar("--chart-4"), tension: 0.35 },
  ],
}));

const workoutData = computed(() => ({
  labels: workouts.value.map((r) => short(r.week_start)),
  datasets: [
    { label: "Sessions", data: workouts.value.map((r) => r.sessions), backgroundColor: cssVar("--chart-3"), yAxisID: "y" },
  ],
}));

const tonnageData = computed(() => ({
  labels: workouts.value.map((r) => short(r.week_start)),
  datasets: [
    { label: "Tonnage (kg)", data: workouts.value.map((r) => r.tonnage_kg), borderColor: cssVar("--chart-1"), backgroundColor: cssVar("--chart-1"), tension: 0.35, fill: true },
  ],
}));

const weightData = computed(() => ({
  labels: weight.value.map((r) => short(r.date)),
  datasets: [
    { label: "Weight (kg)", data: weight.value.map((r) => r.weight_kg), borderColor: cssVar("--chart-3"), backgroundColor: cssVar("--chart-3"), tension: 0.35, pointRadius: 2 },
  ],
}));

const correlationData = computed(() => ({
  labels: correlation.value.map((r) => short(r.week_start)),
  datasets: [
    { type: "bar", label: "Training sessions", data: correlation.value.map((r) => r.sessions), backgroundColor: cssVar("--chart-3"), yAxisID: "y1" },
    { type: "line", label: "Avg daily calories", data: correlation.value.map((r) => r.kcal_avg), borderColor: cssVar("--chart-1"), backgroundColor: cssVar("--chart-1"), tension: 0.35, yAxisID: "y" },
  ],
}));

const correlationOptions = {
  ...baseOptions,
  scales: {
    x: { grid: { display: false } },
    y: { position: "left", grid: { color: "hsl(var(--border))" }, title: { display: true, text: "kcal/day" } },
    y1: { position: "right", grid: { display: false }, title: { display: true, text: "sessions" } },
  },
};
</script>

<template>
  <div class="flex flex-col gap-6">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold tracking-tight">Trends</h1>
      <div class="flex gap-1 rounded-md border p-0.5">
        <button
          v-for="r in RANGES"
          :key="r.weeks"
          type="button"
          class="rounded px-2.5 py-1 text-xs font-medium"
          :class="weeks === r.weeks ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'"
          @click="weeks = r.weeks"
        >
          {{ r.label }}
        </button>
      </div>
    </div>

    <div v-if="!loading" class="grid gap-4 lg:grid-cols-2">
      <Card class="p-4">
        <h2 class="mb-3 text-sm font-medium">Calories per day (weekly avg)</h2>
        <div v-if="food.length" class="h-56"><Line :data="macroData" :options="baseOptions" /></div>
        <p v-else class="py-8 text-center text-sm text-muted-foreground">No food logged yet in this range.</p>
      </Card>

      <Card class="p-4">
        <h2 class="mb-3 text-sm font-medium">Macros per day (weekly avg)</h2>
        <div v-if="food.length" class="h-56"><Line :data="macronutrientData" :options="baseOptions" /></div>
        <p v-else class="py-8 text-center text-sm text-muted-foreground">No food logged yet in this range.</p>
      </Card>

      <Card class="p-4">
        <h2 class="mb-3 text-sm font-medium">Training sessions per week</h2>
        <div v-if="workouts.length" class="h-56"><Bar :data="workoutData" :options="baseOptions" /></div>
        <p v-else class="py-8 text-center text-sm text-muted-foreground">No workouts synced yet in this range.</p>
      </Card>

      <Card class="p-4">
        <h2 class="mb-3 text-sm font-medium">Training tonnage per week</h2>
        <div v-if="workouts.length" class="h-56"><Line :data="tonnageData" :options="baseOptions" /></div>
        <p v-else class="py-8 text-center text-sm text-muted-foreground">No workouts synced yet in this range.</p>
      </Card>

      <Card class="p-4">
        <h2 class="mb-3 text-sm font-medium">Body weight</h2>
        <div v-if="weight.length" class="h-56"><Line :data="weightData" :options="baseOptions" /></div>
        <p v-else class="py-8 text-center text-sm text-muted-foreground">No body-weight measurements logged yet.</p>
      </Card>

      <Card class="p-4">
        <h2 class="mb-3 text-sm font-medium">Intake vs. training</h2>
        <div v-if="correlation.length" class="h-56"><Bar :data="correlationData" :options="correlationOptions" /></div>
        <p v-else class="py-8 text-center text-sm text-muted-foreground">Not enough data yet to correlate.</p>
      </Card>
    </div>
  </div>
</template>
