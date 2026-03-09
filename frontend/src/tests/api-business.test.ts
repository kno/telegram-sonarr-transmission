import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
	getSettings,
	saveSettings,
	fetchChannels,
	search,
	getDownloads,
	addDownload,
	removeDownload,
	pauseDownload,
	resumeDownload,
	getFileUrl,
	getSessionStats,
	testConnection,
	connectDownloadsWS
} from '$lib/api';

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

// --- Settings ---

describe('getSettings', () => {
	it('returns empty strings when nothing stored', () => {
		const s = getSettings();
		expect(s.apiKey).toBe('');
		expect(s.backendUrl).toBe('');
	});

	it('returns stored values', () => {
		storage['apiKey'] = 'mykey';
		storage['backendUrl'] = 'http://localhost:9117';
		const s = getSettings();
		expect(s.apiKey).toBe('mykey');
		expect(s.backendUrl).toBe('http://localhost:9117');
	});
});

describe('saveSettings', () => {
	it('persists apiKey and backendUrl', () => {
		saveSettings('key123', 'http://example.com');
		expect(storage['apiKey']).toBe('key123');
		expect(storage['backendUrl']).toBe('http://example.com');
	});
});

// --- fetchChannels ---

describe('fetchChannels', () => {
	it('parses caps XML and returns channels with id >= 1000', async () => {
		const capsXml = `<?xml version="1.0"?>
<caps>
  <categories>
    <category id="100" name="General"/>
    <category id="500" name="Other"/>
    <category id="1000" name="TestChannel"/>
    <category id="1001" name="AnotherChannel"/>
  </categories>
</caps>`;

		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				text: () => Promise.resolve(capsXml)
			})
		);

		const channels = await fetchChannels('testkey');
		expect(channels).toHaveLength(2);
		expect(channels[0]).toEqual({ id: 1000, name: 'TestChannel', enabled: true });
		expect(channels[1]).toEqual({ id: 1001, name: 'AnotherChannel', enabled: true });
	});

	it('returns empty array when no categories', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				text: () => Promise.resolve('<caps></caps>')
			})
		);

		const channels = await fetchChannels('testkey');
		expect(channels).toEqual([]);
	});

	it('throws on non-ok response', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({ ok: false, status: 500 })
		);

		await expect(fetchChannels('testkey')).rejects.toThrow('Failed to fetch caps: 500');
	});

	it('handles single category (not array)', async () => {
		const capsXml = `<?xml version="1.0"?>
<caps>
  <categories>
    <category id="1000" name="OnlyChannel"/>
  </categories>
</caps>`;

		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				text: () => Promise.resolve(capsXml)
			})
		);

		const channels = await fetchChannels('testkey');
		expect(channels).toHaveLength(1);
		expect(channels[0].name).toBe('OnlyChannel');
	});
});

// --- search ---

describe('search', () => {
	it('parses search results from RSS XML', async () => {
		const rssXml = `<?xml version="1.0"?>
<rss>
  <channel>
    <response total="2" offset="0"/>
    <item>
      <title>Show S01E01</title>
      <guid>-100:123</guid>
      <link>https://t.me/channel/123</link>
      <pubDate>2024-01-15</pubDate>
      <size>1073741824</size>
      <description>A great episode</description>
      <attr name="category" value="1000"/>
      <enclosure url="http://localhost/api/download?id=-100:123"/>
    </item>
  </channel>
</rss>`;

		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				text: () => Promise.resolve(rssXml)
			})
		);

		const result = await search({ query: 'Show', apiKey: 'key' });
		expect(result.total).toBe(2);
		expect(result.offset).toBe(0);
		expect(result.items).toHaveLength(1);
		expect(result.items[0].title).toBe('Show S01E01');
		expect(result.items[0].guid).toBe('-100:123');
		expect(result.items[0].categoryId).toBe(1000);
	});

	it('returns empty result when no channel in response', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				text: () => Promise.resolve('<rss></rss>')
			})
		);

		const result = await search({ query: 'test', apiKey: 'key' });
		expect(result).toEqual({ total: 0, offset: 0, items: [] });
	});

	it('throws on torznab error in XML', async () => {
		const errorXml = `<?xml version="1.0"?><error code="100" description="Incorrect API key"/>`;

		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				text: () => Promise.resolve(errorXml)
			})
		);

		await expect(search({ query: 'test', apiKey: 'bad' })).rejects.toThrow('Incorrect API key');
	});

	it('throws on non-ok response', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({ ok: false, status: 403 })
		);

		await expect(search({ query: 'test', apiKey: 'key' })).rejects.toThrow('Search failed: 403');
	});

	it('builds URL with optional params', async () => {
		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			text: () => Promise.resolve('<rss><channel><response total="0" offset="0"/></channel></rss>')
		});
		vi.stubGlobal('fetch', mockFetch);

		await search({
			query: 'test',
			apiKey: 'key',
			cat: '1000,1001',
			offset: 10,
			limit: 50,
			season: '2',
			ep: '3'
		});

		const calledUrl = mockFetch.mock.calls[0][0];
		expect(calledUrl).toContain('t=search');
		expect(calledUrl).toContain('apikey=key');
		expect(calledUrl).toContain('q=test');
		expect(calledUrl).toContain('cat=1000%2C1001');
		expect(calledUrl).toContain('offset=10');
		expect(calledUrl).toContain('limit=50');
		expect(calledUrl).toContain('season=2');
		expect(calledUrl).toContain('ep=3');
	});

	it('filters out standard Newznab categories from results', async () => {
		const rssXml = `<?xml version="1.0"?>
<rss>
  <channel>
    <response total="1" offset="0"/>
    <item>
      <title>Show</title>
      <guid>-100:1</guid>
      <link/>
      <pubDate/>
      <size>100</size>
      <description/>
      <attr name="category" value="5000"/>
      <attr name="category" value="1000"/>
    </item>
  </channel>
</rss>`;

		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				text: () => Promise.resolve(rssXml)
			})
		);

		const result = await search({ query: 'test', apiKey: 'key' });
		// Should pick the non-standard category (1000), not the standard one (5000)
		expect(result.items[0].categoryId).toBe(1000);
	});

	it('returns empty items when no item in channel', async () => {
		const rssXml = `<?xml version="1.0"?>
<rss>
  <channel>
    <response total="0" offset="0"/>
  </channel>
</rss>`;

		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				text: () => Promise.resolve(rssXml)
			})
		);

		const result = await search({ query: 'test', apiKey: 'key' });
		expect(result.items).toEqual([]);
	});
});

// --- Transmission RPC ---

describe('RPC functions', () => {
	function mockRpcFetch(responseArgs: any, method?: string) {
		let callCount = 0;
		return vi.fn().mockImplementation(async (_url: string, opts?: any) => {
			callCount++;
			// First call might return 409 to get session ID
			if (callCount === 1) {
				return {
					ok: false,
					status: 409,
					headers: new Headers({ 'X-Transmission-Session-Id': 'test-session' })
				};
			}
			return {
				ok: true,
				json: () => Promise.resolve({ result: 'success', arguments: responseArgs })
			};
		});
	}

	it('getDownloads handles 409 and retries with session ID', async () => {
		const torrents = [{ id: 1, name: 'test.mkv', status: 4 }];
		const mockFetch = mockRpcFetch({ torrents });
		vi.stubGlobal('fetch', mockFetch);

		const result = await getDownloads('apikey');
		expect(result).toEqual(torrents);
		expect(mockFetch).toHaveBeenCalledTimes(2);

		// Second call should have the session ID
		const secondCallHeaders = mockFetch.mock.calls[1][1].headers;
		expect(secondCallHeaders['X-Transmission-Session-Id']).toBe('test-session');
	});

	it('getDownloads returns empty array when no torrents', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				json: () => Promise.resolve({ result: 'success', arguments: {} })
			})
		);

		const result = await getDownloads('apikey');
		expect(result).toEqual([]);
	});

	it('addDownload fetches torrent then calls torrent-add', async () => {
		let callIndex = 0;
		vi.stubGlobal(
			'fetch',
			vi.fn().mockImplementation(async (url: string) => {
				callIndex++;
				if (callIndex === 1) {
					// First call: download torrent file
					return {
						ok: true,
						arrayBuffer: () => Promise.resolve(new Uint8Array([100, 52, 58]).buffer)
					};
				}
				// Second call: RPC torrent-add
				return {
					ok: true,
					json: () =>
						Promise.resolve({
							result: 'success',
							arguments: { 'torrent-added': { id: 1 } }
						})
				};
			})
		);

		const result = await addDownload('apikey', '-100:123');
		expect(result).toEqual({ 'torrent-added': { id: 1 } });
	});

	it('addDownload throws on failed torrent fetch', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({ ok: false, status: 404 })
		);

		await expect(addDownload('apikey', '-100:123')).rejects.toThrow(
			'Failed to fetch torrent: 404'
		);
	});

	it('removeDownload calls torrent-remove with correct args', async () => {
		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ result: 'success', arguments: {} })
		});
		vi.stubGlobal('fetch', mockFetch);

		await removeDownload('apikey', 5, true);

		const body = JSON.parse(mockFetch.mock.calls[0][1].body);
		expect(body.method).toBe('torrent-remove');
		expect(body.arguments.ids).toEqual([5]);
		expect(body.arguments['delete-local-data']).toBe(true);
	});

	it('pauseDownload calls torrent-stop', async () => {
		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ result: 'success', arguments: {} })
		});
		vi.stubGlobal('fetch', mockFetch);

		await pauseDownload('apikey', 3);

		const body = JSON.parse(mockFetch.mock.calls[0][1].body);
		expect(body.method).toBe('torrent-stop');
		expect(body.arguments.ids).toEqual([3]);
	});

	it('resumeDownload calls torrent-start', async () => {
		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ result: 'success', arguments: {} })
		});
		vi.stubGlobal('fetch', mockFetch);

		await resumeDownload('apikey', 7);

		const body = JSON.parse(mockFetch.mock.calls[0][1].body);
		expect(body.method).toBe('torrent-start');
		expect(body.arguments.ids).toEqual([7]);
	});

	it('RPC throws on non-success result', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				json: () => Promise.resolve({ result: 'no such method' })
			})
		);

		await expect(getSessionStats('apikey')).rejects.toThrow('no such method');
	});

	it('RPC throws on HTTP error', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({ ok: false, status: 401 })
		);

		await expect(getSessionStats('apikey')).rejects.toThrow('RPC error: 401');
	});
});

// --- getFileUrl ---

describe('getFileUrl', () => {
	it('constructs correct URL', () => {
		const url = getFileUrl('my-key', 42);
		expect(url).toBe('/transmission/files/42?apikey=my-key');
	});

	it('encodes special characters in apikey', () => {
		const url = getFileUrl('key with spaces', 1);
		expect(url).toContain('apikey=key%20with%20spaces');
	});
});

// --- getSessionStats ---

describe('getSessionStats', () => {
	it('returns session stats from RPC', async () => {
		const stats = {
			activeTorrentCount: 3,
			pausedTorrentCount: 1,
			torrentCount: 4,
			downloadSpeed: 1024,
			uploadSpeed: 0
		};

		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				json: () => Promise.resolve({ result: 'success', arguments: stats })
			})
		);

		const result = await getSessionStats('apikey');
		expect(result).toEqual(stats);
	});
});

// --- testConnection ---

describe('testConnection', () => {
	it('returns true when health endpoint responds ok', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				json: () => Promise.resolve({ status: 'ok' })
			})
		);

		expect(await testConnection()).toBe(true);
	});

	it('returns false on non-ok response', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({ ok: false, status: 500 })
		);

		expect(await testConnection()).toBe(false);
	});

	it('returns false on wrong status', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				json: () => Promise.resolve({ status: 'error' })
			})
		);

		expect(await testConnection()).toBe(false);
	});

	it('returns false on network error', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockRejectedValue(new Error('Network error'))
		);

		expect(await testConnection()).toBe(false);
	});
});

// --- connectDownloadsWS ---

describe('connectDownloadsWS', () => {
	it('creates WebSocket and calls onMessage with download data', () => {
		const onMessage = vi.fn();
		let wsInstance: any;

		vi.stubGlobal(
			'WebSocket',
			class {
				url: string;
				onmessage: any;
				onclose: any;
				onerror: any;
				close = vi.fn();
				constructor(url: string) {
					this.url = url;
					wsInstance = this;
				}
			}
		);

		const cleanup = connectDownloadsWS('testkey', onMessage);

		// Simulate message
		wsInstance.onmessage({
			data: JSON.stringify({ type: 'downloads', downloads: [{ id: 1 }] })
		});

		expect(onMessage).toHaveBeenCalledWith([{ id: 1 }]);

		cleanup();
	});

	it('ignores non-downloads messages', () => {
		const onMessage = vi.fn();
		let wsInstance: any;

		vi.stubGlobal(
			'WebSocket',
			class {
				url: string;
				onmessage: any;
				onclose: any;
				onerror: any;
				close = vi.fn();
				constructor(url: string) {
					this.url = url;
					wsInstance = this;
				}
			}
		);

		connectDownloadsWS('testkey', onMessage);
		wsInstance.onmessage({ data: JSON.stringify({ type: 'other' }) });

		expect(onMessage).not.toHaveBeenCalled();
	});

	it('ignores malformed JSON messages', () => {
		const onMessage = vi.fn();
		let wsInstance: any;

		vi.stubGlobal(
			'WebSocket',
			class {
				url: string;
				onmessage: any;
				onclose: any;
				onerror: any;
				close = vi.fn();
				constructor(url: string) {
					this.url = url;
					wsInstance = this;
				}
			}
		);

		connectDownloadsWS('testkey', onMessage);
		wsInstance.onmessage({ data: 'not json' });

		expect(onMessage).not.toHaveBeenCalled();
	});

	it('calls onError and closes on WebSocket error', () => {
		const onMessage = vi.fn();
		const onError = vi.fn();
		let wsInstance: any;

		vi.stubGlobal(
			'WebSocket',
			class {
				url: string;
				onmessage: any;
				onclose: any;
				onerror: any;
				close = vi.fn();
				constructor(url: string) {
					this.url = url;
					wsInstance = this;
				}
			}
		);

		connectDownloadsWS('testkey', onMessage, onError);
		wsInstance.onerror();

		expect(onError).toHaveBeenCalled();
		expect(wsInstance.close).toHaveBeenCalled();
	});

	it('cleanup closes WebSocket and prevents reconnect', () => {
		let wsInstance: any;

		vi.stubGlobal(
			'WebSocket',
			class {
				url: string;
				onmessage: any;
				onclose: any;
				onerror: any;
				close = vi.fn();
				constructor(url: string) {
					this.url = url;
					wsInstance = this;
				}
			}
		);

		const cleanup = connectDownloadsWS('testkey', vi.fn());
		cleanup();

		expect(wsInstance.close).toHaveBeenCalled();
	});

	it('builds correct WebSocket URL with apikey', () => {
		let capturedUrl = '';

		vi.stubGlobal(
			'WebSocket',
			class {
				onmessage: any;
				onclose: any;
				onerror: any;
				close = vi.fn();
				constructor(url: string) {
					capturedUrl = url;
				}
			}
		);

		connectDownloadsWS('my-key', vi.fn());
		expect(capturedUrl).toContain('/ws/downloads?apikey=my-key');
	});
});
