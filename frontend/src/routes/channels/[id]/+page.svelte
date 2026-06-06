<script lang="ts">
	import { settings } from '$lib/stores.svelte';
	import { addMessageDownload, formatDate, formatSize, getChannelMessages } from '$lib/api';
	import type { ChannelInfo, ChannelMessage } from '$lib/types';

	const chatId = typeof window !== 'undefined' ? Number(window.location.pathname.split('/').pop()) : 0;
	const foundMessageId = typeof window !== 'undefined'
		? Number(new URLSearchParams(window.location.search).get('message')) || undefined
		: undefined;
	const limit = 20;

	let loading = $state(true);
	let error = $state('');
	let channel = $state<ChannelInfo | null>(null);
	let messages = $state<ChannelMessage[]>([]);
	let hasMore = $state(false);
	let nextCursor = $state<number | null>(null);
	let currentCursor = $state<number | undefined>(undefined);
	let pageStack = $state<(number | undefined)[]>([]);
	let downloadState = $state<Record<number, 'loading' | 'done' | 'error'>>({});
	let downloadErrors = $state<Record<number, string>>({});

	function thumbnailSrc(message: ChannelMessage) {
		if (!message.thumbnail_url) return '';
		return `${message.thumbnail_url}?apikey=${encodeURIComponent(settings.apiKey)}`;
	}

	async function loadMessages(before?: number, pushHistory = false, around?: number) {
		if (!settings.apiKey) {
			error = 'API key no configurada';
			loading = false;
			return;
		}
		loading = true;
		error = '';
		try {
			const response = await getChannelMessages(settings.apiKey, chatId, before, limit, around);
			if (pushHistory) pageStack = [...pageStack, currentCursor];
			currentCursor = before;
			channel = response.channel;
			messages = response.messages;
			hasMore = response.has_more;
			nextCursor = response.next_cursor;
		} catch (e: any) {
			error = e.message || 'Error al cargar mensajes del canal';
		} finally {
			loading = false;
		}
	}

	async function nextPage() {
		if (nextCursor === null) return;
		await loadMessages(nextCursor, true);
	}

	async function prevPage() {
		if (pageStack.length === 0) return;
		const previous = pageStack[pageStack.length - 1];
		pageStack = pageStack.slice(0, -1);
		await loadMessages(previous, false);
	}

	async function downloadMessage(message: ChannelMessage) {
		downloadState[message.message_id] = 'loading';
		downloadErrors[message.message_id] = '';
		try {
			await addMessageDownload(settings.apiKey, chatId, message.message_id);
			downloadState[message.message_id] = 'done';
		} catch (e: any) {
			downloadState[message.message_id] = 'error';
			downloadErrors[message.message_id] = e.message || 'Error al descargar';
		}
	}

	$effect(() => {
		if (settings.apiKey) loadMessages(undefined, false, foundMessageId);
	});
</script>

<svelte:head>
	<title>Canal - Telegram Search & Download</title>
</svelte:head>

<div class="mb-4">
	<a href="/search" class="text-sm text-(--color-primary) hover:underline">Volver a buscar</a>
</div>

<section class="mb-4 rounded-lg border border-(--color-border) bg-(--color-surface) p-4">
	{#if channel}
		<h1 class="text-2xl font-bold">{channel.title}</h1>
		<div class="mt-1 flex flex-wrap gap-3 text-sm text-(--color-text-muted)">
			{#if channel.participants_count}
				<span>{channel.participants_count} miembros</span>
			{/if}
			{#if channel.username}
				<span>@{channel.username}</span>
			{/if}
		</div>
		{#if channel.description}
			<p class="mt-3 text-sm text-(--color-text-muted)">{channel.description}</p>
		{/if}
	{:else}
		<h1 class="text-2xl font-bold">Canal {chatId}</h1>
	{/if}
</section>

{#if error}
	<div class="mb-4 rounded-md border border-(--color-danger) bg-(--color-danger)/10 p-3 text-sm text-(--color-danger)" role="alert">
		<p>{error}</p>
		<button onclick={() => loadMessages(currentCursor)} class="mt-2 rounded-md border border-(--color-danger) px-3 py-1 text-xs">
			Reintentar
		</button>
	</div>
{/if}

{#if loading}
	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-8 text-center text-(--color-text-muted)">
		Cargando mensajes...
	</div>
{:else if !error && messages.length === 0}
	<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-8 text-center text-(--color-text-muted)">
		No hay archivos disponibles en este canal.
	</div>
{:else if messages.length > 0}
	<div class="grid gap-3">
		{#each messages as message (message.message_id)}
			<div class="rounded-lg border border-(--color-border) bg-(--color-surface) p-4" class:ring-2={message.message_id === foundMessageId} class:ring-(--color-primary)={message.message_id === foundMessageId}>
				{#if message.message_id === foundMessageId}
					<p class="mb-2 text-xs font-medium text-(--color-primary)">Mensaje encontrado</p>
				{/if}
				<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
					{#if message.thumbnail_url}
						<img src={thumbnailSrc(message)} alt={`Miniatura de ${message.filename || 'archivo'}`} class="h-20 w-28 shrink-0 rounded object-cover" loading="lazy" />
					{/if}
					<div class="min-w-0 flex-1">
						<p class="break-all text-sm font-medium">{message.filename || 'unknown'}</p>
						{#if message.caption || message.text}
							<p class="mt-1 line-clamp-2 text-xs text-(--color-text-muted)">{message.caption || message.text}</p>
						{/if}
						<p class="mt-1 flex gap-2 text-xs text-(--color-text-muted)">
							<span>{formatSize(message.file_size)}</span>
							<span>{message.date ? formatDate(message.date) : 'Sin fecha'}</span>
						</p>
					</div>
					<div class="flex items-center gap-2">
						{#if downloadErrors[message.message_id]}
							<span class="text-xs text-(--color-danger)">{downloadErrors[message.message_id]}</span>
						{/if}
						<button
							onclick={() => downloadMessage(message)}
							disabled={downloadState[message.message_id] === 'loading' || downloadState[message.message_id] === 'done'}
							class="rounded-md px-3 py-1.5 text-xs font-medium text-white transition-colors disabled:opacity-50
								{downloadState[message.message_id] === 'done' ? 'bg-(--color-success)' : 'bg-(--color-primary) hover:bg-(--color-primary-hover)'}"
						>
							{#if downloadState[message.message_id] === 'loading'}
								Enviando...
							{:else if downloadState[message.message_id] === 'done'}
								Enviado
							{:else}
								Descargar
							{/if}
						</button>
					</div>
				</div>
			</div>
		{/each}
	</div>
{/if}

<div class="mt-4 flex justify-center gap-3">
	<button
		onclick={prevPage}
		disabled={loading || pageStack.length === 0}
		class="rounded-md border border-(--color-border) px-4 py-2 text-sm transition-colors hover:bg-(--color-surface-hover) disabled:opacity-30"
	>
		Anterior
	</button>
	<button
		onclick={nextPage}
		disabled={loading || !hasMore || nextCursor === null}
		class="rounded-md border border-(--color-border) px-4 py-2 text-sm transition-colors hover:bg-(--color-surface-hover) disabled:opacity-30"
	>
		Siguiente
	</button>
</div>
