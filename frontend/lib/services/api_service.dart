import 'dart:convert';
import 'dart:async';
import 'package:http/http.dart' as http;

/// HTTP-клиент к FastAPI серверу.
class ApiService {
  // В dev: localhost:8000, в проде — настоящий домен
  static const String baseUrl = 'http://localhost:8000';

  // ═══ Генерация ═══

  /// POST /api/generate → возвращает {task_id, status, ...}
  static Future<Map<String, dynamic>> startGeneration(Map<String, dynamic> formData) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/generate'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(formData),
    );
    if (resp.statusCode != 200) {
      throw Exception('Ошибка генерации: ${resp.statusCode} ${resp.body}');
    }
    return jsonDecode(resp.body);
  }

  /// GET /api/generate/{taskId} → polling статуса
  static Future<Map<String, dynamic>> getTaskStatus(String taskId) async {
    final resp = await http.get(Uri.parse('$baseUrl/api/generate/$taskId'));
    if (resp.statusCode != 200) {
      throw Exception('Ошибка статуса: ${resp.statusCode}');
    }
    return jsonDecode(resp.body);
  }

  /// Скачивание URL
  static String downloadUrl(String taskId, String docType) =>
      '$baseUrl/api/download/$taskId/$docType';

  /// GET /api/preview/{taskId}/{docType} → HTML
  static Future<String> getDocHtml(String taskId, String docType) async {
    final resp = await http.get(Uri.parse('$baseUrl/api/preview/$taskId/$docType'));
    if (resp.statusCode != 200) return '<p>Ошибка загрузки документа</p>';
    final data = jsonDecode(resp.body);
    return data['html'] ?? '<p>Пустой документ</p>';
  }

  /// PUT /api/save/{taskId}/{docType}
  static Future<bool> saveDocHtml(String taskId, String docType, String html) async {
    final resp = await http.put(
      Uri.parse('$baseUrl/api/save/$taskId/$docType'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'html': html}),
    );
    return resp.statusCode == 200;
  }

  // ═══ Чат ═══

  static Future<String> sendChat(String message, {String? taskId}) async {
    final resp = await http.post(
      Uri.parse('$baseUrl/api/chat?message=${Uri.encodeComponent(message)}&task_id=${taskId ?? ""}'),
    );
    if (resp.statusCode != 200) return 'Ошибка сервера';
    final data = jsonDecode(resp.body);
    return data['reply'] ?? 'Нет ответа';
  }

  // ═══ Справочники ═══

  static Future<List<Map<String, dynamic>>> searchInn(String q) async {
    final resp = await http.get(Uri.parse('$baseUrl/api/dictionaries/inn?q=${Uri.encodeComponent(q)}'));
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  static Future<List<String>> searchForms(String q) async {
    final resp = await http.get(Uri.parse('$baseUrl/api/dictionaries/forms?q=${Uri.encodeComponent(q)}'));
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<String>();
  }

  static Future<List<String>> getDosages(String inn) async {
    final resp = await http.get(Uri.parse('$baseUrl/api/dictionaries/dosages?inn=${Uri.encodeComponent(inn)}'));
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<String>();
  }

  static Future<List<String>> searchManufacturers(String q) async {
    final resp = await http.get(Uri.parse('$baseUrl/api/dictionaries/manufacturers?q=${Uri.encodeComponent(q)}'));
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<String>();
  }

  /// Универсальный поиск компаний: kind = research_center | biolab | insurance | general
  /// Поддерживает поиск по ИНН (если q — цифры) и по названию
  static Future<List<Map<String, dynamic>>> searchCompany(String q, {String kind = ""}) async {
    final resp = await http.get(Uri.parse(
      '$baseUrl/api/dictionaries/company?q=${Uri.encodeComponent(q)}&kind=${Uri.encodeComponent(kind)}'
    ));
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  static Future<List<Map<String, dynamic>>> searchReference(String inn, String q) async {
    final resp = await http.get(Uri.parse('$baseUrl/api/dictionaries/reference?inn=${Uri.encodeComponent(inn)}&q=${Uri.encodeComponent(q)}'));
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<Map<String, dynamic>>();
  }

  static Future<List<String>> searchExcipients(String q) async {
    final resp = await http.get(Uri.parse('$baseUrl/api/dictionaries/excipients?q=${Uri.encodeComponent(q)}'));
    if (resp.statusCode != 200) return [];
    final list = jsonDecode(resp.body) as List;
    return list.cast<String>();
  }
}