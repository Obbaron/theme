#!/usr/bin/env python3
"""Small Jinja2-based application theme generator."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parent
APPS_DIR = ROOT / "apps"
PALETTE_DIR = ROOT / "palette"


def xdg_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


XDG_CONFIG_HOME = xdg_path("XDG_CONFIG_HOME", "~/.config")
XDG_DATA_HOME = xdg_path("XDG_DATA_HOME", "~/.local/share")
XDG_STATE_HOME = xdg_path("XDG_STATE_HOME", "~/.local/state")
XDG_CACHE_HOME = xdg_path("XDG_CACHE_HOME", "~/.cache")


@dataclass
class Template:
    id: str
    app_id: str
    directory: Path
    input_path: str
    output_paths: list[str]
    requires_path: str | None = None
    pre_hook: str | None = None
    post_hook: str | None = None


@dataclass
class App:
    id: str
    name: str
    category: str
    directory: Path
    templates: list[Template]


def expand_path(value: str) -> Path:
    replacements = {
        "$XDG_CONFIG_HOME": str(XDG_CONFIG_HOME),
        "$XDG_DATA_HOME": str(XDG_DATA_HOME),
        "$XDG_STATE_HOME": str(XDG_STATE_HOME),
        "$XDG_CACHE_HOME": str(XDG_CACHE_HOME),
        "$HOME": str(Path.home()),
    }
    for variable, replacement in replacements.items():
        value = value.replace(variable, replacement)
    return Path(value).expanduser()


def load_palette() -> dict[str, Any]:
    palette_file = PALETTE_DIR / "current.json"
    if not palette_file.exists():
        raise RuntimeError(f"Palette not found: {palette_file}")
    with palette_file.open() as f:
        palette = json.load(f)
    if "colors" not in palette:
        raise RuntimeError(f"{palette_file} does not contain a 'colors' object.")
    return palette


def load_app(directory: Path) -> App:
    manifest_path = directory / "template.toml"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing manifest: {manifest_path}")

    with manifest_path.open("rb") as f:
        data = tomllib.load(f)

    catalog = data.get("catalog", {})
    app_id = catalog.get("id", directory.name)
    name = catalog.get("name", app_id)
    category = catalog.get("category", "misc")
    templates: list[Template] = []

    for template_id, config in data.get("templates", {}).items():
        output_path = config["output_path"]
        output_paths = [output_path] if isinstance(output_path, str) else list(output_path)
        templates.append(
            Template(
                id=template_id,
                app_id=app_id,
                directory=directory,
                input_path=config["input_path"],
                output_paths=output_paths,
                requires_path=config.get("requires_path"),
                pre_hook=config.get("pre_hook"),
                post_hook=config.get("post_hook"),
            )
        )

    return App(app_id, name, category, directory, templates)


def discover_apps() -> list[App]:
    if not APPS_DIR.exists():
        return []
    return [
        load_app(directory)
        for directory in sorted(APPS_DIR.iterdir())
        if directory.is_dir()
    ]


def create_environment(directory: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(directory),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )

    env.filters["shellquote"] = shlex.quote
    return env


def render_template(template: Template, palette: dict[str, Any]) -> str:
    env = create_environment(template.directory)
    source = env.get_template(template.input_path)
    return source.render(
        colors=palette["colors"],
        palette=palette,
        mode=palette.get("mode", "dark"),
        app={"id": template.app_id},
    )


def run_hook(
    hook: str,
    template: Template,
    output_path: Path | None = None,
) -> None:
    environment = {
        **os.environ,
        "THEME_APP": template.app_id,
        "THEME_MODE": "dark",
    }
    if output_path:
        environment["THEME_OUTPUT"] = str(output_path)

    result = subprocess.run(
        hook,
        shell=True,
        cwd=template.directory,
        env=environment,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Hook failed for {template.app_id}: {hook}")


def should_skip(template: Template) -> bool:
    if not template.requires_path:
        return False
    required = expand_path(template.requires_path)
    if not required.exists():
        print(f"    skipped: missing {required}")
        return True
    return False


def write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return False
    path.write_text(content)
    return True


def render_template_entry(template: Template, palette: dict[str, Any]) -> None:
    if should_skip(template):
        return

    print(f"  {template.app_id}/{template.id}")

    if template.pre_hook:
        run_hook(template.pre_hook, template)

    content = render_template(template, palette)

    for output in template.output_paths:
        output_path = expand_path(output)
        changed = write_if_changed(output_path, content)
        print(f"    {'updated' if changed else 'unchanged'}: {output_path}")
        if changed and template.post_hook:
            run_hook(template.post_hook, template, output_path)


def render_app(app: App, palette: dict[str, Any]) -> None:
    print(f"\n{app.name} ({app.id})")
    for template in app.templates:
        render_template_entry(template, palette)


def render_all(selected_app: str | None = None) -> None:
    palette = load_palette()
    apps = discover_apps()
    found = False

    for app in apps:
        if selected_app and app.id != selected_app:
            continue
        found = True
        render_app(app, palette)

    if selected_app and not found:
        raise RuntimeError(f"Unknown application: {selected_app}")


def validate() -> bool:
    success = True

    try:
        palette = load_palette()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return False

    colors = palette.get("colors", {})
    print(f"Palette: {len(colors)} colors")

    try:
        apps = discover_apps()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return False

    print(f"Applications: {len(apps)}\n")

    for app in apps:
        print(f"{app.name}:")
        for template in app.templates:
            input_file = template.directory / template.input_path
            if not input_file.exists():
                print(f"  ERROR: missing input {input_file}")
                success = False
                continue
            try:
                render_template(template, palette)
                print(f"  OK: {template.id}")
            except Exception as exc:
                print(f"  ERROR: {template.id}: {exc}")
                success = False

    return success


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="theme",
        description="Personal application theme generator",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")
    subparsers.add_parser("validate")

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("app", nargs="?")

    args = parser.parse_args()

    try:
        if args.command == "list":
            for app in discover_apps():
                print(f"{app.id:15} {app.name:20} {app.category}")
            return 0

        if args.command == "validate":
            return 0 if validate() else 1

        if args.command == "render":
            render_all(args.app)
            return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
