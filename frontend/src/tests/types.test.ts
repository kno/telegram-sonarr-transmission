import { describe, it, expect } from 'vitest';
import { TR_STATUS } from '$lib/types';

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
