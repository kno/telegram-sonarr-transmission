<script lang="ts">
	import { settings, channelsStore } from '$lib/stores.svelte';
	import { search, fetchChannels } from '$lib/api';
	import type { SearchResult } from '$lib/types';
	import SearchResultCard from '$lib/components/SearchResultCard.svelte';
	import { onMount } from 'svelte';

	let query = $state('');
	let season = $state('');
	let ep = $state('');
	let searching = $state(false);
	let error = $state('');
	let results = $state<SearchResult[]>([]);
	let total = $state(0);
	let offset = $state(0);
	const limit = 50;

	onMount(async () => {
		if (settings.configured && channelsStore.channels.length === 0) {
			try {
				const channels = await fetchChannels(settings.apiKey);
				channelsStore.setChannels(channels);
			} catch {
				// ignore
			}
		}
	});

	const enabledCat = $derived(
		channelsStore.enabledIds.length < channelsStore.channels.length
			? channelsStore.enabledIds.join(',')
			: ''
	);

	async function doSearch(newOffset = 0) {
		if (!settings.apiKey) {
			error = 'API key no configurada';
			return;
		}
		searching = true;
		error = '';
		offset = newOffset;

		try {
			const res = await search({
				query,
				apiKey: settings.apiKey,
				cat: enabledCat || undefined,
				offset,
				limit,
				season: season || undefined,
				ep: ep || undefined
			});
			results = res.items;
			total = res.total;
		} catch (e: any) {
			error = e.message || 'Error en la busqueda';
			results = [];
		} finally {
			searching = false;
		}
	}

	function handleSubmit(e: Event) {
		e.preventDefault();
		doSearch(0);
	}

	const hasMore = $derived(offset + limit < total);
	const hasPrev = $derived(offset > 0);
</script>

<svelte:head>
	<title>Buscar - TG Torznab</title>
</svelte:head>

<h1 class="mb-6 text-2xl font-bold">Buscar</h1>

<form onsubmit={handleSubmit} class="mb-6 rounded-lg border border-(--color-border) bg-(--color-surface) p-4">
	<div class="flex flex-col gap-3 sm:flex-row">
		<input
			type="text"
			bind:value={query}
			placeholder="Buscar contenido..."
			class="flex-1 rounded-md border border-(--color-border) bg-(--color-surface-alt) px-3 py-2 text-sm text-(--color-text) placeholder:text-(--color-text-muted) focus:border-(--color-primary) focus:outline-none"
		/>
		<div class="flex gap-2">
			<input
				type="text"
				bind:value={season}
				placeholder="Temp."
				class="w-16 rounded-md border border-(--color-border) bg-(--color-surface-alt) px-2 py-2 text-center text-sm text-(--color-text) placeholder:text-(--color-text-muted) focus:border-(--color-primary) focus:outline-none"
			/>
			<input
				type="text"
				bind:value={ep}
				placeholder="Ep."
				class="w-16 rounded-md border border-(--color-border) bg-(--color-surface-alt) px-2 py-2 text-center text-sm text-(--color-text) placeholder:text-(--color-text-muted) focus:border-(--color-primary) focus:outline-none"
			/>
			<button
				type="submit"
				disabled={searching}
				class="rounded-md px-5 py-2 text-sm font-medium text-white bg-(--color-primary) hover:bg-(--color-primary-hover) transition-colors disabled:opacity-50"
			>
				{searching ? 'Buscando...' : 'Buscar'}
			</button>
		</div>
	</div>

	{#if channelsStore.channels.length > 0}
		<p class="mt-2 text-xs text-(--color-text-muted)">
			Buscando en {channelsStore.enabledIds.length} canal{channelsStore.enabledIds.length !== 1 ? 'es' : ''}.
			<a href="/channels" class="text-(--color-primary) hover:underline">Gestionar canales</a>
		</p>
	{/if}
</form>

{#if error}
	<div class="mb-4 rounded-md border border-(--color-danger) bg-(--color-danger)/10 p-3 text-sm text-(--color-danger)">
		{error}
	</div>
{/if}

{#if results.length > 0}
	<div class="mb-4 flex items-center justify-between">
		<p class="text-sm text-(--color-text-muted)">
			{total} resultado{total !== 1 ? 's' : ''} — mostrando {offset + 1}-{Math.min(offset + limit, total)}
		</p>
	</div>

	<div class="grid gap-3">
		{#each results as result (result.guid)}
			<SearchResultCard {result} />
		{/each}
	</div>

	{#if hasPrev || hasMore}
		<div class="mt-4 flex justify-center gap-3">
			<button
				onclick={() => doSearch(offset - limit)}
				disabled={!hasPrev || searching}
				class="rounded-md border border-(--color-border) px-4 py-2 text-sm transition-colors hover:bg-(--color-surface-hover) disabled:opacity-30"
			>
				Anterior
			</button>
			<button
				onclick={() => doSearch(offset + limit)}
				disabled={!hasMore || searching}
				class="rounded-md border border-(--color-border) px-4 py-2 text-sm transition-colors hover:bg-(--color-surface-hover) disabled:opacity-30"
			>
				Siguiente
			</button>
		</div>
	{/if}
{:else if !searching && !error && query}
	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-12 text-center">
		<p class="text-(--color-text-muted)">No se encontraron resultados para "{query}"</p>
	</div>
{/if}
