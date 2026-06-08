export interface Channel {
	id: number;
	chatId?: number;
	name: string;
	username?: string;
	enabled: boolean;
}

export interface ChannelInfo {
	id: number;
	title: string;
	username?: string | null;
	participants_count?: number | null;
	description?: string | null;
}

export interface ChannelMessage {
	message_id: number;
	topic_id?: number | null;
	telegram_url: string;
	sender_name?: string | null;
	date: string | null;
	filename: string | null;
	file_size: number | null;
	mime_type: string | null;
	downloadable: boolean;
	media_group_id: string | null;
	text?: string | null;
	caption?: string | null;
	body?: string | null;
	thumbnail_url?: string | null;
}

export interface ChannelMessagesResponse {
	messages: ChannelMessage[];
	has_older: boolean;
	older_cursor: number | null;
	has_newer: boolean;
	newer_cursor: number | null;
	topic_id?: number | null;
	channel: ChannelInfo;
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

export interface Destination {
	id: string;
	name: string;
	path: string;
	created_at: string;
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
	downloadDir?: string;
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
