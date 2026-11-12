import 'package:flutter/material.dart';

import '../models/auth_models.dart';
import '../models/optimizer_models.dart';
import '../services/api_client.dart';
import '../theme/sber_theme.dart';
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

  Future<void> _run() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _progress = 1;
      _message = 'Отправляем запрос…';
    });
    try {
      final jobId = await widget.api.startOptimization(_payload());
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
          await Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ResultsScreen(
                api: widget.api,
                result: job.result!,
                onToggleTheme: widget.onToggleTheme,
              ),
            ),
          );
          return;
        }
        if (job.status == 'error') {
          throw ApiException(job.error ?? 'Не удалось выполнить расчёт.');
        }
      }
    } catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
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
            const SizedBox(width: 10),
            Text(
              'Оптимизатор',
              style: TextStyle(color: theme.colorScheme.onSurfaceVariant, fontSize: 12),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Адрес сервера',
            onPressed: _editServer,
            icon: const Icon(Icons.dns_outlined),
          ),
          IconButton(
            tooltip: 'Светлая / тёмная тема',
            onPressed: widget.onToggleTheme,
            icon: Icon(widget.isDark ? Icons.light_mode : Icons.dark_mode),
          ),
          PopupMenuButton<String>(
            tooltip: 'Аккаунт',
            icon: const Icon(Icons.account_circle_outlined),
            onSelected: (value) async {
              if (value == 'logout') await widget.onLogout();
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
