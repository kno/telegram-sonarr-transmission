<script lang="ts">
	import { settings, destinationsStore } from '$lib/stores.svelte';
	import { testConnection, fetchDestinations, createDestination, deleteDestination, browseFilesystem } from '$lib/api';
	import type { Destination } from '$lib/types';

	let apiKey = $state('');
	let backendUrl = $state('');
	let testing = $state(false);
	let testResult = $state<boolean | null>(null);
	let saved = $state(false);

	// --- Destination state ---
	let destinations = $state<Destination[]>([]);
	let destLoading = $state(true);
	let destError = $state('');
	let showAddModal = $state(false);

	// File browser state
	let browsePath = $state('/');
	let browseEntries = $state<any[]>([]);
	let browseLoading = $state(false);
	let browseError = $state('');
	let newDestName = $state('');

	// Delete confirmation
	let confirmingDelete = $state<string | null>(null);
	let deleting = $state(false);

	$effect(() => {
		apiKey = settings.apiKey;
		backendUrl = settings.backendUrl;
	});

	$effect(() => {
		if (settings.apiKey) {
			loadDestinations();
		}
	});

	async function loadDestinations() {
		destLoading = true;
		destError = '';
		try {
			destinations = await fetchDestinations(settings.apiKey);
			destinationsStore.setDestinations(destinations);
		} catch (e: any) {
			destError = e.message || 'Error al cargar destinos';
		} finally {
			destLoading = false;
		}
	}

	function handleSave() {
		settings.save(apiKey, backendUrl);
		saved = true;
		testResult = null;
		setTimeout(() => (saved = false), 2000);
	}

	async function handleTest() {
		testing = true;
		testResult = null;
		settings.save(apiKey, backendUrl);
		testResult = await testConnection();
		testing = false;
	}

	// --- File browser ---

	async function openAddModal() {
		showAddModal = true;
		newDestName = '';
		browsePath = '/';
		browseEntries = [];
		browseError = '';
		await browseDir('/');
	}

	async function browseDir(path: string) {
		browsePath = path;
		browseLoading = true;
		browseError = '';
		try {
			const result = await browseFilesystem(settings.apiKey, path);
			browseEntries = result.entries || [];
			browseError = result.error || '';
		} catch (e: any) {
			browseError = e.message || 'Error al navegar';
			browseEntries = [];
		} finally {
			browseLoading = false;
		}
	}

	async function handleCreate() {
		if (!newDestName.trim()) return;
		const path = browsePath.trim();
		if (!path || path === '/') return;
		try {
			await createDestination(settings.apiKey, newDestName.trim(), path);
			showAddModal = false;
			await loadDestinations();
		} catch (e: any) {
			browseError = e.message || 'Error al crear destino';
		}
	}

	async function handleDelete(id: string) {
		deleting = true;
		try {
			await deleteDestination(settings.apiKey, id);
			confirmingDelete = null;
			await loadDestinations();
		} catch (e: any) {
			destError = e.message || 'Error al eliminar';
		} finally {
			deleting = false;
		}
	}
</script>

<svelte:head>
	<title>Configuracion - Telegram Search & Download</title>
</svelte:head>

<div class="mx-auto max-w-lg">
	<h1 class="mb-6 text-2xl font-bold">Configuracion</h1>

	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-6">
		<div class="mb-4">
			<label for="apiKey" class="mb-1 block text-sm font-medium">API Key</label>
			<input
				id="apiKey"
				type="password"
				bind:value={apiKey}
				placeholder="Tu TORZNAB_APIKEY"
				class="w-full rounded-md border border-(--color-border) bg-(--color-surface-alt) px-3 py-2 text-sm text-(--color-text) placeholder:text-(--color-text-muted) focus:border-(--color-primary) focus:outline-none"
			/>
		</div>

		<div class="mb-6">
			<label for="backendUrl" class="mb-1 block text-sm font-medium">Backend URL</label>
			<input
				id="backendUrl"
				type="text"
				bind:value={backendUrl}
				placeholder="Dejar vacio si es el mismo servidor"
				class="w-full rounded-md border border-(--color-border) bg-(--color-surface-alt) px-3 py-2 text-sm text-(--color-text) placeholder:text-(--color-text-muted) focus:border-(--color-primary) focus:outline-none"
			/>
			<p class="mt-1 text-xs text-(--color-text-muted)">
				Solo necesario en desarrollo. En produccion se usa el mismo origen.
			</p>
		</div>

		<div class="flex items-center gap-3">
			<button
				onclick={handleSave}
				class="rounded-md px-4 py-2 text-sm font-medium text-white bg-(--color-primary) hover:bg-(--color-primary-hover) transition-colors"
			>
				Guardar
			</button>

			<button
				onclick={handleTest}
				disabled={testing}
				class="rounded-md border border-(--color-border) px-4 py-2 text-sm font-medium text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover) disabled:opacity-50"
			>
				{testing ? 'Probando...' : 'Probar conexion'}
			</button>

			{#if saved}
				<span class="text-sm text-(--color-success)">Guardado</span>
			{/if}

			{#if testResult === true}
				<span class="text-sm text-(--color-success)">Conexion OK</span>
			{:else if testResult === false}
				<span class="text-sm text-(--color-danger)">No se pudo conectar</span>
			{/if}
		</div>
	</div>

	<!-- Carpetas destino -->
	<div class="mt-8">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-lg font-bold">Carpetas destino</h2>
			<button
				onclick={openAddModal}
				class="rounded-md px-3 py-1.5 text-sm font-medium text-white bg-(--color-primary) hover:bg-(--color-primary-hover) transition-colors"
			>
				Agregar carpeta
			</button>
		</div>

		{#if destError}
			<div class="mb-4 rounded-md border border-(--color-danger) bg-(--color-danger)/10 p-3 text-sm text-(--color-danger)">
				{destError}
			</div>
		{/if}

		{#if destLoading}
			<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-8 text-center">
				<p class="text-sm text-(--color-text-muted)">Cargando destinos...</p>
			</div>
		{:else if destinations.length === 0}
			<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-8 text-center">
				<p class="text-sm text-(--color-text-muted)">No hay carpetas destino configuradas.</p>
				<p class="mt-1 text-xs text-(--color-text-muted)">
					Agregá una carpeta para organizar tus descargas.
				</p>
			</div>
		{:else}
			<div class="grid gap-2">
				{#each destinations as dest (dest.id)}
					<div class="flex items-center gap-3 rounded-lg border border-(--color-border) bg-(--color-surface) p-3">
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2">
								<svg class="h-4 w-4 shrink-0 text-(--color-text-muted)" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
								</svg>
								<span class="truncate text-sm font-medium text-(--color-text)">{dest.name}</span>
							</div>
							<p class="ml-6 truncate text-xs text-(--color-text-muted)">{dest.path}</p>
						</div>

						{#if confirmingDelete === dest.id}
							<div class="flex shrink-0 items-center gap-2">
								<span class="text-xs text-(--color-text-muted)">¿Eliminar?</span>
								<button
									onclick={() => handleDelete(dest.id)}
									disabled={deleting}
									class="rounded px-2 py-1 text-xs font-medium text-white bg-(--color-danger) hover:bg-(--color-danger-hover) disabled:opacity-50"
								>
									{deleting ? '...' : 'Si'}
								</button>
								<button
									onclick={() => (confirmingDelete = null)}
									disabled={deleting}
									class="rounded px-2 py-1 text-xs bg-(--color-surface-hover) hover:bg-(--color-border)"
								>
									No
								</button>
							</div>
						{:else}
							<button
								onclick={() => (confirmingDelete = dest.id)}
								class="rounded-md p-1.5 text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover) hover:text-(--color-danger)"
								title="Eliminar {dest.name}"
							>
								<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
								</svg>
							</button>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<!-- File browser modal -->
{#if showAddModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		onclick={() => (showAddModal = false)}
		onkeydown={(e) => e.key === 'Escape' && (showAddModal = false)}
		role="dialog"
		aria-modal="true"
		aria-label="Agregar carpeta destino"
	>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<div
			class="w-full max-w-lg rounded-lg border border-(--color-border) bg-(--color-surface) p-6 shadow-xl"
			onclick={(e) => e.stopPropagation()}
		>
			<div class="mb-4 flex items-center justify-between">
				<h3 class="text-lg font-semibold">Agregar carpeta destino</h3>
				<button
					onclick={() => (showAddModal = false)}
					class="rounded-md p-1 text-(--color-text-muted) hover:bg-(--color-surface-hover)"
					aria-label="Cerrar"
				>
					<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<div class="mb-4">
				<label for="destName" class="mb-1 block text-sm font-medium">Nombre</label>
				<input
					id="destName"
					type="text"
					bind:value={newDestName}
					placeholder="Ej: Series, Peliculas, Musica..."
					class="w-full rounded-md border border-(--color-border) bg-(--color-surface-alt) px-3 py-2 text-sm text-(--color-text) placeholder:text-(--color-text-muted) focus:border-(--color-primary) focus:outline-none"
				/>
			</div>

			<div class="mb-3">
				<label for="browsePath" class="mb-1 block text-sm font-medium">Ruta</label>
				<div class="flex gap-2">
					<input
						id="browsePath"
						type="text"
						bind:value={browsePath}
						onchange={() => browseDir(browsePath)}
						class="flex-1 rounded-md border border-(--color-border) bg-(--color-surface-alt) px-3 py-2 text-sm text-(--color-text) focus:border-(--color-primary) focus:outline-none"
					/>
				</div>
			</div>

			<div class="mb-4 max-h-60 overflow-y-auto rounded-lg border border-(--color-border) bg-(--color-surface-alt)">
				{#if browseLoading}
					<div class="p-4 text-center text-sm text-(--color-text-muted)">Cargando...</div>
				{:else if browseError && browseEntries.length === 0}
					<div class="p-4 text-center text-sm text-(--color-danger)">{browseError}</div>
				{:else if browseEntries.length === 0}
					<div class="p-4 text-center text-sm text-(--color-text-muted)">Carpeta vacia</div>
				{:else}
					{#if browsePath !== '/'}
						<button
							onclick={() => browseDir(browsePath.replace(/\/[^/]+$/, '') || '/')}
							class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-(--color-text) transition-colors hover:bg-(--color-surface-hover)"
						>
							<svg class="h-4 w-4 text-(--color-text-muted)" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
							</svg>
							<span class="text-(--color-text-muted)">..</span>
						</button>
					{/if}
					{#each browseEntries as entry}
						{#if entry.type === 'dir'}
							<button
								onclick={() => browseDir(entry.path)}
								class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-(--color-text) transition-colors hover:bg-(--color-surface-hover)"
							>
								<svg class="h-4 w-4 shrink-0 text-(--color-warning)" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
								</svg>
								<span class="truncate">{entry.name}</span>
							</button>
						{/if}
					{/each}
				{/if}
			</div>

			{#if browseError}
				<p class="mb-2 text-xs text-(--color-danger)">{browseError}</p>
			{/if}

			<div class="flex justify-end gap-3">
				<button
					onclick={() => (showAddModal = false)}
					class="rounded-md border border-(--color-border) px-4 py-2 text-sm font-medium text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover)"
				>
					Cancelar
				</button>
				<button
					onclick={handleCreate}
					disabled={!newDestName.trim() || !browsePath.trim() || browsePath === '/'}
					class="rounded-md px-4 py-2 text-sm font-medium text-white bg-(--color-primary) hover:bg-(--color-primary-hover) transition-colors disabled:opacity-50"
				>
					Aceptar
				</button>
			</div>
		</div>
	</div>
{/if}
