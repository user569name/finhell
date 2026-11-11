/// Модели ответа оптимизатора v2.
///
/// Парсинг ручной, чтобы каркас не зависел от code generation.

double _asDouble(dynamic value, [double fallback = 0]) {
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value.replaceAll(',', '.')) ?? fallback;
  return fallback;
}

int _asInt(dynamic value, [int fallback = 0]) {
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? fallback;
  return fallback;
}

String _asString(dynamic value, [String fallback = '']) {
  return value is String ? value : fallback;
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return value.map((key, item) => MapEntry(key.toString(), item));
  return <String, dynamic>{};
}

List<dynamic> _asList(dynamic value) => value is List ? value : const [];

class DataPoint {
  final double value;
  final String source;
  final String updatedAt;
  final bool isFallback;
  final String? note;

  const DataPoint({
    required this.value,
    required this.source,
    required this.updatedAt,
    required this.isFallback,
    this.note,
  });

  factory DataPoint.fromJson(Map<String, dynamic> json) => DataPoint(
        value: _asDouble(json['value']),
        source: _asString(json['source']),
        updatedAt: _asString(json['updated_at']),
        isFallback: json['is_fallback'] == true,
        note: json['note'] as String?,
      );
}

class MacroSnapshot {
  final DataPoint keyRate;
  final DataPoint inflationExpected;
  final DataPoint depositRate;
  final DataPoint mortgageRate;
  final String fetchedAt;

  const MacroSnapshot({
    required this.keyRate,
    required this.inflationExpected,
    required this.depositRate,
    required this.mortgageRate,
    required this.fetchedAt,
  });

  factory MacroSnapshot.fromJson(Map<String, dynamic> json) {
    DataPoint point(String key) => DataPoint.fromJson(_asMap(json[key]));
    return MacroSnapshot(
      keyRate: point('key_rate'),
      inflationExpected: point('inflation_expected'),
      depositRate: point('deposit_rate'),
      mortgageRate: point('mortgage_rate'),
      fetchedAt: _asString(json['fetched_at']),
    );
  }
}

class AllocationItem {
  final String key;
  final String name;
  final double weight;
  final double amount;
  final double expectedReturn;

  const AllocationItem({
    required this.key,
    required this.name,
    required this.weight,
    required this.amount,
    required this.expectedReturn,
  });

  factory AllocationItem.fromJson(Map<String, dynamic> json) => AllocationItem(
        key: _asString(json['key']),
        name: _asString(json['name']),
        weight: _asDouble(json['weight']),
        amount: _asDouble(json['amount']),
        expectedReturn: _asDouble(json['expected_return']),
      );
}

class SeriesPoint {
  final int month;
  final double p5;
  final double p50;
  final double p95;
  final double contributed;

  const SeriesPoint({
    required this.month,
    required this.p5,
    required this.p50,
    required this.p95,
    required this.contributed,
  });

  factory SeriesPoint.fromJson(Map<String, dynamic> json) => SeriesPoint(
        month: _asInt(json['month']),
        p5: _asDouble(json['p5']),
        p50: _asDouble(json['p50']),
        p95: _asDouble(json['p95']),
        contributed: _asDouble(json['contributed']),
      );
}

class HistogramBin {
  final double from;
  final double to;
  final double count;

  const HistogramBin({required this.from, required this.to, required this.count});

  factory HistogramBin.fromJson(Map<String, dynamic> json) => HistogramBin(
        from: _asDouble(json['from']),
        to: _asDouble(json['to']),
        count: _asDouble(json['count']),
      );
}

class MonteCarloSummary {
  final int paths;
  final String distribution;
  final double terminalP5;
  final double terminalP25;
  final double terminalP50;
  final double terminalP75;
  final double terminalP95;
  final double realTerminalP50;
  final double totalContributions;
  final double? probabilityGoal;
  final double probabilityLoss;
  final double var95;
  final double cvar95;
  final double maxDrawdownMedian;
  final List<SeriesPoint> series;
  final List<HistogramBin> histogram;

  const MonteCarloSummary({
    required this.paths,
    required this.distribution,
    required this.terminalP5,
    required this.terminalP25,
    required this.terminalP50,
    required this.terminalP75,
    required this.terminalP95,
    required this.realTerminalP50,
    required this.totalContributions,
    required this.probabilityGoal,
    required this.probabilityLoss,
    required this.var95,
    required this.cvar95,
    required this.maxDrawdownMedian,
    required this.series,
    required this.histogram,
  });

  factory MonteCarloSummary.fromJson(Map<String, dynamic> json) {
    final goal = json['probability_goal'];
    return MonteCarloSummary(
      paths: _asInt(json['paths']),
      distribution: _asString(json['distribution']),
      terminalP5: _asDouble(json['terminal_p5']),
      terminalP25: _asDouble(json['terminal_p25']),
      terminalP50: _asDouble(json['terminal_p50']),
      terminalP75: _asDouble(json['terminal_p75']),
      terminalP95: _asDouble(json['terminal_p95']),
      realTerminalP50: _asDouble(json['real_terminal_p50']),
      totalContributions: _asDouble(json['total_contributions']),
      probabilityGoal: goal is num ? goal.toDouble() : null,
      probabilityLoss: _asDouble(json['probability_loss']),
      var95: _asDouble(json['var_95']),
      cvar95: _asDouble(json['cvar_95']),
      maxDrawdownMedian: _asDouble(json['max_drawdown_median']),
      series: _asList(json['series'])
          .map((item) => SeriesPoint.fromJson(_asMap(item)))
          .toList(),
      histogram: _asList(json['histogram'])
          .map((item) => HistogramBin.fromJson(_asMap(item)))
          .toList(),
    );
  }
}

class StressItem {
  final String scenario;
  final double impactP50;
  final double impactP5;
  final double terminalP50;
  final String note;

  const StressItem({
    required this.scenario,
    required this.impactP50,
    required this.impactP5,
    required this.terminalP50,
    required this.note,
  });

  factory StressItem.fromJson(Map<String, dynamic> json) => StressItem(
        scenario: _asString(json['scenario']),
        impactP50: _asDouble(json['impact_p50']),
        impactP5: _asDouble(json['impact_p5']),
        terminalP50: _asDouble(json['terminal_p50']),
        note: _asString(json['note']),
      );
}

class TaxSummary {
  final double annualTax;
  final double totalTaxEstimate;
  final double effectiveRate;
  final double deductions;
  final String note;

  const TaxSummary({
    required this.annualTax,
    required this.totalTaxEstimate,
    required this.effectiveRate,
    required this.deductions,
    required this.note,
  });

  factory TaxSummary.fromJson(Map<String, dynamic> json) => TaxSummary(
        annualTax: _asDouble(json['annual_tax']),
        totalTaxEstimate: _asDouble(json['total_tax_estimate']),
        effectiveRate: _asDouble(json['effective_rate']),
        deductions: _asDouble(json['deductions']),
        note: _asString(json['note']),
      );
}

class FeeSummary {
  final double annualFee;
  final double totalFeeEstimate;
  final double effectiveRate;
  final String note;

  const FeeSummary({
    required this.annualFee,
    required this.totalFeeEstimate,
    required this.effectiveRate,
    required this.note,
  });

  factory FeeSummary.fromJson(Map<String, dynamic> json) => FeeSummary(
        annualFee: _asDouble(json['annual_fee']),
        totalFeeEstimate: _asDouble(json['total_fee_estimate']),
        effectiveRate: _asDouble(json['effective_rate']),
        note: _asString(json['note']),
      );
}

class ScenarioOption {
  final String id;
  final String name;
  final String riskLevel;
  final String description;
  final double expectedReturnNominal;
  final double expectedReturnReal;
  final double afterTaxReturn;
  final double volatility;
  final double sharpe;
  final double sortino;
  final double var95;
  final double cvar95;
  final double maxDrawdown;
  final double? probabilityGoal;
  final double probabilityLoss;
  final double liquidity;
  final String liquidityLabel;
  final double durationYears;
  final double npv;
  final double? irr;
  final double score;
  final int rank;
  final String whyRecommended;
  final List<String> tags;
  final List<AllocationItem> allocation;
  final MonteCarloSummary monteCarlo;
  final List<StressItem> stressTests;
  final TaxSummary taxes;
  final FeeSummary fees;

  const ScenarioOption({
    required this.id,
    required this.name,
    required this.riskLevel,
    required this.description,
    required this.expectedReturnNominal,
    required this.expectedReturnReal,
    required this.afterTaxReturn,
    required this.volatility,
    required this.sharpe,
    required this.sortino,
    required this.var95,
    required this.cvar95,
    required this.maxDrawdown,
    required this.probabilityGoal,
    required this.probabilityLoss,
    required this.liquidity,
    required this.liquidityLabel,
    required this.durationYears,
    required this.npv,
    required this.irr,
    required this.score,
    required this.rank,
    required this.whyRecommended,
    required this.tags,
    required this.allocation,
    required this.monteCarlo,
    required this.stressTests,
    required this.taxes,
    required this.fees,
  });

  factory ScenarioOption.fromJson(Map<String, dynamic> json) {
    final goal = json['probability_goal'];
    final irr = json['irr'];
    return ScenarioOption(
      id: _asString(json['id']),
      name: _asString(json['name']),
      riskLevel: _asString(json['risk_level']),
      description: _asString(json['description']),
      expectedReturnNominal: _asDouble(json['expected_return_nominal']),
      expectedReturnReal: _asDouble(json['expected_return_real']),
      afterTaxReturn: _asDouble(json['after_tax_return']),
      volatility: _asDouble(json['volatility']),
      sharpe: _asDouble(json['sharpe']),
      sortino: _asDouble(json['sortino']),
      var95: _asDouble(json['var_95']),
      cvar95: _asDouble(json['cvar_95']),
      maxDrawdown: _asDouble(json['max_drawdown']),
      probabilityGoal: goal is num ? goal.toDouble() : null,
      probabilityLoss: _asDouble(json['probability_loss']),
      liquidity: _asDouble(json['liquidity']),
      liquidityLabel: _asString(json['liquidity_label']),
      durationYears: _asDouble(json['duration_years']),
      npv: _asDouble(json['npv']),
      irr: irr is num ? irr.toDouble() : null,
      score: _asDouble(json['score']),
      rank: _asInt(json['rank']),
      whyRecommended: _asString(json['why_recommended']),
      tags: _asList(json['tags']).map((item) => item.toString()).toList(),
      allocation: _asList(json['allocation'])
          .map((item) => AllocationItem.fromJson(_asMap(item)))
          .toList(),
      monteCarlo: MonteCarloSummary.fromJson(_asMap(json['monte_carlo'])),
      stressTests: _asList(json['stress_tests'])
          .map((item) => StressItem.fromJson(_asMap(item)))
          .toList(),
      taxes: TaxSummary.fromJson(_asMap(json['taxes'])),
      fees: FeeSummary.fromJson(_asMap(json['fees'])),
    );
  }
}

class RiskProfile {
  final String label;
  final String description;
  final String? bestOptionId;
  final List<ScenarioOption> options;

  const RiskProfile({
    required this.label,
    required this.description,
    required this.bestOptionId,
    required this.options,
  });

  factory RiskProfile.fromJson(Map<String, dynamic> json) => RiskProfile(
        label: _asString(json['label']),
        description: _asString(json['description']),
        bestOptionId: json['best_option_id'] as String?,
        options: _asList(json['options'])
            .map((item) => ScenarioOption.fromJson(_asMap(item)))
            .toList(),
      );
}

class AiExplanation {
  final String summary;
  final Map<String, String> riskProfiles;
  final List<String> steps;
  final String why;
  final String risks;
  final String disclaimer;
  final String generatedBy;

  const AiExplanation({
    required this.summary,
    required this.riskProfiles,
    required this.steps,
    required this.why,
    required this.risks,
    required this.disclaimer,
    required this.generatedBy,
  });

  factory AiExplanation.fromJson(Map<String, dynamic> json) {
    final rawRisks = _asMap(json['risk_profiles']);
    return AiExplanation(
      summary: _asString(json['summary']),
      riskProfiles: rawRisks.map(
        (key, value) => MapEntry(key, value is String ? value : value.toString()),
      ),
      steps: _asList(json['steps']).map((item) => item.toString()).toList(),
      why: _asString(json['why']),
      risks: _asString(json['risks']),
      disclaimer: _asString(json['disclaimer']),
      generatedBy: _asString(json['generated_by'], 'template'),
    );
  }
}

class OptimizeResult {
  final String contextId;
  final String generatedAt;
  final MacroSnapshot macro;
  final Map<String, RiskProfile> riskProfiles;
  final List<ScenarioOption> topOptions;
  final AiExplanation aiTemplate;
  final List<String> warnings;
  final String disclaimer;

  const OptimizeResult({
    required this.contextId,
    required this.generatedAt,
    required this.macro,
    required this.riskProfiles,
    required this.topOptions,
    required this.aiTemplate,
    required this.warnings,
    required this.disclaimer,
  });

  factory OptimizeResult.fromJson(Map<String, dynamic> json) {
    final rawProfiles = _asMap(json['risk_profiles']);
    return OptimizeResult(
      contextId: _asString(json['context_id']),
      generatedAt: _asString(json['generated_at']),
      macro: MacroSnapshot.fromJson(_asMap(json['macro'])),
      riskProfiles: rawProfiles.map(
        (key, value) => MapEntry(key, RiskProfile.fromJson(_asMap(value))),
      ),
      topOptions: _asList(json['top_options'])
          .map((item) => ScenarioOption.fromJson(_asMap(item)))
          .toList(),
      aiTemplate: AiExplanation.fromJson(_asMap(json['ai_template'])),
      warnings: _asList(json['warnings']).map((item) => item.toString()).toList(),
      disclaimer: _asString(json['disclaimer']),
    );
  }
}

class JobStatus {
  final String jobId;
  final String status;
  final int progress;
  final String message;
  final OptimizeResult? result;
  final String? error;

  const JobStatus({
    required this.jobId,
    required this.status,
    required this.progress,
    required this.message,
    required this.result,
    required this.error,
  });

  factory JobStatus.fromJson(Map<String, dynamic> json) => JobStatus(
        jobId: _asString(json['job_id']),
        status: _asString(json['status']),
        progress: _asInt(json['progress']),
        message: _asString(json['message']),
        result: json['result'] is Map
            ? OptimizeResult.fromJson(_asMap(json['result']))
            : null,
        error: json['error'] as String?,
      );
}

class ChatResponse {
  final String answer;
  final String generatedBy;

  const ChatResponse({required this.answer, required this.generatedBy});

  factory ChatResponse.fromJson(Map<String, dynamic> json) => ChatResponse(
        answer: _asString(json['answer']),
        generatedBy: _asString(json['generated_by'], 'template'),
      );
}
