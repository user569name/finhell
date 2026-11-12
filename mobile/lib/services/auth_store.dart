import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/auth_models.dart';

/// Хранит токен, пользователя и адрес сервера между запусками.
class AuthStore {
  static const _tokenKey = 'finhell.auth.token';
  static const _userKey = 'finhell.auth.user';
  static const _baseUrlKey = 'finhell.server.base_url';

  Future<AuthSession?> load() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(_tokenKey);
    if (token == null || token.isEmpty) return null;

    AuthUser user = const AuthUser(id: '', email: '');
    final raw = prefs.getString(_userKey);
    if (raw != null && raw.isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is Map<String, dynamic>) {
          user = AuthUser.fromJson(decoded);
        }
      } catch (_) {
        // повреждённые данные не мешают восстановить сессию
      }
    }
    return AuthSession(token: token, user: user);
  }

  Future<void> save(AuthSession session) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, session.token);
    await prefs.setString(_userKey, jsonEncode(session.user.toJson()));
  }

  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_userKey);
  }

  Future<String?> loadBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getString(_baseUrlKey);
    return value == null || value.isEmpty ? null : value;
  }

  Future<void> saveBaseUrl(String baseUrl) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_baseUrlKey, baseUrl);
  }
}
