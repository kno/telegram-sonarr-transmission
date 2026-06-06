import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ChannelPage from '../routes/channels/[id]/+page.svelte';
import { settings } from '$lib/stores.svelte';

const storage: Record<string, string> = {};

function mockStorage() {
	Object.keys(storage).forEach((key) => delete storage[key]);
	storage.apiKey = 'testkey';
	vi.stubGlobal('localStorage', {
		getItem: (key: string) => storage[key] ?? null,
		setItem: (key: string, val: string) => {
			storage[key] = val;
		},
		removeItem: (key: string) => {
			delete storage[key];
		}
	});
	settings.load();
}

function messagesResponse(overrides: any = {}) {
	return {
		channel: { id: -1001234, title: 'Series Channel', participants_count: 1200, description: 'HD files' },
		messages: [
			{
				message_id: 10,
				date: '2025-06-01T14:30:00+00:00',
				filename: 'Show.S01E01.mkv',
				file_size: 1073741824,
				mime_type: 'video/x-matroska',
				media_group_id: null,
				text: 'Original message text',
				caption: 'Original caption',
				thumbnail_url: '/api/v2/channels/-1001234/messages/10/thumbnail'
			}
		],
		has_more: true,
		next_cursor: 10,
		...overrides
	};
}

beforeEach(() => {
	mockStorage();
	window.history.pushState({}, '', '/channels/-1001234');
});

afterEach(() => {
	vi.restoreAllMocks();
});

describe('ChannelPage', () => {
	it('shows loading state before messages arrive', () => {
		vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})));

		render(ChannelPage);

		expect(screen.getByText('Cargando mensajes...')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled();
	});

	it('renders channel metadata and message rows', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(messagesResponse()) }));

		render(ChannelPage);

		await vi.waitFor(() => {
			expect(screen.getByText('Series Channel')).toBeInTheDocument();
		});
		expect(screen.getByText('1200 miembros')).toBeInTheDocument();
		expect(screen.getByText('HD files')).toBeInTheDocument();
		expect(screen.getByText('Show.S01E01.mkv')).toBeInTheDocument();
		expect(screen.getByText('Original caption')).toBeInTheDocument();
		expect(screen.getByRole('img', { name: 'Miniatura de Show.S01E01.mkv' })).toHaveAttribute(
			'src',
			'/api/v2/channels/-1001234/messages/10/thumbnail?apikey=testkey'
		);
		expect(screen.getByText('1.0 GB')).toBeInTheDocument();
	});

	it('loads around and highlights the message from the search result query param', async () => {
		window.history.pushState({}, '', '/channels/-1001234?message=251258');
		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve(messagesResponse({
				messages: [{ ...messagesResponse().messages[0], message_id: 251258, filename: 'Mismatch.S01E01.mkv' }],
				has_more: false,
				next_cursor: null
			}))
		});
		vi.stubGlobal('fetch', mockFetch);

		render(ChannelPage);

		await vi.waitFor(() => expect(screen.getByText('Mismatch.S01E01.mkv')).toBeInTheDocument());
		expect(mockFetch.mock.calls[0][0]).toContain('around=251258');
		expect(screen.getByText('Mensaje encontrado')).toBeInTheDocument();
	});

	it('shows empty state while preserving channel metadata', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve(messagesResponse({ messages: [], has_more: false, next_cursor: null }))
		}));

		render(ChannelPage);

		await vi.waitFor(() => {
			expect(screen.getByText('Series Channel')).toBeInTheDocument();
		});
		expect(screen.getByText('No hay archivos disponibles en este canal.')).toBeInTheDocument();
	});

	it('shows retryable error and retries', async () => {
		const mockFetch = vi.fn()
			.mockResolvedValueOnce({ ok: false, status: 429, json: () => Promise.resolve({ detail: 'Telegram rate limit, retry later' }) })
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(messagesResponse()) });
		vi.stubGlobal('fetch', mockFetch);

		render(ChannelPage);

		await vi.waitFor(() => {
			expect(screen.getByText('Telegram rate limit, retry later')).toBeInTheDocument();
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));

		await vi.waitFor(() => {
			expect(screen.getByText('Show.S01E01.mkv')).toBeInTheDocument();
		});
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it('uses next cursor and enables previous page history', async () => {
		const secondPage = messagesResponse({
			messages: [{ ...messagesResponse().messages[0], message_id: 5, filename: 'Show.S01E02.mkv' }],
			has_more: false,
			next_cursor: null
		});
		const mockFetch = vi.fn()
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(messagesResponse()) })
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(secondPage) })
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(messagesResponse()) });
		vi.stubGlobal('fetch', mockFetch);

		render(ChannelPage);

		await vi.waitFor(() => expect(screen.getByText('Show.S01E01.mkv')).toBeInTheDocument());
		await fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));

		await vi.waitFor(() => expect(screen.getByText('Show.S01E02.mkv')).toBeInTheDocument());
		expect(mockFetch.mock.calls[1][0]).toContain('before=10');
		expect(screen.getByRole('button', { name: 'Anterior' })).not.toBeDisabled();

		await fireEvent.click(screen.getByRole('button', { name: 'Anterior' }));
		await vi.waitFor(() => expect(screen.getByText('Show.S01E01.mkv')).toBeInTheDocument());
	});

	it('tracks download state per message', async () => {
		const mockFetch = vi.fn()
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(messagesResponse()) })
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ status: 'added' }) });
		vi.stubGlobal('fetch', mockFetch);

		render(ChannelPage);

		await vi.waitFor(() => expect(screen.getByText('Show.S01E01.mkv')).toBeInTheDocument());
		await fireEvent.click(screen.getByRole('button', { name: 'Descargar' }));

		await vi.waitFor(() => expect(screen.getByText('Enviado')).toBeInTheDocument());
		expect(mockFetch.mock.calls[1][0]).toBe('/api/v2/downloads?chat_id=-1001234&msg_id=10&apikey=testkey');
	});
});
