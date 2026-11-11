import 'package:flutter/material.dart';

import '../models/optimizer_models.dart';
import '../theme/sber_theme.dart';

/// Цвета инструментов для мини-диаграммы состава портфеля.
const Map<String, Color> kAssetColors = {
  'cash': Color(0xFF9AA79D),
  'savings': Color(0xFF2BB3A3),
  'deposit': Color(0xFF3B82F6),
  'ofz_short': Color(0xFF7BC96F),
  'ofz_long': Color(0xFF21A038),
  'corporate': Color(0xFFF0A51D),
  'municipal': Color(0xFF8B5CF6),
  'real_estate': Color(0xFFB07A52),
};

Color riskColor(String level) {
  switch (level) {
    case 'low':
      return SberColors.green;
    case 'high':
      return SberColors.red;
    default:
      return SberColors.amber;
  }
}

String riskLabel(String level) {
  switch (level) {
    case 'low':
      return 'Низкий риск';
    case 'high':
      return 'Высокий риск';
    default:
      return 'Средний риск';
  }
}

String formatMoney(double value) {
  final negative = value < 0;
  final absolute = value.abs();
  final String text;
  if (absolute >= 1000000) {
    text = '${(absolute / 1000000).toStringAsFixed(2).replaceAll('.', ',')} млн';
  } else if (absolute >= 1000) {
    text = '${(absolute / 1000).toStringAsFixed(0)} тыс.';
  } else {
    text = absolute.toStringAsFixed(0);
  }
  return '${negative ? '−' : ''}$text ₽';
}

String formatPercent(double value, [int digits = 1]) {
  return '${(value * 100).toStringAsFixed(digits).replaceAll('.', ',')}%';
}

/// Карточка одного уровня риска.
class RiskCard extends StatelessWidget {
  const RiskCard({
    super.key,
    required this.profile,
    required this.onOpen,
  });

  final RiskProfile profile;
  final VoidCallback onOpen;

  ScenarioOption? get _best {
    if (profile.options.isEmpty) return null;
    for (final option in profile.options) {
      if (option.id == profile.bestOptionId) return option;
    }
    return profile.options.first;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final best = _best;
    if (best == null) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Text('${profile.label}: нет доступных сценариев'),
        ),
      );
    }
    final accent = riskColor(best.riskLevel);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: accent.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          riskLabel(best.riskLevel),
                          style: TextStyle(
                            color: accent,
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  _ScoreBadge(score: best.score, color: accent),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                best.name,
                style: theme.textTheme.titleMedium?.copyWith(fontSize: 18),
              ),
              const SizedBox(height: 4),
              Text(
                profile.description,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  _Metric(
                    label: 'Доходность',
                    value: formatPercent(best.expectedReturnNominal),
                    accent: true,
                  ),
                  const SizedBox(width: 20),
                  _Metric(
                    label: 'P50',
                    value: formatMoney(best.monteCarlo.terminalP50),
                  ),
                  const SizedBox(width: 20),
                  _Metric(
                    label: 'Цель',
                    value: best.probabilityGoal == null
                        ? '—'
                        : formatPercent(best.probabilityGoal!, 0),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              _CompositionBar(allocation: best.allocation),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'P5–P95: ${formatMoney(best.monteCarlo.terminalP5)} — '
                      '${formatMoney(best.monteCarlo.terminalP95)}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  TextButton(
                    onPressed: onOpen,
                    child: Text('Все сценарии →', style: TextStyle(color: accent)),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  _Pill(text: 'Ликвидность ${best.liquidityLabel}'),
                  _Pill(text: 'Просадка ${formatPercent(best.maxDrawdown, 0)}'),
                  _Pill(text: 'VaR95 ${formatPercent(best.var95, 1)}'),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ScoreBadge extends StatelessWidget {
  const _ScoreBadge({required this.score, required this.color});

  final double score;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final value = score.clamp(0.0, 1.0).toDouble();
    return SizedBox(
      width: 44,
      height: 44,
      child: Stack(
        alignment: Alignment.center,
        children: [
          CircularProgressIndicator(
            value: value,
            strokeWidth: 4,
            backgroundColor: color.withOpacity(0.14),
            valueColor: AlwaysStoppedAnimation<Color>(color),
          ),
          Text(
            '${(value * 100).round()}',
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value, this.accent = false});

  final String label;
  final String value;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.2,
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w800,
            color: accent ? SberColors.green : theme.colorScheme.onSurface,
          ),
        ),
      ],
    );
  }
}

class _CompositionBar extends StatelessWidget {
  const _CompositionBar({required this.allocation});

  final List<AllocationItem> allocation;

  @override
  Widget build(BuildContext context) {
    final items = allocation.where((item) => item.weight > 0).toList();
    if (items.isEmpty) return const SizedBox.shrink();
    return ClipRRect(
      borderRadius: BorderRadius.circular(999),
      child: SizedBox(
        height: 10,
        child: Row(
          children: [
            for (final item in items)
              Expanded(
                flex: (item.weight * 1000).round().clamp(1, 1000).toInt(),
                child: Container(color: kAssetColors[item.key] ?? SberColors.green),
              ),
          ],
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.5),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w600,
          color: theme.colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }
}
