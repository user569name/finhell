import 'dart:async';

import 'package:flutter/material.dart';

import '../models/token_models.dart';
import '../services/api_client.dart';
import '../theme/sber_theme.dart';

/// Зачем открыли окно рекламы.
enum AdDialogReason {
  /// Пользователь сам нажал «Смотреть рекламу».
  manual,

  /// Сервер ответил 402 — на расчёт не хватает токенов.
  insufficient,
}

enum _AdPhase { idle, starting, playing, ready, claiming, success, cooldown, limit }

/// Rewarded-реклама за токены.
///
/// Точка интеграции: вместо демонстрационной карточки в `_AdStage` нужно
/// показать rewarded-видео AdMob (`RewardedAd.load` / `show`) или
/// Yandex Mobile Ads (`RewardedAdLoader`). Награду всё равно выдаёт сервер:
/// `POST /api/v2/tokens/ad/start` → показ → `POST /api/v2/tokens/ad/complete`.
///
/// Возвращает `true`, если токены были начислены.
class RewardedAdDialog extends StatefulWidget {
  const RewardedAdDialog({
    super.key,
    required this.api,
    required this.status,
    this.reason = AdDialogReason.manual,
  });

  final ApiClient api;
  final TokenStatus status;
  final AdDialogReason reason;

  @override
  State<RewardedAdDialog> createState() => _RewardedAdDialogState();
}

class _RewardedAdDialogState extends State<RewardedAdDialog> {
  late TokenStatus _status = widget.status;
  late int _reward = widget.status.adReward;
  late int _duration =
      widget.status.adDurationSeconds > 0 ? widget.status.adDurationSeconds : 15;

  _AdPhase _phase = _AdPhase.idle;
  Timer? _timer;
  int _secondsLeft = 0;
  int _cooldownLeft = 0;
  String? _sessionId;
  String _note = '';
  bool _noteIsError = false;
  bool _credited = false;

  @override
  void initState() {
    super.initState();
    final active = widget.status.activeAdSession;
    if (active != null) {
      _sessionId = active.sessionId;
      if (active.secondsLeft > 0) {
        _secondsLeft = active.secondsLeft;
        _phase = _AdPhase.playing;
        _note = 'Реклама идёт. Не закрывайте окно до конца показа.';
        _startTimer();
      } else {
        // Показ уже закончился — можно сразу забрать награду.
        _phase = _AdPhase.ready;
        _note = 'Реклама просмотрена. Заберите токены.';
      }
    } else if (!widget.status.canWatchAd) {
      _phase = widget.status.adsRemaining <= 0 ? _AdPhase.limit : _AdPhase.cooldown;
      _cooldownLeft = widget.status.cooldownRemainingSeconds;
      _note = widget.status.adsRemaining <= 0
          ? 'Лимит просмотров на сегодня исчерпан. Возвращайтесь завтра.'
          : 'Следующая реклама будет доступна через $_cooldownLeft с.';
      _noteIsError = widget.status.adsRemaining <= 0;
      if (_phase == _AdPhase.cooldown && _cooldownLeft > 0) _startTimer();
    } else {
      _note = 'Реклама длится $_duration секунд. '
          'Награда начисляется только после полного просмотра.';
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() {
        if (_phase == _AdPhase.playing) {
          _secondsLeft -= 1;
          if (_secondsLeft <= 0) {
            _secondsLeft = 0;
            _phase = _AdPhase.ready;
            _note = 'Реклама просмотрена. Заберите токены.';
            _noteIsError = false;
          }
        } else if (_phase == _AdPhase.cooldown) {
          _cooldownLeft -= 1;
          if (_cooldownLeft <= 0) {
            _cooldownLeft = 0;
            _phase = _AdPhase.idle;
            _note = 'Можно смотреть следующую рекламу.';
            _noteIsError = false;
          }
        } else {
          timer.cancel();
        }
      });
    });
  }

  Future<void> _start() async {
    if (_phase == _AdPhase.starting || _phase == _AdPhase.playing) return;
    setState(() {
      _phase = _AdPhase.starting;
      _note = 'Подключаемся к рекламной сети…';
      _noteIsError = false;
    });
    try {
      final result = await widget.api.startAd();
      if (!mounted) return;
      setState(() {
        _sessionId = result.sessionId;
        _reward = result.reward;
        _duration = result.durationSeconds > 0 ? result.durationSeconds : 15;
        _secondsLeft = result.secondsLeft > 0 ? result.secondsLeft : _duration;
        _phase = _AdPhase.playing;
        _note = result.resumed
            ? 'Продолжаем показ. Осталось $_secondsLeft с.'
            : 'Реклама идёт. Не закрывайте окно до конца показа.';
        _noteIsError = false;
      });
      _startTimer();
    } on ApiException catch (error) {
      _handleApiError(error);
    } catch (error) {
      _fail('Не удалось запустить рекламу: $error');
    }
  }

  Future<void> _claim() async {
    final sessionId = _sessionId;
    if (sessionId == null) {
      setState(() {
        _phase = _AdPhase.idle;
        _note = 'Сессия рекламы не найдена. Начните показ заново.';
        _noteIsError = true;
      });
      return;
    }
    setState(() {
      _phase = _AdPhase.claiming;
      _note = 'Проверяем просмотр и начисляем токены…';
      _noteIsError = false;
    });
    try {
      final result = await widget.api.completeAd(sessionId);
      if (!mounted) return;
      setState(() {
        _credited = true;
        _phase = _AdPhase.success;
        _reward = result.reward;
        _status = _status.copyWith(
          tokens: result.tokens,
          adsToday: result.adsToday,
          adsRemaining: result.adsRemaining,
          canWatchAd: false,
          cooldownRemainingSeconds: _status.adCooldownSeconds,
        );
        _note = 'Готово! Начислено ${result.reward} '
            '${_tokenWord(result.reward)}. Баланс: ${result.tokens}.';
        _noteIsError = false;
      });
    } on ApiException catch (error) {
      _handleApiError(error);
    } catch (error) {
      _fail('Не удалось получить награду: $error');
    }
  }

  void _handleApiError(ApiException error) {
    if (!mounted) return;
    switch (error.code) {
      case 'ad_cooldown':
        final seconds = error.retryAfterSeconds ?? _status.adCooldownSeconds;
        setState(() {
          _phase = _AdPhase.cooldown;
          _cooldownLeft = seconds;
          _note = 'Следующая реклама будет доступна через $seconds с.';
          _noteIsError = false;
        });
        if (seconds > 0) _startTimer();
        return;
      case 'ad_daily_limit':
        setState(() {
          _phase = _AdPhase.limit;
          _note = 'Лимит просмотров на сегодня исчерпан. Возвращайтесь завтра.';
          _noteIsError = true;
        });
        return;
      case 'ad_not_finished':
        final seconds = error.retryAfterSeconds ?? 1;
        setState(() {
          _phase = _AdPhase.playing;
          _secondsLeft = seconds > 0 ? seconds : 1;
          _note = 'Досмотрите рекламу до конца. Осталось $_secondsLeft с.';
          _noteIsError = false;
        });
        _startTimer();
        return;
      case 'ad_session_invalid':
        setState(() {
          _sessionId = null;
          _phase = _AdPhase.idle;
          _note = error.message;
          _noteIsError = true;
        });
        return;
      default:
        _fail(error.message);
    }
  }

  void _fail(String message) {
    if (!mounted) return;
    setState(() {
      _phase = _AdPhase.idle;
      _note = message;
      _noteIsError = true;
    });
  }

  bool get _showProgress =>
      _phase == _AdPhase.playing ||
      _phase == _AdPhase.ready ||
      _phase == _AdPhase.claiming ||
      _phase == _AdPhase.success;

  double get _progress {
    if (_phase == _AdPhase.ready ||
        _phase == _AdPhase.claiming ||
        _phase == _AdPhase.success) {
      return 1;
    }
    if (_duration <= 0) return 1;
    return ((_duration - _secondsLeft) / _duration).clamp(0, 1).toDouble();
  }

  String get _title => widget.reason == AdDialogReason.insufficient
      ? 'Для расчёта нужен токен'
      : 'Токены за просмотр рекламы';

  String get _subtitle => widget.reason == AdDialogReason.insufficient
      ? 'Посмотрите короткую рекламу — начислим токены, и расчёт станет доступен.'
      : 'Досмотрите рекламу до конца — награда начислится автоматически.';

  String get _buttonLabel {
    switch (_phase) {
      case _AdPhase.idle:
        return 'Смотреть рекламу';
      case _AdPhase.starting:
        return 'Подключаемся…';
      case _AdPhase.playing:
        return 'Идёт показ… $_secondsLeft с';
      case _AdPhase.ready:
        return 'Получить награду';
      case _AdPhase.claiming:
        return 'Начисляем…';
      case _AdPhase.success:
        return 'Готово';
      case _AdPhase.cooldown:
        return 'Подождите $_cooldownLeft с';
      case _AdPhase.limit:
        return 'Лимит на сегодня';
    }
  }

  bool get _buttonEnabled {
    switch (_phase) {
      case _AdPhase.idle:
        return true;
      case _AdPhase.ready:
      case _AdPhase.success:
        return true;
      case _AdPhase.starting:
      case _AdPhase.playing:
      case _AdPhase.claiming:
      case _AdPhase.cooldown:
      case _AdPhase.limit:
        return false;
    }
  }

  void _onAction() {
    switch (_phase) {
      case _AdPhase.idle:
        _start();
      case _AdPhase.ready:
        _claim();
      case _AdPhase.success:
        Navigator.of(context).pop(_credited);
      case _AdPhase.starting:
      case _AdPhase.playing:
      case _AdPhase.claiming:
      case _AdPhase.cooldown:
      case _AdPhase.limit:
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Container(
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(28),
            border: Border.all(
              color: theme.colorScheme.outlineVariant.withOpacity(0.55),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(dark ? 0.45 : 0.18),
                blurRadius: 34,
                offset: const Offset(0, 16),
              ),
            ],
          ),
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 9,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: SberColors.green.withOpacity(0.14),
                              borderRadius: BorderRadius.circular(999),
                            ),
                            child: const Text(
                              'REWARDED AD',
                              style: TextStyle(
                                fontSize: 9,
                                letterSpacing: 1.1,
                                fontWeight: FontWeight.w800,
                                color: SberColors.greenDark,
                              ),
                            ),
                          ),
                          const SizedBox(height: 10),
                          Text(_title, style: theme.textTheme.headlineSmall),
                          const SizedBox(height: 6),
                          Text(
                            _subtitle,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                              height: 1.4,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      tooltip: 'Закрыть',
                      onPressed: () => Navigator.of(context).pop(_credited),
                      icon: const Icon(Icons.close, size: 20),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                _AdStage(
                  phase: _phase,
                  secondsLeft: _secondsLeft,
                  progress: _progress,
                  showProgress: _showProgress,
                  rewarded: _phase == _AdPhase.success,
                ),
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest
                        .withOpacity(dark ? 0.45 : 0.5),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Row(
                    children: [
                      _AdStat(
                        label: 'Награда',
                        value: '+$_reward ${_tokenWord(_reward)}',
                        highlight: true,
                      ),
                      _AdStat(label: 'Баланс', value: '${_status.tokens}'),
                      _AdStat(
                        label: 'Осталось сегодня',
                        value: '${_status.adsRemaining}',
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                FilledButton.icon(
                  onPressed: _buttonEnabled ? _onAction : null,
                  icon: Icon(
                    _phase == _AdPhase.success
                        ? Icons.check_circle_outline
                        : _phase == _AdPhase.ready
                            ? Icons.card_giftcard
                            : Icons.play_circle_outline,
                  ),
                  label: Text(_buttonLabel),
                ),
                const SizedBox(height: 10),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 220),
                  child: Text(
                    _note,
                    key: ValueKey('$_note-$_noteIsError'),
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: _noteIsError
                          ? theme.colorScheme.error
                          : _phase == _AdPhase.success
                              ? SberColors.greenDark
                              : theme.colorScheme.onSurfaceVariant,
                      fontWeight: _phase == _AdPhase.success
                          ? FontWeight.w600
                          : FontWeight.w400,
                    ),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Токены начисляет сервер после полного просмотра. '
                  'Купить токены нельзя — только реклама.',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontSize: 10,
                    color: theme.colorScheme.onSurfaceVariant.withOpacity(0.8),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _tokenWord(int value) {
    final mod10 = value % 10;
    final mod100 = value % 100;
    if (mod10 == 1 && mod100 != 11) return 'токен';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
      return 'токена';
    }
    return 'токенов';
  }
}

class _AdStage extends StatelessWidget {
  const _AdStage({
    required this.phase,
    required this.secondsLeft,
    required this.progress,
    required this.showProgress,
    required this.rewarded,
  });

  final _AdPhase phase;
  final int secondsLeft;
  final double progress;
  final bool showProgress;
  final bool rewarded;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 170,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: const LinearGradient(
          colors: [Color(0xFF07250F), Color(0xFF0D5A21), Color(0xFF137A2C)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: Border.all(color: Colors.white24),
      ),
      child: Stack(
        children: [
          // Место для видеоплеера рекламной сети: замените этот блок на
          // RewardedAd / Yandex Ads widget или нативный platform view.
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 16, 18, 26),
            child: Row(
              children: [
                Container(
                  width: 54,
                  height: 54,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white.withOpacity(0.12),
                    border: Border.all(color: Colors.white24),
                  ),
                  child: Icon(
                    rewarded ? Icons.verified : Icons.play_arrow_rounded,
                    color: Colors.white,
                    size: 28,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        rewarded ? 'НАГРАДА ПОЛУЧЕНА' : 'ДЕМО-РЕКЛАМА',
                        style: const TextStyle(
                          color: Colors.white60,
                          fontSize: 9,
                          letterSpacing: 1.1,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        rewarded
                            ? 'Спасибо за просмотр'
                            : 'Место для rewarded-видео',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          height: 1.2,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        rewarded
                            ? 'Токены зачислены. Можно возвращаться к расчёту.'
                            : 'Здесь будет реклама AdMob или Yandex Ads. '
                                'Пока показываем демонстрационный ролик.',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 11,
                          height: 1.35,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (showProgress && !rewarded)
            Positioned(
              top: 12,
              right: 14,
              child: Container(
                width: 38,
                height: 38,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.black.withOpacity(0.28),
                  border: Border.all(color: Colors.white24),
                ),
                child: Text(
                  '${phase == _AdPhase.playing ? secondsLeft : 0}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 15,
                  ),
                ),
              ),
            ),
          if (showProgress)
            Positioned(
              left: 16,
              right: 16,
              bottom: 14,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 5,
                  backgroundColor: Colors.white.withOpacity(0.16),
                  valueColor: const AlwaysStoppedAnimation<Color>(
                    SberColors.greenBright,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _AdStat extends StatelessWidget {
  const _AdStat({
    required this.label,
    required this.value,
    this.highlight = false,
  });

  final String label;
  final String value;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Expanded(
      child: Column(
        children: [
          Text(
            label,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(
              fontSize: 10,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            textAlign: TextAlign.center,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w800,
              color: highlight ? SberColors.greenDark : null,
            ),
          ),
        ],
      ),
    );
  }
}
