import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../models/optimizer_models.dart';
import '../theme/sber_theme.dart';
import 'risk_card.dart';

/// Гистограмма терминального капитала по 20 корзинам.
class HistogramChart extends StatelessWidget {
  const HistogramChart({super.key, required this.option});

  final ScenarioOption option;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final bins = option.monteCarlo.histogram;
    if (bins.isEmpty) {
      return const SizedBox(
        height: 200,
        child: Center(child: Text('Нет данных гистограммы')),
      );
    }
    final maxCount = math.max(
      1.0,
      bins.map((bin) => bin.count).reduce((left, right) => math.max(left, right)),
    );
    final p5 = option.monteCarlo.terminalP5;
    final p5Index = bins.indexWhere((bin) => bin.to >= p5);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 200,
          child: BarChart(
            BarChartData(
              alignment: BarChartAlignment.spaceAround,
              maxY: maxCount * 1.12,
              barTouchData: BarTouchData(enabled: false),
              extraLinesData: ExtraLinesData(
                verticalLines: p5Index < 0
                    ? const []
                    : [
                        VerticalLine(
                          x: p5Index.toDouble(),
                          color: SberColors.red,
                          strokeWidth: 1.4,
                          dashArray: [4, 4],
                        ),
                      ],
              ),
              titlesData: FlTitlesData(
                topTitles: const AxisTitles(
                  sideTitles: SideTitles(showTitles: false),
                ),
                rightTitles: const AxisTitles(
                  sideTitles: SideTitles(showTitles: false),
                ),
                leftTitles: const AxisTitles(
                  sideTitles: SideTitles(showTitles: false),
                ),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 26,
                    interval: 1,
                    getTitlesWidget: (value, meta) {
                      final index = value.round();
                      if (index < 0 || index >= bins.length) {
                        return const SizedBox.shrink();
                      }
                      if (index != 0 &&
                          index != bins.length ~/ 2 &&
                          index != bins.length - 1) {
                        return const SizedBox.shrink();
                      }
                      return Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          _compact(bins[index].to),
                          style: TextStyle(
                            fontSize: 9,
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
              gridData: const FlGridData(show: false),
              borderData: FlBorderData(show: false),
              barGroups: [
                for (var index = 0; index < bins.length; index++)
                  BarChartGroupData(
                    x: index,
                    barRods: [
                      BarChartRodData(
                        toY: bins[index].count,
                        width: 7,
                        color: bins[index].from < p5
                            ? SberColors.red.withOpacity(0.75)
                            : SberColors.green.withOpacity(
                                0.45 + 0.55 * (index / bins.length),
                              ),
                        borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(2),
                        ),
                      ),
                    ],
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 10,
          runSpacing: 6,
          children: [
            _Stat(label: 'P5', value: formatMoney(option.monteCarlo.terminalP5)),
            _Stat(label: 'P50', value: formatMoney(option.monteCarlo.terminalP50)),
            _Stat(label: 'P95', value: formatMoney(option.monteCarlo.terminalP95)),
            _Stat(
              label: 'Убыток',
              value: formatPercent(option.probabilityLoss, 0),
              color: SberColors.red,
            ),
          ],
        ),
      ],
    );
  }

  static String _compact(double value) {
    if (value >= 1000000) {
      return '${(value / 1000000).toStringAsFixed(1).replaceAll('.', ',')} млн';
    }
    if (value >= 1000) {
      return '${(value / 1000).toStringAsFixed(0)} тыс.';
    }
    return value.toStringAsFixed(0);
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value, this.color});

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.5),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '$label ',
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w800,
              color: color ?? theme.colorScheme.onSurface,
            ),
          ),
        ],
      ),
    );
  }
}
