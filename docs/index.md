---
layout: default
title: Wave Overhangs
---

# Wave Overhangs for OrcaSlicer 2.5.0

**Экспериментальный Python-плагин** для генерации anchored wavefront-траекторий на неподдерживаемых нависаниях в штатном OrcaSlicer 2.5.0.

<blockquote>
  <strong>Статус: экспериментальный, не готов к печати.</strong>
  Сквозная проверка в OrcaSlicer 2.5.0 ещё не завершена. Функция выключена по умолчанию. Не отправляйте созданный G-code на принтер до проверки геометрии и всех вставленных команд.
</blockquote>

## Разделы документации

- [README проекта](https://github.com/4lexandrvs/WaveOverhangs/blob/main/README.md) — что реализовано, параметры, ограничения и инструкция по проверке.
- [Roadmap](https://github.com/4lexandrvs/WaveOverhangs/blob/main/README.md#roadmap) — план работ от runtime-проверки до готовности релиза.
- [Implementation notes](IMPLEMENTATION_NOTES.html) — архитектура, алгоритм, G-code и известные приближения.
- [OrcaSlicer API findings](API_FINDINGS.html) — результаты исследования Python API OrcaSlicer 2.5.0.
- [Исходный код плагина](https://github.com/4lexandrvs/WaveOverhangs/blob/main/plugin/WaveOverhangs.py).
- [Тесты](https://github.com/4lexandrvs/WaveOverhangs/tree/main/tests).

## Что уже реализовано

- Интеграция с `Step.posPrepareInfill` и `Step.psGCodePostProcess`.
- Поиск неподдерживаемых участков внутренних infill-поверхностей.
- Anchored wavefront propagation через последовательные polygon offsets.
- Smart Bridgeability: два критерия отбора областей и обработка отверстий.
- Морфологическое разделение узких перемычек.
- Приближённое построение seed-полосы.
- Вычитание занятой wavefront-области из обычного infill.
- Вставка траекторий в экспортируемый G-code с восстановлением ряда модальных состояний.

Это перечень реализованного кода, а не утверждение о подтверждённой работе на принтере.

## Что пока не завершено

- Реальная проверка в штатном OrcaSlicer 2.5.0.
- Точная ClipperZ-экстракция открытых seed-полилиний: сейчас используется приближение через offsets и boolean operations.
- Полный порт ZigZag joining, Smart path orientation и corner-aware spacing taper.
- Полная проверка G-code на разных принтерах и firmware.
- Физические тестовые печати.

## Как начать проверку

1. Запустить Python unit-тесты из [README](https://github.com/4lexandrvs/WaveOverhangs/blob/main/README.md#how-to-test).
2. Проверить загрузку плагина с `enabled = false` в чистом профиле OrcaSlicer 2.5.0.
3. Подготовить тестовые модели: широкое нависание, узкая шейка, отверстие, близкие островки опоры, вогнутая область и отрицательный контроль.
4. Только для отдельного тестового экспорта включить плагин.
5. Проверить экспортированный G-code, а не только preview OrcaSlicer: вставленные после slicing траектории в preview не отображаются.

Полная последовательность и критерии проверки описаны в [README](https://github.com/4lexandrvs/WaveOverhangs/blob/main/README.md#how-to-test).

## Репозиторий

[4lexandrvs/WaveOverhangs на GitHub](https://github.com/4lexandrvs/WaveOverhangs)
