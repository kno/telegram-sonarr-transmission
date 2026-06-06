<script lang="ts">
	import type { Download, Destination } from '$lib/types';
	import { TR_STATUS } from '$lib/types';
	import { formatSize, formatSpeed, formatEta, removeDownload, pauseDownload, resumeDownload, getFileUrl, fetchDestinations, moveDownload } from '$lib/api';
	import { settings } from '$lib/stores.svelte';
	import ProgressBar from './ProgressBar.svelte';

	let {
		download,
		onRemoved,
		selected = false,
		onToggleSelect
	}: {
		download: Download;
		onRemoved: () => void;
		selected?: boolean;
		onToggleSelect?: (id: number, checked: boolean) => void;
	} = $props();

	let removing = $state(false);
	let showConfirm = $state(false);
	let showMoveMenu = $state(false);
	let moveDestinations = $state<Destination[]>([]);
	let loadingDestinations = $state(false);
	let moving = $state(false);
	let moveError = $state('');
	let moveSuccess = $state('');

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
	const isCompleted = $derived(download.isFinished || download.status === TR_STATUS.SEED);
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

	async function openMoveMenu() {
		showMoveMenu = true;
		moveError = '';
		moveSuccess = '';
		loadingDestinations = true;
		try {
			moveDestinations = await fetchDestinations(settings.apiKey);
		} catch {
			moveError = 'Error al cargar destinos';
		} finally {
			loadingDestinations = false;
		}
	}

	async function handleMove(destId: string) {
		moving = true;
		moveError = '';
		moveSuccess = '';
		try {
			await moveDownload(settings.apiKey, download.id, destId);
			moveSuccess = 'Movido';
			showMoveMenu = false;
			onRemoved();
		} catch (e: any) {
			moveError = e.message || 'Error al mover';
		} finally {
			moving = false;
		}
	}

	function closeMoveMenu() {
		showMoveMenu = false;
		moveError = '';
		moveSuccess = '';
	}

	function handleRowClick(e: MouseEvent) {
		if (!onToggleSelect) return;
		// Ignore clicks that landed on (or inside) any interactive control
		// in the row — the action icons, the file-download link, and the
		// checkbox itself all need to keep their native behavior.
		const target = e.target as HTMLElement | null;
		if (target?.closest('button, a, input, label')) return;
		onToggleSelect(download.id, !selected);
	}

	function handleRowKeydown(e: KeyboardEvent) {
		if (!onToggleSelect) return;
		if (e.key !== ' ' && e.key !== 'Enter') return;
		const target = e.target as HTMLElement | null;
		if (target?.closest('button, a, input, label')) return;
		e.preventDefault();
		onToggleSelect(download.id, !selected);
	}
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="rounded-lg border bg-(--color-surface) p-4 transition-colors"
	class:border-transparent={selected}
	class:ring-2={selected}
	class:ring-(--color-primary)={selected}
	class:border-(--color-border)={!selected}
	class:cursor-pointer={!!onToggleSelect}
	class:hover:bg-(--color-surface-hover)={!!onToggleSelect && !selected}
	role={onToggleSelect ? 'checkbox' : undefined}
	aria-checked={onToggleSelect ? selected : undefined}
	tabindex={onToggleSelect ? 0 : undefined}
	onclick={handleRowClick}
	onkeydown={handleRowKeydown}
>
	<div class="mb-2 flex items-start gap-3">
		{#if onToggleSelect}
			<input
				type="checkbox"
				checked={selected}
				onchange={(e) => onToggleSelect?.(download.id, e.currentTarget.checked)}
				class="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-(--color-primary)"
				aria-label="Seleccionar {download.name}"
			/>
		{/if}
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
				{#if isCompleted}
					<a
						href={getFileUrl(settings.apiKey, download.id)}
						download
						class="rounded-md p-1.5 text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover) hover:text-(--color-primary)"
						title="Descargar archivo"
					>
						<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
						</svg>
					</a>
					<div class="relative" class:z-10={showMoveMenu}>
						<button
							onclick={openMoveMenu}
							disabled={moving}
							class="rounded-md p-1.5 text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover) hover:text-(--color-primary) disabled:opacity-50"
							title="Mover a..."
						>
							<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
							</svg>
						</button>

						{#if showMoveMenu}
							<div class="move-menu-open absolute right-0 top-full z-20 mt-1 w-56 rounded-lg border border-(--color-border) bg-(--color-surface) p-2 shadow-lg">
								<div class="mb-1 flex items-center justify-between">
									<span class="text-xs font-medium text-(--color-text-muted)">Mover a...</span>
								<button
									onclick={closeMoveMenu}
									class="rounded p-0.5 text-(--color-text-muted) hover:bg-(--color-surface-hover)"
									aria-label="Cerrar"
								>
										<svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
										</svg>
									</button>
								</div>

								{#if loadingDestinations}
									<p class="py-2 text-center text-xs text-(--color-text-muted)">Cargando...</p>
								{:else if moveDestinations.length === 0}
									<p class="py-2 text-center text-xs text-(--color-text-muted)">Sin destinos configurados</p>
								{:else}
									{#each moveDestinations as dest (dest.id)}
										<button
											onclick={() => handleMove(dest.id)}
											disabled={moving}
											class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-(--color-text) transition-colors hover:bg-(--color-surface-hover) disabled:opacity-50"
										>
											<svg class="h-3.5 w-3.5 shrink-0 text-(--color-text-muted)" fill="none" viewBox="0 0 24 24" stroke="currentColor">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
											</svg>
											<span class="truncate">{dest.name}</span>
											<span class="ml-auto shrink-0 text-xs text-(--color-text-muted)">{dest.path}</span>
										</button>
									{/each}
								{/if}

								{#if moveError}
									<p class="mt-1 text-xs text-(--color-danger)">{moveError}</p>
								{/if}
								{#if moveSuccess}
									<p class="mt-1 text-xs text-(--color-success)">{moveSuccess}</p>
								{/if}
							</div>
						{/if}
					</div>
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
	{#if download.downloadDir}
		<div class="mt-0.5 text-right text-xs text-(--color-text-muted)">
			{download.downloadDir}
		</div>
	{/if}
</div>
