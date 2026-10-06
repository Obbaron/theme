# Personal Theme

A small, Noctalia-inspired application theme generator using Python and Jinja2.

## Install

```bash
cd ~/.config/theme
python -m venv .venv
.venv/bin/pip install -e .
```

Or install the package into your preferred Python environment:

```bash
pip install -e ~/.config/theme
```

## Commands

```bash
theme list
theme validate
theme render
theme render kitty
```

## Palette

`palette/current.json` is the source of truth.

`palette/noctalia.json` is included as a starting point for preserving the Noctalia role vocabulary.

Replace the example colors/templates with your existing Noctalia community templates as you migrate.

## Generated files

Application theme fragments are written to the paths specified in each app's `template.toml`.

For Hyprland, source the generated file from your main config:

```ini
source = ~/.config/hypr/generated/colors.conf
```

The `generated/` directory is reserved for future templates that should be kept entirely inside this repository. Application-specific output paths remain controlled by each manifest.
