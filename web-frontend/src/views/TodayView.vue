<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { toast } from "vue-sonner";
import { Search, X, Pencil } from "lucide-vue-next";
import MacroCard from "@/components/MacroCard.vue";
import FoodRow from "@/components/FoodRow.vue";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import Label from "@/components/ui/Label.vue";
import Badge from "@/components/ui/Badge.vue";
import Sheet from "@/components/ui/Sheet.vue";

const MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"];

const today = ref(null);
const recent = ref([]);
const loading = ref(true);

const query = ref("");
const results = ref([]);
const searching = ref(false);

// The pending meal: nothing here is written to the server until "Log meal" is
// tapped. Quick-add and search both stage into this cart instead of writing
// directly — a bare tap must never mutate stored data (see DESIGN.md, "The No
// Silent Write Rule" — carried forward from the prior Instrument Panel build,
// which this shadcn-vue rebuild replaces visually but not behaviorally).
let cartClientId = 0;
const cart = reactive({ mealType: "lunch", items: [] });

const cartKeys = computed(() => new Set(cart.items.map((i) => i.matchKey)));
const cartKcal = computed(() => cart.items.reduce((sum, i) => sum + (i.kcal_100g * i.grams) / 100, 0));

const sheet = reactive({
  open: false,
  mode: null, // "product" | "one-off" | "edit"
  editingEntry: null,
  name: "",
  productId: null,
  source: "estimated",
  grams: 100,
  macros: { kcal_100g: 0, protein_100g: 0, carbs_100g: 0, fat_100g: 0 },
});

async function loadToday() {
  const res = await fetch("/api/today");
  today.value = await res.json();
}

async function loadRecent() {
  const res = await fetch("/api/products/recent");
  recent.value = await res.json();
}

onMounted(async () => {
  const [, , suggested] = await Promise.all([
    loadToday(),
    loadRecent(),
    fetch("/api/meals/suggested-type").then((r) => r.json()),
  ]);
  cart.mealType = suggested.meal_type;
  loading.value = false;
});

let debounceHandle;
watch(query, (q) => {
  clearTimeout(debounceHandle);
  if (!q.trim()) {
    results.value = [];
    return;
  }
  debounceHandle = setTimeout(async () => {
    searching.value = true;
    const res = await fetch(`/api/products?q=${encodeURIComponent(q)}`);
    results.value = await res.json();
    searching.value = false;
  }, 220);
});

function openProduct(product) {
  sheet.open = true;
  sheet.mode = "product";
  sheet.editingEntry = null;
  sheet.name = product.name;
  sheet.productId = product.id;
  sheet.source = product.source;
  sheet.grams = 100;
  sheet.macros = {
    kcal_100g: product.kcal_100g,
    protein_100g: product.protein_100g,
    carbs_100g: product.carbs_100g,
    fat_100g: product.fat_100g,
  };
}

function openOneOff() {
  sheet.open = true;
  sheet.mode = "one-off";
  sheet.editingEntry = null;
  sheet.name = query.value;
  sheet.productId = null;
  sheet.source = "estimated";
  sheet.grams = 100;
  sheet.macros = { kcal_100g: 0, protein_100g: 0, carbs_100g: 0, fat_100g: 0 };
}

function openEdit(entry) {
  sheet.open = true;
  sheet.mode = "edit";
  sheet.editingEntry = entry;
  sheet.name = entry.name;
  sheet.productId = entry.product_id;
  sheet.source = entry.source;
  sheet.grams = entry.grams;
  const scale = 100 / entry.grams;
  sheet.macros = {
    kcal_100g: entry.kcal * scale,
    protein_100g: entry.protein * scale,
    carbs_100g: entry.carbs * scale,
    fat_100g: entry.fat * scale,
  };
}

function closeSheet() {
  sheet.open = false;
}

function addSheetToCart() {
  cart.items.push({
    clientId: ++cartClientId,
    matchKey: sheet.productId ?? sheet.name,
    productId: sheet.productId,
    name: sheet.name,
    source: sheet.source,
    grams: sheet.grams,
    kcal_100g: sheet.macros.kcal_100g,
    protein_100g: sheet.macros.protein_100g,
    carbs_100g: sheet.macros.carbs_100g,
    fat_100g: sheet.macros.fat_100g,
  });
  closeSheet();
  query.value = "";
  results.value = [];
}

async function submitSheet() {
  if (sheet.mode === "edit") {
    const original = sheet.editingEntry;
    await fetch(`/api/log/${original.id}`, { method: "DELETE" });
    await fetch("/api/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        sheet.productId != null
          ? { grams: sheet.grams, product_id: sheet.productId, meal_id: original.meal_id }
          : { grams: sheet.grams, name: sheet.name, macros: sheet.macros, meal_id: original.meal_id }
      ),
    });
    closeSheet();
    toast(`Updated ${sheet.name}`);
    await Promise.all([loadToday(), loadRecent()]);
    return;
  }
  addSheetToCart();
}

function toggleCartFood(food) {
  const key = food.product_id ?? food.name;
  const idx = cart.items.findIndex((i) => i.matchKey === key);
  if (idx !== -1) {
    cart.items.splice(idx, 1);
    return;
  }
  cart.items.push({
    clientId: ++cartClientId,
    matchKey: key,
    productId: food.product_id,
    name: food.name,
    source: food.source,
    grams: food.last_grams,
    kcal_100g: food.kcal_100g,
    protein_100g: food.protein_100g,
    carbs_100g: food.carbs_100g,
    fat_100g: food.fat_100g,
  });
}

function removeCartItem(clientId) {
  cart.items = cart.items.filter((i) => i.clientId !== clientId);
}

function clearCart() {
  cart.items = [];
}

async function commitMeal() {
  if (cart.items.length === 0) return;
  const mealType = cart.mealType;
  const count = cart.items.length;
  const payload = {
    meal_type: mealType,
    items: cart.items.map((i) => ({
      grams: i.grams,
      product_id: i.productId ?? undefined,
      name: i.productId ? undefined : i.name,
      macros: i.productId
        ? undefined
        : { kcal_100g: i.kcal_100g, protein_100g: i.protein_100g, carbs_100g: i.carbs_100g, fat_100g: i.fat_100g },
    })),
  };
  const res = await fetch("/api/meals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    toast.error("Couldn't log that meal — try again.");
    return;
  }
  const result = await res.json();
  clearCart();
  await Promise.all([loadToday(), loadRecent()]);
  toast(`Logged ${mealType} · ${count} item${count === 1 ? "" : "s"}`, {
    action: {
      label: "Undo",
      onClick: async () => {
        await fetch(`/api/meals/${result.meal_id}`, { method: "DELETE" });
        await Promise.all([loadToday(), loadRecent()]);
      },
    },
  });
}

async function deleteEntry(entry) {
  await fetch(`/api/log/${entry.id}`, { method: "DELETE" });
  await Promise.all([loadToday(), loadRecent()]);
  toast(`Deleted ${entry.name}`, {
    action: {
      label: "Undo",
      onClick: async () => {
        await fetch("/api/log", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            entry.product_id != null
              ? { grams: entry.grams, product_id: entry.product_id, meal_id: entry.meal_id }
              : {
                  grams: entry.grams,
                  name: entry.name,
                  macros: {
                    kcal_100g: (entry.kcal / entry.grams) * 100,
                    protein_100g: (entry.protein / entry.grams) * 100,
                    carbs_100g: (entry.carbs / entry.grams) * 100,
                    fat_100g: (entry.fat / entry.grams) * 100,
                  },
                  meal_id: entry.meal_id,
                }
          ),
        });
        await Promise.all([loadToday(), loadRecent()]);
      },
    },
  });
}

const totals = computed(() => today.value?.totals ?? { kcal: 0, protein: 0, carbs: 0, fat: 0 });
const targets = computed(() => today.value?.targets ?? null);

function mealTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
</script>

<template>
  <div v-if="!loading" class="flex flex-col gap-6 pb-32">
    <section class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <MacroCard label="Calories" unit="kcal" :value="totals.kcal" :target="targets?.kcal" />
      <MacroCard label="Protein" unit="g" :value="totals.protein" :target="targets?.protein" />
      <MacroCard label="Carbs" unit="g" :value="totals.carbs" :target="targets?.carbs" />
      <MacroCard label="Fat" unit="g" :value="totals.fat" :target="targets?.fat" />
    </section>

    <section class="relative">
      <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input v-model="query" type="search" placeholder="Search the Catalog…" class="pl-9" />
      <div v-if="query.trim()" class="mt-2 flex flex-col gap-1.5">
        <div v-if="searching" class="px-1 py-2 text-xs text-muted-foreground">Searching…</div>
        <template v-else>
          <button
            v-for="p in results"
            :key="p.id"
            type="button"
            class="flex items-center justify-between gap-2 rounded-md border bg-card px-3 py-2 text-left text-sm hover:bg-accent/50"
            @click="openProduct(p)"
          >
            <span class="truncate">{{ p.name }}<span v-if="p.brand" class="text-muted-foreground"> — {{ p.brand }}</span></span>
            <Badge :variant="p.source === 'verified' ? 'success' : 'warning'">{{ p.source }}</Badge>
          </button>
          <button
            v-if="results.length === 0"
            type="button"
            class="rounded-md border border-dashed px-3 py-2 text-left text-sm text-primary hover:bg-accent/50"
            @click="openOneOff"
          >
            + Add "{{ query }}" as a one-off
          </button>
        </template>
      </div>
    </section>

    <section v-if="recent.length" class="flex flex-col gap-2">
      <h2 class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Quick add to meal</h2>
      <div class="flex flex-col gap-2">
        <FoodRow
          v-for="f in recent"
          :key="f.product_id ?? f.name"
          :food="f"
          :in-cart="cartKeys.has(f.product_id ?? f.name)"
          @toggle="toggleCartFood"
        />
      </div>
    </section>

    <section v-if="today.meals.length || today.ungrouped.length" class="flex flex-col gap-5">
      <h2 class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Today — {{ today.date }}</h2>

      <div v-for="meal in today.meals" :key="meal.id" class="flex flex-col gap-2">
        <div class="flex items-baseline gap-2 px-0.5">
          <span class="text-sm font-semibold capitalize text-primary">{{ meal.meal_type }}</span>
          <span class="text-xs tabular text-muted-foreground">{{ mealTime(meal.logged_at) }}</span>
          <span class="ml-auto text-xs tabular text-muted-foreground">{{ Math.round(meal.subtotals.kcal) }} kcal</span>
        </div>
        <ul class="flex flex-col gap-2">
          <li v-for="e in meal.entries" :key="e.id" class="flex items-stretch gap-2">
            <button type="button" class="flex flex-1 flex-col gap-1 rounded-lg border bg-card px-3 py-2 text-left hover:bg-accent/50" @click="openEdit(e)">
              <span class="flex items-center justify-between gap-2">
                <span class="truncate text-sm">{{ e.name }}</span>
                <Pencil class="h-3.5 w-3.5 flex-none text-muted-foreground" />
              </span>
              <span class="flex items-center gap-2 text-xs tabular text-muted-foreground">
                <Badge :variant="e.source === 'verified' ? 'success' : 'warning'">{{ e.source }}</Badge>
                {{ Math.round(e.grams) }}g · {{ Math.round(e.kcal) }} kcal
              </span>
            </button>
            <button
              type="button"
              class="flex w-10 flex-none items-center justify-center rounded-lg border bg-card text-destructive hover:bg-destructive/10"
              aria-label="Delete entry"
              @click="deleteEntry(e)"
            >
              <X class="h-4 w-4" />
            </button>
          </li>
        </ul>
      </div>

      <div v-if="today.ungrouped.length" class="flex flex-col gap-2">
        <div class="px-0.5 text-sm font-semibold text-muted-foreground">Other</div>
        <ul class="flex flex-col gap-2">
          <li v-for="e in today.ungrouped" :key="e.id" class="flex items-stretch gap-2">
            <button type="button" class="flex flex-1 flex-col gap-1 rounded-lg border bg-card px-3 py-2 text-left hover:bg-accent/50" @click="openEdit(e)">
              <span class="truncate text-sm">{{ e.name }}</span>
              <span class="flex items-center gap-2 text-xs tabular text-muted-foreground">
                <Badge :variant="e.source === 'verified' ? 'success' : 'warning'">{{ e.source }}</Badge>
                {{ Math.round(e.grams) }}g · {{ Math.round(e.kcal) }} kcal
              </span>
            </button>
            <button
              type="button"
              class="flex w-10 flex-none items-center justify-center rounded-lg border bg-card text-destructive hover:bg-destructive/10"
              aria-label="Delete entry"
              @click="deleteEntry(e)"
            >
              <X class="h-4 w-4" />
            </button>
          </li>
        </ul>
      </div>
    </section>

    <div
      v-if="cart.items.length"
      class="fixed inset-x-0 bottom-16 z-30 mx-auto flex w-full max-w-lg flex-col gap-2.5 rounded-t-xl border bg-card p-3 shadow-lg sm:bottom-4 sm:rounded-xl"
    >
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="t in MEAL_TYPES"
          :key="t"
          type="button"
          class="rounded-full border px-3 py-1 text-xs font-medium capitalize"
          :class="cart.mealType === t ? 'border-primary bg-primary/10 text-primary' : 'text-muted-foreground'"
          @click="cart.mealType = t"
        >
          {{ t }}
        </button>
      </div>
      <ul class="flex max-h-28 flex-col gap-1 overflow-y-auto">
        <li v-for="item in cart.items" :key="item.clientId" class="flex items-center justify-between gap-2 text-sm">
          <span class="truncate">{{ item.name }} · {{ Math.round(item.grams) }}g</span>
          <button type="button" class="flex-none text-muted-foreground hover:text-foreground" aria-label="Remove from meal" @click="removeCartItem(item.clientId)">
            <X class="h-3.5 w-3.5" />
          </button>
        </li>
      </ul>
      <Button @click="commitMeal">
        Log {{ cart.mealType }} · {{ cart.items.length }} item{{ cart.items.length === 1 ? "" : "s" }} · {{ Math.round(cartKcal) }} kcal
      </Button>
    </div>

    <Sheet v-model:open="sheet.open" :title="sheet.mode === 'edit' ? 'Edit entry' : sheet.name">
      <div class="flex flex-col gap-3">
        <div class="flex flex-col gap-1.5">
          <Label>Grams</Label>
          <Input type="number" v-model.number="sheet.grams" min="1" step="1" />
        </div>
        <template v-if="sheet.mode === 'one-off' || sheet.mode === 'edit'">
          <div v-if="sheet.mode === 'one-off'" class="flex flex-col gap-1.5">
            <Label>Name</Label>
            <Input type="text" v-model="sheet.name" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="flex flex-col gap-1.5"><Label>kcal/100g</Label><Input type="number" v-model.number="sheet.macros.kcal_100g" /></div>
            <div class="flex flex-col gap-1.5"><Label>protein/100g</Label><Input type="number" v-model.number="sheet.macros.protein_100g" /></div>
            <div class="flex flex-col gap-1.5"><Label>carbs/100g</Label><Input type="number" v-model.number="sheet.macros.carbs_100g" /></div>
            <div class="flex flex-col gap-1.5"><Label>fat/100g</Label><Input type="number" v-model.number="sheet.macros.fat_100g" /></div>
          </div>
        </template>
        <div class="mt-2 flex justify-end gap-2">
          <Button variant="ghost" @click="closeSheet">Cancel</Button>
          <Button @click="submitSheet">{{ sheet.mode === "edit" ? "Save" : "Add to meal" }}</Button>
        </div>
      </div>
    </Sheet>
  </div>
</template>
