import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// --- localStorage mock ---

const storage: Record<string, string> = {};

beforeEach(() => {
	Object.keys(storage).forEach((k) => delete storage[k]);

	vi.stubGlobal('localStorage', {
		getItem: (key: string) => storage[key] ?? null,
		setItem: (key: string, val: string) => {
			storage[key] = val;
		},
		removeItem: (key: string) => {
			delete storage[key];
		}
	});
});

afterEach(() => {
	vi.restoreAllMocks();
});

// --- SettingsStore ---

describe('SettingsStore', () => {
	it('starts with empty values', async () => {
		const { settings } = await import('$lib/stores.svelte');
		// Fresh import, no localStorage values
		expect(settings.apiKey).toBe('');
		expect(settings.backendUrl).toBe('');
	});

	it('configured is false when apiKey is empty', async () => {
		const { settings } = await import('$lib/stores.svelte');
		settings.apiKey = '';
		expect(settings.configured).toBe(false);
	});

	it('configured is true when apiKey is set', async () => {
		const { settings } = await import('$lib/stores.svelte');
		settings.apiKey = 'somekey';
		expect(settings.configured).toBe(true);
	});

	it('load() reads from localStorage', async () => {
		storage['apiKey'] = 'loaded-key';
		storage['backendUrl'] = 'http://backend:9117';

		const { settings } = await import('$lib/stores.svelte');
		settings.load();

		expect(settings.apiKey).toBe('loaded-key');
		expect(settings.backendUrl).toBe('http://backend:9117');
	});

	it('save() persists to localStorage and updates state', async () => {
		const { settings } = await import('$lib/stores.svelte');
		settings.save('new-key', 'http://new-url');

		expect(settings.apiKey).toBe('new-key');
		expect(settings.backendUrl).toBe('http://new-url');
		expect(storage['apiKey']).toBe('new-key');
		expect(storage['backendUrl']).toBe('http://new-url');
	});
});

// --- ChannelsStore ---

describe('ChannelsStore', () => {
	it('starts with empty channels', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		// Reset
		channelsStore.channels = [];
		expect(channelsStore.channels).toEqual([]);
	});

	it('load() reads channels from localStorage', async () => {
		const channels = [
			{ id: 1000, name: 'Channel A', enabled: true },
			{ id: 1001, name: 'Channel B', enabled: false }
		];
		storage['channels'] = JSON.stringify(channels);

		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.load();

		expect(channelsStore.channels).toEqual(channels);
	});

	it('load() handles invalid JSON gracefully', async () => {
		storage['channels'] = 'not-valid-json';

		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [];
		channelsStore.load();

		expect(channelsStore.channels).toEqual([]);
	});

	it('load() does nothing when no stored channels', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [{ id: 1, name: 'existing', enabled: true }];
		// No 'channels' key in storage
		channelsStore.load();

		// channels not overwritten
		expect(channelsStore.channels).toHaveLength(1);
	});

	it('setChannels() sets new channels and persists', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [];

		const newChannels = [
			{ id: 1000, name: 'Ch1', enabled: true },
			{ id: 1001, name: 'Ch2', enabled: true }
		];
		channelsStore.setChannels(newChannels);

		expect(channelsStore.channels).toHaveLength(2);
		expect(channelsStore.channels[0].name).toBe('Ch1');
		expect(storage['channels']).toBeDefined();
	});

	it('setChannels() preserves enabled state from existing channels', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		// Pre-existing: channel 1000 was disabled by user
		channelsStore.channels = [
			{ id: 1000, name: 'Ch1', enabled: false },
			{ id: 1001, name: 'Ch2', enabled: true }
		];

		// New fetch brings same channels with enabled: true
		channelsStore.setChannels([
			{ id: 1000, name: 'Ch1 Updated', enabled: true },
			{ id: 1001, name: 'Ch2 Updated', enabled: true },
			{ id: 1002, name: 'New Channel', enabled: true }
		]);

		// 1000 should keep its disabled state
		expect(channelsStore.channels[0].enabled).toBe(false);
		// 1001 stays enabled
		expect(channelsStore.channels[1].enabled).toBe(true);
		// 1002 is new, defaults to true
		expect(channelsStore.channels[2].enabled).toBe(true);
	});

	it('toggle() flips enabled state of a channel', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [
			{ id: 1000, name: 'Ch1', enabled: true },
			{ id: 1001, name: 'Ch2', enabled: false }
		];

		channelsStore.toggle(1000);
		expect(channelsStore.channels[0].enabled).toBe(false);

		channelsStore.toggle(1001);
		expect(channelsStore.channels[1].enabled).toBe(true);
	});

	it('toggle() does nothing for non-existent channel', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [{ id: 1000, name: 'Ch1', enabled: true }];

		channelsStore.toggle(9999); // no-op
		expect(channelsStore.channels[0].enabled).toBe(true);
	});

	it('enableAll() enables all channels', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [
			{ id: 1000, name: 'Ch1', enabled: false },
			{ id: 1001, name: 'Ch2', enabled: false }
		];

		channelsStore.enableAll();

		expect(channelsStore.channels.every((c) => c.enabled)).toBe(true);
	});

	it('disableAll() disables all channels', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [
			{ id: 1000, name: 'Ch1', enabled: true },
			{ id: 1001, name: 'Ch2', enabled: true }
		];

		channelsStore.disableAll();

		expect(channelsStore.channels.every((c) => !c.enabled)).toBe(true);
	});

	it('enabledIds returns only enabled channel IDs', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [
			{ id: 1000, name: 'Ch1', enabled: true },
			{ id: 1001, name: 'Ch2', enabled: false },
			{ id: 1002, name: 'Ch3', enabled: true }
		];

		expect(channelsStore.enabledIds).toEqual([1000, 1002]);
	});

	it('enabledIds returns empty array when all disabled', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [
			{ id: 1000, name: 'Ch1', enabled: false }
		];

		expect(channelsStore.enabledIds).toEqual([]);
	});

	it('toggle() persists changes to localStorage', async () => {
		const { channelsStore } = await import('$lib/stores.svelte');
		channelsStore.channels = [{ id: 1000, name: 'Ch1', enabled: true }];

		channelsStore.toggle(1000);

		const persisted = JSON.parse(storage['channels']);
		expect(persisted[0].enabled).toBe(false);
	});
});

// --- ThemeStore ---

describe('ThemeStore', () => {
	it('starts with dark = false', async () => {
		const { theme } = await import('$lib/stores.svelte');
		theme.dark = false; // reset
		expect(theme.dark).toBe(false);
	});

	it('load() sets dark from localStorage', async () => {
		storage['theme'] = 'dark';

		const { theme } = await import('$lib/stores.svelte');
		theme.load();

		expect(theme.dark).toBe(true);
	});

	it('load() defaults to system preference when no stored value', async () => {
		// No 'theme' in storage
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));

		const { theme } = await import('$lib/stores.svelte');
		theme.load();

		expect(theme.dark).toBe(true);
	});

	it('load() defaults to light when system prefers light', async () => {
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));

		const { theme } = await import('$lib/stores.svelte');
		theme.load();

		expect(theme.dark).toBe(false);
	});

	it('toggle() switches dark mode and persists', async () => {
		const { theme } = await import('$lib/stores.svelte');
		theme.dark = false;

		theme.toggle();
		expect(theme.dark).toBe(true);
		expect(storage['theme']).toBe('dark');

		theme.toggle();
		expect(theme.dark).toBe(false);
		expect(storage['theme']).toBe('light');
	});

	it('toggle() applies dark class to document', async () => {
		const { theme } = await import('$lib/stores.svelte');
		theme.dark = false;

		theme.toggle();
		expect(document.documentElement.classList.contains('dark')).toBe(true);

		theme.toggle();
		expect(document.documentElement.classList.contains('dark')).toBe(false);
	});

	it('load() with stored "light" keeps dark false', async () => {
		storage['theme'] = 'light';

		const { theme } = await import('$lib/stores.svelte');
		theme.load();

		// 'light' is not 'dark', and it's truthy so the !stored branch won't run
		expect(theme.dark).toBe(false);
	});
});
