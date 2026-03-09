import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/search_result.dart';
import '../providers/settings_provider.dart';
import '../providers/channels_provider.dart';
import '../widgets/search_result_card.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _queryController = TextEditingController();
  final _seasonController = TextEditingController();
  final _episodeController = TextEditingController();

  SearchResponse? _results;
  bool _loading = false;
  String? _error;
  int _offset = 0;
  static const _limit = 50;

  Future<void> _search({int offset = 0}) async {
    final api = context.read<SettingsProvider>().apiService;
    if (api == null) return;

    final query = _queryController.text.trim();
    if (query.isEmpty) return;

    setState(() {
      _loading = true;
      _error = null;
      _offset = offset;
    });

    try {
      final channels = context.read<ChannelsProvider>().enabledIds;
      final channelsParam = channels.isNotEmpty ? channels.join(',') : null;

      final results = await api.search(
        query: query,
        channels: channelsParam,
        season: _seasonController.text.trim().isNotEmpty ? _seasonController.text.trim() : null,
        ep: _episodeController.text.trim().isNotEmpty ? _episodeController.text.trim() : null,
        offset: offset,
        limit: _limit,
      );
      setState(() => _results = results);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _queryController.dispose();
    _seasonController.dispose();
    _episodeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final enabledCount = context.watch<ChannelsProvider>().enabledIds.length;

    return Scaffold(
      appBar: AppBar(title: const Text('Buscar')),
      body: Column(
        children: [
          // Search form
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _queryController,
                  decoration: InputDecoration(
                    hintText: 'Buscar en Telegram...',
                    prefixIcon: const Icon(Icons.search),
                    border: const OutlineInputBorder(),
                    suffixIcon: IconButton(
                      icon: const Icon(Icons.clear),
                      onPressed: () {
                        _queryController.clear();
                        setState(() => _results = null);
                      },
                    ),
                  ),
                  textInputAction: TextInputAction.search,
                  onSubmitted: (_) => _search(),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _seasonController,
                        decoration: const InputDecoration(
                          hintText: 'Temporada',
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                        keyboardType: TextInputType.number,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextField(
                        controller: _episodeController,
                        decoration: const InputDecoration(
                          hintText: 'Episodio',
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                        keyboardType: TextInputType.number,
                      ),
                    ),
                    const SizedBox(width: 8),
                    FilledButton(
                      onPressed: _loading ? null : () => _search(),
                      child: _loading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Text('Buscar'),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  '$enabledCount canales habilitados',
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                ),
              ],
            ),
          ),

          // Results
          if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Card(
                color: theme.colorScheme.errorContainer,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(_error!, style: TextStyle(color: theme.colorScheme.onErrorContainer)),
                ),
              ),
            ),

          if (_results != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                '${_results!.total} resultados',
                style: theme.textTheme.bodySmall,
              ),
            ),

          Expanded(
            child: _results == null
                ? Center(
                    child: Text(
                      'Introduce un termino de busqueda',
                      style: theme.textTheme.bodyLarge?.copyWith(color: theme.colorScheme.outline),
                    ),
                  )
                : _results!.items.isEmpty
                    ? Center(
                        child: Text(
                          'Sin resultados',
                          style: theme.textTheme.bodyLarge?.copyWith(color: theme.colorScheme.outline),
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _results!.items.length,
                        itemBuilder: (context, index) {
                          return SearchResultCard(result: _results!.items[index]);
                        },
                      ),
          ),

          // Pagination
          if (_results != null && _results!.total > _limit)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  TextButton(
                    onPressed: _offset > 0 ? () => _search(offset: _offset - _limit) : null,
                    child: const Text('Anterior'),
                  ),
                  const SizedBox(width: 16),
                  Text('${(_offset ~/ _limit) + 1} / ${((_results!.total - 1) ~/ _limit) + 1}'),
                  const SizedBox(width: 16),
                  TextButton(
                    onPressed: _offset + _limit < _results!.total
                        ? () => _search(offset: _offset + _limit)
                        : null,
                    child: const Text('Siguiente'),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
