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
				topic_id: 900,
				telegram_url: 'https://t.me/c/1234/10',
				sender_name: 'Uploader',
				date: '2025-06-01T14:30:00+00:00',
				filename: 'Show.S01E01.mkv',
				file_size: 1073741824,
				mime_type: 'video/x-matroska',
				downloadable: true,
				media_group_id: null,
				text: 'Original message text',
				caption: 'Original caption',
				thumbnail_url: '/api/v2/channels/-1001234/messages/10/thumbnail'
			}
		],
		has_older: true,
		older_cursor: 10,
		has_newer: false,
		newer_cursor: null,
		topic_id: 900,
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
		expect(screen.getByRole('button', { name: '← Más antiguos' })).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Más recientes →' })).toBeDisabled();
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
		expect(screen.getByText('Uploader')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Abrir en Telegram' })).toHaveAttribute('href', 'https://t.me/c/1234/10');
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
				has_older: false,
				older_cursor: null,
				has_newer: false,
				newer_cursor: null
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
			json: () => Promise.resolve(messagesResponse({ messages: [], has_older: false, older_cursor: null, has_newer: false, newer_cursor: null }))
		}));

		render(ChannelPage);

		await vi.waitFor(() => {
			expect(screen.getByText('Series Channel')).toBeInTheDocument();
		});
		expect(screen.getByText('No hay mensajes disponibles en este canal.')).toBeInTheDocument();
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

	it('navigates older and newer with bidirectional pagination', async () => {
		const olderPage = messagesResponse({
			messages: [{ ...messagesResponse().messages[0], message_id: 5, filename: 'Older.S01E02.mkv' }],
			has_older: false,
			older_cursor: null,
			has_newer: true,
			newer_cursor: 5
		});
		const mockFetch = vi.fn()
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(messagesResponse({ has_newer: true, newer_cursor: 10 })) })
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(olderPage) })
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(messagesResponse({ has_newer: true, newer_cursor: 10 })) });
		vi.stubGlobal('fetch', mockFetch);

		render(ChannelPage);

		await vi.waitFor(() => expect(screen.getByText('Show.S01E01.mkv')).toBeInTheDocument());
		const olderBtn = () => screen.getAllByRole('button', { name: '← Más antiguos' })[0];
		const newerBtn = () => screen.getAllByRole('button', { name: 'Más recientes →' })[0];

		expect(olderBtn()).not.toBeDisabled();

		await fireEvent.click(olderBtn());

		await vi.waitFor(() => expect(screen.getByText('Older.S01E02.mkv')).toBeInTheDocument());
		expect(mockFetch.mock.calls[1][0]).toContain('before=10');
		expect(mockFetch.mock.calls[1][0]).toContain('include_channel=false');
		expect(mockFetch.mock.calls[1][0]).toContain('topic_id=900');
		expect(olderBtn()).toBeDisabled();
		expect(newerBtn()).not.toBeDisabled();

		await fireEvent.click(newerBtn());
		await vi.waitFor(() => expect(screen.getByText('Show.S01E01.mkv')).toBeInTheDocument());
		expect(mockFetch.mock.calls[2][0]).toContain('after=5');
		expect(mockFetch.mock.calls[2][0]).toContain('include_channel=false');
		expect(mockFetch.mock.calls[2][0]).toContain('topic_id=900');
	});

	it('starts pagination from the found message when opening from search', async () => {
		window.history.pushState({}, '', '/channels/-1001234?message=251258');
		const aroundPage = messagesResponse({
			messages: [{ ...messagesResponse().messages[0], message_id: 251258, filename: 'Found.S01E01.mkv' }],
			has_older: true,
			older_cursor: 251258,
			has_newer: false,
			newer_cursor: null
		});
		const olderPage = messagesResponse({
			messages: [{ ...messagesResponse().messages[0], message_id: 251200, filename: 'Older.S01E01.mkv' }],
			has_older: false,
			older_cursor: null,
			has_newer: true,
			newer_cursor: 251200
		});
		const mockFetch = vi.fn()
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(aroundPage) })
			.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(olderPage) });
		vi.stubGlobal('fetch', mockFetch);

		render(ChannelPage);

		await vi.waitFor(() => expect(screen.getByText('Found.S01E01.mkv')).toBeInTheDocument());
		expect(screen.queryByText('Older.S01E01.mkv')).not.toBeInTheDocument();
		const olderBtn = () => screen.getAllByRole('button', { name: '← Más antiguos' })[0];
		expect(olderBtn()).not.toBeDisabled();

		await fireEvent.click(olderBtn());
		await vi.waitFor(() => expect(screen.getByText('Older.S01E01.mkv')).toBeInTheDocument());
		expect(olderBtn()).toBeDisabled();
		expect(mockFetch.mock.calls[0][0]).toContain('around=251258');
		expect(mockFetch.mock.calls[1][0]).toContain('before=251258');
		expect(mockFetch.mock.calls[1][0]).toContain('include_channel=false');
		expect(mockFetch.mock.calls[1][0]).toContain('topic_id=900');
	});

	it('renders text-only channel messages without a download button', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve(messagesResponse({
				messages: [{
					...messagesResponse().messages[0],
					message_id: 11,
					filename: null,
					file_size: null,
					mime_type: null,
					downloadable: false,
					text: 'Only a text update',
					caption: null,
					thumbnail_url: null
				}],
				has_older: false,
				older_cursor: null,
				has_newer: false,
				newer_cursor: null
			}))
		}));

		render(ChannelPage);

		await vi.waitFor(() => expect(screen.getAllByText('Only a text update')).toHaveLength(2));
		expect(screen.getByText('Sin archivo')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Descargar' })).not.toBeInTheDocument();
	});

	it('renders unnamed text files as text files', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve(messagesResponse({
				messages: [{
					...messagesResponse().messages[0],
					message_id: 12,
					filename: null,
					file_size: 2048,
					mime_type: 'text/plain',
					downloadable: true,
					text: null,
					caption: null,
					thumbnail_url: null
				}],
				has_older: false,
				older_cursor: null,
				has_newer: false,
				newer_cursor: null
			}))
		}));

		render(ChannelPage);

		await vi.waitFor(() => expect(screen.getByText('Archivo de texto')).toBeInTheDocument());
		expect(screen.getByRole('button', { name: 'Descargar' })).toBeInTheDocument();
		expect(screen.queryByText('Contenido no soportado por Telegram API')).not.toBeInTheDocument();
	});

	it('labels unsupported Telegram content without pretending it is empty', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve(messagesResponse({
				messages: [{
					...messagesResponse().messages[0],
					message_id: 13,
					filename: null,
					file_size: null,
					mime_type: null,
					downloadable: false,
					text: null,
					caption: null,
					thumbnail_url: null
				}],
				has_older: false,
				older_cursor: null,
				has_newer: false,
				newer_cursor: null
			}))
		}));

		render(ChannelPage);

		await vi.waitFor(() => expect(screen.getByText('Contenido no soportado por Telegram API')).toBeInTheDocument());
		expect(screen.getByRole('link', { name: 'Abrir en Telegram' })).toBeInTheDocument();
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
