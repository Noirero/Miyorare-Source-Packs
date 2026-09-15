#!/usr/bin/env python3
"""Apply constrained, reusable Compatibility Farm source repair recipes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class RepairError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RepairError(f"{path} must contain a JSON object")
    return value


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def find_recipe(data: dict[str, Any], recipe_id: str, provider: str) -> dict[str, Any]:
    recipes = data.get("recipes")
    if not isinstance(recipes, list):
        raise RepairError("recipes must be a list")
    for recipe in recipes:
        if isinstance(recipe, dict) and recipe.get("id") == recipe_id:
            providers = recipe.get("providers")
            if not isinstance(providers, list) or provider not in providers:
                raise RepairError(f"recipe {recipe_id} does not support provider {provider}")
            return recipe
    raise RepairError(f"unknown repair recipe: {recipe_id}")


def _matching_paren(text: str, open_index: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    i = open_index
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        else:
            if ch in ('"', "'"):
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise RepairError("unbalanced webClient.httpGet(...) call")


def _has_top_level_comma(value: str) -> bool:
    paren = bracket = brace = 0
    quote: str | None = None
    escaped = False
    for ch in value:
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch == "," and paren == bracket == brace == 0:
            return True
    return False


def append_http_get_header_argument(text: str, argument: str) -> tuple[str, int, int]:
    marker = "webClient.httpGet("
    cursor = 0
    replacements: list[tuple[int, str]] = []
    already = 0
    while True:
        start = text.find(marker, cursor)
        if start < 0:
            break
        open_index = start + len(marker) - 1
        close_index = _matching_paren(text, open_index)
        inner = text[open_index + 1 : close_index]
        if _has_top_level_comma(inner):
            if argument in inner:
                already += 1
        else:
            replacements.append((close_index, f", {argument}"))
        cursor = close_index + 1

    if not replacements:
        return text, 0, already

    result = text
    for index, insertion in reversed(replacements):
        result = result[:index] + insertion + result[index:]
    return result, len(replacements), already


def apply_recipe(
    recipes: dict[str, Any],
    recipe_id: str,
    provider: str,
    canonical_id: str,
    source_path: Path,
) -> dict[str, Any]:
    recipe = find_recipe(recipes, recipe_id, provider)
    if recipe.get("operation") != "append-http-get-header-argument":
        raise RepairError(f"unsupported operation for {recipe_id}")
    if not source_path.is_file():
        raise RepairError(f"source path does not exist: {source_path}")

    before = source_path.read_text(encoding="utf-8")
    requires = recipe.get("requiresTokens", [])
    if not isinstance(requires, list) or any(not isinstance(x, str) for x in requires):
        raise RepairError("requiresTokens must be a string list")
    missing = [token for token in requires if token not in before]
    if missing:
        raise RepairError(f"repair precondition failed; missing tokens: {missing}")

    argument = recipe.get("argument")
    if not isinstance(argument, str) or not argument:
        raise RepairError("repair argument must be non-empty")
    after, changes, already = append_http_get_header_argument(before, argument)

    safety = recipe.get("safety")
    if not isinstance(safety, dict) or safety.get("failClosed") is not True:
        raise RepairError("recipe must be failClosed")
    minimum = int(safety.get("minChanges", 1))
    maximum = int(safety.get("maxChanges", 0))
    if changes == 0 and already > 0 and safety.get("idempotent") is True:
        status = "ALREADY_APPLIED"
    else:
        if changes < minimum:
            raise RepairError(f"repair changed {changes} call(s), below minimum {minimum}")
        if maximum <= 0 or changes > maximum:
            raise RepairError(f"repair changed {changes} call(s), above maximum {maximum}")
        source_path.write_text(after, encoding="utf-8")
        status = "APPLIED"

    return {
        "schemaVersion": 1,
        "recipeId": recipe_id,
        "provider": provider,
        "canonicalId": canonical_id,
        "sourcePath": str(source_path),
        "status": status,
        "changes": changes,
        "alreadyAppliedCalls": already,
        "beforeSha256": sha256_text(before),
        "afterSha256": sha256_text(after),
        "ownerActionRequired": False,
        "publishEligible": False,
        "requiresRetest": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipes", default="compatibility/repair-recipes.json")
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--canonical-id", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        recipes = load_json(args.recipes)
        source_path = args.root / args.path
        report = apply_recipe(recipes, args.recipe, args.provider, args.canonical_id, source_path)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        return 0
    except (RepairError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
