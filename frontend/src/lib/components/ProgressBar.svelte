<script lang="ts">
	let { percent, color = 'bg-(--color-primary)', animated = false }: {
		percent: number;
		color?: string;
		animated?: boolean;
	} = $props();

	const width = $derived(Math.min(100, Math.max(0, percent * 100)));
</script>

<div class="h-2.5 w-full overflow-hidden rounded-full bg-(--color-surface-hover)">
	<div
		class="h-full rounded-full transition-all duration-300 {color}"
		class:animate-pulse={animated}
		style="width: {width}%"
	></div>
</div>
