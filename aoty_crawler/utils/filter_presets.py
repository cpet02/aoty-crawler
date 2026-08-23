"""Named, reusable combinations of the Results-view sidebar filters.

Stored as a flat JSON dict keyed by preset name in data/filter_presets.json —
same pattern as ratings.json, independent of any scrape job.
"""

import json
import os

PRESETS_FILENAME = 'filter_presets.json'


def presets_path(data_dir):
    return os.path.join(data_dir, PRESETS_FILENAME)


def load_presets(data_dir):
    path = presets_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_presets(presets, data_dir):
    path = presets_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(presets, f, indent=2)


def set_preset(data_dir, name, filters):
    presets = load_presets(data_dir)
    presets[name] = filters
    save_presets(presets, data_dir)
    return presets[name]


def delete_preset(data_dir, name):
    presets = load_presets(data_dir)
    if name in presets:
        del presets[name]
        save_presets(presets, data_dir)
