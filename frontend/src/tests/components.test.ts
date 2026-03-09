import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import ProgressBar from '$lib/components/ProgressBar.svelte';
import SearchResultCard from '$lib/components/SearchResultCard.svelte';
import DownloadRow from '$lib/components/DownloadRow.svelte';
import Navbar from '$lib/components/Navbar.svelte';
import ThemeToggle from '$lib/components/ThemeToggle.svelte';
import type { Download, SearchResult } from '$lib/types';
import { TR_STATUS } from '$lib/types';

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

// --- ProgressBar ---

describe('ProgressBar', () => {
	it('renders with correct width percentage', () => {
		const { container } = render(ProgressBar, { props: { percent: 0.5 } });
		const bar = container.querySelector('[style]') as HTMLElement;
		expect(bar.style.width).toBe('50%');
	});

	it('renders 0% for percent=0', () => {
		const { container } = render(ProgressBar, { props: { percent: 0 } });
		const bar = container.querySelector('[style]') as HTMLElement;
		expect(bar.style.width).toBe('0%');
	});

	it('renders 100% for percent=1', () => {
		const { container } = render(ProgressBar, { props: { percent: 1 } });
		const bar = container.querySelector('[style]') as HTMLElement;
		expect(bar.style.width).toBe('100%');
	});

	it('clamps to 100% for values > 1', () => {
		const { container } = render(ProgressBar, { props: { percent: 1.5 } });
		const bar = container.querySelector('[style]') as HTMLElement;
		expect(bar.style.width).toBe('100%');
	});

	it('clamps to 0% for negative values', () => {
		const { container } = render(ProgressBar, { props: { percent: -0.5 } });
		const bar = container.querySelector('[style]') as HTMLElement;
		expect(bar.style.width).toBe('0%');
	});

	it('applies animated class when animated prop is true', () => {
		const { container } = render(ProgressBar, {
			props: { percent: 0.5, animated: true }
		});
		const bar = container.querySelector('[style]') as HTMLElement;
		expect(bar.classList.contains('animate-pulse')).toBe(true);
	});

	it('does not apply animated class by default', () => {
		const { container } = render(ProgressBar, { props: { percent: 0.5 } });
		const bar = container.querySelector('[style]') as HTMLElement;
		expect(bar.classList.contains('animate-pulse')).toBe(false);
	});

	it('applies custom color class', () => {
		const { container } = render(ProgressBar, {
			props: { percent: 0.5, color: 'bg-(--color-success)' }
		});
		const bar = container.querySelector('[style]') as HTMLElement;
		expect(bar.className).toContain('bg-(--color-success)');
	});
});

// --- Helper factories ---

function makeSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
	return {
		title: 'Test Show S01E01',
		guid: '-100:123',
		link: 'https://t.me/channel/123',
		pubDate: '2024-03-15T10:00:00Z',
		size: 1073741824,
		description: 'A test episode',
		categoryId: 1000,
		downloadUrl: 'http://localhost/api/download?id=-100:123',
		...overrides
	};
}

function makeDownload(overrides: Partial<Download> = {}): Download {
	return {
		id: 1,
		name: 'test-file.mkv',
		status: TR_STATUS.DOWNLOAD,
		percentDone: 0.5,
		totalSize: 1073741824,
		downloadedEver: 536870912,
		rateDownload: 1048576,
		eta: 300,
		error: 0,
		errorString: '',
		isFinished: false,
		doneDate: 0,
		...overrides
	};
}

// --- SearchResultCard ---

describe('SearchResultCard', () => {
	it('renders title and size', () => {
		render(SearchResultCard, {
			props: { result: makeSearchResult() }
		});

		expect(screen.getByText('Test Show S01E01')).toBeInTheDocument();
		expect(screen.getByText('1.0 GB')).toBeInTheDocument();
	});

	it('renders description when present', () => {
		render(SearchResultCard, {
			props: { result: makeSearchResult({ description: 'My description' }) }
		});

		expect(screen.getByText('My description')).toBeInTheDocument();
	});

	it('does not render description when empty', () => {
		const { container } = render(SearchResultCard, {
			props: { result: makeSearchResult({ description: '' }) }
		});

		const descP = container.querySelector('.line-clamp-2');
		expect(descP).toBeNull();
	});

	it('renders channel name when provided', () => {
		render(SearchResultCard, {
			props: { result: makeSearchResult(), channelName: 'MyChannel' }
		});

		expect(screen.getByText('MyChannel')).toBeInTheDocument();
	});

	it('does not render channel name when not provided', () => {
		const { container } = render(SearchResultCard, {
			props: { result: makeSearchResult() }
		});

		// No channel badge
		const badges = container.querySelectorAll('[class*="text-(--color-primary)"]');
		// The only primary-colored text should not be a channel badge
		const channelBadge = Array.from(badges).find(
			(el) => el.textContent?.trim() && !el.textContent.includes('Telegram')
		);
		expect(channelBadge).toBeUndefined();
	});

	it('renders Telegram link when link is present', () => {
		render(SearchResultCard, {
			props: { result: makeSearchResult({ link: 'https://t.me/test/1' }) }
		});

		const link = screen.getByText('Telegram');
		expect(link).toBeInTheDocument();
		expect(link.getAttribute('href')).toBe('https://t.me/test/1');
		expect(link.getAttribute('target')).toBe('_blank');
	});

	it('does not render Telegram link when link is empty', () => {
		render(SearchResultCard, {
			props: { result: makeSearchResult({ link: '' }) }
		});

		expect(screen.queryByText('Telegram')).toBeNull();
	});

	it('shows "Descargar" button initially', () => {
		render(SearchResultCard, {
			props: { result: makeSearchResult() }
		});

		expect(screen.getByText('Descargar')).toBeInTheDocument();
	});

	it('shows "Enviando..." while downloading', async () => {
		// Mock fetch to never resolve (keep pending)
		vi.stubGlobal(
			'fetch',
			vi.fn().mockReturnValue(new Promise(() => {}))
		);

		render(SearchResultCard, {
			props: { result: makeSearchResult() }
		});

		const btn = screen.getByText('Descargar');
		await fireEvent.click(btn);

		expect(screen.getByText('Enviando...')).toBeInTheDocument();
	});

	it('shows "Enviado" after successful download', async () => {
		// Mock: first call = torrent file, second call = RPC response
		let callIndex = 0;
		vi.stubGlobal(
			'fetch',
			vi.fn().mockImplementation(async () => {
				callIndex++;
				if (callIndex === 1) {
					return {
						ok: true,
						arrayBuffer: () => Promise.resolve(new Uint8Array([100]).buffer)
					};
				}
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

		render(SearchResultCard, {
			props: { result: makeSearchResult() }
		});

		const btn = screen.getByText('Descargar');
		await fireEvent.click(btn);

		// Wait for async completion
		await vi.waitFor(() => {
			expect(screen.getByText('Enviado')).toBeInTheDocument();
		});
	});

	it('shows error message on download failure', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({ ok: false, status: 500 })
		);

		render(SearchResultCard, {
			props: { result: makeSearchResult() }
		});

		const btn = screen.getByText('Descargar');
		await fireEvent.click(btn);

		await vi.waitFor(() => {
			expect(screen.getByText('Failed to fetch torrent: 500')).toBeInTheDocument();
		});
	});

	it('formats date in result', () => {
		render(SearchResultCard, {
			props: { result: makeSearchResult({ pubDate: '2024-03-15T10:00:00Z' }) }
		});

		// Should contain "15" and "2024" in Spanish locale format
		const dateText = screen.getByText(/15/);
		expect(dateText).toBeInTheDocument();
	});
});

// --- DownloadRow ---

describe('DownloadRow', () => {
	const onRemoved = vi.fn();

	beforeEach(() => {
		onRemoved.mockClear();
	});

	it('renders download name and size', () => {
		render(DownloadRow, {
			props: { download: makeDownload(), onRemoved }
		});

		expect(screen.getByText('test-file.mkv')).toBeInTheDocument();
		expect(screen.getByText('1.0 GB')).toBeInTheDocument();
	});

	it('shows "Descargando" for active downloads', () => {
		render(DownloadRow, {
			props: { download: makeDownload({ status: TR_STATUS.DOWNLOAD }), onRemoved }
		});

		expect(screen.getByText('Descargando')).toBeInTheDocument();
	});

	it('shows "Completo" for seeding status', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ status: TR_STATUS.SEED, percentDone: 1, isFinished: true }),
				onRemoved
			}
		});

		expect(screen.getByText('Completo')).toBeInTheDocument();
	});

	it('shows "Completo" for stopped + finished', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ status: TR_STATUS.STOPPED, isFinished: true, percentDone: 1 }),
				onRemoved
			}
		});

		expect(screen.getByText('Completo')).toBeInTheDocument();
	});

	it('shows "Detenido" for stopped + not finished', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ status: TR_STATUS.STOPPED, isFinished: false }),
				onRemoved
			}
		});

		expect(screen.getByText('Detenido')).toBeInTheDocument();
	});

	it('shows "En cola" for download wait', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ status: TR_STATUS.DOWNLOAD_WAIT }),
				onRemoved
			}
		});

		expect(screen.getByText('En cola')).toBeInTheDocument();
	});

	it('shows "Verificando" for check status', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ status: TR_STATUS.CHECK }),
				onRemoved
			}
		});

		expect(screen.getByText('Verificando')).toBeInTheDocument();
	});

	it('shows "Error" and error string when download has error', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ error: 3, errorString: 'Connection refused' }),
				onRemoved
			}
		});

		expect(screen.getByText('Error')).toBeInTheDocument();
		expect(screen.getByText('Connection refused')).toBeInTheDocument();
	});

	it('shows speed and ETA for active downloads', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({
					status: TR_STATUS.DOWNLOAD,
					rateDownload: 1048576,
					eta: 300
				}),
				onRemoved
			}
		});

		expect(screen.getByText('1.0 MB/s')).toBeInTheDocument();
		expect(screen.getByText('ETA: 5m')).toBeInTheDocument();
	});

	it('does not show speed/ETA for non-active downloads', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ status: TR_STATUS.STOPPED, isFinished: true }),
				onRemoved
			}
		});

		expect(screen.queryByText(/MB\/s/)).toBeNull();
		expect(screen.queryByText(/ETA:/)).toBeNull();
	});

	it('shows percentage', () => {
		render(DownloadRow, {
			props: { download: makeDownload({ percentDone: 0.753 }), onRemoved }
		});

		expect(screen.getByText('75.3%')).toBeInTheDocument();
	});

	it('shows pause button for active downloads', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ status: TR_STATUS.DOWNLOAD }),
				onRemoved
			}
		});

		expect(screen.getByTitle('Pausar')).toBeInTheDocument();
	});

	it('shows resume button for stopped (not finished) downloads', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({ status: TR_STATUS.STOPPED, isFinished: false }),
				onRemoved
			}
		});

		expect(screen.getByTitle('Reanudar')).toBeInTheDocument();
	});

	it('shows download file link for completed downloads', () => {
		render(DownloadRow, {
			props: {
				download: makeDownload({
					status: TR_STATUS.SEED,
					isFinished: true,
					percentDone: 1
				}),
				onRemoved
			}
		});

		expect(screen.getByTitle('Descargar archivo')).toBeInTheDocument();
	});

	it('shows delete button', () => {
		render(DownloadRow, {
			props: { download: makeDownload(), onRemoved }
		});

		expect(screen.getByTitle('Eliminar')).toBeInTheDocument();
	});

	it('shows confirm dialog on delete click', async () => {
		render(DownloadRow, {
			props: { download: makeDownload(), onRemoved }
		});

		const deleteBtn = screen.getByTitle('Eliminar');
		await fireEvent.click(deleteBtn);

		expect(screen.getByText('Solo quitar')).toBeInTheDocument();
		expect(screen.getByText('+ Borrar archivo')).toBeInTheDocument();
		expect(screen.getByText('Cancelar')).toBeInTheDocument();
	});

	it('hides confirm dialog on cancel', async () => {
		render(DownloadRow, {
			props: { download: makeDownload(), onRemoved }
		});

		const deleteBtn = screen.getByTitle('Eliminar');
		await fireEvent.click(deleteBtn);

		const cancelBtn = screen.getByText('Cancelar');
		await fireEvent.click(cancelBtn);

		// Confirm buttons should be gone
		expect(screen.queryByText('Solo quitar')).toBeNull();
		expect(screen.getByTitle('Eliminar')).toBeInTheDocument();
	});

	it('"Solo quitar" calls removeDownload without deleteData', async () => {
		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ result: 'success', arguments: {} })
		});
		vi.stubGlobal('fetch', mockFetch);

		render(DownloadRow, {
			props: { download: makeDownload({ id: 42 }), onRemoved }
		});

		await fireEvent.click(screen.getByTitle('Eliminar'));
		await fireEvent.click(screen.getByText('Solo quitar'));

		await vi.waitFor(() => {
			expect(onRemoved).toHaveBeenCalled();
		});

		// Verify the RPC call body
		const body = JSON.parse(mockFetch.mock.calls[0][1].body);
		expect(body.method).toBe('torrent-remove');
		expect(body.arguments['delete-local-data']).toBe(false);
	});

	it('"+ Borrar archivo" calls removeDownload with deleteData', async () => {
		const mockFetch = vi.fn().mockResolvedValue({
			ok: true,
			json: () => Promise.resolve({ result: 'success', arguments: {} })
		});
		vi.stubGlobal('fetch', mockFetch);

		render(DownloadRow, {
			props: { download: makeDownload({ id: 42 }), onRemoved }
		});

		await fireEvent.click(screen.getByTitle('Eliminar'));
		await fireEvent.click(screen.getByText('+ Borrar archivo'));

		await vi.waitFor(() => {
			expect(onRemoved).toHaveBeenCalled();
		});

		const body = JSON.parse(mockFetch.mock.calls[0][1].body);
		expect(body.arguments['delete-local-data']).toBe(true);
	});
});

// --- Navbar ---

describe('Navbar', () => {
	it('renders app title', () => {
		render(Navbar);
		expect(screen.getByText('Telegram Search & Download')).toBeInTheDocument();
	});

	it('renders desktop navigation links', () => {
		render(Navbar);
		// Mobile menu is hidden (menuOpen = false), so only desktop links render
		expect(screen.getByText('Dashboard')).toBeInTheDocument();
		expect(screen.getByText('Canales')).toBeInTheDocument();
		expect(screen.getByText('Buscar')).toBeInTheDocument();
		expect(screen.getByText('Descargas')).toBeInTheDocument();
		expect(screen.getByText('Config')).toBeInTheDocument();
	});

	it('shows API key warning when not configured', () => {
		render(Navbar);
		expect(screen.getByText(/API key no configurada/)).toBeInTheDocument();
		expect(screen.getByText('Configurar')).toBeInTheDocument();
	});

	it('hides API key warning when configured', async () => {
		storage['apiKey'] = 'configured-key';
		const { settings } = await import('$lib/stores.svelte');
		settings.load();

		render(Navbar);
		expect(screen.queryByText(/API key no configurada/)).toBeNull();
	});
});

// --- ThemeToggle ---

describe('ThemeToggle', () => {
	it('renders a button', () => {
		render(ThemeToggle);
		// ThemeToggle is rendered inside Navbar too, so multiple buttons may exist
		const buttons = screen.getAllByRole('button');
		expect(buttons.length).toBeGreaterThan(0);
	});

	it('shows "Modo oscuro" title in light mode', async () => {
		const { theme } = await import('$lib/stores.svelte');
		theme.dark = false;

		render(ThemeToggle);
		expect(screen.getByTitle('Modo oscuro')).toBeInTheDocument();
	});

	it('shows "Modo claro" title in dark mode', async () => {
		const { theme } = await import('$lib/stores.svelte');
		theme.dark = true;

		render(ThemeToggle);
		expect(screen.getByTitle('Modo claro')).toBeInTheDocument();
	});

	it('toggles theme on click', async () => {
		const { theme } = await import('$lib/stores.svelte');
		theme.dark = false;

		render(ThemeToggle);
		const button = screen.getByTitle('Modo oscuro');
		await fireEvent.click(button);

		expect(theme.dark).toBe(true);
	});
});
