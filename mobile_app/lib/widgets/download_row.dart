import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/download.dart';
import '../providers/settings_provider.dart';
import '../utils/formatters.dart';

class DownloadRow extends StatefulWidget {
  final Download download;

  const DownloadRow({super.key, required this.download});

  @override
  State<DownloadRow> createState() => _DownloadRowState();
}

class _DownloadRowState extends State<DownloadRow> {
  bool _showDeleteConfirm = false;

  String _statusLabel(Download dl) {
    if (dl.hasError) return 'Error';
    switch (dl.status) {
      case Download.stopped:
        return dl.isFinished ? 'Completada' : 'Pausada';
      case Download.checkWait:
      case Download.check:
        return 'Verificando';
      case Download.downloadWait:
        return 'En cola';
      case Download.downloading:
        return 'Descargando';
      case Download.seedWait:
      case Download.seeding:
        return 'Completada';
      default:
        return 'Desconocido';
    }
  }

  Color _statusColor(Download dl, ThemeData theme) {
    if (dl.hasError) return theme.colorScheme.error;
    if (dl.isActive) return theme.colorScheme.primary;
    if (dl.isCompleted) return Colors.green;
    return theme.colorScheme.outline;
  }

  Color _progressColor(Download dl, ThemeData theme) {
    if (dl.hasError) return theme.colorScheme.error;
    if (dl.isCompleted) return Colors.green;
    return theme.colorScheme.primary;
  }

  Future<void> _pause() async {
    final api = context.read<SettingsProvider>().apiService;
    if (api == null) return;
    try {
      await api.pauseDownload(widget.download.id);
    } catch (_) {}
  }

  Future<void> _resume() async {
    final api = context.read<SettingsProvider>().apiService;
    if (api == null) return;
    try {
      await api.resumeDownload(widget.download.id);
    } catch (_) {}
  }

  Future<void> _remove({bool deleteFile = false}) async {
    final api = context.read<SettingsProvider>().apiService;
    if (api == null) return;
    try {
      await api.removeDownload(widget.download.id, deleteFile: deleteFile);
    } catch (_) {}
    setState(() => _showDeleteConfirm = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dl = widget.download;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header: name + actions
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        dl.name,
                        style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                            decoration: BoxDecoration(
                              color: _statusColor(dl, theme).withOpacity(0.15),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              _statusLabel(dl),
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: _statusColor(dl, theme),
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            formatSize(dl.totalSize),
                            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                // Action buttons
                _buildActions(dl, theme),
              ],
            ),

            // Error message
            if (dl.hasError && dl.errorString.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                dl.errorString,
                style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],

            const SizedBox(height: 8),

            // Progress bar
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: dl.percentDone,
                backgroundColor: theme.colorScheme.surfaceContainerHighest,
                color: _progressColor(dl, theme),
                minHeight: 6,
              ),
            ),

            // Stats row
            if (dl.isActive) ...[
              const SizedBox(height: 4),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    '${(dl.percentDone * 100).toStringAsFixed(1)}%',
                    style: theme.textTheme.bodySmall,
                  ),
                  Text(
                    formatSpeed(dl.rateDownload),
                    style: theme.textTheme.bodySmall,
                  ),
                  Text(
                    'ETA: ${formatEta(dl.eta)}',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
            ],

            // Delete confirmation
            if (_showDeleteConfirm) ...[
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => _remove(),
                    child: const Text('Solo quitar'),
                  ),
                  const SizedBox(width: 8),
                  TextButton(
                    onPressed: () => _remove(deleteFile: true),
                    style: TextButton.styleFrom(foregroundColor: theme.colorScheme.error),
                    child: const Text('+ Borrar archivo'),
                  ),
                  const SizedBox(width: 8),
                  TextButton(
                    onPressed: () => setState(() => _showDeleteConfirm = false),
                    child: const Text('Cancelar'),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildActions(Download dl, ThemeData theme) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (dl.isActive)
          IconButton(
            icon: const Icon(Icons.pause, size: 20),
            onPressed: _pause,
            tooltip: 'Pausar',
            visualDensity: VisualDensity.compact,
          ),
        if (!dl.isFinished && (dl.status == Download.stopped || dl.hasError))
          IconButton(
            icon: const Icon(Icons.play_arrow, size: 20),
            onPressed: _resume,
            tooltip: 'Reanudar',
            visualDensity: VisualDensity.compact,
          ),
        if (dl.isCompleted)
          IconButton(
            icon: const Icon(Icons.file_download, size: 20),
            onPressed: () {
              final api = context.read<SettingsProvider>().apiService;
              if (api != null) {
                final url = api.getFileUrl(dl.id);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('URL: $url')),
                );
              }
            },
            tooltip: 'Descargar archivo',
            visualDensity: VisualDensity.compact,
          ),
        IconButton(
          icon: Icon(Icons.delete_outline, size: 20, color: theme.colorScheme.error),
          onPressed: () => setState(() => _showDeleteConfirm = !_showDeleteConfirm),
          tooltip: 'Eliminar',
          visualDensity: VisualDensity.compact,
        ),
      ],
    );
  }
}
