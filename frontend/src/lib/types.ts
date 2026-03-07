export interface Channel {
	id: number;
	name: string;
	username?: string;
	enabled: boolean;
}

export interface SearchResult {
	title: string;
	guid: string;
	link: string;
	pubDate: string;
	size: number;
	description: string;
	categoryId: number;
	downloadUrl: string;
}

export interface SearchResponse {
	total: number;
	offset: number;
	items: SearchResult[];
}

export interface Download {
	id: number;
	name: string;
	status: number;
	percentDone: number;
	totalSize: number;
	downloadedEver: number;
	rateDownload: number;
	eta: number;
	error: number;
	errorString: string;
	isFinished: boolean;
	doneDate: number;
}

export interface SessionStats {
	activeTorrentCount: number;
	pausedTorrentCount: number;
	torrentCount: number;
	downloadSpeed: number;
	uploadSpeed: number;
}

export interface AppSettings {
	apiKey: string;
	backendUrl: string;
}

// Transmission status constants
export const TR_STATUS = {
	STOPPED: 0,
	CHECK_WAIT: 1,
	CHECK: 2,
	DOWNLOAD_WAIT: 3,
	DOWNLOAD: 4,
	SEED_WAIT: 5,
	SEED: 6
} as const;
