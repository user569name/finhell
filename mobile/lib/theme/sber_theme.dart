import 'package:flutter/material.dart';

/// Палитра и темы в стиле Сбера: зелёный, белый, почти чёрный.
class SberColors {
  static const green = Color(0xFF21A038);
  static const greenBright = Color(0xFF37C455);
  static const greenDark = Color(0xFF0D7A24);
  static const greenDeep = Color(0xFF0A4F19);
  static const greenSoft = Color(0xFFE7F6EA);
  static const black = Color(0xFF0A0F0B);
  static const ink = Color(0xFF0B1F12);
  static const muted = Color(0xFF68786C);
  static const line = Color(0xFFE1E9E2);
  static const surface = Color(0xFFFFFFFF);
  static const background = Color(0xFFF4F7F4);
  static const amber = Color(0xFFF0A51D);
  static const red = Color(0xFFE5484D);
}

class SberTheme {
  static ThemeData light() {
    final scheme = ColorScheme.fromSeed(
      seedColor: SberColors.green,
      brightness: Brightness.light,
    ).copyWith(
      primary: SberColors.green,
      secondary: SberColors.greenDark,
      error: SberColors.red,
      surface: SberColors.surface,
    );
    return _base(scheme, SberColors.background, SberColors.ink);
  }

  static ThemeData dark() {
    final scheme = ColorScheme.fromSeed(
      seedColor: SberColors.green,
      brightness: Brightness.dark,
    ).copyWith(
      primary: SberColors.greenBright,
      secondary: SberColors.green,
      error: SberColors.red,
      surface: const Color(0xFF121914),
    );
    return _base(scheme, const Color(0xFF0A0E0B), const Color(0xFFF1F6F2));
  }

  static ThemeData _base(ColorScheme scheme, Color background, Color onBackground) {
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      fontFamily: 'Roboto',
      textTheme: TextTheme(
        displaySmall: TextStyle(
          fontSize: 34,
          fontWeight: FontWeight.w800,
          letterSpacing: -1.2,
          color: onBackground,
        ),
        headlineSmall: TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.7,
          color: onBackground,
        ),
        titleMedium: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: onBackground,
        ),
        bodyMedium: TextStyle(fontSize: 14, height: 1.45, color: onBackground),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surface,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(24),
          side: BorderSide(color: scheme.outlineVariant.withOpacity(0.5)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHighest.withOpacity(0.5),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: scheme.primary, width: 1.6),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        ),
      ),
      chipTheme: ChipThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
        side: BorderSide.none,
      ),
    );
  }
}
