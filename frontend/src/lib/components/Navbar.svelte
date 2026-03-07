<script lang="ts">
	import ThemeToggle from './ThemeToggle.svelte';
	import { settings } from '$lib/stores.svelte';

	const links = [
		{ href: '/', label: 'Dashboard' },
		{ href: '/channels', label: 'Canales' },
		{ href: '/search', label: 'Buscar' },
		{ href: '/downloads', label: 'Descargas' },
		{ href: '/settings', label: 'Config' }
	];

	let menuOpen = $state(false);
</script>

<nav class="bg-(--color-surface) border-b border-(--color-border) shadow-sm">
	<div class="mx-auto max-w-6xl px-4">
		<div class="flex h-14 items-center justify-between">
			<a href="/" class="text-lg font-bold text-(--color-primary)">TG Torznab</a>

			<!-- Desktop links -->
			<div class="hidden items-center gap-1 md:flex">
				{#each links as { href, label }}
					<a
						{href}
						class="rounded-md px-3 py-2 text-sm font-medium text-(--color-text-muted) transition-colors hover:bg-(--color-surface-hover) hover:text-(--color-text)"
					>
						{label}
					</a>
				{/each}
				<ThemeToggle />
			</div>

			<!-- Mobile menu button -->
			<div class="flex items-center gap-2 md:hidden">
				<ThemeToggle />
				<button
					onclick={() => (menuOpen = !menuOpen)}
					class="rounded-md p-2 text-(--color-text-muted) hover:bg-(--color-surface-hover)"
				>
					<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						{#if menuOpen}
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
						{:else}
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
						{/if}
					</svg>
				</button>
			</div>
		</div>

		<!-- Mobile menu -->
		{#if menuOpen}
			<div class="border-t border-(--color-border) pb-3 pt-2 md:hidden">
				{#each links as { href, label }}
					<a
						{href}
						onclick={() => (menuOpen = false)}
						class="block rounded-md px-3 py-2 text-sm font-medium text-(--color-text-muted) hover:bg-(--color-surface-hover)"
					>
						{label}
					</a>
				{/each}
			</div>
		{/if}
	</div>

	{#if !settings.configured}
		<div class="bg-(--color-warning) px-4 py-2 text-center text-sm text-black">
			API key no configurada. <a href="/settings" class="font-bold underline">Configurar</a>
		</div>
	{/if}
</nav>
