import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/sber_theme.dart';

/// Рекламный слот-баннер.
///
/// Точка интеграции: сюда вставляется адаптивный баннер AdMob
/// (`AdWidget(ad: bannerAd)` после `BannerAd.load`) или
/// Yandex Mobile Ads (`AdWidget` с `BannerAdSize.stickySize`).
/// Пока показываем размеченный placeholder, чтобы место было видно в макете.
class AdBannerSlot extends StatelessWidget {
  const AdBannerSlot({super.key, this.onWatchAd, this.reward = 5});

  /// Кнопка rewarded-рекламы рядом с баннером (необязательна).
  final VoidCallback? onWatchAd;
  final int reward;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final borderColor = dark ? Colors.white24 : SberColors.line;

    return CustomPaint(
      painter: _DashedBorderPainter(
        color: borderColor,
        radius: 18,
      ),
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 14, 12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: LinearGradient(
            colors: dark
                ? [const Color(0xFF101812), const Color(0xFF14251A)]
                : [const Color(0xFFF8FBF8), const Color(0xFFEEF6EF)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                color: SberColors.green.withOpacity(dark ? 0.2 : 0.12),
              ),
              child: const Icon(
                Icons.campaign_outlined,
                size: 22,
                color: SberColors.green,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(5),
                          color: SberColors.amber.withOpacity(0.18),
                        ),
                        child: const Text(
                          'РЕКЛАМА',
                          style: TextStyle(
                            fontSize: 8,
                            letterSpacing: 0.8,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFF8A5B00),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          'Баннерный слот',
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(
                    'Здесь будет баннер AdMob или Yandex Ads',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontSize: 11,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            if (onWatchAd != null) ...[
              const SizedBox(width: 8),
              TextButton(
                onPressed: onWatchAd,
                style: TextButton.styleFrom(
                  foregroundColor: SberColors.greenDark,
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  visualDensity: VisualDensity.compact,
                ),
                child: Text(
                  '+$reward',
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _DashedBorderPainter extends CustomPainter {
  const _DashedBorderPainter({
    required this.color,
    this.radius = 18,
    this.dash = 6,
    this.gap = 5,
  });

  final Color color;
  final double radius;
  final double dash;
  final double gap;

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()
      ..addRRect(
        RRect.fromRectAndRadius(Offset.zero & size, Radius.circular(radius)),
      );
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;
    for (final metric in path.computeMetrics()) {
      var distance = 0.0;
      while (distance < metric.length) {
        final end = math.min(distance + dash, metric.length);
        canvas.drawPath(metric.extractPath(distance, end), paint);
        distance = end + gap;
      }
    }
  }

  @override
  bool shouldRepaint(covariant _DashedBorderPainter oldDelegate) {
    return oldDelegate.color != color ||
        oldDelegate.radius != radius ||
        oldDelegate.dash != dash ||
        oldDelegate.gap != gap;
  }
}
