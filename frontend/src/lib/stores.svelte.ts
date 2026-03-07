import { getSettings, saveSettings as persistSettings } from './api';
import type { Channel } from './types';

// --- Settings Store ---

class SettingsStore {
	apiKey = $state('');
	backendUrl = $state('');
	configured = $derived(this.apiKey.length > 0);

	load() {
		const s = getSettings();
		this.apiKey = s.apiKey;
		this.backendUrl = s.backendUrl;
	}

	save(apiKey: string, backendUrl: string) {
		this.apiKey = apiKey;
		this.backendUrl = backendUrl;
		persistSettings(apiKey, backendUrl);
	}
}

export const settings = new SettingsStore();

// --- Channels Store ---

class ChannelsStore {
	channels = $state<Channel[]>([]);

	load() {
		if (typeof localStorage === 'undefined') return;
		const raw = localStorage.getItem('channels');
		if (raw) {
			try {
				this.channels = JSON.parse(raw);
			} catch {
				// ignore
			}
		}
	}

	setChannels(channels: Channel[]) {
		// Preserve enabled state from stored channels
		const stored = new Map(this.channels.map((c) => [c.id, c.enabled]));
		this.channels = channels.map((c) => ({
			...c,
			enabled: stored.get(c.id) ?? true
		}));
		this.persist();
	}

	toggle(id: number) {
		const ch = this.channels.find((c) => c.id === id);
		if (ch) {
			ch.enabled = !ch.enabled;
			this.persist();
		}
	}

	enableAll() {
		this.channels.forEach((c) => (c.enabled = true));
		this.persist();
	}

	disableAll() {
		this.channels.forEach((c) => (c.enabled = false));
		this.persist();
	}

	get enabledIds(): number[] {
		return this.channels.filter((c) => c.enabled).map((c) => c.id);
	}

	private persist() {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('channels', JSON.stringify(this.channels));
		}
	}
}

export const channelsStore = new ChannelsStore();

// --- Theme Store ---

class ThemeStore {
	dark = $state(false);

	load() {
		if (typeof localStorage === 'undefined') return;
		const stored = localStorage.getItem('theme');
		if (stored === 'dark') {
			this.dark = true;
		} else if (!stored) {
			this.dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
		}
		this.apply();
	}

	toggle() {
		this.dark = !this.dark;
		localStorage.setItem('theme', this.dark ? 'dark' : 'light');
		this.apply();
	}

	private apply() {
		if (typeof document !== 'undefined') {
			document.documentElement.classList.toggle('dark', this.dark);
		}
	}
}

export const theme = new ThemeStore();
