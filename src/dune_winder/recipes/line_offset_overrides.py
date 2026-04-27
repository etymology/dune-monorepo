from __future__ import annotations

import re


_WRAP_IDENTIFIER_RE = re.compile(r"\((\d+),(\d+)\)")
_ANCHOR_TO_TARGET_NAME = "~anchorToTarget("
_EPSILON = 1e-9


def format_number(value: float) -> str:
    text = "{0:.6f}".format(float(value)).rstrip("0").rstrip(".")
    if text in ("", "-0"):
        return "0"
    return text


def normalize_line_key(line_key) -> str:
    text = str(line_key).strip()
    match = _WRAP_IDENTIFIER_RE.fullmatch(text)
    if match is None:
        raise ValueError("Line key must look like '(wrap,line)'.")
    return f"({int(match.group(1))},{int(match.group(2))})"


def normalize_line_offset_overrides(raw_overrides) -> dict[str, dict]:
    if not isinstance(raw_overrides, dict):
        return {}

    normalized = {}
    for raw_key, raw_value in raw_overrides.items():
        if not isinstance(raw_value, dict):
            continue
        line_key = normalize_line_key(raw_key)
        entry = dict(raw_value)
        entry["x"] = float(entry.get("x", 0.0))
        entry["y"] = float(entry.get("y", 0.0))
        normalized[line_key] = entry
    return normalized


def line_offset_override_items(overrides) -> list[dict]:
    items = []
    for line_key, entry in normalize_line_offset_overrides(overrides).items():
        wrap_number, wrap_line_number = parse_line_key(line_key)
        item = dict(entry)
        item["lineKey"] = line_key
        item["wrapNumber"] = wrap_number
        item["wrapLineNumber"] = wrap_line_number
        items.append(item)
    return sorted(items, key=lambda item: (item["wrapNumber"], item["wrapLineNumber"]))


def parse_line_key(line_key: str) -> tuple[int, int]:
    normalized = normalize_line_key(line_key)
    match = _WRAP_IDENTIFIER_RE.fullmatch(normalized)
    assert match is not None
    return int(match.group(1)), int(match.group(2))


def extract_line_key(line: str) -> str | None:
    match = _WRAP_IDENTIFIER_RE.search(str(line))
    if match is None:
        return None
    return f"({int(match.group(1))},{int(match.group(2))})"


def apply_line_offset_overrides(
    lines,
    overrides,
    *,
    normalize_line_text_fn,
):
    normalized_overrides = normalize_line_offset_overrides(overrides)
    if not normalized_overrides:
        return list(lines)

    updated = []
    for line in lines:
        line_key = extract_line_key(line)
        if line_key is None or line_key not in normalized_overrides:
            updated.append(line)
            continue

        entry = normalized_overrides[line_key]
        delta_x = float(entry.get("x", 0.0))
        delta_y = float(entry.get("y", 0.0))
        if abs(delta_x) < _EPSILON and abs(delta_y) < _EPSILON:
            updated.append(line)
            continue

        if _ANCHOR_TO_TARGET_NAME in str(line):
            updated.append(
                _apply_anchor_to_target_override(
                    str(line),
                    delta_x,
                    delta_y,
                    normalize_line_text_fn=normalize_line_text_fn,
                )
            )
            continue

        updated.append(
            _append_offset_fragments(
                str(line),
                delta_x,
                delta_y,
                normalize_line_text_fn=normalize_line_text_fn,
            )
        )

    return updated


def _split_trailing_comments(line: str) -> tuple[str, list[str]]:
    body = str(line).rstrip()
    comments = []
    while True:
        match = re.search(r"\s+(\([^()]*\))\s*$", body)
        if match is None:
            break
        comments.insert(0, match.group(1))
        body = body[: match.start()].rstrip()
    return body, comments


def _split_arguments(arguments: str) -> list[str]:
    tokens = []
    current = []
    depth = 0
    for char in str(arguments):
        if char == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                tokens.append(token)
            current = []
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        current.append(char)
    token = "".join(current).strip()
    if token:
        tokens.append(token)
    return tokens


def _extract_anchor_to_target_call(line: str) -> tuple[str, str, str]:
    text = str(line)
    start = text.find(_ANCHOR_TO_TARGET_NAME)
    if start < 0:
        raise ValueError("Line does not contain ~anchorToTarget.")

    depth = 0
    end = None
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end is None:
        raise ValueError("Malformed ~anchorToTarget call.")

    return text[:start].rstrip(), text[start : end + 1], text[end + 1 :].strip()


def _apply_anchor_to_target_override(
    line: str,
    delta_x: float,
    delta_y: float,
    *,
    normalize_line_text_fn,
) -> str:
    prefix, call, suffix = _extract_anchor_to_target_call(line)
    arguments = _split_arguments(call[len(_ANCHOR_TO_TARGET_NAME) : -1])
    if len(arguments) < 2:
        return line

    current_offset_x = 0.0
    current_offset_y = 0.0
    remaining = []
    for token in arguments[2:]:
        if "=" not in token:
            remaining.append(token)
            continue
        key, value = token.split("=", 1)
        if key.strip().lower() != "offset":
            remaining.append(token)
            continue
        value = value.strip()
        if not value.startswith("(") or not value.endswith(")"):
            remaining.append(token)
            continue
        values = _split_arguments(value[1:-1])
        if len(values) != 2:
            remaining.append(token)
            continue
        current_offset_x = float(values[0])
        current_offset_y = float(values[1])

    combined_x = current_offset_x + float(delta_x)
    combined_y = current_offset_y + float(delta_y)
    rebuilt = list(arguments[:2])
    if abs(combined_x) >= _EPSILON or abs(combined_y) >= _EPSILON:
        rebuilt.append(
            "offset=("
            + format_number(combined_x)
            + ","
            + format_number(combined_y)
            + ")"
        )
    rebuilt.extend(remaining)
    rebuilt_call = _ANCHOR_TO_TARGET_NAME + ",".join(rebuilt) + ")"

    parts = []
    if prefix:
        parts.append(prefix)
    parts.append(rebuilt_call)
    if suffix:
        parts.append(suffix)
    return normalize_line_text_fn(" ".join(parts))


def _append_offset_fragments(
    line: str,
    delta_x: float,
    delta_y: float,
    *,
    normalize_line_text_fn,
) -> str:
    body, comments = _split_trailing_comments(line)
    fragments = []
    if abs(delta_x) >= _EPSILON:
        fragments.append("G105 PX" + format_number(delta_x))
    if abs(delta_y) >= _EPSILON:
        fragments.append("G105 PY" + format_number(delta_y))
    if not fragments:
        return line
    return normalize_line_text_fn(" ".join([body] + fragments + comments))


__all__ = [
    "apply_line_offset_overrides",
    "extract_line_key",
    "line_offset_override_items",
    "normalize_line_key",
    "normalize_line_offset_overrides",
    "parse_line_key",
]
