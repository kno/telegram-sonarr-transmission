import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/svelte';
import SearchPage from '../routes/search/+page.svelte';
import { settings, channelsStore } from '$lib/stores.svelte';
import type { Channel, SearchResponse } from '$lib/types';

const apiMocks = vi.hoisted(() => ({
	fetchChannels: vi.fn(),
	search: vi.fn()
}));

vi.mock('$lib/api', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/api')>();
	return {
		...actual,
		fetchChannels: apiMocks.fetchChannels,
		search: apiMocks.search
	};
});

const storage: Record<string, string> = {};

beforeEach(() => {
	Object.keys(storage).forEach((key) => delete storage[key]);
	vi.stubGlobal('localStorage', {
		getItem: (key: string) => storage[key] ?? null,
		setItem: (key: string, val: string) => {
			storage[key] = val;
		},
		removeItem: (key: string) => {
			delete storage[key];
		}
	});

	settings.apiKey = 'test-key';
	settings.backendUrl = '';
	channelsStore.channels = [];
	apiMocks.fetchChannels.mockReset();
	apiMocks.search.mockReset();
});

afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
});

function channel(overrides: Partial<Channel> = {}): Channel {
	return {
		id: 1000,
		name: 'Stored Channel',
		enabled: true,
		...overrides
	};
}

function searchResponse(): SearchResponse {
	return {
		total: 1,
		offset: 0,
		items: [
			{
				title: 'Test Show S01E01',
				guid: '-1001234:44',
				link: 'https://t.me/example/44',
				pubDate: '2024-03-15T10:00:00Z',
				size: 1073741824,
				description: 'Episode from a refreshed channel',
				categoryId: 1000,
				downloadUrl: '/api/download?id=-1001234:44'
			}
		]
	};
}

describe('Search page channel loading', () => {
	it('loads channels when settings are configured and the channel list is empty', async () => {
		apiMocks.fetchChannels.mockResolvedValue([
			channel({ name: 'Fresh Channel', chatId: -1001234, enabled: true })
		]);

		render(SearchPage);

		await waitFor(() => {
			expect(apiMocks.fetchChannels).toHaveBeenCalledWith('test-key');
		});
		expect(channelsStore.channels).toEqual([
			channel({ name: 'Fresh Channel', chatId: -1001234, enabled: true })
		]);
	});

	it('refreshes stale stored channels without chatId and passes clickable channelChatId to result cards', async () => {
		storage.channels = JSON.stringify([channel({ enabled: false })]);
		channelsStore.load();
		apiMocks.fetchChannels.mockResolvedValue([
			channel({ name: 'Fresh Channel', chatId: -1001234, enabled: true })
		]);
		apiMocks.search.mockResolvedValue(searchResponse());

		render(SearchPage);

		await waitFor(() => {
			expect(apiMocks.fetchChannels).toHaveBeenCalledWith('test-key');
		});
		expect(channelsStore.channels[0]).toMatchObject({
			id: 1000,
			name: 'Fresh Channel',
			chatId: -1001234,
			enabled: false
		});

		await fireEvent.input(screen.getByPlaceholderText('Buscar contenido...'), {
			target: { value: 'Test Show' }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

		const channelLink = await screen.findByRole('link', { name: 'Fresh Channel' });
		expect(channelLink.getAttribute('href')).toBe('/channels/-1001234?message=44');
	});
});
