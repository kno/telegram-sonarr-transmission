<script lang="ts">
	import { settings, channelsStore } from '$lib/stores.svelte';
	import { fetchChannels } from '$lib/api';
	import { onMount } from 'svelte';

	let loading = $state(false);
	let error = $state('');
	let filter = $state('');

	async function loadChannels() {
		if (!settings.apiKey) {
			error = 'API key no configurada';
			return;
		}
		loading = true;
		error = '';
		try {
			const channels = await fetchChannels(settings.apiKey);
			channelsStore.setChannels(channels);
		} catch (e: any) {
			error = e.message || 'Error al cargar canales';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		if (settings.configured && channelsStore.channels.length === 0) {
			loadChannels();
		}
	});

	const filtered = $derived(
		filter
			? channelsStore.channels.filter((c) =>
					c.name.toLowerCase().includes(filter.toLowerCase())
				)
			: channelsStore.channels
	);

	const enabledCount = $derived(channelsStore.channels.filter((c) => c.enabled).length);
	const allFilteredEnabled = $derived(filtered.length > 0 && filtered.every((c) => c.enabled));
	const noneFilteredEnabled = $derived(filtered.length > 0 && filtered.every((c) => !c.enabled));

	function setFiltered(enabled: boolean) {
		const ids = new Set(filtered.map((c) => c.id));
		for (const ch of channelsStore.channels) {
			if (ids.has(ch.id)) ch.enabled = enabled;
		}
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('channels', JSON.stringify(channelsStore.channels));
		}
	}
</script>

<svelte:head>
	<title>Canales - Telegram Search & Download</title>
</svelte:head>

<div class="mb-4 flex items-center justify-between">
	<div>
		<h1 class="text-2xl font-bold">Canales</h1>
		<p class="text-sm text-(--color-text-muted)">
			{enabledCount} de {channelsStore.channels.length} habilitados
		</p>
	</div>
	<button
		onclick={loadChannels}
		disabled={loading}
		class="rounded-md px-4 py-2 text-sm font-medium text-white bg-(--color-primary) hover:bg-(--color-primary-hover) transition-colors disabled:opacity-50"
	>
		{loading ? 'Cargando...' : 'Recargar'}
	</button>
</div>

{#if error}
	<div class="mb-4 rounded-md border border-(--color-danger) bg-(--color-danger)/10 p-3 text-sm text-(--color-danger)">
		{error}
	</div>
{/if}

{#if channelsStore.channels.length > 0}
	<!-- Filter + bulk actions -->
	<div class="mb-4 flex flex-col gap-3 rounded-lg border border-(--color-border) bg-(--color-surface) p-3 sm:flex-row sm:items-center">
		<div class="relative flex-1">
			<svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-(--color-text-muted)" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
			</svg>
			<input
				type="text"
				bind:value={filter}
				placeholder="Filtrar canales..."
				class="w-full rounded-md border border-(--color-border) bg-(--color-surface-alt) py-2 pl-9 pr-3 text-sm text-(--color-text) placeholder:text-(--color-text-muted) focus:border-(--color-primary) focus:outline-none"
			/>
		</div>

		<div class="flex gap-2">
			<button
				onclick={() => filter ? setFiltered(true) : channelsStore.enableAll()}
				disabled={allFilteredEnabled}
				class="rounded-md border border-(--color-border) px-3 py-2 text-xs font-medium transition-colors hover:bg-(--color-surface-hover) disabled:opacity-30"
			>
				{filter ? `Seleccionar ${filtered.length}` : 'Seleccionar todos'}
			</button>
			<button
				onclick={() => filter ? setFiltered(false) : channelsStore.disableAll()}
				disabled={noneFilteredEnabled}
				class="rounded-md border border-(--color-border) px-3 py-2 text-xs font-medium transition-colors hover:bg-(--color-surface-hover) disabled:opacity-30"
			>
				{filter ? `Quitar ${filtered.length}` : 'Quitar todos'}
			</button>
		</div>
	</div>

	{#if filter && filtered.length === 0}
		<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-8 text-center">
			<p class="text-(--color-text-muted)">No hay canales que coincidan con "{filter}"</p>
		</div>
	{:else}
		<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each filtered as channel (channel.id)}
				<button
					onclick={() => channelsStore.toggle(channel.id)}
					class="flex items-center gap-3 rounded-lg border p-4 text-left transition-all
						{channel.enabled
							? 'border-(--color-primary) bg-(--color-primary)/5 shadow-sm'
							: 'border-(--color-border) bg-(--color-surface) opacity-60'}"
				>
					<div
						class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white
							{channel.enabled ? 'bg-(--color-primary)' : 'bg-(--color-text-muted)'}"
					>
						{channel.id - 999}
					</div>
					<div class="min-w-0 flex-1">
						<p class="truncate text-sm font-medium">{channel.name}</p>
						<p class="text-xs text-(--color-text-muted)">ID: {channel.id}</p>
					</div>
				</button>
			{/each}
		</div>
	{/if}

	{#if filter}
		<p class="mt-3 text-center text-xs text-(--color-text-muted)">
			Mostrando {filtered.length} de {channelsStore.channels.length} canales
		</p>
	{/if}
{:else if !loading && !error}
	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-12 text-center">
		<p class="text-(--color-text-muted)">No hay canales disponibles.</p>
		<p class="mt-1 text-sm text-(--color-text-muted)">
			Asegurate de tener la API key configurada y el backend corriendo.
		</p>
	</div>
{/if}
