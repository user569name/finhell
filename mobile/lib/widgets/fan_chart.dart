import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../models/optimizer_models.dart';
import '../theme/sber_theme.dart';

/// «Веер» капитала: коридор P5–P95, медиана P50 и линия взносов.
class FanChart extends StatelessWidget {
  const FanChart({super.key, required this.option});

  final ScenarioOption option;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final series = [...option.monteCarlo.series]
      ..sort((left, right) => left.month.compareTo(right.month));
    if (series.length < 2) {
      return const SizedBox(
        height: 220,
        child: Center(child: Text('Недостаточно данных для графика')),
      );
    }

    final maxMonth = series.last.month;
    final maxYears = math.max(1, (maxMonth / 12).ceil());
    final peak = series
        .map((point) => math.max(point.p95, point.contributed))
        .reduce((left, right) => math.max(left, right));
    final maxY = math.max(1.0, peak * 1.08);
    final yInterval = maxY / 4;
    final yearStep = maxYears <= 5 ? 1 : (maxYears <= 12 ? 2 : 5);

    List<FlSpot> spots(double Function(SeriesPoint point) pick) {
      return series
          .map((point) => FlSpot(point.month / 12.0, pick(point)))
          .toList();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: 240,
          child: LineChart(
            LineChartData(
              minX: 0,
              maxX: maxYears.toDouble(),
              minY: 0,
              maxY: maxY,
              clipData: const FlClipData.all(),
              betweenBarsData: [
                BetweenBarsData(
                  fromIndex: 0,
                  toIndex: 2,
                  color: SberColors.green.withOpacity(0.16),
                ),
              ],
              lineBarsData: [
                LineChartBarData(
                  spots: spots((point) => point.p5),
                  isCurved: true,
                  curveSmoothness: 0.18,
                  color: Colors.transparent,
                  barWidth: 0,
                  dotData: const FlDotData(show: false),
                ),
                LineChartBarData(
                  spots: spots((point) => point.p50),
                  isCurved: true,
                  curveSmoothness: 0.18,
                  color: SberColors.green,
                  barWidth: 2.8,
                  isStrokeCapRound: true,
                  dotData: const FlDotData(show: false),
                ),
                LineChartBarData(
                  spots: spots((point) => point.p95),
                  isCurved: true,
                  curveSmoothness: 0.18,
                  color: Colors.transparent,
                  barWidth: 0,
                  dotData: const FlDotData(show: false),
                ),
                LineChartBarData(
                  spots: spots((point) => point.contributed),
                  isCurved: false,
                  color: theme.colorScheme.onSurfaceVariant.withOpacity(0.65),
                  barWidth: 1.4,
                  dashArray: [6, 4],
                  dotData: const FlDotData(show: false),
                ),
              ],
              titlesData: FlTitlesData(
                topTitles: const AxisTitles(
                  sideTitles: SideTitles(showTitles: false),
                ),
                rightTitles: const AxisTitles(
                  sideTitles: SideTitles(showTitles: false),
                ),
                leftTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 46,
                    interval: yInterval,
                    getTitlesWidget: (value, meta) {
                      if (value <= 0) return const SizedBox.shrink();
                      return Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: Text(
                          _compact(value),
                          style: TextStyle(
                            fontSize: 9,
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      );
                    },
                  ),
                ),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 26,
                    interval: yearStep.toDouble(),
                    getTitlesWidget: (value, meta) {
                      if (value < 0) return const SizedBox.shrink();
                      return Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          value == 0 ? '0' : '${value.round()} г.',
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
              gridData: FlGridData(
                show: true,
                drawVerticalLine: false,
                horizontalInterval: yInterval,
                getDrawingHorizontalLine: (value) => FlLine(
                  color: theme.colorScheme.outlineVariant.withOpacity(0.4),
                  strokeWidth: 1,
                  dashArray: [4, 4],
                ),
              ),
              borderData: FlBorderData(show: false),
            ),
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 14,
          runSpacing: 6,
          children: [
            _Legend(color: SberColors.green, text: 'Медиана P50'),
            _Legend(
              color: SberColors.green.withOpacity(0.3),
              text: 'Коридор P5–P95',
            ),
            _Legend(
              color: theme.colorScheme.onSurfaceVariant.withOpacity(0.6),
              text: 'Внесённые деньги',
              dashed: true,
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

class _Legend extends StatelessWidget {
  const _Legend({required this.color, required this.text, this.dashed = false});

  final Color color;
  final String text;
  final bool dashed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 16,
          height: 3,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          text,
          style: TextStyle(
            fontSize: 10,
            color: theme.colorScheme.onSurfaceVariant,
            decoration: dashed ? TextDecoration.underline : null,
            decorationStyle: dashed ? TextDecorationStyle.dashed : null,
          ),
        ),
      ],
    );
  }
}
