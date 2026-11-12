import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/auth_models.dart';
import '../models/optimizer_models.dart';

/// HTTP-клиент оптимизатора.
///
/// Адрес задаётся при сборке:
///   flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8002
///
/// По умолчанию Android-эмулятор ходит на 10.0.2.2 (хост-машина).
class ApiClient {
  ApiClient({String? baseUrl, http.Client? client})
      : baseUrl = baseUrl ??
            const String.fromEnvironment(
              'API_BASE_URL',
              defaultValue: 'http://10.0.2.2:8002',
            ),
        _client = client ?? http.Client();

  /// Адрес можно изменить из интерфейса приложения (иконка сервера).
  String baseUrl;
  final http.Client _client;

  /// Bearer-токен, полученный после входа по email.
  String? token;

  /// Вызывается, когда сервер ответил 401 — сессия истекла.
  void Function()? onUnauthorized;

  Map<String, String> get _headers {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    final current = token;
    if (current != null && current.isNotEmpty) {
      headers['Authorization'] = 'Bearer $current';
    }
    return headers;
  }

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<AuthSession> register({
    required String email,
    required String password,
    String name = '',
  }) async {
    final data = await _post(
      '/api/v2/auth/register',
      {'email': email, 'password': password, 'name': name},
      timeout: const Duration(seconds: 40),
    );
    final session = AuthSession.fromJson(data);
    token = session.token;
    return session;
  }

  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    final data = await _post(
      '/api/v2/auth/login',
      {'email': email, 'password': password},
      timeout: const Duration(seconds: 40),
    );
    final session = AuthSession.fromJson(data);
    token = session.token;
    return session;
  }

  Future<AuthUser> me() async {
    final response = await _client
        .get(_uri('/api/v2/auth/me'), headers: _headers)
        .timeout(const Duration(seconds: 25));
    _ensureOk(response);
    final data = _decode(response);
    final user = data['user'];
    if (user is! Map<String, dynamic>) {
      throw ApiException('Сервер не вернул данные пользователя.');
    }
    return AuthUser.fromJson(user);
  }

  Future<void> logout() async {
    try {
      await _client
          .post(_uri('/api/v2/auth/logout'), headers: _headers)
          .timeout(const Duration(seconds: 10));
    } catch (_) {
      // сервер не хранит токены — выход всё равно локальный
    }
    token = null;
  }

  Future<MacroSnapshot> fetchMacro({bool refresh = false}) async {
    final response = await _client
        .get(_uri('/api/v2/macro?refresh=$refresh'), headers: _headers)
        .timeout(const Duration(seconds: 25));
    _ensureOk(response);
    return MacroSnapshot.fromJson(_decode(response));
  }

  Future<String> startOptimization(Map<String, dynamic> payload) async {
    final data = await _post(
      '/api/v2/optimize/async',
      payload,
      timeout: const Duration(seconds: 30),
    );
    final jobId = data['job_id'];
    if (jobId is! String || jobId.isEmpty) {
      throw ApiException('Сервер не вернул job_id.');
    }
    return jobId;
  }

  Future<JobStatus> fetchJob(String jobId) async {
    final response = await _client
        .get(_uri('/api/v2/jobs/$jobId'), headers: _headers)
        .timeout(const Duration(seconds: 25));
    _ensureOk(response);
    return JobStatus.fromJson(_decode(response));
  }

  Future<ChatResponse> chat({
    required String contextId,
    required String question,
    List<Map<String, String>> history = const [],
    bool useLlm = true,
  }) async {
    final data = await _post(
      '/api/v2/ai/chat',
      {
        'context_id': contextId,
        'question': question,
        'history': history,
        'use_llm': useLlm,
      },
      timeout: const Duration(seconds: 40),
    );
    return ChatResponse.fromJson(data);
  }

  Future<AiExplanation> explain({
    required String contextId,
    bool useLlm = true,
  }) async {
    final data = await _post(
      '/api/v2/ai/explain',
      {'context_id': contextId, 'use_llm': useLlm},
      timeout: const Duration(seconds: 40),
    );
    return AiExplanation.fromJson(data);
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> payload, {
    required Duration timeout,
  }) async {
    final response = await _client
        .post(_uri(path), headers: _headers, body: jsonEncode(payload))
        .timeout(timeout);
    _ensureOk(response);
    return _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is Map<String, dynamic>) return decoded;
    throw ApiException('Неожиданный формат ответа сервера.');
  }

  void _ensureOk(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    if (response.statusCode == 401) {
      onUnauthorized?.call();
    }
    String detail = 'HTTP ${response.statusCode}';
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map && decoded['detail'] != null) {
        detail = decoded['detail'].toString();
      }
    } catch (_) {
      // оставляем код статуса
    }
    throw ApiException(detail, statusCode: response.statusCode);
  }

  void dispose() => _client.close();
}

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}
