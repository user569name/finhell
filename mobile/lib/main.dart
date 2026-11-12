import 'package:flutter/material.dart';

import 'models/auth_models.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'services/api_client.dart';
import 'services/auth_store.dart';
import 'theme/sber_theme.dart';

void main() {
  runApp(const FinhellApp());
}

class FinhellApp extends StatefulWidget {
  const FinhellApp({super.key});

  @override
  State<FinhellApp> createState() => _FinhellAppState();
}

class _FinhellAppState extends State<FinhellApp> {
  ThemeMode _mode = ThemeMode.light;
  late final ApiClient _api = ApiClient();
  final AuthStore _authStore = AuthStore();

  AuthSession? _session;
  bool _booting = true;

  @override
  void initState() {
    super.initState();
    _api.onUnauthorized = _handleUnauthorized;
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    final savedBaseUrl = await _authStore.loadBaseUrl();
    if (savedBaseUrl != null && savedBaseUrl.isNotEmpty) {
      _api.baseUrl = savedBaseUrl;
    }

    final stored = await _authStore.load();
    AuthSession? session;
    if (stored != null) {
      _api.token = stored.token;
      try {
        final user = await _api.me();
        session = AuthSession(token: stored.token, user: user);
        await _authStore.save(session);
      } on ApiException catch (error) {
        if (error.statusCode == 401) {
          _api.token = null;
          await _authStore.clear();
        } else {
          // Сервер недоступен — оставляем сохранённую сессию.
          session = stored;
        }
      } catch (_) {
        session = stored;
      }
    }

    if (!mounted) return;
    setState(() {
      _session = session;
      _booting = false;
    });
  }

  Future<void> _handleAuthenticated(AuthSession session) async {
    await _authStore.save(session);
    if (!mounted) return;
    setState(() => _session = session);
  }

  Future<void> _logout() async {
    await _api.logout();
    await _authStore.clear();
    if (!mounted) return;
    setState(() => _session = null);
  }

  void _handleUnauthorized() {
    if (_session == null) return;
    _api.token = null;
    _session = null;
    _authStore.clear();
    if (mounted) setState(() {});
  }

  Future<void> _saveBaseUrl(String baseUrl) => _authStore.saveBaseUrl(baseUrl);

  @override
  void dispose() {
    _api.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ФинХелл — оптимизатор капитала',
      debugShowCheckedModeBanner: false,
      theme: SberTheme.light(),
      darkTheme: SberTheme.dark(),
      themeMode: _mode,
      home: _booting
          ? const _BootScreen()
          : _session == null
              ? AuthScreen(
                  api: _api,
                  onAuthenticated: _handleAuthenticated,
                  onBaseUrlChanged: _saveBaseUrl,
                )
              : HomeScreen(
                  key: ValueKey(_session!.user.email),
                  api: _api,
                  user: _session!.user,
                  onLogout: _logout,
                  onBaseUrlChanged: _saveBaseUrl,
                  isDark: _mode == ThemeMode.dark,
                  onToggleTheme: () {
                    setState(() {
                      _mode = _mode == ThemeMode.dark
                          ? ThemeMode.light
                          : ThemeMode.dark;
                    });
                  },
                ),
    );
  }
}

class _BootScreen extends StatelessWidget {
  const _BootScreen();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(22),
                gradient: const LinearGradient(
                  colors: [SberColors.greenBright, SberColors.greenDark],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
              alignment: Alignment.center,
              child: const Text(
                'Ф',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 34,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(height: 18),
            Text(
              'ФинХелл',
              style: theme.textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 16),
            const SizedBox(
              width: 26,
              height: 26,
              child: CircularProgressIndicator(strokeWidth: 2.6),
            ),
          ],
        ),
      ),
    );
  }
}
