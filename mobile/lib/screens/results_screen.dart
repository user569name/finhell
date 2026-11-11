import 'package:flutter/material.dart';

import '../models/optimizer_models.dart';
import '../services/api_client.dart';
import '../theme/sber_theme.dart';
import '../widgets/ai_chat.dart';
import '../widgets/fan_chart.dart';
import '../widgets/histogram_chart.dart';
import '../widgets/risk_card.dart';

class ResultsScreen extends StatefulWidget {
  const ResultsScreen({
    super.key,
    required this.api,
    required this.result,
    required this.onToggleTheme,
  });

  final ApiClient api;
  final OptimizeResult result;
  final VoidCallback onToggleTheme;

  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  late List<ScenarioOption> _options;
  ScenarioOption? _selected;
  int _stressIndex = 0;

  @override
  void initState() {
    super.initState();
    _options = _collectOptions(widget.result);
    _selected = _options.isEmpty ? null : _options.first;
  }

  static List<ScenarioOption> _collectOptions(OptimizeResult result) {
    if (result.topOptions.isNotEmpty) return result.topOptions;
    final all = <ScenarioOption>[];
    for (final level in ['low', 'medium', 'high']) {
      final profile = result.riskProfiles[level];
      if (profile != null) all.addAll(profile.options);
    }
    return all;
  }

  void _select(ScenarioOption option) {
    setState(() {
      _selected = option;
      _stressIndex = 0;
    });
  }

  Future<void> _openProfile(RiskProfile profile) async {
    final theme = Theme.of(context);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: theme.colorScheme.surface,
      builder: (sheetContext) {
        return FractionallySizedBox(
          heightFactor: 0.9,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 28),
            children: [
              Text(
                '${profile.label} — все сценарии',
                style: theme.textTheme.headlineSmall,
              ),
              const SizedBox(height: 4),
              Text(
                profile.description,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 14),
              for (final option in profile.options)
                Card(
                  margin: const EdgeInsets.only(bottom: 10),
                  child: ListTile(
                    contentPadding: const EdgeInsets.fromLTRB(14, 8, 6, 8),
                    onTap: () {
                      Navigator.of(sheetContext).pop();
                      _select(option);
                    },
                    title: Text(
                      option.name,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    subtitle: Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        '${formatPercent(option.expectedReturnNominal)} · '
                        'P50 ${formatMoney(option.monteCarlo.terminalP50)} · '
                        'Sharpe ${option.sharpe.toStringAsFixed(2).replaceAll('.', ',')}',
                      ),
                    ),
                    trailing: IconButton(
                      tooltip: 'Подробнее',
                      icon: const Icon(Icons.info_outline, size: 20),
                      onPressed: () {
                        Navigator.of(sheetContext).pop();
                        Future<void>.delayed(
                          Duration.zero,
                          () => _openOptionDetails(option),
                        );
                      },
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _openOptionDetails(ScenarioOption option) async {
    final theme = Theme.of(context);
    final metrics = <(String, String)>[
      ('Доходность', formatPercent(option.expectedReturnNominal)),
      ('Реальная', formatPercent(option.expectedReturnReal)),
      ('После налогов', formatPercent(option.afterTaxReturn)),
      ('Волатильность', formatPercent(option.volatility)),
      ('Sharpe', option.sharpe.toStringAsFixed(2).replaceAll('.', ',')),
      ('Sortino', option.sortino.toStringAsFixed(2).replaceAll('.', ',')),
      ('VaR 95', formatPercent(option.var95)),
      ('CVaR 95', formatPercent(option.cvar95)),
      ('Просадка', formatPercent(option.maxDrawdown)),
      ('Дюрация', '${option.durationYears.toStringAsFixed(1).replaceAll('.', ',')} г.'),
      ('NPV', formatMoney(option.npv)),
      ('IRR', option.irr == null ? '—' : formatPercent(option.irr!)),
      ('P5', formatMoney(option.monteCarlo.terminalP5)),
      ('P50', formatMoney(option.monteCarlo.terminalP50)),
      ('P95', formatMoney(option.monteCarlo.terminalP95)),
      ('Цель', option.probabilityGoal == null
          ? '—'
          : formatPercent(option.probabilityGoal!, 0)),
    ];

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: theme.colorScheme.surface,
      builder: (sheetContext) {
        return FractionallySizedBox(
          heightFactor: 0.92,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 30),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(option.name, style: theme.textTheme.headlineSmall),
                  ),
                  _RiskBadge(level: option.riskLevel),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                option.description,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 14),
              _DetailSection(
                title: 'Ключевые метрики',
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final width = (constraints.maxWidth - 10) / 2;
                    return Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        for (final metric in metrics)
                          SizedBox(
                            width: width,
                            child: _DetailMetric(
                              label: metric.$1,
                              value: metric.$2,
                            ),
                          ),
                      ],
                    );
                  },
                ),
              ),
              _DetailSection(
                title: 'Состав портфеля',
                child: Column(
                  children: [
                    for (final item in option.allocation)
                      _AllocationRow(item: item),
                  ],
                ),
              ),
              _DetailSection(
                title: 'Налоги и вычеты',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _KeyValue(
                      label: 'Годовой налог',
                      value: formatMoney(option.taxes.annualTax),
                    ),
                    _KeyValue(
                      label: 'Налог за горизонт',
                      value: formatMoney(option.taxes.totalTaxEstimate),
                    ),
                    _KeyValue(
                      label: 'Эффективная ставка',
                      value: formatPercent(option.taxes.effectiveRate),
                    ),
                    _KeyValue(
                      label: 'Вычеты',
                      value: formatMoney(option.taxes.deductions),
                    ),
                    if (option.taxes.note.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          option.taxes.note,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              _DetailSection(
                title: 'Комиссии',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _KeyValue(
                      label: 'Годовые комиссии',
                      value: formatMoney(option.fees.annualFee),
                    ),
                    _KeyValue(
                      label: 'За горизонт',
                      value: formatMoney(option.fees.totalFeeEstimate),
                    ),
                    _KeyValue(
                      label: 'Эффективная ставка',
                      value: formatPercent(option.fees.effectiveRate),
                    ),
                    if (option.fees.note.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          option.fees.note,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              _DetailSection(
                title: 'Стресс-тесты',
                child: Column(
                  children: [
                    for (final stress in option.stressTests)
                      _StressRow(stress: stress, compact: true),
                  ],
                ),
              ),
              if (option.whyRecommended.isNotEmpty)
                _DetailSection(
                  title: 'Почему этот сценарий',
                  child: Text(option.whyRecommended),
                ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final selected = _selected;
    final best = _options.isEmpty ? null : _options.first;
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Результаты расчёта'),
        actions: [
          IconButton(
            tooltip: 'Светлая / тёмная тема',
            onPressed: widget.onToggleTheme,
            icon: Icon(
              theme.brightness == Brightness.dark
                  ? Icons.light_mode
                  : Icons.dark_mode,
            ),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
          children: [
            if (best != null) _hero(best),
            if (widget.result.warnings.isNotEmpty) ...[
              const SizedBox(height: 12),
              _warningsCard(theme),
            ],
            const SizedBox(height: 12),
            _macroCard(theme),
            const SizedBox(height: 22),
            _sectionHeader(
              theme,
              'Три уровня риска',
              'Одинаковые макроданные, разные компромиссы',
            ),
            for (final level in ['low', 'medium', 'high'])
              if (widget.result.riskProfiles[level] != null) ...[
                RiskCard(
                  profile: widget.result.riskProfiles[level]!,
                  onOpen: () => _openProfile(widget.result.riskProfiles[level]!),
                ),
                const SizedBox(height: 10),
              ],
            const SizedBox(height: 10),
            _sectionHeader(
              theme,
              'Коридор капитала',
              'P5–P95 и медиана по выбранному сценарию',
            ),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: selected == null
                    ? const Text('Нет сценариев для графика')
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _chartSelector(theme, selected),
                          const SizedBox(height: 14),
                          FanChart(option: selected),
                        ],
                      ),
              ),
            ),
            const SizedBox(height: 10),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: selected == null
                    ? const SizedBox.shrink()
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Распределение капитала',
                            style: theme.textTheme.titleMedium,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${selected.monteCarlo.paths} путей · '
                            'капитал через ${_horizonLabel(selected)}',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(height: 12),
                          HistogramChart(option: selected),
                        ],
                      ),
              ),
            ),
            const SizedBox(height: 22),
            _sectionHeader(
              theme,
              'Топ сценариев',
              'Нажмите на строку, чтобы увидеть состав и налоги',
            ),
            Card(
              clipBehavior: Clip.antiAlias,
              child: Column(
                children: [
                  for (var index = 0; index < _options.length; index++) ...[
                    _TopRow(
                      option: _options[index],
                      onTap: () => _openOptionDetails(_options[index]),
                      onChart: () => _select(_options[index]),
                      isSelected: selected?.id == _options[index].id,
                    ),
                    if (index != _options.length - 1)
                      Divider(
                        height: 1,
                        color: theme.colorScheme.outlineVariant.withOpacity(0.5),
                      ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 22),
            _sectionHeader(
              theme,
              'Стресс-тесты',
              'Что будет при шоках ставки, инфляции и налогов',
            ),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: selected == null
                    ? const SizedBox.shrink()
                    : selected.stressTests.isEmpty
                        ? const Text('Для этого сценария стресс-тесты отключены.')
                        : Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              DropdownButtonFormField<int>(
                                value: _stressIndex < selected.stressTests.length
                                    ? _stressIndex
                                    : 0,
                                decoration: const InputDecoration(
                                  labelText: 'Сценарий',
                                ),
                                items: [
                                  for (var index = 0;
                                      index < selected.stressTests.length;
                                      index++)
                                    DropdownMenuItem(
                                      value: index,
                                      child: Text(
                                        selected.stressTests[index].scenario,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                ],
                                onChanged: (value) {
                                  if (value != null) {
                                    setState(() => _stressIndex = value);
                                  }
                                },
                              ),
                              const SizedBox(height: 12),
                              for (var index = 0;
                                  index < selected.stressTests.length;
                                  index++)
                                _StressRow(
                                  stress: selected.stressTests[index],
                                  highlighted: index ==
                                      (_stressIndex < selected.stressTests.length
                                          ? _stressIndex
                                          : 0),
                                ),
                            ],
                          ),
              ),
            ),
            const SizedBox(height: 22),
            _sectionHeader(
              theme,
              'AI-объяснение',
              'Сгенерировано по детерминированному контексту расчёта',
            ),
            _aiCard(theme),
            if (widget.result.contextId.isNotEmpty) ...[
              const SizedBox(height: 12),
              AiChat(
                api: widget.api,
                contextId: widget.result.contextId,
                welcome: best == null
                    ? null
                    : 'Расчёт готов. Лучший сценарий — «${best.name}»: '
                        'ожидаемая доходность ${formatPercent(best.expectedReturnNominal)}, '
                        'медианный капитал ${formatMoney(best.monteCarlo.terminalP50)}. '
                        'Спросите про риски, налоги, ставку или сравнение сценариев.',
              ),
            ],
            const SizedBox(height: 14),
            Text(
              widget.result.disclaimer.isNotEmpty
                  ? widget.result.disclaimer
                  : 'Это не индивидуальная инвестиционная рекомендация.',
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 10,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _hero(ScenarioOption best) {
    final years = _horizonLabel(best);
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: const LinearGradient(
          colors: [Color(0xFF064312), Color(0xFF0B6A22), SberColors.green],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
            color: SberColors.green.withOpacity(0.24),
            blurRadius: 30,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: Colors.white12,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: Colors.white24),
                ),
                child: Text(
                  riskLabel(best.riskLevel).toUpperCase(),
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 9,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
              const Spacer(),
              Text(
                'ТОП-${best.rank}',
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Text(
            'ЛУЧШИЙ СЦЕНАРИЙ',
            style: TextStyle(
              color: Colors.white60,
              fontSize: 10,
              fontWeight: FontWeight.w700,
              letterSpacing: 1,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            best.name,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 24,
              height: 1.1,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.8,
            ),
          ),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                formatPercent(best.expectedReturnNominal),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 38,
                  height: 1,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -1.5,
                ),
              ),
              const SizedBox(width: 8),
              const Padding(
                padding: EdgeInsets.only(bottom: 4),
                child: Text(
                  'годовых',
                  style: TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Медианный капитал через $years: '
            '${formatMoney(best.monteCarlo.terminalP50)}',
            style: const TextStyle(color: Colors.white70, height: 1.4),
          ),
          const SizedBox(height: 16),
          Container(height: 1, color: Colors.white24),
          const SizedBox(height: 14),
          Row(
            children: [
              _HeroMetric(
                label: 'P5',
                value: formatMoney(best.monteCarlo.terminalP5),
              ),
              const SizedBox(width: 18),
              _HeroMetric(
                label: 'Цель',
                value: best.probabilityGoal == null
                    ? '—'
                    : formatPercent(best.probabilityGoal!, 0),
              ),
              const SizedBox(width: 18),
              _HeroMetric(
                label: 'Просадка',
                value: formatPercent(best.maxDrawdown, 0),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _warningsCard(ThemeData theme) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: SberColors.amber.withOpacity(0.1),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: SberColors.amber.withOpacity(0.3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline, color: SberColors.amber, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final warning in widget.result.warnings)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      warning,
                      style: theme.textTheme.bodySmall?.copyWith(height: 1.4),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _macroCard(ThemeData theme) {
    final macro = widget.result.macro;
    final tiles = <(String, DataPoint)>[
      ('Ключевая ставка', macro.keyRate),
      ('Инфляция (ожид.)', macro.inflationExpected),
      ('Средний вклад', macro.depositRate),
      ('Ипотека', macro.mortgageRate),
    ];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Макроданные', style: theme.textTheme.titleMedium),
                const Spacer(),
                Text(
                  'источник и время',
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontSize: 10,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            LayoutBuilder(
              builder: (context, constraints) {
                final width = (constraints.maxWidth - 10) / 2;
                return Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    for (final tile in tiles)
                      SizedBox(
                        width: width,
                        child: _MacroTile(label: tile.$1, point: tile.$2),
                      ),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _chartSelector(ThemeData theme, ScenarioOption selected) {
    final items = [..._options];
    if (!items.any((option) => option.id == selected.id)) {
      items.add(selected);
    }
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Сценарий на графике', style: theme.textTheme.titleMedium),
              const SizedBox(height: 2),
              Text(
                'P5 ${formatMoney(selected.monteCarlo.terminalP5)} · '
                'P50 ${formatMoney(selected.monteCarlo.terminalP50)} · '
                'P95 ${formatMoney(selected.monteCarlo.terminalP95)}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        DropdownButton<String>(
          value: selected.id,
          underline: const SizedBox.shrink(),
          items: [
            for (final option in items)
              DropdownMenuItem(
                value: option.id,
                child: SizedBox(
                  width: 120,
                  child: Text(
                    option.name,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12),
                  ),
                ),
              ),
          ],
          onChanged: (id) {
            ScenarioOption? option;
            for (final item in items) {
              if (item.id == id) {
                option = item;
                break;
              }
            }
            if (option != null) _select(option);
          },
        ),
      ],
    );
  }

  Widget _sectionHeader(ThemeData theme, String title, String subtitle) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: theme.textTheme.headlineSmall),
          const SizedBox(height: 2),
          Text(
            subtitle,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _aiCard(ThemeData theme) {
    final explanation = widget.result.aiTemplate;
    final order = ['low', 'medium', 'high'];
    final labels = {
      'low': 'Низкий риск',
      'medium': 'Средний риск',
      'high': 'Высокий риск',
    };
    final colors = {
      'low': SberColors.green,
      'medium': SberColors.amber,
      'high': SberColors.red,
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: SberColors.green.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(
                    Icons.auto_awesome,
                    color: SberColors.green,
                    size: 18,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Что важно знать',
                    style: theme.textTheme.titleMedium,
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    explanation.generatedBy == 'template' ? 'шаблон' : 'LLM',
                    style: TextStyle(
                      fontSize: 9,
                      fontWeight: FontWeight.w700,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(explanation.summary, style: theme.textTheme.bodyMedium),
            if (explanation.riskProfiles.isNotEmpty) ...[
              const SizedBox(height: 14),
              for (final level in order)
                if (explanation.riskProfiles[level] != null)
                  Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                    decoration: BoxDecoration(
                      color: colors[level]!.withOpacity(0.06),
                      borderRadius: BorderRadius.circular(12),
                      border: Border(
                        left: BorderSide(color: colors[level]!, width: 3),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          labels[level]!,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w800,
                            color: colors[level],
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          explanation.riskProfiles[level]!,
                          style: theme.textTheme.bodySmall?.copyWith(height: 1.4),
                        ),
                      ],
                    ),
                  ),
            ],
            if (explanation.steps.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text('Шаги', style: theme.textTheme.titleSmall),
              const SizedBox(height: 6),
              for (var index = 0; index < explanation.steps.length; index++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 20,
                        height: 20,
                        margin: const EdgeInsets.only(top: 1),
                        decoration: BoxDecoration(
                          color: SberColors.green.withOpacity(0.1),
                          shape: BoxShape.circle,
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          '${index + 1}',
                          style: const TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w800,
                            color: SberColors.green,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          explanation.steps[index],
                          style: theme.textTheme.bodySmall?.copyWith(height: 1.4),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
            if (explanation.why.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text('Почему так', style: theme.textTheme.titleSmall),
              const SizedBox(height: 4),
              Text(explanation.why, style: theme.textTheme.bodySmall),
            ],
            if (explanation.risks.isNotEmpty) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: SberColors.amber.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.warning_amber_rounded,
                      color: SberColors.amber,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        explanation.risks,
                        style: theme.textTheme.bodySmall?.copyWith(height: 1.4),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 10),
            Text(
              explanation.disclaimer,
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 10,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _horizonLabel(ScenarioOption option) {
    if (option.monteCarlo.series.isEmpty) return 'горизонт';
    final months = option.monteCarlo.series.last.month;
    final years = months / 12.0;
    if (years >= 1 && years == years.roundToDouble()) {
      final count = years.round();
      final mod10 = count % 10;
      final mod100 = count % 100;
      final word = mod10 == 1 && mod100 != 11
          ? 'год'
          : (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
              ? 'года'
              : 'лет');
      return '$count $word';
    }
    return '${years.toStringAsFixed(1).replaceAll('.', ',')} года';
  }
}

class _HeroMetric extends StatelessWidget {
  const _HeroMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: Colors.white54,
              fontSize: 9,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}

class _RiskBadge extends StatelessWidget {
  const _RiskBadge({required this.level});

  final String level;

  @override
  Widget build(BuildContext context) {
    final color = riskColor(level);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        riskLabel(level),
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w800,
          color: color,
        ),
      ),
    );
  }
}

class _MacroTile extends StatelessWidget {
  const _MacroTile({required this.label, required this.point});

  final String label;
  final DataPoint point;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final date = point.updatedAt.length >= 10
        ? point.updatedAt.substring(0, 10)
        : point.updatedAt;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.4),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
              if (point.isFallback)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                  decoration: BoxDecoration(
                    color: SberColors.amber.withOpacity(0.16),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    'демо',
                    style: TextStyle(
                      fontSize: 8,
                      fontWeight: FontWeight.w700,
                      color: SberColors.amber,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            formatPercent(point.value),
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 2),
          Text(
            '${point.source} · $date',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 9,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _TopRow extends StatelessWidget {
  const _TopRow({
    required this.option,
    required this.onTap,
    required this.onChart,
    required this.isSelected,
  });

  final ScenarioOption option;
  final VoidCallback onTap;
  final VoidCallback onChart;
  final bool isSelected;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = riskColor(option.riskLevel);
    return InkWell(
      onTap: onTap,
      child: Container(
        color: isSelected ? SberColors.green.withOpacity(0.05) : null,
        padding: const EdgeInsets.fromLTRB(12, 11, 4, 11),
        child: Row(
          children: [
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                shape: BoxShape.circle,
              ),
              alignment: Alignment.center,
              child: Text(
                '${option.rank}',
                style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    option.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Row(
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                      ),
                      const SizedBox(width: 5),
                      Text(
                        riskLabel(option.riskLevel),
                        style: TextStyle(
                          fontSize: 9,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'P50 ${formatMoney(option.monteCarlo.terminalP50)}',
                        style: TextStyle(
                          fontSize: 9,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  formatPercent(option.expectedReturnNominal),
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: SberColors.green,
                  ),
                ),
                Text(
                  'Sharpe ${option.sharpe.toStringAsFixed(2).replaceAll('.', ',')}',
                  style: TextStyle(
                    fontSize: 9,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            IconButton(
              tooltip: 'Показать на графике',
              onPressed: onChart,
              icon: Icon(
                Icons.show_chart,
                size: 18,
                color: isSelected
                    ? SberColors.green
                    : theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StressRow extends StatelessWidget {
  const _StressRow({
    required this.stress,
    this.highlighted = false,
    this.compact = false,
  });

  final StressItem stress;
  final bool highlighted;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final negative = stress.impactP50 < 0;
    final color = negative ? SberColors.red : SberColors.green;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(10, 9, 10, 9),
      decoration: BoxDecoration(
        color: highlighted
            ? color.withOpacity(0.07)
            : theme.colorScheme.surfaceContainerHighest.withOpacity(0.3),
        borderRadius: BorderRadius.circular(12),
        border: highlighted ? Border.all(color: color.withOpacity(0.3)) : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  stress.scenario,
                  style: TextStyle(
                    fontSize: compact ? 11 : 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '${stress.impactP50 >= 0 ? '+' : ''}'
                '${formatPercent(stress.impactP50)}',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  color: color,
                ),
              ),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            'P50 ${formatMoney(stress.terminalP50)} · '
            'P5 ${formatPercent(stress.impactP5)}',
            style: TextStyle(
              fontSize: 9,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (!compact && stress.note.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              stress.note,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 9,
                height: 1.35,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _DetailSection extends StatelessWidget {
  const _DetailSection({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          child,
        ],
      ),
    );
  }
}

class _DetailMetric extends StatelessWidget {
  const _DetailMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(11),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.4),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 9,
              fontWeight: FontWeight.w700,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }
}

class _AllocationRow extends StatelessWidget {
  const _AllocationRow({required this.item});

  final AllocationItem item;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = kAssetColors[item.key] ?? SberColors.green;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Container(
            width: 9,
            height: 9,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              item.name,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
          Text(
            formatMoney(item.amount),
            style: TextStyle(
              fontSize: 10,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: 44,
            child: Text(
              formatPercent(item.weight, 0),
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800),
            ),
          ),
        ],
      ),
    );
  }
}

class _KeyValue extends StatelessWidget {
  const _KeyValue({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Text(
            value,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
