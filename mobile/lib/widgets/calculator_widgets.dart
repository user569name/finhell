import 'package:flutter/material.dart';

import '../models/calculator_models.dart';
import '../theme/sber_theme.dart';

const Color kInflationAccent = Color(0xFF3B82F6);
const Color kTaxAccent = Color(0xFFF0A51D);

/// Разбор числа из поля ввода: пробелы, запятая и неразрывный пробел.
double calcNumber(TextEditingController controller, [double fallback = 0]) {
  final raw = controller.text
      .trim()
      .replaceAll(' ', '')
      .replaceAll('\u00A0', '')
      .replaceAll(',', '.');
  return double.tryParse(raw) ?? fallback;
}

String formatRub(double value) {
  final negative = value < 0;
  final rounded = value.abs().round().toString();
  final buffer = StringBuffer();
  for (var i = 0; i < rounded.length; i++) {
    if (i > 0 && (rounded.length - i) % 3 == 0) buffer.write(' ');
    buffer.write(rounded[i]);
  }
  return '${negative ? '−' : ''}$buffer ₽';
}

String formatPct(double value, [int digits = 1]) {
  return '${(value * 100).toStringAsFixed(digits).replaceAll('.', ',')}%';
}

String formatYears(int years) {
  final mod10 = years % 10;
  final mod100 = years % 100;
  if (mod10 == 1 && mod100 != 11) return '$years год';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return '$years года';
  }
  return '$years лет';
}

class CalculatorTab extends StatelessWidget {
  const CalculatorTab({
    super.key,
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.accent,
    required this.children,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final Color accent;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 32),
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      children: [
        Row(
          children: [
            Container(
              width: 50,
              height: 50,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(17),
                gradient: LinearGradient(
                  colors: [accent.withOpacity(0.18), accent.withOpacity(0.05)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                border: Border.all(color: accent.withOpacity(0.3)),
              ),
              child: Icon(icon, color: accent, size: 25),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: theme.textTheme.headlineSmall?.copyWith(
                      fontSize: 23,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    subtitle,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                      height: 1.35,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        ...children,
        const SizedBox(height: 14),
        const CalculatorDisclaimer(),
      ],
    );
  }
}

class CalcCard extends StatelessWidget {
  const CalcCard({
    super.key,
    this.title,
    this.subtitle,
    required this.children,
  });

  final String? title;
  final String? subtitle;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (title != null) ...[
              Text(
                title!,
                style: theme.textTheme.titleMedium?.copyWith(fontSize: 15),
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 3),
                Text(
                  subtitle!,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontSize: 11,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
              const SizedBox(height: 14),
            ],
            ...children,
          ],
        ),
      ),
    );
  }
}

class CalcField extends StatelessWidget {
  const CalcField({
    super.key,
    required this.controller,
    required this.label,
    this.suffix,
    this.helper,
    this.onChanged,
  });

  final TextEditingController controller;
  final String label;
  final String? suffix;
  final String? helper;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      style: const TextStyle(fontWeight: FontWeight.w700),
      decoration: InputDecoration(
        labelText: label,
        suffixText: suffix,
        helperText: helper,
        helperMaxLines: 2,
      ),
      onChanged: (_) => onChanged?.call(),
    );
  }
}

class CalcDropdown<T> extends StatelessWidget {
  const CalcDropdown({
    super.key,
    required this.value,
    required this.label,
    required this.items,
    required this.onChanged,
  });

  final T value;
  final String label;
  final List<DropdownMenuItem<T>> items;
  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<T>(
      value: value,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: items,
      onChanged: (value) {
        if (value != null) onChanged(value);
      },
    );
  }
}

class ResultHero extends StatelessWidget {
  const ResultHero({
    super.key,
    required this.eyebrow,
    required this.value,
    required this.caption,
    this.chips = const [],
  });

  final String eyebrow;
  final String value;
  final String caption;
  final List<String> chips;

  @override
  Widget build(BuildContext context) {
    return Container(
      clipBehavior: Clip.hardEdge,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(
          colors: [Color(0xFF064312), Color(0xFF0B6A22), SberColors.green],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
            color: SberColors.green.withOpacity(0.22),
            blurRadius: 24,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            right: -42,
            top: -58,
            child: Container(
              width: 150,
              height: 150,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withOpacity(0.06),
              ),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                eyebrow.toUpperCase(),
                style: const TextStyle(
                  color: Colors.white60,
                  fontSize: 10,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.8,
                ),
              ),
              const SizedBox(height: 5),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  value,
                  maxLines: 1,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 33,
                    height: 1.05,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -1.1,
                  ),
                ),
              ),
              const SizedBox(height: 5),
              Text(
                caption,
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 11.5,
                  height: 1.35,
                ),
              ),
              if (chips.isNotEmpty) ...[
                const SizedBox(height: 13),
                Wrap(
                  spacing: 7,
                  runSpacing: 7,
                  children: [
                    for (final chip in chips)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 9,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.white10,
                          borderRadius: BorderRadius.circular(999),
                          border: Border.all(color: Colors.white24),
                        ),
                        child: Text(
                          chip,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10.5,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class CalcMetric {
  const CalcMetric({
    required this.label,
    required this.value,
    this.accent,
    this.note,
  });

  final String label;
  final String value;
  final Color? accent;
  final String? note;
}

class MetricGrid extends StatelessWidget {
  const MetricGrid({super.key, required this.metrics});

  final List<CalcMetric> metrics;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = (constraints.maxWidth - 10) / 2;
        return Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            for (final metric in metrics)
              SizedBox(
                width: width,
                child: _MetricCard(metric: metric),
              ),
          ],
        );
      },
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.metric});

  final CalcMetric metric;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.fromLTRB(13, 12, 13, 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(17),
        color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.45),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withOpacity(0.45),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            metric.label,
            style: TextStyle(
              fontSize: 10,
              height: 1.25,
              fontWeight: FontWeight.w700,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            metric.value,
            style: TextStyle(
              fontSize: 14.5,
              height: 1.2,
              fontWeight: FontWeight.w800,
              color: metric.accent ?? theme.colorScheme.onSurface,
            ),
          ),
          if (metric.note != null) ...[
            const SizedBox(height: 3),
            Text(
              metric.note!,
              style: TextStyle(
                fontSize: 9.5,
                height: 1.25,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class TaxCard extends StatelessWidget {
  const TaxCard({super.key, required this.breakdown});

  final TaxBreakdown breakdown;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = breakdown.isRefund ? SberColors.green : kTaxAccent;
    final badge = breakdown.isRefund
        ? (breakdown.total == 0
              ? formatRub(0)
              : '−${formatRub(breakdown.total)}')
        : formatRub(breakdown.total);
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: BorderSide(color: accent.withOpacity(0.35)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(13),
                    color: accent.withOpacity(0.13),
                  ),
                  child: Icon(
                    Icons.receipt_long_outlined,
                    color: accent,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    breakdown.title,
                    style: theme.textTheme.titleMedium?.copyWith(fontSize: 15),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 9,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(999),
                    color: accent.withOpacity(0.12),
                  ),
                  child: Text(
                    badge,
                    style: TextStyle(
                      color: accent,
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            for (final row in breakdown.rows) _BreakdownRow(row: row),
            Divider(
              height: 18,
              color: theme.colorScheme.outlineVariant.withOpacity(0.6),
            ),
            Row(
              children: [
                Expanded(
                  child: Text(
                    breakdown.isRefund ? 'К возврату' : 'Итого налогов',
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
                Text(
                  breakdown.isRefund
                      ? (breakdown.total == 0
                            ? formatRub(0)
                            : '−${formatRub(breakdown.total)}')
                      : formatRub(breakdown.total),
                  style: TextStyle(fontWeight: FontWeight.w800, color: accent),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              breakdown.note,
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 10.5,
                height: 1.35,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class InflationCard extends StatelessWidget {
  const InflationCard({super.key, required this.breakdown});

  final InflationBreakdown breakdown;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final lossLabel = breakdown.loss >= 0
        ? '−${formatRub(breakdown.loss)}'
        : '+${formatRub(-breakdown.loss)}';
    final badgeText = breakdown.benefit != null
        ? '+${formatRub(breakdown.benefit!)}'
        : lossLabel;
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: BorderSide(color: kInflationAccent.withOpacity(0.3)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(13),
                    color: kInflationAccent.withOpacity(0.12),
                  ),
                  child: const Icon(
                    Icons.trending_down,
                    color: kInflationAccent,
                    size: 21,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Влияние инфляции',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontSize: 15,
                        ),
                      ),
                      Text(
                        '${breakdown.realLabel} ${formatPct(breakdown.realAnnualReturn)}',
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontSize: 10.5,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 9,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(999),
                    color: kInflationAccent.withOpacity(0.1),
                  ),
                  child: Text(
                    badgeText,
                    style: const TextStyle(
                      color: kInflationAccent,
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            for (final row in breakdown.rows) _BreakdownRow(row: row),
            const SizedBox(height: 8),
            Text(
              breakdown.note,
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 10.5,
                height: 1.35,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BreakdownRow extends StatelessWidget {
  const _BreakdownRow({required this.row});

  final CalcRow row;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final value = row.percent ? formatPct(row.value) : formatRub(row.value);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  row.label,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontSize: 11.5,
                    height: 1.3,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Text(
                value,
                style: const TextStyle(
                  fontSize: 11.5,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          if (row.note != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                row.note!,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontSize: 9.5,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class CalculatorDisclaimer extends StatelessWidget {
  const CalculatorDisclaimer({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          Icons.info_outline,
          size: 15,
          color: theme.colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 7),
        Expanded(
          child: Text(
            'Расчёт приблизительный и не является индивидуальной '
            'инвестиционной или налоговой рекомендацией. Ставки, лимиты '
            'и правила могут меняться.',
            style: theme.textTheme.bodySmall?.copyWith(
              fontSize: 10,
              height: 1.35,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
      ],
    );
  }
}
