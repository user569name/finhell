/// Баланс токенов, сессии rewarded-рекламы и результаты начисления.
class TokenStatus {
  const TokenStatus({
    required this.tokens,
    required this.calculationCost,
    required this.adReward,
    required this.adDurationSeconds,
    required this.adCooldownSeconds,
    required this.adDailyLimit,
    required this.adsToday,
    required this.adsRemaining,
    required this.cooldownRemainingSeconds,
    required this.canWatchAd,
    this.activeAdSession,
  });

  final int tokens;
  final int calculationCost;
  final int adReward;
  final int adDurationSeconds;
  final int adCooldownSeconds;
  final int adDailyLimit;
  final int adsToday;
  final int adsRemaining;
  final int cooldownRemainingSeconds;
  final bool canWatchAd;
  final ActiveAdSession? activeAdSession;

  factory TokenStatus.fromJson(Map<String, dynamic> json) {
    final active = json['active_ad_session'];
    return TokenStatus(
      tokens: _int(json['tokens']),
      calculationCost: _int(json['calculation_cost'], 1),
      adReward: _int(json['ad_reward'], 5),
      adDurationSeconds: _int(json['ad_duration_seconds'], 15),
      adCooldownSeconds: _int(json['ad_cooldown_seconds'], 30),
      adDailyLimit: _int(json['ad_daily_limit'], 20),
      adsToday: _int(json['ads_today']),
      adsRemaining: _int(json['ads_remaining']),
      cooldownRemainingSeconds: _int(json['cooldown_remaining_seconds']),
      canWatchAd: json['can_watch_ad'] == true,
      activeAdSession: active is Map<String, dynamic>
          ? ActiveAdSession.fromJson(active)
          : null,
    );
  }

  /// Копия статуса с обновлёнными полями (после начисления токенов).
  TokenStatus copyWith({
    int? tokens,
    int? calculationCost,
    int? adReward,
    int? adDurationSeconds,
    int? adCooldownSeconds,
    int? adDailyLimit,
    int? adsToday,
    int? adsRemaining,
    int? cooldownRemainingSeconds,
    bool? canWatchAd,
    ActiveAdSession? activeAdSession,
  }) {
    return TokenStatus(
      tokens: tokens ?? this.tokens,
      calculationCost: calculationCost ?? this.calculationCost,
      adReward: adReward ?? this.adReward,
      adDurationSeconds: adDurationSeconds ?? this.adDurationSeconds,
      adCooldownSeconds: adCooldownSeconds ?? this.adCooldownSeconds,
      adDailyLimit: adDailyLimit ?? this.adDailyLimit,
      adsToday: adsToday ?? this.adsToday,
      adsRemaining: adsRemaining ?? this.adsRemaining,
      cooldownRemainingSeconds:
          cooldownRemainingSeconds ?? this.cooldownRemainingSeconds,
      canWatchAd: canWatchAd ?? this.canWatchAd,
      activeAdSession: activeAdSession ?? this.activeAdSession,
    );
  }
}

class ActiveAdSession {
  const ActiveAdSession({
    required this.sessionId,
    required this.startedAt,
    required this.expiresAt,
    required this.secondsLeft,
  });

  final String sessionId;
  final double startedAt;
  final double expiresAt;
  final int secondsLeft;

  factory ActiveAdSession.fromJson(Map<String, dynamic> json) {
    return ActiveAdSession(
      sessionId: (json['session_id'] ?? '').toString(),
      startedAt: _double(json['started_at']),
      expiresAt: _double(json['expires_at']),
      secondsLeft: _int(json['seconds_left']),
    );
  }
}

class AdStartResult {
  const AdStartResult({
    required this.sessionId,
    required this.reward,
    required this.durationSeconds,
    required this.secondsLeft,
    required this.tokens,
    required this.resumed,
  });

  final String sessionId;
  final int reward;
  final int durationSeconds;
  final int secondsLeft;
  final int tokens;
  final bool resumed;

  factory AdStartResult.fromJson(Map<String, dynamic> json) {
    return AdStartResult(
      sessionId: (json['session_id'] ?? '').toString(),
      reward: _int(json['reward'], 5),
      durationSeconds: _int(json['duration_seconds'], 15),
      secondsLeft: _int(json['seconds_left']),
      tokens: _int(json['tokens']),
      resumed: json['resumed'] == true,
    );
  }
}

class AdCompleteResult {
  const AdCompleteResult({
    required this.sessionId,
    required this.reward,
    required this.tokens,
    required this.adsToday,
    required this.adsRemaining,
  });

  final String sessionId;
  final int reward;
  final int tokens;
  final int adsToday;
  final int adsRemaining;

  factory AdCompleteResult.fromJson(Map<String, dynamic> json) {
    return AdCompleteResult(
      sessionId: (json['session_id'] ?? '').toString(),
      reward: _int(json['reward'], 5),
      tokens: _int(json['tokens']),
      adsToday: _int(json['ads_today']),
      adsRemaining: _int(json['ads_remaining']),
    );
  }
}

int _int(dynamic value, [int fallback = 0]) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

double _double(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? 0;
}
