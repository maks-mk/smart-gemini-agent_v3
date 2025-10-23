"""
Утилиты отображения для Rich интерфейса
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.tree import Tree
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich import box
from rich.rule import Rule
from rich.align import Align


class DisplayUtils:
    """Утилиты для красивого отображения в терминале"""

    def __init__(self, console: Console):
        self.console = console

    def print_header(self):
        """Отображение заголовка приложения"""
        header_text = Text("🧠 Smart Gemini FileSystem Agent", style="bold white")
        subtitle_text = Text(
            "Intelligent file operations", style="dim white"
        )

        header_panel = Panel(
            Align.center(f"{header_text}\n{subtitle_text}"),
            style="bold blue",
            box=box.DOUBLE,
        )

        self.console.print(header_panel)
        self.console.print()

    def print_status_bar(self, agent=None):
        """Статус-бар с информацией о системе"""
        if not agent:
            status_text = "🔧 Agent not initialized"
        else:
            status = agent.get_status()
            tools_count = status.get("total_tools", 0)
            memory_status = (
                "🧠 Memory" if status.get("use_memory", False) else "🚫 No Memory"
            )

            status_text = (
                f"[#40E0D0]🔧 Smart Gemini Agent[/#40E0D0] "  # Яркая бирюза
                f"📁 [#FF69B4]{os.path.basename(status.get('working_directory', '/'))}[/#FF69B4] "  # Ярко-розовый
                f"[#7CFC00]{memory_status}[/#7CFC00] "  # Лайм-зелёный
                f"🔧 [#FFD700]{tools_count} tools[/#FFD700] "  # Золотой
                f"💬 [bold #F8F8FF]Thread: main[/bold #F8F8FF]"
            )  # Почти белый

        status_panel = Panel(
            status_text, title="System Status", style="dim blue", box=box.ROUNDED
        )

        self.console.print(status_panel)

    def display_tool_call(self, tool_name: str, tool_args: dict):
        """Отображение вызова инструмента с красивым форматированием"""
        import json
        
        # Заголовок с именем инструмента
        header = Text()
        header.append("🔧 ", style="bold yellow")
        header.append(tool_name, style="bold cyan")
        
        # Форматируем аргументы
        if not tool_args:
            content = Text("(no arguments)", style="dim italic")
        elif len(tool_args) == 1 and len(str(tool_args)) < 60:
            # Если один короткий аргумент - выводим в одну строку
            key, value = list(tool_args.items())[0]
            content = Text()
            content.append(f"{key}: ", style="bold white")
            content.append(self._format_arg_value(value))
        else:
            # Создаем таблицу для аргументов
            args_table = Table(
                show_header=False,
                box=None,
                padding=(0, 1),
                collapse_padding=True,
                show_edge=False
            )
            args_table.add_column("Key", style="bold white", no_wrap=True, width=15)
            args_table.add_column("Value", overflow="fold")
            
            for key, value in tool_args.items():
                formatted_value = self._format_arg_value(value)
                args_table.add_row(f"📌 {key}:", formatted_value)
            
            content = args_table
        
        self.console.print(
            Panel(
                content,
                title=header,
                title_align="left",
                border_style="bold yellow",
                box=box.ROUNDED,
                expand=False,
                padding=(0, 1)
            )
        )
    
    def _format_arg_value(self, value: Any) -> Text:
        """Форматирование значения аргумента для красивого вывода"""
        import json
        
        if value is None:
            result = Text("null", style="dim italic")
        elif isinstance(value, bool):
            result = Text(str(value), style=f"bold {'green' if value else 'red'}")
        elif isinstance(value, (int, float)):
            result = Text(str(value), style="cyan")
        elif isinstance(value, str):
            # Если строка очень длинная, обрезаем
            if len(value) > 100:
                result = Text(f"'{value[:97]}...'", style="green")
            else:
                result = Text(f"'{value}'", style="green")
        elif isinstance(value, (list, dict)):
            # Форматируем JSON для сложных структур
            try:
                formatted = json.dumps(value, ensure_ascii=False, indent=2)
                if len(formatted) > 150:
                    # Если JSON слишком большой, компактное представление
                    compact = json.dumps(value, ensure_ascii=False)
                    if len(compact) > 100:
                        result = Text(compact[:97] + "...", style="dim")
                    else:
                        result = Text(compact, style="dim")
                else:
                    result = Text(formatted, style="dim")
            except:
                result = Text(str(value), style="dim")
        else:
            result = Text(str(value), style="white")
        
        return result

    def display_tool_result(self, tool_name: str, content: str):
        """Отображение результата работы инструмента с форматированием"""
        try:
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="ignore")
            else:
                content = str(content)
        except Exception:
            content = str(content)

        # Специальная обработка для list_directory JSON-ответов
        pretty_list_panel = None
        if tool_name.lower() in ("list_directory", "ls", "dir"):
            import json
            try:
                data = json.loads(content)
                items = []
                # Поддержка разных структур
                if isinstance(data, dict):
                    candidates = []
                    for key in ("entries", "items", "files", "list", "result"):
                        if key in data and isinstance(data[key], list):
                            candidates = data[key]
                            break
                    if not candidates and isinstance(data.get("data"), list):
                        candidates = data["data"]
                    for it in candidates:
                        name = it.get("name") or it.get("path") or it.get("file")
                        is_dir = bool(it.get("is_dir") or it.get("directory") or it.get("isDirectory"))
                        if name:
                            emoji = "📁" if is_dir else "📄"
                            items.append(f"{emoji} {name}")
                elif isinstance(data, list):
                    for it in data:
                        if isinstance(it, dict):
                            name = it.get("name") or it.get("path") or it.get("file")
                            is_dir = bool(it.get("is_dir") or it.get("directory") or it.get("isDirectory"))
                            if name:
                                emoji = "📁" if is_dir else "📄"
                                items.append(f"{emoji} {name}")
                        else:
                            items.append(f"📄 {str(it)}")
                if items:
                    # Используем Text вместо Markdown чтобы избежать интерпретации спецсимволов
                    content_text = Text("Содержимое текущей рабочей директории:\n", style="bold")
                    for item in items:
                        content_text.append(item + "\n")
                    
                    pretty_list_panel = Panel(
                        content_text,
                        title=f"[green]✅ Tool '{tool_name}' Result[/green]",
                        border_style="green",
                        expand=False,
                    )
            except Exception:
                pass

        if pretty_list_panel is not None:
            self.console.print(pretty_list_panel)
            return

        # Если это код-блок ```lang\n...```, отрисуем с подсветкой
        if content.startswith("```") and content.endswith("```"):
            lines = content.strip("`").split("\n")
            language = lines[0] if lines and lines[0] else "text"
            code = "\n".join(lines[1:])
            syntax = Syntax(
                code, language, theme="monokai", line_numbers=False, word_wrap=True
            )
            body = syntax
        else:
            # Попробуем как Markdown, иначе обычный текст
            try:
                body = Markdown(content)
            except Exception:
                body = Text(content)

        self.console.print(
            Panel(
                body,
                title=f"[green]✅ Tool '{tool_name}' Result[/green]",
                border_style="green",
                expand=False,
            )
        )

    def display_agent_thought(self, thought: str):
        """Отображение мыслей агента"""
        self.console.print(
            Panel(
                f"[dim italic]{thought}[/dim italic]",
                title="[bold dim]🤔 Thinking...[/bold dim]",
                border_style="dim",
                expand=False,
            )
        )

    def display_file_tree(
        self, start_path: str, max_depth: int = 3, show_hidden: bool = False
    ):
        """Отображение дерева файлов"""
        path = Path(start_path)
        if not path.exists():
            self.display_error(f"Path does not exist: {start_path}")
            return

        def add_tree_items(tree_node, current_path, current_depth: int = 0):
            if current_depth >= max_depth:
                return

            try:
                items = []
                path_obj = Path(current_path)

                for item in path_obj.iterdir():
                    if not show_hidden and item.name.startswith("."):
                        continue
                    items.append(item)

                items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

                for item in items:
                    if item.is_dir():
                        branch = tree_node.add(f"📁 {item.name}/", style="bold blue")
                        add_tree_items(branch, item, current_depth + 1)
                    else:
                        try:
                            size = item.stat().st_size
                            size_str = self._format_file_size(size)
                            tree_node.add(
                                f"{self._get_file_emoji(item.name)} {item.name} [dim]({size_str})[/dim]",
                                style=self._get_file_color(item.name),
                            )
                        except (OSError, PermissionError):
                            tree_node.add(
                                f"{self._get_file_emoji(item.name)} {item.name} [dim](access denied)[/dim]",
                                style="red",
                            )

            except PermissionError:
                tree_node.add("❌ Access denied", style="red")

        tree = Tree(f"📂 {Path(path).name or path}", style="bold green")
        add_tree_items(tree, path, 0)

        panel = Panel(
            tree, title=f"[bold]File Tree: {path}[/bold]", border_style="green"
        )
        self.console.print(panel)

    def _format_file_size(self, size_bytes: int) -> str:
        """Форматирование размера файла"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)

        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.1f} {size_names[i]}"

    def _get_file_emoji(self, filename: str) -> str:
        """Получение эмодзи для файла по расширению"""
        extension = filename.lower().split(".")[-1] if "." in filename else ""

        emoji_map = {
            "py": "🐍",
            "js": "📜",
            "ts": "📘",
            "json": "📋",
            "md": "📝",
            "txt": "📄",
            "pdf": "📕",
            "doc": "📘",
            "docx": "📘",
            "xls": "📊",
            "xlsx": "📊",
            "csv": "📊",
            "jpg": "🖼️",
            "jpeg": "🖼️",
            "png": "🖼️",
            "gif": "🖼️",
            "svg": "🖼️",
            "mp4": "🎬",
            "avi": "🎬",
            "mov": "🎬",
            "mp3": "🎵",
            "wav": "🎵",
            "flac": "🎵",
            "zip": "📦",
            "rar": "📦",
            "7z": "📦",
            "tar": "📦",
            "exe": "⚙️",
            "msi": "⚙️",
            "deb": "⚙️",
            "rpm": "⚙️",
            "html": "🌐",
            "css": "🎨",
            "xml": "📰",
            "sql": "🗃️",
            "db": "🗃️",
            "sqlite": "🗃️",
            "log": "📜",
            "cfg": "⚙️",
            "conf": "⚙️",
            "ini": "⚙️",
        }

        return emoji_map.get(extension, "📄")

    def _get_file_color(self, filename: str) -> str:
        """Получение цвета для файла по расширению"""
        extension = filename.lower().split(".")[-1] if "." in filename else ""

        color_map = {
            "py": "green",
            "js": "yellow",
            "ts": "blue",
            "json": "cyan",
            "md": "magenta",
            "txt": "white",
            "jpg": "bright_magenta",
            "jpeg": "bright_magenta",
            "png": "bright_magenta",
            "mp4": "red",
            "mp3": "bright_green",
            "zip": "bright_yellow",
            "exe": "bright_red",
            "html": "bright_blue",
            "css": "bright_cyan",
            "log": "dim white",
        }

        return color_map.get(extension, "white")

    def display_help(self):
        """Отображение справки по командам"""
        commands = {
            "Системные команды": {
                "/help": "Показать эту справку",
                "/status": "Статус агента и инструментов",
                "/history [N]": "История команд (последние N)",
                "/clear": "Очистить экран",
                "/tree [path]": "Показать файловую структуру",
                "/tools": "Показать доступные инструменты",
                "/reload": "Перезагрузить системный промпт из файла",
                "/memory": "Очистить контекстную память агента",
                "/insights": "Показать аналитику производительности и контекста",
                "/export_context [json|markdown]": "Экспортировать контекст и статистику агента",
                "/export": "Экспортировать историю чата в файл",
                "/quit": "Выход из программы",
            },
            "Файловые операции": {
                "создай файл test.txt": "Создать новый файл",
                "прочитай config.py": "Показать содержимое файла",
                "удали old.log": "Удалить файл (безопасно)",
                "покажи файлы": "Список файлов в директории",
                "найди *.py": "Поиск файлов по маске",
            },
            "Веб-операции": {
                "найди в интернете Python": "Поиск в интернете",
                "скачай https://...": "Загрузить файл по URL",
            },
        }

        help_panels = []
        for category, cmds in commands.items():
            table = Table(show_header=False, box=None, padding=(0, 1))
            table.add_column("Command", style="cyan", no_wrap=True)
            table.add_column("Description", style="white")

            for cmd, desc in cmds.items():
                table.add_row(cmd, desc)

            panel = Panel(table, title=f"[bold]{category}[/bold]", border_style="blue")
            help_panels.append(panel)

        self.console.print(Columns(help_panels, equal=True, expand=True))

    def display_history(self, history: List, limit: int = 10):
        """Отображение истории команд"""
        if not history:
            self.console.print("[yellow]История пуста[/yellow]")
            return

        table = Table(title="История команд", box=box.ROUNDED)
        table.add_column("#", style="dim", width=4)
        table.add_column("Время", style="cyan", width=20)
        table.add_column("Тип", style="magenta", width=10)
        table.add_column("Команда/Ответ", style="white")

        recent_history = history[-limit:] if len(history) > limit else history

        for i, entry in enumerate(recent_history, 1):
            timestamp = entry.get("timestamp", "N/A")
            entry_type = entry.get("type", "unknown")
            content = entry.get("content", "")

            if len(content) > 80:
                content = content[:77] + "..."

            type_style = {"user": "green", "agent": "blue", "error": "red"}.get(
                entry_type, "white"
            )

            table.add_row(
                str(i), timestamp, f"[{type_style}]{entry_type}[/{type_style}]", content
            )

        self.console.print(table)

    def display_agent_response(
        self, response: str, response_time: Optional[float] = None
    ):
        """Красивое отображение ответа агента"""
        # Проверяем, содержит ли ответ список файлов с эмодзи
        has_file_list = ("📁" in response or "📄" in response) and (
            "Содержимое" in response or "директор" in response.lower()
        )
        
        if has_file_list or response.startswith("Содержимое текущей рабочей директории:"):
            # Используем Text вместо Markdown для списков файлов
            content = Text(response)
            panel = Panel(
                content,
                title="[bold green]🤖 Gemini Response[/bold green]",
                border_style="green",
            )
        elif response.startswith("```") and response.endswith("```"):
            lines = response.strip("`").split("\n")
            language = lines[0] if lines[0] else "text"
            code = "\n".join(lines[1:])

            syntax = Syntax(
                code, language, theme="monokai", line_numbers=True, word_wrap=True
            )
            panel = Panel(
                syntax,
                title="[bold green]🤖 Gemini Response (Code)[/bold green]",
                border_style="green",
            )
        else:
            # Попытка распаковать обёртку {'type':'text','text':'...'} или JSON {"type":"text","text":"..."}
            resp = response
            try:
                txt = resp.strip()
                if txt.startswith("{") and "text" in txt:
                    try:
                        import json as _json

                        data = _json.loads(txt)
                    except Exception:
                        import ast as _ast

                        data = _ast.literal_eval(txt)
                    if isinstance(data, dict) and isinstance(data.get("text"), str):
                        resp = (
                            data["text"]
                            .replace("\\n", "\n")
                            .replace('\\"', '"')
                            .replace("\\'", "'")
                        )
            except Exception:
                pass
            try:
                content = Markdown(resp)
            except Exception:
                content = Text(resp)
            panel = Panel(
                content,
                title="[bold green]🤖 Gemini Response[/bold green]",
                border_style="green",
            )

        self.console.print(panel)

        if response_time:
            self.console.print(f"[dim]⏱️ Response time: {response_time:.2f}s[/dim]")

    def display_error(self, error_message: str):
        """Отображение ошибки"""
        panel = Panel(
            f"❌ {error_message}",
            title="[bold red]Error[/bold red]",
            border_style="red",
        )
        self.console.print(panel)

    def display_success(self, message: str):
        """Отображение успешного выполнения"""
        panel = Panel(
            f"✅ {message}",
            title="[bold green]Success[/bold green]",
            border_style="green",
        )
        self.console.print(panel)

    def display_status_info(self, status: Dict[str, Any]):
        """Подробное отображение статуса системы"""
        main_table = Table(title="[bold]🤖 Smart Agent Status[/bold]", box=box.ROUNDED)
        main_table.add_column("Property", style="cyan")
        main_table.add_column("Value", style="green")

        simple_status = {
            k: v
            for k, v in status.items()
            if not isinstance(v, (dict, list)) or k == "intelligence_features"
        }

        for key, value in simple_status.items():
            if key == "intelligence_features":
                value = ", ".join(value)
            table_key = key.replace("_", " ").title()
            main_table.add_row(table_key, str(value))

        self.console.print(main_table)

        if "tools_by_category" in status and status["tools_by_category"]:
            tools_table = Table(
                title="[bold]🔧 Tools by Category[/bold]", box=box.SIMPLE
            )
            tools_table.add_column("Category", style="magenta")
            tools_table.add_column("Count", style="yellow", justify="right")

            category_icons = {
                "read_file": "📖",
                "write_file": "✏️",
                "list_directory": "📁",
                "create_directory": "📂",
                "delete_file": "🗑️",
                "move_file": "📦",
                "search": "🔍",
                "web_search": "🌐",
                "fetch_url": "⬇️",
                "other": "🔧",
            }

            for category, count in status["tools_by_category"].items():
                icon = category_icons.get(category, "•")
                category_name = category.replace("_", " ").title()
                tools_table.add_row(f"{icon} {category_name}", str(count))

            self.console.print(tools_table)

        if status.get("context_memory_items", 0) > 0:
            memory_panel = Panel(
                f"🧠 Context Memory: {status['context_memory_items']} items\n"
                f"🎯 Last Action: {status.get('last_action', status.get('last_intent', 'None'))}",
                title="[bold]Memory Status[/bold]",
                border_style="blue",
            )
            self.console.print(memory_panel)

    def clear_screen(self):
        """Очистка экрана"""
        self.console.clear()

    def print_rule(self, title: Optional[str] = None):
        """Печать разделительной линии"""
        self.console.print(Rule(title, style="dim"))

    def display_context_insights(self, insights: Dict[str, Any]):
        """Отображение аналитики контекста и производительности"""
        self.console.print()
        self.console.print(
            "[bold blue]📊 Performance Analytics & Context Insights[/bold blue]"
        )
        self.console.print()

        # Общая статистика
        if insights.get("total_operations", 0) > 0:
            overview_table = Table(title="[bold]📈 Overview[/bold]", box=box.ROUNDED)
            overview_table.add_column("Metric", style="cyan")
            overview_table.add_column("Value", style="white")

            total_ops = insights["total_operations"]
            success_rate = insights.get("overall_success_rate", 0)
            avg_time = insights.get("avg_execution_time", 0)

            overview_table.add_row("Total Operations", str(total_ops))
            overview_table.add_row("Success Rate", f"{success_rate:.1f}%")
            overview_table.add_row("Avg Execution Time", f"{avg_time:.2f}s")

            self.console.print(overview_table)
            self.console.print()

            # Статистика по намерениям
            intent_stats = insights.get("intent_statistics", {})
            if intent_stats:
                intent_table = Table(
                    title="[bold]🎯 Operation Performance[/bold]", box=box.ROUNDED
                )
                intent_table.add_column("Intent", style="cyan")
                intent_table.add_column("Total", style="white")
                intent_table.add_column("Success Rate", style="green")
                intent_table.add_column("Avg Time", style="yellow")

                # Сортируем по количеству использований
                sorted_intents = sorted(
                    intent_stats.items(), key=lambda x: x[1]["total"], reverse=True
                )

                for intent, stats in sorted_intents[:10]:  # Показываем топ-10
                    success_rate = stats.get("success_rate", 0)
                    avg_time = stats.get("avg_time", 0)
                    total = stats.get("total", 0)

                    # Цветовое кодирование успешности
                    if success_rate >= 90:
                        success_style = "bold green"
                    elif success_rate >= 70:
                        success_style = "yellow"
                    else:
                        success_style = "bold red"

                    intent_table.add_row(
                        intent.replace("_", " ").title(),
                        str(total),
                        f"[{success_style}]{success_rate:.1f}%[/{success_style}]",
                        f"{avg_time:.2f}s",
                    )

                self.console.print(intent_table)
                self.console.print()

            # Проблемные области
            problematic = insights.get("problematic_intents", [])
            if problematic:
                problem_panel = Panel(
                    "\n".join(
                        [
                            f"⚠️ {intent.replace('_', ' ').title()}"
                            for intent in problematic
                        ]
                    ),
                    title="[bold red]⚠️ Problematic Operations[/bold red]",
                    border_style="red",
                )
                self.console.print(problem_panel)
                self.console.print()

            # Статистика инструментов
            tool_stats = insights.get("most_used_tools", {})
            if tool_stats:
                tools_table = Table(
                    title="[bold]🔧 Most Used Tools[/bold]", box=box.ROUNDED
                )
                tools_table.add_column("Tool", style="cyan")
                tools_table.add_column("Usage Count", style="white")

                sorted_tools = sorted(
                    tool_stats.items(), key=lambda x: x[1], reverse=True
                )
                for tool, count in sorted_tools[:8]:  # Топ-8 инструментов
                    tools_table.add_row(tool, str(count))

                self.console.print(tools_table)
                self.console.print()

            # Рекомендации
            recommendations = []

            if success_rate < 80:
                recommendations.append(
                    "🔍 Consider reviewing error patterns and improving input validation"
                )

            if avg_time > 2.0:
                recommendations.append(
                    "⚡ Performance could be improved - consider caching frequently used operations"
                )

            if len(problematic) > 2:
                recommendations.append(
                    "🛠️ Multiple operations showing issues - review tool configurations"
                )

            if total_ops > 50 and not tool_stats:
                recommendations.append(
                    "📊 Enable tool usage tracking for better insights"
                )

            if recommendations:
                rec_panel = Panel(
                    "\n".join(recommendations),
                    title="[bold yellow]💡 Recommendations[/bold yellow]",
                    border_style="yellow",
                )
                self.console.print(rec_panel)

        else:
            no_data_panel = Panel(
                "No operations recorded yet. Start using the agent to see analytics!",
                title="[bold]📊 Analytics[/bold]",
                border_style="dim",
            )
            self.console.print(no_data_panel)
