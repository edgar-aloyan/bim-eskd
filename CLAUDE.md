# CLAUDE.md

> Читай этот файл первым. Это главная точка входа в проект.

---

## Суть проекта

Система генерации инженерной документации по ЕСКД на основе BIM/IFC моделей.

Рабочий процесс:
- Инженер промптит Claude Code
- Claude Code через MCP-сервер генерирует IFC модель
- Сервер рендерит SVG виды (ifcopenshell.draw, HLR), собирает ЕСКД листы, публикует на GitHub Pages
- Заказчику отправляются .ifc + .pdf (Print→PDF из viewer)

Каждый проект — самостоятельная единица с номером. Новые проекты ссылаются на предыдущие как на референсы.

---

## Стек

| Инструмент | Роль |
|---|---|
| Claude Code | LLM-агент |
| **bim-eskd server** | MCP-сервер (3 инструмента: execute_code, search_rag, manage_rag) |
| ifcopenshell | Python API для IFC + ifcopenshell.draw (HLR рендер) |

---

## Установка

```bash
cd /home/edgar/projects/bim-eskd/server
~/.local/bin/uv sync
```

MCP подключение — в `~/.claude.json` (секция `mcpServers`):
```json
"bim-eskd": {
  "type": "stdio",
  "command": "/home/edgar/projects/bim-eskd/server/.venv/bin/python",
  "args": ["-m", "bim_eskd.main"],
  "cwd": "/home/edgar/projects/bim-eskd/server"
}
```

---

## Запуск

```bash
# Как MCP-сервер (автоматически через Claude Code):
cd server && .venv/bin/python -m bim_eskd.main

# С авто-открытием IFC:
BIM_ESKD_IFC_PATH=../projects/001_server_container/model.ifc .venv/bin/python -m bim_eskd.main
```

---

## Структура проекта

```
/
├── CLAUDE.md                        ← ТЫ ЗДЕСЬ
│
├── server/                          ← MCP-сервер
│   ├── pyproject.toml
│   └── src/bim_eskd/
│       ├── main.py                  ← MCP entry point (3 инструмента)
│       ├── sandbox/                 ← execute_code sandbox (security, executor, rasterizer)
│       ├── lib/                     ← Фасад для sandbox (documents, html_sheet, render, eskd_api)
│       ├── ifc_engine/              ← project_manager + ifc_utils (singleton, утилиты)
│       ├── svg_renderer/            ← IFC → SVG через ifcopenshell.draw (HLR)
│       ├── eskd/                    ← ЕСКД рамки, штампы, компоновка листов
│       └── rag/                     ← Unified RAG (5 категорий, ChromaDB)
│
├── standards/                       ← нормативная база
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
├── docs/                           ← GitHub Pages viewer
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

## Работа с MCP

**Никогда не читай .ifc файлы напрямую.** Работай через `execute_code`.

### Порядок работы

1. Открыть проект: `execute_code("project.open_project('/path/to/model.ifc')")`
2. Писать Python/ifcopenshell код через `execute_code` (любые IFC операции)
3. Проверить: `execute_code("print(lib.get_info())")`
4. Сохранить: `execute_code("project.save()")`
5. При необходимости искать паттерны: `search_rag("как создать стену")`

---

## MCP-сервер

Автономный MCP-сервер на чистом ifcopenshell. Живёт в `server/`.

### Инструменты (3 шт)

| Инструмент | Описание |
|---|---|
| `execute_code` | Выполнение Python/ifcopenshell кода в sandbox. Доступны: `ifcopenshell`, `numpy`, `lxml`, `lib` (фасад), `project`, `ifc`, `workdir`. SVG авто-растеризуется в PNG. |
| `search_rag` | Поиск по unified RAG (5 категорий: API, SCRIPTS, REGULATIONS, GLOSSARY, TEMPLATES). Фильтр по jurisdiction. |
| `manage_rag` | Управление RAG: add, mark_failure, seed, build_standards. |

### Sandbox namespace (execute_code)

| Переменная | Что это |
|---|---|
| `project` | ProjectManager (open_project, save, get_element, get_products) |
| `ifc` | Текущий ifcopenshell.file |
| `workdir` | Path к рабочей директории (SVG-файлы тут авто-растеризуются) |
| `lib` | Фасад: add_sheet, generate_docs, list_sheets, render_plan, render_elevation, compose_eskd_sheet, create_spec_table, create_sld, get_info, save |
| `ifcopenshell` | Полный ifcopenshell + ifcopenshell.api, .draw, .geom |
| `np` / `numpy` | NumPy |
| `etree` | lxml.etree |
| `math, json, re, collections, itertools, datetime, Path` | Python stdlib |

### SVG рендеринг

Через `lib.render_plan()` / `lib.render_elevation()` или напрямую `ifcopenshell.draw`.
HLR, ~8с на вид (320 продуктов). `IfcBuildingStorey.Elevation` выставляется автоматически.

### Комплект документов (IFC → HTML)

Документы описываются в IFC модели:
- `IfcDocumentInformation` — каждый лист (title, designation)
- `IfcAnnotation` + `Pset_ESKD_Sheet` — все поля штампа
- `IfcRelAssociatesDocument` — привязка к проекту

```python
# Через execute_code:

# 1. Описать листы в IFC
lib.add_sheet("plan", view="plan", title="План расположения оборудования",
    designation="001.ЭОМ.001", scale="1:50", format="A3",
    organization="BIM-ESKD", developed_by="Инженер",
    date="03.2026", sheet_number="1", total_sheets="3")
lib.add_sheet("front", view="front", title="Фасад",
    designation="001.ЭОМ.002", form=2, sheet_number="2", total_sheets="3", ...)
project.save()

# 2. Сгенерировать HTML (читает IFC → рендерит виды → собирает листы)
paths = lib.generate_docs(str(workdir))
# → ["/path/plan.html", "/path/front.html"]
```

HTML-лист: рамка (SVG линии) + чертёж (SVG) + штамп (HTML-текст).
Печать: File → Print → Save as PDF (размер страницы из @page).

Модули:
- `lib/documents.py` — CRUD для IfcDocumentInformation + Pset_ESKD_Sheet
- `lib/html_sheet.py` — генерация HTML из IFC-описания листа
- `eskd/frame.py` — ЕСКД рамка + основная надпись (ГОСТ 2.104-2006)
- `eskd/composer.py` — компоновщик SVG-листа (legacy)
- `eskd/spec_table.py` — таблица спецификации (ГОСТ 21.110)

---

## RAG нормативной базы

### Парсинг стандартов

```bash
cd /home/edgar/projects/bim-eskd
.venv/bin/python -m standards.parser.cli standards/raw/ -o standards/parsed/
```

PDF → JSONL чанки (текст + таблицы в markdown). Таблицы сохраняются целиком.

### Поиск по нормативам

Через MCP:
- `search_rag(query, categories="REGULATIONS")` — семантический поиск по нормам
- `search_rag(query, categories="API,SCRIPTS")` — поиск по ifcopenshell API и скриптам
- `search_rag(query, categories="GLOSSARY")` — мультиязычный глоссарий (en/ru/hy + IFC маппинг)
- `search_rag(query, jurisdiction="RU")` — фильтр по юрисдикции (RU, AM, US; универсальные записи включаются всегда)
- `manage_rag(action="seed")` — заполнить RAG паттернами из кодовой базы (30 записей: API, скрипты, глоссарий, шаблоны)
- `manage_rag(action="build_standards")` — проиндексировать JSONL из standards/parsed/

### Юрисдикция проекта

В IFC модели юрисдикция хранится в `Pset_ProjectJurisdiction` на IfcProject:
```python
lib.set_jurisdiction("AM", languages=["hy", "ru", "en"])
info = lib.get_jurisdiction()  # {"jurisdiction": "AM", "languages": ["hy", "ru", "en"]}
```

RAG search автоматически фильтрует по jurisdiction — возвращает записи для указанной юрисдикции + универсальные.
Глоссарий содержит cross-jurisdiction refs через `equivalent_rules` (e.g. "RU:ПУЭ 1.7|US:NEC 250").

### Добавление документов

1. Положить PDF в `standards/raw/`
2. Запустить парсер: `python -m standards.parser.cli standards/raw/ -o standards/parsed/`
3. Вызвать `manage_rag(action="build_standards")` для переиндексации

---

## Статус проектов

| # | Название | Раздел | Refs | Статус |
|---|---|---|---|---|
| 001 | server_container | ЭОМ | — | in-progress |

_Обновлять при добавлении каждого нового проекта._
