import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SessionStore {
  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'auth_token';
  static const _baseUrlKey = 'base_url';
  static const _nameKey = 'student_name';
  static const _idKey = 'student_id';

  static const defaultBaseUrl = 'https://172.19.15.179:8000';

  Future<String?> getToken() => _storage.read(key: _tokenKey);

  Future<String> getBaseUrl() async {
    final value = await _storage.read(key: _baseUrlKey);
    return (value == null || value.trim().isEmpty) ? defaultBaseUrl : value.trim();
  }

  Future<Map<String, String?>> getStudent() async => {
        'name': await _storage.read(key: _nameKey),
        'identifier': await _storage.read(key: _idKey),
      };

  Future<void> saveSession({
    required String token,
    required String baseUrl,
    required String name,
    required String identifier,
  }) async {
    await _storage.write(key: _tokenKey, value: token);
    await _storage.write(key: _baseUrlKey, value: baseUrl);
    await _storage.write(key: _nameKey, value: name);
    await _storage.write(key: _idKey, value: identifier);
  }

  Future<void> saveBaseUrl(String baseUrl) =>
      _storage.write(key: _baseUrlKey, value: baseUrl);

  Future<void> clearSession() async {
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _nameKey);
    await _storage.delete(key: _idKey);
  }
}
