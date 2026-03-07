<script lang="ts">
	import { settings, channelsStore } from '$lib/stores.svelte';
	import { getDownloads, getSessionStats, fetchChannels, formatSize, formatSpeed } from '$lib/api';
	import { TR_STATUS } from '$lib/types';
	import type { Download, SessionStats } from '$lib/types';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import { onMount } from 'svelte';

	let stats = $state<SessionStats | null>(null);
	let activeDownloads = $state<Download[]>([]);
	let loading = $state(true);
	let error = $state('');

	async function refresh() {
		if (!settings.apiKey) {
			loading = false;
			return;
		}
		try {
			const [s, dl] = await Promise.all([
				getSessionStats(settings.apiKey),
				getDownloads(settings.apiKey)
			]);
			stats = s;
			activeDownloads = dl.filter(
				(d) => d.status === TR_STATUS.DOWNLOAD || d.status === TR_STATUS.DOWNLOAD_WAIT
			);
			error = '';
		} catch (e: any) {
			error = e.message || 'Error al conectar';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		refresh();
		if (settings.configured && channelsStore.channels.length === 0) {
			fetchChannels(settings.apiKey)
				.then((ch) => channelsStore.setChannels(ch))
				.catch(() => {});
		}
	});

	$effect(() => {
		const interval = setInterval(refresh, activeDownloads.length > 0 ? 2000 : 10000);
		return () => clearInterval(interval);
	});
</script>

<svelte:head>
	<title>Dashboard - TG Torznab</title>
</svelte:head>

<h1 class="mb-6 text-2xl font-bold">Dashboard</h1>

{#if !settings.configured}
	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-12 text-center">
		<p class="mb-2 text-lg font-medium">Bienvenido a TG Torznab</p>
		<p class="mb-4 text-(--color-text-muted)">Configura tu API key para empezar.</p>
		<a
			href="/settings"
			class="inline-block rounded-md px-4 py-2 text-sm font-medium text-white bg-(--color-primary) hover:bg-(--color-primary-hover)"
		>
			Ir a configuracion
		</a>
	</div>
{:else if loading}
	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-12 text-center">
		<p class="text-(--color-text-muted)">Cargando...</p>
	</div>
{:else}
	{#if error}
		<div class="mb-4 rounded-md border border-(--color-danger) bg-(--color-danger)/10 p-3 text-sm text-(--color-danger)">
			{error}
		</div>
	{/if}

	<!-- Stats cards -->
	<div class="mb-6 grid gap-4 sm:grid-cols-3">
		<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-5">
			<p class="text-xs font-medium uppercase text-(--color-text-muted)">Descargas activas</p>
			<p class="mt-1 text-3xl font-bold text-(--color-primary)">
				{stats?.activeTorrentCount ?? 0}
			</p>
		</div>
		<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-5">
			<p class="text-xs font-medium uppercase text-(--color-text-muted)">Velocidad</p>
			<p class="mt-1 text-3xl font-bold">
				{formatSpeed(stats?.downloadSpeed ?? 0)}
			</p>
		</div>
		<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-5">
			<p class="text-xs font-medium uppercase text-(--color-text-muted)">Canales</p>
			<p class="mt-1 text-3xl font-bold">
				{channelsStore.channels.length}
			</p>
		</div>
	</div>

	<!-- Quick actions -->
	<div class="mb-6 flex gap-3">
		<a
			href="/search"
			class="rounded-md px-4 py-2 text-sm font-medium text-white bg-(--color-primary) hover:bg-(--color-primary-hover) transition-colors"
		>
			Buscar contenido
		</a>
		<a
			href="/downloads"
			class="rounded-md border border-(--color-border) px-4 py-2 text-sm font-medium text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover)"
		>
			Ver descargas
		</a>
	</div>

	<!-- Active downloads summary -->
	{#if activeDownloads.length > 0}
		<h2 class="mb-3 text-sm font-semibold uppercase text-(--color-text-muted)">Descargas activas</h2>
		<div class="grid gap-3">
			{#each activeDownloads as dl (dl.id)}
				<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-4">
					<div class="mb-2 flex items-center justify-between">
						<p class="truncate text-sm font-medium">{dl.name}</p>
						<span class="shrink-0 text-xs text-(--color-text-muted)">
							{(dl.percentDone * 100).toFixed(1)}% — {formatSpeed(dl.rateDownload)}
						</span>
					</div>
					<ProgressBar percent={dl.percentDone} animated={true} />
				</div>
			{/each}
		</div>
	{/if}
{/if}
