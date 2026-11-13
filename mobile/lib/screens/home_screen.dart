import 'package:flutter/material.dart';

import '../models/auth_models.dart';
import '../models/optimizer_models.dart';
import '../models/token_models.dart';
import '../services/api_client.dart';
import '../theme/sber_theme.dart';
import '../widgets/ad_banner_slot.dart';
import '../widgets/rewarded_ad_dialog.dart';
import 'results_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.api,
    required this.user,
    required this.onLogout,
    required this.isDark,
    required this.onToggleTheme,
    this.onBaseUrlChanged,
  });

  final ApiClient api;
  final AuthUser user;
  final Future<void> Function() onLogout;
  final bool isDark;
  final VoidCallback onToggleTheme;
  final Future<void> Function(String baseUrl)? onBaseUrlChanged;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _capital = TextEditingController(text: '500000');
  final _monthly = TextEditingController(text: '20000');
  final _goal = TextEditingController(text: '1500000');
  final _expenses = TextEditingController(text: '50000');
  final _emergencyMonths = TextEditingController(text: '6');

  String _risk = 'moderate';
  String _liquidity = 'medium';
  bool _creditWillingness = false;
  String _creditType = 'mortgage';
  int _horizon = 60;
  int _paths = 10000;
  int _scenarios = 10;

  bool _loading = false;
  int _progress = 0;
  String _message = '';

  TokenStatus? _tokens;
  bool _tokensLoading = false;
  int _tokenRequest = 0;

  @override
  void initState() {
    super.initState();
    _refreshTokens();
  }

  @override
  void dispose() {
    _capital.dispose();
    _monthly.dispose();
    _goal.dispose();
    _expenses.dispose();
    _emergencyMonths.dispose();
    super.dispose();
  }

  double _number(TextEditingController controller, [double fallback = 0]) {
    final raw = controller.text.trim().replaceAll(',', '.');
    return double.tryParse(raw) ?? fallback;
  }

  Map<String, dynamic> _payload() {
    final profile = <String, dynamic>{
      'capital': _number(_capital),
      'monthly': _number(_monthly),
      'horizon_months': _horizon,
      'risk_tolerance': _risk,
      'liquidity_need': _liquidity,
      'credit_willingness': _creditWillingness,
      'credit_type': _creditWillingness ? _creditType : 'none',
      'monthly_expenses': _number(_expenses),
      'emergency_fund_months': _number(_emergencyMonths).round(),
      'region': 'Москва',
    };
    final goal = _number(_goal);
    if (goal > 0) profile['goal_amount'] = goal;
    return {
      'profile': profile,
      'options': {
        'monte_carlo_paths': _paths,
        'distribution': 'normal',
        'seed': 42,
        'max_scenarios': _scenarios,
        'include_real_estate': true,
        'include_mortgage': true,
        'run_stress_tests': true,
      },
    };
  }

  Future<void> _refreshTokens() async {
    final request = ++_tokenRequest;
    setState(() => _tokensLoading = true);
    try {
      final status = await widget.api.fetchTokenStatus();
      if (!mounted || request != _tokenRequest) return;
      setState(() => _tokens = status);
    } catch (_) {
      // Баланс обновится при следующем запросе или после расчёта.
    } finally {
      if (mounted && request == _tokenRequest) {
        setState(() => _tokensLoading = false);
      }
    }
  }

  Future<void> _openAdDialog({bool insufficient = false}) async {
    var status = _tokens;
    if (status == null) {
      await _refreshTokens();
      if (!mounted) return;
      status = _tokens;
    }
    if (!mounted) return;
    if (status == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Не удалось получить баланс токенов. Проверьте адрес сервера и соединение.',
          ),
        ),
      );
      return;
    }
    final readyStatus = status;
    final credited = await showDialog<bool>(
      context: context,
      barrierDismissible: true,
      builder: (_) => RewardedAdDialog(
        api: widget.api,
        status: readyStatus,
        reason: insufficient
            ? AdDialogReason.insufficient
            : AdDialogReason.manual,
      ),
    );
    if (!mounted) return;
    await _refreshTokens();
    if (!mounted || credited != true) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Токены начислены. Баланс: ${_tokens?.tokens ?? readyStatus.tokens}.',
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

  Future<void> _run() async {
    if (_loading) return;
    final cost = _tokens?.calculationCost ?? 1;
    if (_tokens != null && _tokens!.tokens < cost) {
      await _openAdDialog(insufficient: true);
      return;
    }
    setState(() {
      _loading = true;
      _progress = 1;
      _message = 'Отправляем запрос…';
    });
    try {
      final jobId = await widget.api.startOptimization(_payload());
      // Расчёт списывает токен сразу при постановке в очередь.
      await _refreshTokens();
      while (mounted) {
        await Future<void>.delayed(const Duration(milliseconds: 900));
        final job = await widget.api.fetchJob(jobId);
        if (!mounted) return;
        setState(() {
          _progress = job.progress;
          _message = job.message;
        });
        if (job.status == 'done' && job.result != null) {
          setState(() => _loading = false);
          await _refreshTokens();
          if (!mounted) return;
          await Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ResultsScreen(
                api: widget.api,
                result: job.result!,
                onToggleTheme: widget.onToggleTheme,
              ),
            ),
          );
          await _refreshTokens();
          return;
        }
        if (job.status == 'error') {
          throw ApiException(job.error ?? 'Не удалось выполнить расчёт.');
        }
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
      await _refreshTokens();
      if (!mounted) return;
      if (error.isInsufficientTokens) {
        await _openAdDialog(insufficient: true);
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Ошибка расчёта: ${error.message}')),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
      await _refreshTokens();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Ошибка расчёта: $error')),
      );
    }
  }

  Future<void> _editServer() async {
    final controller = TextEditingController(text: widget.api.baseUrl);
    final value = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Адрес сервера'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Укажите адрес, по которому доступен FastAPI. '
              'Для эмулятора — http://10.0.2.2:8002, для телефона — '
              'http://<IP-компьютера>:8002.',
              style: TextStyle(fontSize: 12),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              autofocus: true,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(labelText: 'API_BASE_URL'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () =>
                Navigator.of(dialogContext).pop(controller.text.trim()),
            child: const Text('Сохранить'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (!mounted || value == null) return;
    final normalized = value.replaceAll(RegExp(r'/+$'), '');
    if (!normalized.startsWith('http://') && !normalized.startsWith('https://')) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Адрес должен начинаться с http:// или https://'),
        ),
      );
      return;
    }
    setState(() => widget.api.baseUrl = normalized);
    await widget.onBaseUrlChanged?.call(normalized);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Сервер: $normalized')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        titleSpacing: 20,
        title: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                gradient: const LinearGradient(
                  colors: [SberColors.greenBright, SberColors.greenDark],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
              alignment: Alignment.center,
              child: const Text(
                'Ф',
                style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800),
              ),
            ),
            const SizedBox(width: 10),
            const Text('ФинХелл', style: TextStyle(fontWeight: FontWeight.w800)),
          ],
        ),
        actions: [
          _tokenChip(theme),
          const SizedBox(width: 2),
          IconButton(
            tooltip: 'Светлая / тёмная тема',
            onPressed: widget.onToggleTheme,
            icon: Icon(widget.isDark ? Icons.light_mode : Icons.dark_mode),
          ),
          PopupMenuButton<String>(
            tooltip: 'Аккаунт',
            icon: const Icon(Icons.account_circle_outlined),
            onSelected: (value) async {
              if (value == 'server') {
                await _editServer();
              } else if (value == 'logout') {
                await widget.onLogout();
              }
            },
            itemBuilder: (context) => [
              PopupMenuItem<String>(
                enabled: false,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      widget.user.displayName,
                      style: const TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 13,
                      ),
                    ),
                    if (widget.user.name.trim().isNotEmpty)
                      Text(
                        widget.user.email,
                        style: const TextStyle(fontSize: 11),
                      ),
                  ],
                ),
              ),
              const PopupMenuDivider(),
              const PopupMenuItem<String>(
                value: 'server',
                child: Row(
                  children: [
                    Icon(Icons.dns_outlined, size: 18),
                    SizedBox(width: 8),
                    Text('Адрес сервера'),
                  ],
                ),
              ),
              const PopupMenuItem<String>(
                value: 'logout',
                child: Row(
                  children: [
                    Icon(Icons.logout, size: 18),
                    SizedBox(width: 8),
                    Text('Выйти'),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          _hero(theme),
          const SizedBox(height: 16),
          _tokenCard(theme),
          const SizedBox(height: 14),
          AdBannerSlot(
            reward: _tokens?.adReward ?? 5,
            onWatchAd: () => _openAdDialog(),
          ),
          const SizedBox(height: 18),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Ваши параметры', style: theme.textTheme.headlineSmall),
                  const SizedBox(height: 4),
                  Text(
                    'Макроданные подставятся автоматически. Любое значение можно переопределить на сервере.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 18),
                  _section('Капитал и цель'),
                  _moneyField(_capital, 'Текущий капитал'),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(child: _moneyField(_monthly, 'Взнос в месяц')),
                      const SizedBox(width: 12),
                      Expanded(child: _horizonField()),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _moneyField(_goal, 'Цель по капиталу'),
                  const SizedBox(height: 18),
                  _section('Риск и ликвидность'),
                  Text('Риск-профиль', style: _label(theme)),
                  const SizedBox(height: 8),
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(value: 'conservative', label: Text('Консерв.')),
                      ButtonSegment(value: 'moderate', label: Text('Умеренный')),
                      ButtonSegment(value: 'aggressive', label: Text('Агрессив.')),
                    ],
                    selected: {_risk},
                    onSelectionChanged: (value) => setState(() => _risk = value.first),
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<String>(
                    value: _liquidity,
                    decoration: const InputDecoration(labelText: 'Потребность в ликвидности'),
                    items: const [
                      DropdownMenuItem(value: 'high', child: Text('Высокая')),
                      DropdownMenuItem(value: 'medium', child: Text('Средняя')),
                      DropdownMenuItem(value: 'low', child: Text('Низкая')),
                    ],
                    onChanged: (value) {
                      if (value != null) setState(() => _liquidity = value);
                    },
                  ),
                  const SizedBox(height: 6),
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: const Text(
                      'Готов использовать кредит',
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                    ),
                    subtitle: const Text(
                      'Добавит ипотечные сценарии с плечом',
                      style: TextStyle(fontSize: 11),
                    ),
                    value: _creditWillingness,
                    onChanged: (value) {
                      setState(() {
                        _creditWillingness = value;
                        if (value && _creditType == 'none') {
                          _creditType = 'mortgage';
                        }
                      });
                    },
                  ),
                  if (_creditWillingness) ...[
                    const SizedBox(height: 4),
                    DropdownButtonFormField<String>(
                      value: _creditType,
                      decoration: const InputDecoration(labelText: 'Тип кредита'),
                      items: const [
                        DropdownMenuItem(value: 'mortgage', child: Text('Ипотека')),
                        DropdownMenuItem(
                          value: 'consumer',
                          child: Text('Потребительский'),
                        ),
                      ],
                      onChanged: (value) {
                        if (value != null) setState(() => _creditType = value);
                      },
                    ),
                  ],
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(child: _moneyField(_expenses, 'Расходы в месяц')),
                      const SizedBox(width: 12),
                      Expanded(
                        child: TextFormField(
                          controller: _emergencyMonths,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(labelText: 'Резерв, мес.'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  _section('Расчёт'),
                  Row(
                    children: [
                      Expanded(
                        child: DropdownButtonFormField<int>(
                          value: _paths,
                          decoration: const InputDecoration(labelText: 'Путей'),
                          items: const [
                            DropdownMenuItem(value: 1000, child: Text('1 000')),
                            DropdownMenuItem(value: 5000, child: Text('5 000')),
                            DropdownMenuItem(value: 10000, child: Text('10 000')),
                            DropdownMenuItem(value: 20000, child: Text('20 000')),
                          ],
                          onChanged: (value) {
                            if (value != null) setState(() => _paths = value);
                          },
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: DropdownButtonFormField<int>(
                          value: _scenarios,
                          decoration: const InputDecoration(labelText: 'Сценариев'),
                          items: const [
                            DropdownMenuItem(value: 10, child: Text('10')),
                            DropdownMenuItem(value: 12, child: Text('12')),
                            DropdownMenuItem(value: 18, child: Text('18')),
                          ],
                          onChanged: (value) {
                            if (value != null) setState(() => _scenarios = value);
                          },
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  if (_loading) _progressCard(theme),
                  _costRow(theme),
                  const SizedBox(height: 10),
                  FilledButton.icon(
                    onPressed: _loading ? null : _run,
                    icon: const Icon(Icons.arrow_forward),
                    label: Text(_loading ? 'Считаем…' : 'Рассчитать план'),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Сервер: ${widget.api.baseUrl}',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontSize: 10,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '10 000 путей на сценарий. Это не индивидуальная инвестиционная рекомендация.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _tokenChip(ThemeData theme) {
    final balance = _tokens?.tokens;
    final dark = theme.brightness == Brightness.dark;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: () => _openAdDialog(),
        child: Container(
          height: 38,
          padding: const EdgeInsets.symmetric(horizontal: 11),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            gradient: LinearGradient(
              colors: dark
                  ? [const Color(0xFF17281B), const Color(0xFF3A2E12)]
                  : [const Color(0xFF10361A), const Color(0xFF3A2B0D)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            border: Border.all(color: SberColors.amber.withOpacity(0.4)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_tokensLoading && balance == null)
                const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: SberColors.amber,
                  ),
                )
              else
                const Icon(
                  Icons.monetization_on,
                  size: 16,
                  color: SberColors.amber,
                ),
              const SizedBox(width: 6),
              Text(
                balance == null ? '—' : '$balance',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                  fontSize: 13,
                ),
              ),
              const SizedBox(width: 4),
              const Icon(Icons.add, size: 14, color: Colors.white70),
            ],
          ),
        ),
      ),
    );
  }

  Widget _tokenCard(ThemeData theme) {
    final status = _tokens;
    final cost = status?.calculationCost ?? 1;
    final reward = status?.adReward ?? 5;
    final balance = status?.tokens ?? 0;
    final runs = cost > 0 ? balance ~/ cost : 0;
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 15),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(
          colors: [Color(0xFF0A2A12), Color(0xFF125022), Color(0xFF166B2B)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: Border.all(color: Colors.white12),
        boxShadow: [
          BoxShadow(
            color: SberColors.greenDeep.withOpacity(0.24),
            blurRadius: 24,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white10,
                  border: Border.all(color: Colors.white24),
                ),
                child: const Icon(
                  Icons.toll_outlined,
                  color: SberColors.amber,
                  size: 22,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'БАЛАНС ТОКЕНОВ',
                      style: TextStyle(
                        color: Colors.white60,
                        fontSize: 10,
                        letterSpacing: 0.8,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          status == null ? '—' : '$balance',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 26,
                            height: 1,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Padding(
                          padding: const EdgeInsets.only(bottom: 3),
                          child: Text(
                            _tokenWord(balance),
                            style: const TextStyle(
                              color: Colors.white70,
                              fontSize: 11,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(999),
                  color: Colors.white10,
                  border: Border.all(color: Colors.white24),
                ),
                child: Text(
                  '≈ $runs ${_runWord(runs)}',
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Divider(color: Colors.white.withOpacity(0.12), height: 1),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Text(
                  'Расчёт стоит $cost ${_tokenWord(cost)}. '
                  'Токены начисляются только за рекламу.',
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 11,
                    height: 1.35,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              FilledButton.icon(
                onPressed: () => _openAdDialog(),
                style: FilledButton.styleFrom(
                  backgroundColor: SberColors.greenBright,
                  foregroundColor: const Color(0xFF05200C),
                  minimumSize: const Size(0, 40),
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                  textStyle: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                icon: const Icon(Icons.play_circle_outline, size: 18),
                label: Text('+$reward'),
              ),
            ],
          ),
          if (status != null) ...[
            const SizedBox(height: 8),
            Text(
              'Сегодня просмотрено ${status.adsToday} из ${status.adDailyLimit} · '
              'осталось ${status.adsRemaining}',
              style: TextStyle(
                color: Colors.white.withOpacity(0.42),
                fontSize: 10,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _costRow(ThemeData theme) {
    final cost = _tokens?.calculationCost ?? 1;
    final balance = _tokens?.tokens;
    final enough = balance == null || balance >= cost;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        color: enough
            ? theme.colorScheme.primary.withOpacity(0.07)
            : theme.colorScheme.error.withOpacity(0.08),
        border: Border.all(
          color: enough
              ? theme.colorScheme.primary.withOpacity(0.18)
              : theme.colorScheme.error.withOpacity(0.3),
        ),
      ),
      child: Row(
        children: [
          Icon(
            Icons.bolt,
            size: 18,
            color: enough ? SberColors.green : theme.colorScheme.error,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              balance == null
                  ? 'Стоимость расчёта — $cost ${_tokenWord(cost)}'
                  : enough
                      ? 'Стоимость расчёта — $cost ${_tokenWord(cost)} · '
                          'баланс $balance'
                      : 'Не хватает токенов: нужно $cost, на балансе $balance',
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w600,
                color: enough
                    ? theme.colorScheme.onSurface
                    : theme.colorScheme.error,
              ),
            ),
          ),
          if (!enough)
            TextButton(
              onPressed: () => _openAdDialog(insufficient: true),
              style: TextButton.styleFrom(
                visualDensity: VisualDensity.compact,
                padding: const EdgeInsets.symmetric(horizontal: 8),
              ),
              child: const Text('Получить'),
            ),
        ],
      ),
    );
  }

  String _runWord(int value) {
    final mod10 = value % 10;
    final mod100 = value % 100;
    if (mod10 == 1 && mod100 != 11) return 'расчёт';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
      return 'расчёта';
    }
    return 'расчётов';
  }

  Widget _hero(ThemeData theme) {
    return Container(
      padding: const EdgeInsets.all(24),
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
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: Colors.white24),
              color: Colors.white10,
            ),
            child: const Text(
              'ДАННЫЕ ЦБ РФ И MOEX ISS',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 10,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.8,
              ),
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Оптимизатор\nкапитала',
            style: TextStyle(
              color: Colors.white,
              fontSize: 38,
              height: 0.98,
              fontWeight: FontWeight.w800,
              letterSpacing: -1.8,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Три уровня риска, 10 000 сценариев Монте-Карло и честный диапазон исходов вместо одной «красивой» цифры.',
            style: TextStyle(color: Colors.white70, height: 1.5),
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: const [
              _HeroChip(text: '10 000 путей'),
              _HeroChip(text: 'Стресс-тесты'),
              _HeroChip(text: 'AI-объяснение'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _progressCard(ThemeData theme) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.primary.withOpacity(0.08),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Считаем сценарии', style: theme.textTheme.titleSmall),
              Text('$_progress%'),
            ],
          ),
          const SizedBox(height: 8),
          LinearProgressIndicator(value: _progress / 100),
          const SizedBox(height: 6),
          Text(
            _message,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _section(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              color: SberColors.green,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }

  TextStyle _label(ThemeData theme) => TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w700,
        color: theme.colorScheme.onSurfaceVariant,
      );

  Widget _moneyField(TextEditingController controller, String label) {
    return TextFormField(
      controller: controller,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      decoration: InputDecoration(labelText: label, suffixText: '₽'),
    );
  }

  Widget _horizonField() {
    return DropdownButtonFormField<int>(
      value: _horizon,
      decoration: const InputDecoration(labelText: 'Горизонт'),
      items: const [
        DropdownMenuItem(value: 12, child: Text('1 год')),
        DropdownMenuItem(value: 24, child: Text('2 года')),
        DropdownMenuItem(value: 36, child: Text('3 года')),
        DropdownMenuItem(value: 60, child: Text('5 лет')),
        DropdownMenuItem(value: 84, child: Text('7 лет')),
        DropdownMenuItem(value: 120, child: Text('10 лет')),
        DropdownMenuItem(value: 180, child: Text('15 лет')),
        DropdownMenuItem(value: 240, child: Text('20 лет')),
      ],
      onChanged: (value) {
        if (value != null) setState(() => _horizon = value);
      },
    );
  }
}

class _HeroChip extends StatelessWidget {
  const _HeroChip({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white12,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white24),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
