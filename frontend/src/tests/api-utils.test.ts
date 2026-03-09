import { describe, it, expect } from 'vitest';
import { formatSize, formatSpeed, formatEta, formatDate } from '$lib/api';

describe('formatSize', () => {
	it('returns "0 B" for zero', () => {
		expect(formatSize(0)).toBe('0 B');
	});

	it('formats bytes', () => {
		expect(formatSize(500)).toBe('500 B');
	});

	it('formats kilobytes', () => {
		expect(formatSize(1024)).toBe('1.0 KB');
		expect(formatSize(1536)).toBe('1.5 KB');
	});

	it('formats megabytes', () => {
		expect(formatSize(1048576)).toBe('1.0 MB');
		expect(formatSize(10 * 1024 * 1024)).toBe('10.0 MB');
	});

	it('formats gigabytes', () => {
		expect(formatSize(1073741824)).toBe('1.0 GB');
		expect(formatSize(2.5 * 1024 * 1024 * 1024)).toBe('2.5 GB');
	});

	it('formats terabytes', () => {
		expect(formatSize(1024 ** 4)).toBe('1.0 TB');
	});
});

describe('formatSpeed', () => {
	it('appends /s to formatted size', () => {
		expect(formatSpeed(0)).toBe('0 B/s');
		expect(formatSpeed(1024)).toBe('1.0 KB/s');
		expect(formatSpeed(5 * 1024 * 1024)).toBe('5.0 MB/s');
	});
});

describe('formatEta', () => {
	it('returns -- for negative values', () => {
		expect(formatEta(-1)).toBe('--');
		expect(formatEta(-100)).toBe('--');
	});

	it('formats seconds', () => {
		expect(formatEta(0)).toBe('0s');
		expect(formatEta(30)).toBe('30s');
		expect(formatEta(59)).toBe('59s');
	});

	it('formats minutes', () => {
		expect(formatEta(60)).toBe('1m');
		expect(formatEta(150)).toBe('2m');
		expect(formatEta(3599)).toBe('59m');
	});

	it('formats hours and minutes', () => {
		expect(formatEta(3600)).toBe('1h 0m');
		expect(formatEta(3660)).toBe('1h 1m');
		expect(formatEta(7200)).toBe('2h 0m');
		expect(formatEta(7380)).toBe('2h 3m');
	});
});

describe('formatDate', () => {
	it('formats a valid date string in Spanish locale', () => {
		const result = formatDate('2024-03-15T10:00:00Z');
		// Spanish locale should produce something like "15 mar 2024"
		expect(result).toMatch(/15/);
		expect(result).toMatch(/2024/);
	});

	it('returns a string for invalid dates without crashing', () => {
		const result = formatDate('not-a-date');
		expect(typeof result).toBe('string');
	});

	it('handles ISO date strings', () => {
		const result = formatDate('2023-12-25T00:00:00Z');
		expect(result).toMatch(/2023/);
	});
});
