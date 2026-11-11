import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../theme/sber_theme.dart';

class _ChatMessage {
  const _ChatMessage({required this.text, required this.isUser});

  final String text;
  final bool isUser;
}

/// Чат по готовому расчёту. Числа не считаются моделью: сервер отвечает
/// только на основе детерминированного контекста и валидатора.
class AiChat extends StatefulWidget {
  const AiChat({
    super.key,
    required this.api,
    required this.contextId,
    this.welcome,
  });

  final ApiClient api;
  final String contextId;
  final String? welcome;

  @override
  State<AiChat> createState() => _AiChatState();
}

class _AiChatState extends State<AiChat> {
  static const _suggestions = [
    'Что выбрать и почему?',
    'Какие риски при высокой ставке?',
    'Как работают налоги и ИИС?',
    'Что лучше: вклад или ОФЗ?',
    'Что с ипотекой и арендой?',
  ];

  final _input = TextEditingController();
  final _scroll = ScrollController();
  late final List<_ChatMessage> _messages;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _messages = [
      _ChatMessage(
        text: widget.welcome ??
            'Спросите про риски, налоги, вклады, ОФЗ, ипотеку или сравнение сценариев. '
                'Отвечаю только по числам из вашего расчёта.',
        isUser: false,
      ),
    ];
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send([String? preset]) async {
    final question = (preset ?? _input.text).trim();
    if (question.isEmpty || _sending) return;
    setState(() {
      _messages.add(_ChatMessage(text: question, isUser: true));
      _input.clear();
      _sending = true;
    });
    _scrollToEnd();
    try {
      final history = _messages
          .sublist(1, _messages.length - 1)
          .map((message) => {
                'role': message.isUser ? 'user' : 'assistant',
                'content': message.text,
              })
          .toList();
      final response = await widget.api.chat(
        contextId: widget.contextId,
        question: question,
        history: history.length > 10
            ? history.sublist(history.length - 10)
            : history,
      );
      if (!mounted) return;
      setState(() {
        _messages.add(_ChatMessage(text: response.answer, isUser: false));
        _sending = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _messages.add(
          _ChatMessage(
            text: 'Не удалось получить ответ: $error',
            isUser: false,
          ),
        );
        _sending = false;
      });
    }
    _scrollToEnd();
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
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
                    gradient: const LinearGradient(
                      colors: [SberColors.greenBright, SberColors.greenDark],
                    ),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  alignment: Alignment.center,
                  child: const Icon(Icons.auto_awesome, color: Colors.white, size: 17),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('AI-консультант', style: theme.textTheme.titleMedium),
                      Text(
                        'по вашему расчёту',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: SberColors.green.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: const Text(
                    'контекст',
                    style: TextStyle(
                      fontSize: 9,
                      fontWeight: FontWeight.w700,
                      color: SberColors.green,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              height: 300,
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.35),
                borderRadius: BorderRadius.circular(16),
              ),
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.all(12),
                itemCount: _messages.length + (_sending ? 1 : 0),
                itemBuilder: (context, index) {
                  if (index >= _messages.length) {
                    return const _TypingBubble();
                  }
                  final message = _messages[index];
                  return _Bubble(message: message);
                },
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              height: 36,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _suggestions.length,
                separatorBuilder: (_, __) => const SizedBox(width: 6),
                itemBuilder: (context, index) {
                  final suggestion = _suggestions[index];
                  return ActionChip(
                    label: Text(suggestion, style: const TextStyle(fontSize: 11)),
                    onPressed: _sending ? null : () => _send(suggestion),
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                  );
                },
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _input,
                    enabled: !_sending,
                    maxLength: 2000,
                    minLines: 1,
                    maxLines: 3,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(
                      hintText: 'Спросите про риски, налоги, ставку…',
                      counterText: '',
                      contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(
                  onPressed: _sending ? null : () => _send(),
                  icon: _sending
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.arrow_upward, size: 20),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'AI объясняет расчёт и не является индивидуальной инвестиционной рекомендацией.',
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
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final _ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isUser = message.isUser;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 520),
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
        decoration: BoxDecoration(
          color: isUser ? SberColors.green : theme.colorScheme.surface,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(14),
            topRight: const Radius.circular(14),
            bottomLeft: Radius.circular(isUser ? 14 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 14),
          ),
          border: isUser
              ? null
              : Border.all(color: theme.colorScheme.outlineVariant.withOpacity(0.5)),
        ),
        child: Text(
          message.text,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: isUser ? Colors.white : theme.colorScheme.onSurface,
            height: 1.4,
          ),
        ),
      ),
    );
  }
}

class _TypingBubble extends StatelessWidget {
  const _TypingBubble();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: theme.colorScheme.outlineVariant.withOpacity(0.5)),
        ),
        child: const SizedBox(
          width: 42,
          child: LinearProgressIndicator(minHeight: 3),
        ),
      ),
    );
  }
}
