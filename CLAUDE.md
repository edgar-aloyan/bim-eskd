# CLAUDE.md

> Читай этот файл первым. Это главная точка входа в проект.

---

## Суть проекта

Система генерации инженерной документации по ЕСКД на основе BIM/IFC моделей.

Рабочий процесс:
- Инженер промптит Claude Code
- Claude Code через standalone сервер или Bonsai-mcp генерирует IFC модель
- Сервер рендерит SVG виды (ifcopenshell.draw, HLR), собирает ЕСКД листы, публикует на GitHub Pages
- Заказчику отправляются .ifc + .pdf (Print→PDF из viewer)

Каждый проект — самостоятельная единица с номером. Новые проекты ссылаются на предыдущие как на референсы.

---

## Стек

| Инструмент | Роль |
|---|---|
| Claude Code | LLM-агент |
| **bim-eskd server** | Standalone MCP-сервер (29 инструментов), IFC CRUD, SVG рендер, ЕСКД листы |
| ifcopenshell | Python API для IFC + ifcopenshell.draw (HLR рендер) |
| Blender 4.5+ / Bonsai | BIM среда (опционально, для визуальной работы) |
| ifc-bonsai-mcp (форк) | MCP сервер Blender, 50+ инструментов, RAG по ifcopenshell |

Форк: `git@github.com:edgar-aloyan/ifc-bonsai-mcp.git`
Upstream: `https://github.com/Show2Instruct/ifc-bonsai-mcp`

---

## Установка (Debian)

```bash
# 1. Blender — скачать с blender.org, распаковать в ~/apps/
# Внутри Blender: Edit → Preferences → Get Extensions → "Bonsai" → Install

# 2. ifc-bonsai-mcp (форк)
git clone git@github.com:edgar-aloyan/ifc-bonsai-mcp.git ~/apps/ifc-bonsai-mcp
cd ~/apps/ifc-bonsai-mcp
~/.local/bin/uv sync

# 3. Установить пакеты в Blender Python
~/.local/bin/uv run python scripts/install_blender_packages.py

# 4. Установить аддон в Blender
python3 -c "
import zipfile, os, shutil
src = os.path.expanduser('~/apps/ifc-bonsai-mcp/blender_addon')
with zipfile.ZipFile('/tmp/blender_addon.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(src):
        for f in files:
            fp = os.path.join(root, f)
            z.write(fp, os.path.relpath(fp, os.path.dirname(src)))
"
# Blender → Edit → Preferences → Add-ons → Install → /tmp/blender_addon.zip

# 5. Подключить MCP к Claude Code
claude mcp add bonsai -- /path/to/.venv/bin/python /path/to/ifc-bonsai-mcp/main.py

# 6. Инициализировать RAG базу знаний (один раз)
cd ~/apps/ifc-bonsai-mcp && ~/.local/bin/uv run python scripts/init_knowledge_base.py
```

---

## Запуск (каждая сессия)

```bash
# 1. Запустить Blender
DISPLAY=:0 ~/apps/blender-4.5.7-linux-x64/blender > /tmp/blender.log 2>&1 &

# 2. В Blender: открыть IFC проект через File → Open IFC Project
#    Затем: N-панель → BlenderMCP → Connect to MCP server
```

> IFC файл нельзя открыть через аргумент CLI — только через Bonsai меню.

### Embedding server (RAG)

Работает как systemd user service — стартует автоматически при логине:
```bash
systemctl --user status ifc-embedding-server.service   # проверить
systemctl --user restart ifc-embedding-server.service   # перезапустить
journalctl --user -u ifc-embedding-server.service -f    # логи
```

**В начале каждой сессии** Claude должен вызвать `ensure_ifc_knowledge_ready` для инициализации RAG-индекса (занимает ~0.1с если уже готов).

---

## Обновление аддона после изменений в форке

```bash
cp -r ~/apps/ifc-bonsai-mcp/blender_addon/. \
      ~/.config/blender/4.5/scripts/addons/blender_addon/
find ~/.config/blender/4.5/scripts/addons/blender_addon -name "__pycache__" -exec rm -rf {} + 2>/dev/null
# Перезапустить Blender полностью
```

---

## Структура проекта

```
/
├── CLAUDE.md                        ← ТЫ ЗДЕСЬ
│
├── server/                          ← Phase 2: standalone IFC сервер (без Blender)
│   ├── pyproject.toml
│   └── src/bim_eskd/
│       ├── main.py                  ← MCP entry point (29 инструментов)
│       ├── ifc_engine/              ← IFC CRUD (wall, slab, door, window, roof, feature)
│       ├── svg_renderer/            ← IFC → SVG через ifcopenshell.draw (HLR)
│       ├── eskd/                    ← Phase 3: ЕСКД рамки, штампы, компоновка листов
│       ├── rag/                     ← RAG: standards (ПУЭ, ГОСТ, IEC)
│       └── mcp_tools/               ← MCP tool definitions
│
├── standards/                       ← Phase 1: нормативная база
│   ├── raw/                         ← исходные PDF (ПУЭ, ГОСТ, СП, IEC)
│   ├── parsed/                      ← JSONL чанки для embedding
│   └── parser/                      ← парсер PDF → JSONL (таблицы + текст)
│
├── projects/
│   ├── 001_название/
│   │   ├── prompt.md                ← промпт которым генерировался проект
│   │   ├── model.ifc                ← IFC модель
│   │   ├── drawings/                ← SVG/PDF листы
│   │   └── README.md                ← описание, refs, статус
│   └── ...
│
├── docs/                           ← Phase 4: GitHub Pages viewer
│   ├── index.html                  ← entry point
│   ├── style.css / app.js          ← стили и логика
│   └── projects/NNN/               ← SVG листы + manifest.json
│
└── shared/
    ├── eskd_stamps/                 ← SVG штампы ЕСКД (ГОСТ 2.104-2006)
    └── ifc_templates/               ← переиспользуемые IFC типы и семейства
```

---

## Соглашения

### Нумерация проектов
- Формат: `NNN_короткое_название` (001, 002, 003...)
- Нули обязательны для корректной сортировки

### README.md каждого проекта
```markdown
# 001_название

## Описание
Что это за проект, назначение.

## Раздел
ЭОМ / СС / РСЗА / ОВК / ...

## Референсы
- refs: [] — список номеров проектов использованных как контекст

## Deliverables
- [ ] model.ifc
- [ ] drawings/sheet_001.pdf

## Статус
in-progress / done
```

### Файлы
- Максимум 300 строк на файл
- Имена функций самодокументирующие
- Один модуль — одна ответственность

---

## ЕСКД требования (ГОСТ 2.104-2006)

Штампы генерируются динамически в `eskd/frame.py` (ГОСТ 2.104-2006, формы 1 и 2а).

Обязательные поля основной надписи:
- Наименование изделия / документа
- Обозначение документа
- Организация
- Разработал / Проверил / Утвердил (ФИО + дата)
- Номер листа / Листов всего

Форматы листов: A4 (210×297), A3 (297×420), A1 (594×841)
Поля: левое 20 мм, остальные 5 мм

---

## Разделы проектирования

| Раздел | Описание | Основные IFC типы | Статус |
|---|---|---|---|
| ЭОМ | Электроосвещение и электрооборудование | IfcElectricDistributionBoard, IfcLightFixture, IfcCableSegment | первый |
| СС | Слаботочные системы | IfcCommunicationsAppliance, IfcCableSegment | следующий |
| РСЗА | Релейная защита и автоматика | IfcController, IfcActuator | следующий |
| ОВК | Отопление, вентиляция, кондиционирование | IfcDuctSegment, IfcAirTerminal, IfcPipeSegment | позже |

---

## Работа с MCP (ОБЯЗАТЕЛЬНО)

**Никогда не читай .ifc файлы напрямую.** Всегда работай через MCP-инструменты Bonsai.

### Иерархия инструментов (строго по приоритету)

**Уровень 1 — Специализированные MCP-инструменты** (всегда предпочтительны):
- Стены: `create_wall`, `create_two_point_wall`, `create_polyline_walls`, `update_wall`, `get_wall_properties`
- Двери: `create_door`, `update_door`, `get_door_properties`, `get_door_operation_types`
- Окна: `create_window`, `update_window`, `get_window_properties`, `get_window_partition_types`
- Плиты: `create_slab`, `update_slab`, `get_slab_properties`
- Крыши: `create_roof`, `update_roof`, `delete_roof`, `get_roof_types`
- Лестницы: `create_stairs`, `update_stairs`, `delete_stairs`, `get_stairs_types`
- Mesh: `create_mesh_ifc`, `create_trimesh_ifc`, `get_trimesh_examples`
- Стили: `create_surface_style`, `create_pbr_style`, `apply_style_to_object`, `list_styles`, `update_style`, `remove_style`
- Инфо: `get_scene_info`, `get_object_info`, `get_selected_objects`, `list_ifc_entities`
- Скриншоты: `capture_blender_3dviewport_screenshot`, `capture_blender_window_screenshot`

**Уровень 2 — `execute_ifc_code_tool`** (когда нет специализированного инструмента):
- Работает через ifcopenshell API в песочнице (без bpy)
- Использовать для: удаления элементов (`root.remove_product`), назначения свойств, материалов, и т.д.
- **ПЕРЕД использованием** — обязательно найти правильную функцию через RAG

**Уровень 3 — `execute_blender_code`** (крайний случай):
- Прямой доступ к bpy — только когда задача НЕ решается через IFC API
- Примеры: настройка камеры, viewport, рендер, манипуляции с UI Blender

> **Известные пробелы:** `delete` есть только для roof и stairs. Для удаления wall, door, slab, window — используй `execute_ifc_code_tool` + `root.remove_product`.

### RAG база знаний (ifcopenshell)

**Перед любым вызовом `execute_ifc_code_tool`** — ищи правильный подход через RAG:
1. `search_ifc_knowledge` — семантический поиск по базе
2. `find_ifc_function` — поиск по операции и типу объекта
3. `get_ifc_function_details` — полная документация функции
4. `get_ifc_module_info` — обзор модуля

Если RAG не инициализирован — сначала вызови `ensure_ifc_knowledge_ready`.

### Порядок работы

1. Получить состояние сцены (`get_scene_info`)
2. Проверить есть ли специализированный инструмент (уровень 1)
3. Если нет — найти подход через RAG, затем выполнить через `execute_ifc_code_tool` (уровень 2)
4. Проверить результат (`get_scene_info` / скриншот)

---

## Standalone IFC-сервер (Phase 2)

Автономный MCP-сервер без зависимости от Blender. Живёт в `server/`.

### Запуск

```bash
cd server
~/.local/bin/uv sync
# Как MCP-сервер:
.venv/bin/python -m bim_eskd.main
# С авто-открытием IFC:
BIM_ESKD_IFC_PATH=../projects/001_server_container/model.ifc .venv/bin/python -m bim_eskd.main
```

### Инструменты (29 шт)

| Категория | Инструменты |
|---|---|
| Проект | `new_ifc_project`, `open_ifc_project`, `save_ifc_project` |
| Стены | `create_wall`, `create_two_point_wall`, `update_wall`, `get_wall_properties` |
| Плиты | `create_slab`, `get_slab_properties` |
| Двери | `create_door`, `get_door_properties` |
| Окна | `create_window`, `get_window_properties` |
| Крыши | `create_roof`, `delete_roof` |
| Проёмы | `create_opening`, `delete_element` |
| Сцена | `get_scene_info`, `get_object_info`, `list_ifc_entities` |
| SVG | `render_view`, `get_model_bounds` |
| RAG | `search_standards`, `ensure_standards_ready` |
| ЕСКД | `generate_sheet`, `generate_spec`, `list_sheets`, `get_sheet` |
| Публикация | `publish_sheets` |

### SVG рендеринг

```
render_view(output_path, view="plan|front|back|left|right", scale=50)
```

Генерирует SVG-проекции из IFC-модели через `ifcopenshell.draw` (hidden-line removal).
Требует `IfcBuildingStorey.Elevation != None` — рендерер выставляет автоматически.
Plan: `auto_floorplan=True`, elevation: `auto_elevation=True` (все 4 фасада в одном SVG).
Время: ~8с на вид (320 продуктов).

### ЕСКД чертежи (Phase 3)

```python
# Генерация листа с ЕСКД рамкой + штампом
generate_sheet(project_id="001_server_container", view="plan", scale=50,
               title="План", designation="001.АР.001", ...)

# Спецификация оборудования (ГОСТ 21.110)
generate_spec(project_id="001_server_container", entity_types=["IfcProduct"])

# Публикация в docs/ для GitHub Pages
publish_sheets(project_id="001_server_container")
```

Модули:
- `eskd/frame.py` — ЕСКД рамка + основная надпись (ГОСТ 2.104-2006)
- `eskd/composer.py` — компоновщик листа (рамка + вид + масштаб)
- `eskd/spec_table.py` — таблица спецификации (ГОСТ 21.110)

### GitHub Pages viewer (Phase 4)

Статический HTML/CSS/JS просмотрщик чертежей: `docs/index.html`.
Функции: навигация по проектам/листам, zoom/pan, Print→PDF, тёмная тема.

---

## RAG нормативной базы (Phase 1)

### Парсинг стандартов

```bash
cd /home/edgar/projects/bim-eskd
.venv/bin/python -m standards.parser.cli standards/raw/ -o standards/parsed/
```

PDF → JSONL чанки (текст + таблицы в markdown). Таблицы сохраняются целиком.

### Поиск по нормативам

Через MCP (bonsai-mcp или standalone):
- `search_standards(query, document?, section?)` — семантический поиск
- `ensure_standards_ready(force_rebuild?)` — инициализация индекса

### Добавление документов

1. Положить PDF в `standards/raw/`
2. Запустить парсер: `python -m standards.parser.cli standards/raw/ -o standards/parsed/`
3. Вызвать `ensure_standards_ready(force_rebuild=True)` для переиндексации

---

## Дополнительные сценарии

- **Входящий IFC от архитектора** — обогащение существующей модели инженерными системами через ifc-bonsai-mcp

---

## Статус проектов

| # | Название | Раздел | Refs | Статус |
|---|---|---|---|---|
| 001 | server_container | ЭОМ | — | in-progress |

_Обновлять при добавлении каждого нового проекта._
