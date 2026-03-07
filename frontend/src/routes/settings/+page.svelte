<script lang="ts">
	import { settings } from '$lib/stores.svelte';
	import { testConnection } from '$lib/api';

	let apiKey = $state('');
	let backendUrl = $state('');
	let testing = $state(false);
	let testResult = $state<boolean | null>(null);
	let saved = $state(false);

	$effect(() => {
		apiKey = settings.apiKey;
		backendUrl = settings.backendUrl;
	});

	function handleSave() {
		settings.save(apiKey, backendUrl);
		saved = true;
		testResult = null;
		setTimeout(() => (saved = false), 2000);
	}

	async function handleTest() {
		testing = true;
		testResult = null;
		// Save first so getBaseUrl picks up the new URL
		settings.save(apiKey, backendUrl);
		testResult = await testConnection();
		testing = false;
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
</div>
