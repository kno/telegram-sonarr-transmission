<script lang="ts">
	import { settings } from '$lib/stores.svelte';
	import { getDownloads } from '$lib/api';
	import { TR_STATUS } from '$lib/types';
	import type { Download } from '$lib/types';
	import DownloadRow from '$lib/components/DownloadRow.svelte';
	import { onMount } from 'svelte';

	let downloads = $state<Download[]>([]);
	let loading = $state(true);
	let error = $state('');

	const hasActive = $derived(
		downloads.some((d) => d.status === TR_STATUS.DOWNLOAD || d.status === TR_STATUS.DOWNLOAD_WAIT)
	);

	async function fetchDownloads() {
		if (!settings.apiKey) return;
		try {
			downloads = await getDownloads(settings.apiKey);
			error = '';
		} catch (e: any) {
			error = e.message || 'Error al obtener descargas';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		fetchDownloads();
	});

	$effect(() => {
		const ms = hasActive ? 2000 : 10000;
		const interval = setInterval(fetchDownloads, ms);
		return () => clearInterval(interval);
	});

	const activeDownloads = $derived(
		downloads.filter((d) => d.status === TR_STATUS.DOWNLOAD || d.status === TR_STATUS.DOWNLOAD_WAIT)
	);
	const completedDownloads = $derived(
		downloads.filter((d) => d.status === TR_STATUS.SEED || (d.status === TR_STATUS.STOPPED && d.isFinished))
	);
	const errorDownloads = $derived(downloads.filter((d) => d.error > 0));
</script>

<svelte:head>
	<title>Descargas - TG Torznab</title>
</svelte:head>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-2xl font-bold">Descargas</h1>
	<span class="text-sm text-(--color-text-muted)">
		{downloads.length} total
		{#if hasActive}
			<span class="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-(--color-primary)"></span>
		{/if}
	</span>
</div>

{#if error}
	<div class="mb-4 rounded-md border border-(--color-danger) bg-(--color-danger)/10 p-3 text-sm text-(--color-danger)">
		{error}
	</div>
{/if}

{#if loading}
	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-12 text-center">
		<p class="text-(--color-text-muted)">Cargando descargas...</p>
	</div>
{:else if downloads.length === 0}
	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-12 text-center">
		<p class="text-(--color-text-muted)">No hay descargas.</p>
		<p class="mt-1 text-sm text-(--color-text-muted)">
			<a href="/search" class="text-(--color-primary) hover:underline">Busca contenido</a> para empezar a descargar.
		</p>
	</div>
{:else}
	{#if activeDownloads.length > 0}
		<h2 class="mb-3 text-sm font-semibold uppercase text-(--color-text-muted)">Activas</h2>
		<div class="mb-6 grid gap-3">
			{#each activeDownloads as download (download.id)}
				<DownloadRow {download} onRemoved={fetchDownloads} />
			{/each}
		</div>
	{/if}

	{#if errorDownloads.length > 0}
		<h2 class="mb-3 text-sm font-semibold uppercase text-(--color-danger)">Con errores</h2>
		<div class="mb-6 grid gap-3">
			{#each errorDownloads as download (download.id)}
				<DownloadRow {download} onRemoved={fetchDownloads} />
			{/each}
		</div>
	{/if}

	{#if completedDownloads.length > 0}
		<h2 class="mb-3 text-sm font-semibold uppercase text-(--color-text-muted)">Completadas</h2>
		<div class="grid gap-3">
			{#each completedDownloads as download (download.id)}
				<DownloadRow {download} onRemoved={fetchDownloads} />
			{/each}
		</div>
	{/if}
{/if}
