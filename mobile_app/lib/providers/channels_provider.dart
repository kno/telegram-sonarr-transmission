import 'package:flutter/material.dart';
import '../models/channel.dart';
import '../services/storage_service.dart';

class ChannelsProvider extends ChangeNotifier {
  final StorageService _storage = StorageService();
  List<Channel> _channels = [];

  List<Channel> get channels => _channels;
  List<int> get enabledIds =>
      _channels.where((c) => c.enabled).map((c) => c.id).toList();

  Future<void> load() async {
    _channels = await _storage.getChannels();
    notifyListeners();
  }

  Future<void> setChannels(List<Channel> newChannels) async {
    final existing = {for (var c in _channels) c.id: c.enabled};
    for (var ch in newChannels) {
      ch.enabled = existing[ch.id] ?? true;
    }
    _channels = newChannels;
    await _storage.saveChannels(_channels);
    notifyListeners();
  }

  Future<void> toggle(int id) async {
    final index = _channels.indexWhere((c) => c.id == id);
    if (index != -1) {
      _channels[index].enabled = !_channels[index].enabled;
      await _storage.saveChannels(_channels);
      notifyListeners();
    }
  }

  Future<void> enableAll() async {
    for (var ch in _channels) {
      ch.enabled = true;
    }
    await _storage.saveChannels(_channels);
    notifyListeners();
  }

  Future<void> disableAll() async {
    for (var ch in _channels) {
      ch.enabled = false;
    }
    await _storage.saveChannels(_channels);
    notifyListeners();
  }
}
