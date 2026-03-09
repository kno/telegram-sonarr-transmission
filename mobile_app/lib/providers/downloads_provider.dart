import 'package:flutter/material.dart';
import '../models/download.dart';
import '../services/websocket_service.dart';

class DownloadsProvider extends ChangeNotifier {
  List<Download> _downloads = [];
  WebSocketService? _wsService;

  List<Download> get downloads => _downloads;
  List<Download> get active =>
      _downloads.where((d) => d.isActive).toList();
  List<Download> get paused =>
      _downloads.where((d) => d.isPaused).toList();
  List<Download> get withErrors =>
      _downloads.where((d) => d.hasError).toList();
  List<Download> get completed =>
      _downloads.where((d) => d.isCompleted).toList();

  void connectWebSocket(String baseUrl, String apiKey) {
    _wsService?.disconnect();
    _wsService = WebSocketService(baseUrl: baseUrl, apiKey: apiKey);
    _wsService!.onDownloadsUpdate = (downloads) {
      _downloads = downloads;
      notifyListeners();
    };
    _wsService!.connect();
  }

  void disconnect() {
    _wsService?.disconnect();
    _wsService = null;
  }

  void setDownloads(List<Download> downloads) {
    _downloads = downloads;
    notifyListeners();
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}
