<script lang="ts">
	import { settings } from '$lib/stores.svelte';
	import {
		getDownloads,
		connectDownloadsWS,
		pauseDownloads,
		resumeDownloads,
		removeDownloads
	} from '$lib/api';
	import { TR_STATUS } from '$lib/types';
	import type { Download } from '$lib/types';
	import DownloadRow from '$lib/components/DownloadRow.svelte';
	import { SvelteSet } from 'svelte/reactivity';

	let downloads = $state<Download[]>([]);
	let loading = $state(true);
	let error = $state('');
	let selectedIds = new SvelteSet<number>();
	let confirmingDelete = $state(false);
	let bulkPending = $state(false);

	const hasActive = $derived(
		downloads.some((d) => d.status === TR_STATUS.DOWNLOAD || d.status === TR_STATUS.DOWNLOAD_WAIT)
	);

	function canPauseStatus(d: Download) {
		return d.status === TR_STATUS.DOWNLOAD || d.status === TR_STATUS.DOWNLOAD_WAIT;
	}

	function canResumeStatus(d: Download) {
		return !d.isFinished && (d.status === TR_STATUS.STOPPED || d.error > 0);
	}

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

	// Connect (or reconnect) when the apiKey becomes available. A hard reload
	// on /downloads mounts this page before +layout.svelte's onMount populates
	// the settings store, so we can't rely on apiKey being set at first run —
	// $effect re-runs when it changes from '' to a real value.
	$effect(() => {
		const apiKey = settings.apiKey;
		if (!apiKey) return;

		const disconnect = connectDownloadsWS(
			apiKey,
			(updated) => {
				downloads = updated;
				loading = false;
				error = '';
			},
			() => {
				fetchDownloads();
			}
		);

		return disconnect;
	});

	// Drop selection entries for downloads no longer present (websocket may
	// remove items we had ticked).
	$effect(() => {
		const liveIds = new Set(downloads.map((d) => d.id));
		for (const id of selectedIds) {
			if (!liveIds.has(id)) selectedIds.delete(id);
		}
	});

	function toggleSelect(id: number, checked: boolean) {
		if (checked) selectedIds.add(id);
		else selectedIds.delete(id);
	}

	function clearSelection() {
		selectedIds.clear();
		confirmingDelete = false;
	}

	const activeDownloads = $derived(
		downloads.filter((d) => d.status === TR_STATUS.DOWNLOAD || d.status === TR_STATUS.DOWNLOAD_WAIT)
	);
	const stoppedDownloads = $derived(
		downloads.filter((d) => d.status === TR_STATUS.STOPPED && !d.isFinished && d.error === 0)
	);
	const completedDownloads = $derived(
		downloads.filter((d) => d.status === TR_STATUS.SEED || (d.status === TR_STATUS.STOPPED && d.isFinished))
	);
	const errorDownloads = $derived(downloads.filter((d) => d.error > 0));

	const selectedDownloads = $derived(downloads.filter((d) => selectedIds.has(d.id)));
	const pausableSelected = $derived(selectedDownloads.filter(canPauseStatus).map((d) => d.id));
	const resumableSelected = $derived(selectedDownloads.filter(canResumeStatus).map((d) => d.id));
	const allVisibleSelected = $derived(
		downloads.length > 0 && selectedIds.size === downloads.length
	);
	const someVisibleSelected = $derived(
		selectedIds.size > 0 && selectedIds.size < downloads.length
	);

	function selectAllToggle(checked: boolean) {
		if (checked) {
			for (const d of downloads) selectedIds.add(d.id);
		} else {
			selectedIds.clear();
		}
	}

	async function bulkPause() {
		if (pausableSelected.length === 0) return;
		bulkPending = true;
		try {
			await pauseDownloads(settings.apiKey, pausableSelected);
			clearSelection();
		} catch (e: any) {
			error = e.message || 'Error al pausar';
		} finally {
			bulkPending = false;
		}
	}

	async function bulkResume() {
		if (resumableSelected.length === 0) return;
		bulkPending = true;
		try {
			await resumeDownloads(settings.apiKey, resumableSelected);
			clearSelection();
		} catch (e: any) {
			error = e.message || 'Error al reanudar';
		} finally {
			bulkPending = false;
		}
	}

	async function bulkRemove(deleteData: boolean) {
		if (selectedIds.size === 0) return;
		bulkPending = true;
		try {
			await removeDownloads(settings.apiKey, [...selectedIds], deleteData);
			clearSelection();
		} catch (e: any) {
			error = e.message || 'Error al eliminar';
		} finally {
			bulkPending = false;
		}
	}
</script>

<svelte:head>
	<title>Descargas - Telegram Search & Download</title>
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

{#if downloads.length > 0}
	<div
		class="sticky top-2 z-10 mb-4 rounded-lg border border-(--color-border) bg-(--color-surface) p-3 shadow-sm"
		class:opacity-60={selectedIds.size === 0}
	>
		<div class="flex flex-wrap items-center gap-3">
			<label class="flex items-center gap-2 text-sm">
				<input
					type="checkbox"
					checked={allVisibleSelected}
					indeterminate={someVisibleSelected}
					onchange={(e) => selectAllToggle(e.currentTarget.checked)}
					class="h-4 w-4 cursor-pointer accent-(--color-primary)"
					aria-label="Seleccionar todas"
				/>
				<span class="font-medium">
					{#if selectedIds.size === 0}
						Seleccionar todas
					{:else}
						{selectedIds.size} seleccionada{selectedIds.size === 1 ? '' : 's'}
					{/if}
				</span>
			</label>

			<div class="ml-auto flex flex-wrap items-center gap-2">
				{#if !confirmingDelete}
					<button
						onclick={bulkPause}
						disabled={bulkPending || pausableSelected.length === 0}
						class="rounded-md px-3 py-1.5 text-sm font-medium text-white bg-(--color-warning) transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
						title="Pausar las descargas activas seleccionadas"
					>
						Pausar{pausableSelected.length > 0 ? ` (${pausableSelected.length})` : ''}
					</button>
					<button
						onclick={bulkResume}
						disabled={bulkPending || resumableSelected.length === 0}
						class="rounded-md px-3 py-1.5 text-sm font-medium text-white bg-(--color-success) transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
						title="Reanudar las descargas pausadas seleccionadas"
					>
						Reanudar{resumableSelected.length > 0 ? ` (${resumableSelected.length})` : ''}
					</button>
					<button
						onclick={() => (confirmingDelete = true)}
						disabled={bulkPending || selectedIds.size === 0}
						class="rounded-md px-3 py-1.5 text-sm font-medium text-white bg-(--color-danger) transition-colors hover:bg-(--color-danger-hover) disabled:cursor-not-allowed disabled:opacity-30"
					>
						Eliminar
					</button>
					{#if selectedIds.size > 0}
						<button
							onclick={clearSelection}
							class="rounded-md border border-(--color-border) px-3 py-1.5 text-sm transition-colors hover:bg-(--color-surface-hover)"
						>
							Limpiar
						</button>
					{/if}
				{:else}
					<span class="text-sm text-(--color-text-muted)">
						¿Eliminar {selectedIds.size}?
					</span>
					<button
						onclick={() => bulkRemove(false)}
						disabled={bulkPending}
						class="rounded-md px-3 py-1.5 text-sm bg-(--color-surface-hover) hover:bg-(--color-border) disabled:opacity-50"
					>
						Solo quitar
					</button>
					<button
						onclick={() => bulkRemove(true)}
						disabled={bulkPending}
						class="rounded-md px-3 py-1.5 text-sm font-medium text-white bg-(--color-danger) hover:bg-(--color-danger-hover) disabled:opacity-50"
					>
						+ Borrar archivo
					</button>
					<button
						onclick={() => (confirmingDelete = false)}
						disabled={bulkPending}
						class="rounded-md border border-(--color-border) px-3 py-1.5 text-sm transition-colors hover:bg-(--color-surface-hover) disabled:opacity-50"
					>
						Cancelar
					</button>
				{/if}
			</div>
		</div>
	</div>
{/if}

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
				<DownloadRow
					{download}
					onRemoved={fetchDownloads}
					selected={selectedIds.has(download.id)}
					onToggleSelect={toggleSelect}
				/>
			{/each}
		</div>
	{/if}

	{#if stoppedDownloads.length > 0}
		<h2 class="mb-3 text-sm font-semibold uppercase text-(--color-warning)">Pausadas</h2>
		<div class="mb-6 grid gap-3">
			{#each stoppedDownloads as download (download.id)}
				<DownloadRow
					{download}
					onRemoved={fetchDownloads}
					selected={selectedIds.has(download.id)}
					onToggleSelect={toggleSelect}
				/>
			{/each}
		</div>
	{/if}

	{#if errorDownloads.length > 0}
		<h2 class="mb-3 text-sm font-semibold uppercase text-(--color-danger)">Con errores</h2>
		<div class="mb-6 grid gap-3">
			{#each errorDownloads as download (download.id)}
				<DownloadRow
					{download}
					onRemoved={fetchDownloads}
					selected={selectedIds.has(download.id)}
					onToggleSelect={toggleSelect}
				/>
			{/each}
		</div>
	{/if}

	{#if completedDownloads.length > 0}
		<h2 class="mb-3 text-sm font-semibold uppercase text-(--color-text-muted)">Completadas</h2>
		<div class="grid gap-3">
			{#each completedDownloads as download (download.id)}
				<DownloadRow
					{download}
					onRemoved={fetchDownloads}
					selected={selectedIds.has(download.id)}
					onToggleSelect={toggleSelect}
				/>
			{/each}
		</div>
	{/if}
{/if}
