<script setup lang="ts">
defineProps<{ name: string }>();
</script>
<template>
  <svg
    viewBox="0 0 24 24"
    width="24"
    height="24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.4"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'builder'">
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v5h4" />
    </template>
    <template v-else-if="name === 'flow'">
      <path d="M4 18h4c5 0 3-12 8-12h4" />
      <circle cx="4" cy="18" r="2" fill="white" />
      <circle cx="20" cy="6" r="2" fill="white" />
    </template>
    <template v-else>
      <path d="M3 6h18M3 12h18M3 18h18" />
      <circle cx="8" cy="6" r="2" fill="white" />
      <circle cx="16" cy="12" r="2" fill="white" />
      <circle cx="8" cy="18" r="2" fill="white" />
    </template>
  </svg>
</template>
