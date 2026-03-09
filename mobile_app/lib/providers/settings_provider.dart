import 'package:flutter/material.dart';
import '../services/storage_service.dart';
import '../services/api_service.dart';

class SettingsProvider extends ChangeNotifier {
  final StorageService _storage = StorageService();
  String _apiKey = '';
  String _backendUrl = '';

  String get apiKey => _apiKey;
  String get backendUrl => _backendUrl;
  bool get configured => _apiKey.isNotEmpty;

  ApiService? get apiService =>
      configured ? ApiService(baseUrl: _backendUrl, apiKey: _apiKey) : null;

  Future<void> load() async {
    _apiKey = await _storage.getApiKey();
    _backendUrl = await _storage.getBackendUrl();
    notifyListeners();
  }

  Future<void> save(String apiKey, String backendUrl) async {
    _apiKey = apiKey;
    _backendUrl = backendUrl;
    await _storage.setApiKey(apiKey);
    await _storage.setBackendUrl(backendUrl);
    notifyListeners();
  }
}
