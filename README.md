# searcher

Консольная утилита для macOS и Linux, которая подсказывает команды на русском языке через локальный сервер LM Studio/OpenAI API (`http://127.0.0.1:1234`).

## Возможности

- Проверка, что локальный API запущен (через `GET /v1/models`).
- Режим по умолчанию: reasoning-ответ с кратким объяснением и 1-3 вероятными командами.
- Флаг `-s` (`--short`): короткий командный режим с выбором номера и запуском команды.
- Флаг `--tools`: приоритетный список инструментов (через запятую), которые желательно использовать в ответе.
- Флаг `--dry-run`: в `--short` не выполнять выбранную команду, только показать её.
- Флаг `--llm-validate`: дополнительная валидация команды отдельным запросом к модели.
- Динамический учёт доступных CLI-утилит в системе (modern + fallback).
- Динамический учёт популярных dev/devops-инструментов (`docker`, `git`, `systemctl`, `journalctl`, `kubectl`, `npm`, и др.).
- Передача контекста текущей директории (путь и список файлов/папок) для более точных подсказок.
- Режим `--strict-modern` для строгого использования modern-утилит.
- Без внешних Python-зависимостей (только стандартная библиотека).

## Требования

- macOS
- `uv` (рекомендуемый способ установки и запуска без вмешательства в системный Python)
- Запущенный Local Server в LM Studio на `http://127.0.0.1:1234`
- Опционально для красивого рендера режима по умолчанию: `glow` или `mdcat`

## Установка в пользовательском режиме

Установите утилиту как `uv tool`, чтобы команда была доступна из любой папки:

```bash
cd /Users/mac/g/searcher
uv tool install --editable .
```

Проверьте, что `searcher` доступен:

```bash
which searcher
searcher "как найти самые большие файлы в текущей папке"
```

Если `which searcher` ничего не вывел, добавьте путь `uv tool` в `PATH`:

```bash
uv tool dir
```

Обычно бинарники находятся в `~/.local/bin`. Добавьте его в `~/.zshrc`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Переустановка после изменений в проекте:

```bash
cd /Users/mac/g/searcher
uv tool install --editable . --reinstall
```

Удаление утилиты:

```bash
uv tool uninstall searcher
```

## Использование

Режим по умолчанию (reasoning):

```bash
searcher "как безопасно очистить кэш DNS на macOS"
```

Короткий командный режим:

```bash
searcher -s "как показать открытые порты"
```

Приоритет конкретных инструментов:

```bash
searcher --tools docker,git "как посмотреть последние коммиты и контейнеры"
```

Для корректного markdown-рендера в режиме по умолчанию установите один из инструментов:

```bash
brew install glow
# или
brew install mdcat
```

Dry-run (не выполнять команду):

```bash
searcher -s --dry-run "как показать открытые порты"
```

Дополнительная LLM-валидация команды:

```bash
searcher --llm-validate "как найти TODO в проекте"
```

Явно предпочитать modern-утилиты (режим по умолчанию):

```bash
searcher --prefer-modern "как найти TODO в проекте"
```

Строгий modern-режим:

```bash
searcher --strict-modern "как найти TODO в проекте"
```

Сгенерировать скрипт автодополнения для zsh:

```bash
searcher --print-zsh-completion
```

После генерации утилита показывает список команд и просит ввести номер:

```text
Выберите команду по номеру (0 или Enter для отмены):
1. ...
2. ...
> 2
```

- число в диапазоне — выбрать и выполнить соответствующую команду
- `0` или `Enter` без ввода — отменить запуск

### Логика выбора утилит

- Утилита проверяет, какие команды реально доступны в `PATH`.
- Для доменных запросов (Docker/Git/systemd/Kubernetes/Node.js) модель ориентируется на соответствующие рабочие инструменты, если они доступны.
- Для известных пар применяется приоритет modern → fallback:
  - `cat -> bat`
  - `grep -> rg`
  - `find -> fd`
  - `ls -> eza`
  - `du -> dust`
- В `--prefer-modern` допускается fallback на стандартные команды.
- В `--strict-modern` для этих пар требуется modern-утилита; если она отсутствует, утилита завершится с ошибкой.

## Автодополнение zsh

Установите completion-скрипт:

```bash
mkdir -p ~/.zsh/completions
searcher --print-zsh-completion > ~/.zsh/completions/_searcher
```

Подключите completions в `~/.zshrc` (один раз):

```bash
echo 'fpath=(~/.zsh/completions $fpath)' >> ~/.zshrc
echo 'autoload -Uz compinit' >> ~/.zshrc
echo 'compinit' >> ~/.zshrc
source ~/.zshrc
```

Проверка:

```bash
searcher --<TAB>
```

## Поведение при ошибках

- Если API на `http://127.0.0.1:1234` недоступен, утилита завершится с ошибкой и попросит запустить сервер LM Studio.
- Если сервер запущен, но не загружена модель, утилита сообщит об этом и завершится.

## Архитектурные решения

Все принятые проектные решения фиксируются в `docs/PROP-*`:

- `docs/PROP-001-modular-architecture.md`
- `docs/PROP-002-dynamic-capabilities.md`
- `docs/PROP-003-command-policy.md`
- `docs/PROP-004-cli-ux.md`
- `docs/PROP-005-core-models-usecases.md`
- `docs/PROP-006-llm-command-validation.md`
- `docs/PROP-007-minimum-command-usefulness.md`
- `docs/PROP-008-unicode-arguments-in-commands.md`
- `docs/PROP-009-numbered-command-selection.md`
- `docs/PROP-010-markdown-rendering-in-reasoning.md`
- `docs/PROP-011-default-reasoning-and-short-mode.md`
- `docs/PROP-012-dev-tools-capabilities.md`
- `docs/PROP-013-preferred-tools-flag.md`
- `docs/PROP-014-working-directory-context.md`
