<script lang="ts">
	import type { SearchResult } from '$lib/types';
	import { formatSize, formatDate, addDownload } from '$lib/api';
	import { settings } from '$lib/stores.svelte';

	let { result, channelName }: { result: SearchResult; channelName?: string } = $props();

	let downloading = $state(false);
	let downloaded = $state(false);
	let error = $state('');

	async function handleDownload() {
		downloading = true;
		error = '';
		try {
			await addDownload(settings.apiKey, result.guid);
			downloaded = true;
		} catch (e: any) {
			error = e.message || 'Error al descargar';
		} finally {
			downloading = false;
		}
	}
</script>

<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-4 transition-shadow hover:shadow-md">
	<div class="mb-2 flex items-start justify-between gap-3">
		<h3 class="min-w-0 flex-1 text-sm font-medium leading-tight break-all">
			{result.title}
		</h3>
		<span class="shrink-0 rounded bg-(--color-surface-alt) px-2 py-0.5 text-xs font-mono text-(--color-text-muted)">
			{formatSize(result.size)}
		</span>
	</div>

	{#if result.description}
		<p class="mb-3 line-clamp-2 text-xs text-(--color-text-muted)">
			{result.description}
		</p>
	{/if}

	<div class="flex items-center justify-between">
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-(--color-text-muted)">
			{#if channelName}
				<span class="rounded bg-(--color-primary)/10 px-1.5 py-0.5 text-xs font-medium text-(--color-primary)">
					{channelName}
				</span>
			{/if}
			<span>{formatDate(result.pubDate)}</span>
			{#if result.link}
				<a href={result.link} target="_blank" rel="noopener" class="text-(--color-primary) hover:underline">
					Telegram
				</a>
			{/if}
		</div>

		<div class="flex items-center gap-2">
			{#if error}
				<span class="text-xs text-(--color-danger)">{error}</span>
			{/if}
			<button
				onclick={handleDownload}
				disabled={downloading || downloaded}
				class="rounded-md px-3 py-1.5 text-xs font-medium text-white transition-colors disabled:opacity-50
					{downloaded ? 'bg-(--color-success)' : 'bg-(--color-primary) hover:bg-(--color-primary-hover)'}"
			>
				{#if downloading}
					Enviando...
				{:else if downloaded}
					Enviado
				{:else}
					Descargar
				{/if}
			</button>
		</div>
	</div>
</div>
