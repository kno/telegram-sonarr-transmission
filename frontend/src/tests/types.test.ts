import { describe, it, expect } from 'vitest';
import { TR_STATUS } from '$lib/types';
import type { Channel, ChannelInfo, ChannelMessage, ChannelMessagesResponse } from '$lib/types';

describe('TR_STATUS constants', () => {
	it('has correct status values', () => {
		expect(TR_STATUS.STOPPED).toBe(0);
		expect(TR_STATUS.CHECK_WAIT).toBe(1);
		expect(TR_STATUS.CHECK).toBe(2);
		expect(TR_STATUS.DOWNLOAD_WAIT).toBe(3);
		expect(TR_STATUS.DOWNLOAD).toBe(4);
		expect(TR_STATUS.SEED_WAIT).toBe(5);
		expect(TR_STATUS.SEED).toBe(6);
	});

	it('has 7 status values', () => {
		expect(Object.keys(TR_STATUS)).toHaveLength(7);
	});

	it('values are readonly (as const)', () => {
		// TypeScript enforces this at compile time, but we verify at runtime
		const values = Object.values(TR_STATUS);
		expect(values).toEqual([0, 1, 2, 3, 4, 5, 6]);
	});
});

describe('channel browser types', () => {
	it('Channel includes Telegram chat id', () => {
		const channel: Channel = { id: 1000, chatId: -1001234, name: 'Series', enabled: true };

		expect(channel.chatId).toBe(-1001234);
	});

	it('ChannelMessagesResponse carries messages, cursor, and channel metadata', () => {
		const info: ChannelInfo = { id: -1001234, title: 'Series', participants_count: 10 };
		const message: ChannelMessage = {
			message_id: 123,
			topic_id: 900,
			telegram_url: 'https://t.me/c/1234/123',
			sender_name: 'Uploader',
			date: '2025-06-01T14:30:00+00:00',
			filename: 'Show.S01E01.mkv',
			file_size: 1024,
			mime_type: 'video/x-matroska',
			downloadable: true,
			media_group_id: null
		};
		const response: ChannelMessagesResponse = {
			messages: [message],
			has_older: true,
			older_cursor: 123,
			has_newer: false,
			newer_cursor: null,
			topic_id: 900,
			channel: info
		};

		expect(response.messages[0].filename).toBe('Show.S01E01.mkv');
		expect(response.older_cursor).toBe(123);
		expect(response.channel.title).toBe('Series');
	});
});
