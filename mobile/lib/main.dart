import 'package:flutter/material.dart';

import 'screens/home_screen.dart';
import 'services/api_client.dart';
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
      home: HomeScreen(
        api: _api,
        isDark: _mode == ThemeMode.dark,
        onToggleTheme: () {
          setState(() {
            _mode = _mode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
          });
        },
      ),
    );
  }
}
