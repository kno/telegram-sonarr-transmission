import { XMLParser } from 'fast-xml-parser';
import type { Channel, SearchResult, SearchResponse, Download, SessionStats } from './types';

const xmlParser = new XMLParser({
	ignoreAttributes: false,
	attributeNamePrefix: '@_',
	removeNSPrefix: true
});

// --- Settings (localStorage) ---

export function getSettings() {
	if (typeof localStorage === 'undefined') return { apiKey: '', backendUrl: '' };
	return {
		apiKey: localStorage.getItem('apiKey') || '',
		backendUrl: localStorage.getItem('backendUrl') || ''
	};
}

export function saveSettings(apiKey: string, backendUrl: string) {
	localStorage.setItem('apiKey', apiKey);
	localStorage.setItem('backendUrl', backendUrl);
}

function getBaseUrl(): string {
	if (typeof localStorage !== 'undefined') {
		const url = localStorage.getItem('backendUrl');
		if (url) return url;
	}
	return '';
}

// --- Caps / Channels ---

export async function fetchChannels(apiKey: string): Promise<Channel[]> {
	const base = getBaseUrl();
	const res = await fetch(`${base}/api?t=caps`);
	if (!res.ok) throw new Error(`Failed to fetch caps: ${res.status}`);

	const xml = await res.text();
	const parsed = xmlParser.parse(xml);

	const categories = parsed?.caps?.categories?.category;
	if (!categories) return [];

	const cats = Array.isArray(categories) ? categories : [categories];
	return cats
		.filter((c: any) => parseInt(c['@_id']) >= 1000)
		.map((c: any) => ({
			id: parseInt(c['@_id']),
			name: c['@_name'],
			enabled: true
		}));
}

// --- Search ---

export async function search(params: {
	query: string;
	apiKey: string;
	cat?: string;
	offset?: number;
	limit?: number;
	season?: string;
	ep?: string;
}): Promise<SearchResponse> {
	const base = getBaseUrl();
	const url = new URL(`${base}/api`, window.location.origin);
	url.searchParams.set('t', 'search');
	url.searchParams.set('apikey', params.apiKey);
	if (params.query) url.searchParams.set('q', params.query);
	if (params.cat) url.searchParams.set('cat', params.cat);
	if (params.offset) url.searchParams.set('offset', String(params.offset));
	if (params.limit) url.searchParams.set('limit', String(params.limit));
	if (params.season) url.searchParams.set('season', params.season);
	if (params.ep) url.searchParams.set('ep', params.ep);

	const res = await fetch(url.toString());
	if (!res.ok) throw new Error(`Search failed: ${res.status}`);

	const xml = await res.text();
	const parsed = xmlParser.parse(xml);

	// Check for torznab error
	const error = parsed?.error;
	if (error) throw new Error(error['@_description'] || 'Search error');

	const channel = parsed?.rss?.channel;
	if (!channel) return { total: 0, offset: 0, items: [] };

	const response = channel['response'] || {};
	const total = parseInt(response['@_total'] || '0');
	const offset = parseInt(response['@_offset'] || '0');

	let rawItems = channel.item;
	if (!rawItems) return { total, offset, items: [] };
	if (!Array.isArray(rawItems)) rawItems = [rawItems];

	const items: SearchResult[] = rawItems.map((item: any) => {
		const attrs = item['attr'] || [];
		const attrList = Array.isArray(attrs) ? attrs : [attrs];
		// Standard Newznab categories (TV: 5000+, Movies: 2000+) — skip these
		const NEWZNAB_CATS = new Set([2000, 2030, 2040, 2045, 5000, 5030, 5040, 5045]);
		const catAttr = attrList.find(
			(a: any) =>
				a['@_name'] === 'category' &&
				!NEWZNAB_CATS.has(parseInt(a['@_value']))
		);

		return {
			title: item.title || '',
			guid: item.guid || '',
			link: item.link || '',
			pubDate: item.pubDate || '',
			size: parseInt(item.size || '0'),
			description: item.description || '',
			categoryId: catAttr ? parseInt(catAttr['@_value']) : 0,
			downloadUrl: item.enclosure?.['@_url'] || ''
		};
	});

	return { total, offset, items };
}

// --- Transmission RPC ---

let sessionId = '';

async function rpcCall(apiKey: string, method: string, args: any = {}): Promise<any> {
	const base = getBaseUrl();
	const url = `${base}/transmission/rpc`;
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		'X-Transmission-Session-Id': sessionId
	};
	if (apiKey) {
		headers['Authorization'] = 'Basic ' + btoa(':' + apiKey);
	}

	const body = JSON.stringify({ method, arguments: args });

	let res = await fetch(url, { method: 'POST', headers, body });

	if (res.status === 409) {
		sessionId = res.headers.get('X-Transmission-Session-Id') || '';
		headers['X-Transmission-Session-Id'] = sessionId;
		res = await fetch(url, { method: 'POST', headers, body });
	}

	if (!res.ok) throw new Error(`RPC error: ${res.status}`);

	const data = await res.json();
	if (data.result !== 'success') throw new Error(data.result || 'RPC failed');
	return data.arguments;
}

export async function getDownloads(apiKey: string): Promise<Download[]> {
	const args = await rpcCall(apiKey, 'torrent-get', {
		fields: [
			'id',
			'name',
			'status',
			'percentDone',
			'totalSize',
			'downloadedEver',
			'rateDownload',
			'eta',
			'error',
			'errorString',
			'isFinished',
			'doneDate'
		]
	});
	return args.torrents || [];
}

export async function addDownload(apiKey: string, guid: string): Promise<any> {
	const base = getBaseUrl();
	const dlUrl = `${base}/api/download?id=${encodeURIComponent(guid)}&apikey=${encodeURIComponent(apiKey)}`;
	const res = await fetch(dlUrl);
	if (!res.ok) throw new Error(`Failed to fetch torrent: ${res.status}`);

	const buffer = await res.arrayBuffer();
	const bytes = new Uint8Array(buffer);
	let binary = '';
	for (let i = 0; i < bytes.length; i++) {
		binary += String.fromCharCode(bytes[i]);
	}
	const metainfo = btoa(binary);

	return rpcCall(apiKey, 'torrent-add', { metainfo });
}

export async function removeDownload(
	apiKey: string,
	id: number,
	deleteData: boolean = false
): Promise<void> {
	await rpcCall(apiKey, 'torrent-remove', {
		ids: [id],
		'delete-local-data': deleteData
	});
}

export async function pauseDownload(apiKey: string, id: number): Promise<void> {
	await rpcCall(apiKey, 'torrent-stop', { ids: [id] });
}

export async function resumeDownload(apiKey: string, id: number): Promise<void> {
	await rpcCall(apiKey, 'torrent-start', { ids: [id] });
}

export function getFileUrl(apiKey: string, torrentId: number): string {
	const base = getBaseUrl();
	return `${base}/transmission/files/${torrentId}?apikey=${encodeURIComponent(apiKey)}`;
}

export async function getSessionStats(apiKey: string): Promise<SessionStats> {
	return rpcCall(apiKey, 'session-stats');
}

export async function testConnection(): Promise<boolean> {
	const base = getBaseUrl();
	try {
		const res = await fetch(`${base}/health`);
		if (!res.ok) return false;
		const data = await res.json();
		return data.status === 'ok';
	} catch {
		return false;
	}
}

// --- Utilities ---

export function formatSize(bytes: number): string {
	if (bytes === 0) return '0 B';
	const units = ['B', 'KB', 'MB', 'GB', 'TB'];
	const i = Math.floor(Math.log(bytes) / Math.log(1024));
	return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

export function formatSpeed(bytesPerSec: number): string {
	return formatSize(bytesPerSec) + '/s';
}

export function formatEta(seconds: number): string {
	if (seconds < 0) return '--';
	if (seconds < 60) return `${seconds}s`;
	if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	return `${h}h ${m}m`;
}

export function formatDate(dateStr: string): string {
	try {
		return new Date(dateStr).toLocaleDateString('es', {
			day: '2-digit',
			month: 'short',
			year: 'numeric'
		});
	} catch {
		return dateStr;
	}
}
