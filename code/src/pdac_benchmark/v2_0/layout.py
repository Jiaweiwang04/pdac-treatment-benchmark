"""Enforce raw/processed/result separation before creating any output."""
from pathlib import Path


def resolve_paths(base, config):
    base = Path(base).resolve()
    resolved = []
    for field, directory in [("source_root", "data/raw"), ("processed_dir", "data/processed/v2.0"), ("results_dir", "code/results/v2.0")]:
        allowed = (base / directory).resolve()
        target = (base / config[field]).resolve()
        if not allowed.is_relative_to(base) or not target.is_relative_to(allowed) or target == allowed:
            raise ValueError(f"{field} must be a subdirectory of {directory}: {target}")
        resolved.append(target)
    for i, left in enumerate(resolved):
        for right in resolved[i + 1:]:
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ValueError("Raw data, processed data and results must not overlap")
    return tuple(resolved)
