<script setup lang="ts">
import { ref, nextTick } from "vue";
const props = defineProps<{
  modelValue: string;
  placeholder?: string;
  multiline?: boolean;
}>();
const emit = defineEmits<{ (e: "update:modelValue", value: string): void }>();
const editing = ref(false),
  input = ref<HTMLInputElement | HTMLTextAreaElement | null>(null);
async function edit() {
  editing.value = true;
  await nextTick();
  input.value?.focus();
}
</script>
<template>
  <textarea
    v-if="editing && multiline"
    ref="input"
    class="inline-edit"
    :value="props.modelValue"
    :placeholder="placeholder"
    @input="
      emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)
    "
    @blur="editing = false"
  /><input
    v-else-if="editing"
    ref="input"
    class="inline-edit"
    :value="modelValue"
    :placeholder="placeholder"
    @input="
      emit('update:modelValue', ($event.target as HTMLInputElement).value)
    "
    @blur="editing = false"
    @keydown.enter="editing = false"
  /><button
    v-else
    class="inline-display"
    :class="{ placeholder: !modelValue }"
    @click="edit"
  >
    {{ modelValue || placeholder || "Click to edit" }}
  </button>
</template>
