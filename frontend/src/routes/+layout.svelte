<script lang="ts">
	import '../app.css';
	import Navbar from '$lib/components/Navbar.svelte';
	import { settings, theme, channelsStore } from '$lib/stores.svelte';
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();

	onMount(() => {
		settings.load();
		theme.load();
		channelsStore.load();
	});
</script>

<div class="min-h-screen">
	<Navbar />
	<main class="mx-auto max-w-6xl px-4 py-6">
		{@render children()}
	</main>
</div>
