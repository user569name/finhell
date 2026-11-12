import 'dart:convert';

import 'package:http/http.dart' as http;

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

  Map<String, String> get _headers => const {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<MacroSnapshot> fetchMacro({bool refresh = false}) async {
    final response = await _client
        .get(_uri('/api/v2/macro?refresh=$refresh'), headers: _headers)
        .timeout(const Duration(seconds: 25));
    _ensureOk(response);
    return MacroSnapshot.fromJson(_decode(response));
  }

  Future<String> startOptimization(Map<String, dynamic> payload) async {
    final response = await _client
        .post(_uri('/api/v2/optimize/async'),
            headers: _headers, body: jsonEncode(payload))
        .timeout(const Duration(seconds: 30));
    _ensureOk(response);
    final data = _decode(response);
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
    final response = await _client
        .post(
          _uri('/api/v2/ai/chat'),
          headers: _headers,
          body: jsonEncode({
            'context_id': contextId,
            'question': question,
            'history': history,
            'use_llm': useLlm,
          }),
        )
        .timeout(const Duration(seconds: 40));
    _ensureOk(response);
    return ChatResponse.fromJson(_decode(response));
  }

  Future<AiExplanation> explain({
    required String contextId,
    bool useLlm = true,
  }) async {
    final response = await _client
        .post(
          _uri('/api/v2/ai/explain'),
          headers: _headers,
          body: jsonEncode({'context_id': contextId, 'use_llm': useLlm}),
        )
        .timeout(const Duration(seconds: 40));
    _ensureOk(response);
    return AiExplanation.fromJson(_decode(response));
  }

  Map<String, dynamic> _decode(http.Response response) {
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is Map<String, dynamic>) return decoded;
    throw ApiException('Неожиданный формат ответа сервера.');
  }

  void _ensureOk(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    String detail = 'HTTP ${response.statusCode}';
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map && decoded['detail'] != null) {
        detail = decoded['detail'].toString();
      }
    } catch (_) {
      // оставляем код статуса
    }
    throw ApiException(detail);
  }

  void dispose() => _client.close();
}

class ApiException implements Exception {
  ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}
