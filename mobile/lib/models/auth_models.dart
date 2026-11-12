/// Пользователь и сессия авторизации.
class AuthUser {
  const AuthUser({
    required this.id,
    required this.email,
    this.name = '',
    this.createdAt = '',
  });

  final String id;
  final String email;
  final String name;
  final String createdAt;

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: (json['id'] ?? '').toString(),
      email: (json['email'] ?? '').toString(),
      name: (json['name'] ?? '').toString(),
      createdAt: (json['created_at'] ?? '').toString(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'name': name,
        'created_at': createdAt,
      };

  String get displayName => name.trim().isEmpty ? email : name.trim();
}

class AuthSession {
  const AuthSession({required this.token, required this.user});

  final String token;
  final AuthUser user;

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    final userJson = json['user'];
    return AuthSession(
      token: (json['token'] ?? '').toString(),
      user: userJson is Map<String, dynamic>
          ? AuthUser.fromJson(userJson)
          : const AuthUser(id: '', email: ''),
    );
  }

  Map<String, dynamic> toJson() => {
        'token': token,
        'user': user.toJson(),
      };
}
