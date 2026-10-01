#!/bin/sh
# Первый Compose-файл заменяется новым релизом; остальные — конфигурация
# владельца установки. Метка Compose хранит абсолютные пути в порядке применения.

updater_override_files() {
  case "${1:-}" in
    *,*) printf '%s' "${1#*,}" ;;
  esac
}

compose() {
  compose_with_overrides "${OVERRIDE_FILES:-}" "$@"
}

compose_with_overrides() {
  if [ -z "$1" ]; then
    shift
    if [ -n "$WORKDIR" ]; then
      docker compose -p "$PROJECT" --project-directory "$WORKDIR" -f "$FILE" "$@"
    else
      docker compose -p "$PROJECT" -f "$FILE" "$@"
    fi
    return
  fi

  # Собираем аргументы с конца: -f сохраняют исходный порядок, а пути с
  # пробелами остаются одним аргументом. Пустой/пропавший override не игнорируем.
  override_file="${1##*,}"
  if [ ! -f "$override_file" ] || [ ! -r "$override_file" ]; then
    printf 'Compose override is missing or unreadable: %s\n' "$override_file" >&2
    return 1
  fi
  case "$1" in
    *,*) remaining_files="${1%,*}" ;;
    *) remaining_files="" ;;
  esac
  shift
  compose_with_overrides "$remaining_files" -f "$override_file" "$@"
}
