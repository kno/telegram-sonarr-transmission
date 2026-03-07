<script lang="ts">
	import type { Download } from '$lib/types';
	import { TR_STATUS } from '$lib/types';
	import { formatSize, formatSpeed, formatEta, removeDownload, pauseDownload, resumeDownload } from '$lib/api';
	import { settings } from '$lib/stores.svelte';
	import ProgressBar from './ProgressBar.svelte';

	let { download, onRemoved }: { download: Download; onRemoved: () => void } = $props();

	let removing = $state(false);
	let showConfirm = $state(false);

	const statusLabel = $derived.by(() => {
		if (download.error) return 'Error';
		switch (download.status) {
			case TR_STATUS.DOWNLOAD: return 'Descargando';
			case TR_STATUS.SEED: return 'Completo';
			case TR_STATUS.STOPPED: return download.isFinished ? 'Completo' : 'Detenido';
			case TR_STATUS.DOWNLOAD_WAIT: return 'En cola';
			case TR_STATUS.CHECK: return 'Verificando';
			default: return 'Desconocido';
		}
	});

	const statusColor = $derived.by(() => {
		if (download.error) return 'text-(--color-danger)';
		switch (download.status) {
			case TR_STATUS.DOWNLOAD: return 'text-(--color-primary)';
			case TR_STATUS.SEED: return 'text-(--color-success)';
			default: return 'text-(--color-text-muted)';
		}
	});

	const progressColor = $derived.by(() => {
		if (download.error) return 'bg-(--color-danger)';
		if (download.status === TR_STATUS.SEED || download.isFinished) return 'bg-(--color-success)';
		return 'bg-(--color-primary)';
	});

	const isActive = $derived(download.status === TR_STATUS.DOWNLOAD);
	const canPause = $derived(
		download.status === TR_STATUS.DOWNLOAD || download.status === TR_STATUS.DOWNLOAD_WAIT
	);
	const canResume = $derived(
		!download.isFinished &&
		(download.status === TR_STATUS.STOPPED || download.error > 0)
	);

	let toggling = $state(false);

	async function handleToggle() {
		toggling = true;
		try {
			if (canPause) {
				await pauseDownload(settings.apiKey, download.id);
			} else if (canResume) {
				await resumeDownload(settings.apiKey, download.id);
			}
			onRemoved(); // refresh list
		} catch {
			// ignore
		} finally {
			toggling = false;
		}
	}

	async function handleRemove(deleteData: boolean) {
		removing = true;
		try {
			await removeDownload(settings.apiKey, download.id, deleteData);
			onRemoved();
		} catch {
			// ignore
		} finally {
			removing = false;
			showConfirm = false;
		}
	}
</script>

<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-4">
	<div class="mb-2 flex items-start justify-between gap-3">
		<div class="min-w-0 flex-1">
			<h3 class="truncate text-sm font-medium">{download.name}</h3>
			<div class="mt-1 flex items-center gap-3 text-xs">
				<span class={statusColor}>{statusLabel}</span>
				<span class="text-(--color-text-muted)">{formatSize(download.totalSize)}</span>
				{#if isActive}
					<span class="text-(--color-text-muted)">{formatSpeed(download.rateDownload)}</span>
					<span class="text-(--color-text-muted)">ETA: {formatEta(download.eta)}</span>
				{/if}
			</div>
		</div>

		{#if !showConfirm}
			<div class="flex shrink-0 gap-1">
				{#if canPause}
					<button
						onclick={handleToggle}
						disabled={toggling}
						class="rounded-md p-1.5 text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover) hover:text-(--color-warning) disabled:opacity-50"
						title="Pausar"
					>
						<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
						</svg>
					</button>
				{:else if canResume}
					<button
						onclick={handleToggle}
						disabled={toggling}
						class="rounded-md p-1.5 text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover) hover:text-(--color-success) disabled:opacity-50"
						title="Reanudar"
					>
						<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
						</svg>
					</button>
				{/if}
				<button
					onclick={() => (showConfirm = true)}
					disabled={removing}
					class="rounded-md p-1.5 text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover) hover:text-(--color-danger)"
					title="Eliminar"
				>
					<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
					</svg>
				</button>
			</div>
		{:else}
			<div class="flex shrink-0 gap-1">
				<button
					onclick={() => handleRemove(false)}
					class="rounded px-2 py-1 text-xs bg-(--color-surface-hover) hover:bg-(--color-border)"
				>
					Solo quitar
				</button>
				<button
					onclick={() => handleRemove(true)}
					class="rounded px-2 py-1 text-xs text-white bg-(--color-danger) hover:bg-(--color-danger-hover)"
				>
					+ Borrar archivo
				</button>
				<button
					onclick={() => (showConfirm = false)}
					class="rounded px-2 py-1 text-xs bg-(--color-surface-hover)"
				>
					Cancelar
				</button>
			</div>
		{/if}
	</div>

	{#if download.error}
		<p class="mb-2 text-xs text-(--color-danger)">{download.errorString}</p>
	{/if}

	<ProgressBar percent={download.percentDone} color={progressColor} animated={isActive} />

	<div class="mt-1 text-right text-xs text-(--color-text-muted)">
		{(download.percentDone * 100).toFixed(1)}%
	</div>
</div>
