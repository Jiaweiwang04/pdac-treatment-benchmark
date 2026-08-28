from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_DOCUMENTS = [
    ROOT / "docs" / "notes" / "project_document_index_v1.0.md",
    ROOT / "docs" / "notes" / "candidate_treatment_space_design_v0.1.md",
    ROOT / "docs" / "notes" / "evidence_constraint_label_schema_design_v0.1.md",
    ROOT / "docs" / "notes" / "external_material_intake_v0.1.md",
    ROOT / "docs" / "notes" / "pilot_label_validation_design_v0.1.md",
    ROOT / "docs" / "notes" / "standards" / "standards_index_v1.0.md",
    ROOT / "code" / "results" / "reports" / "pilot_label_validation_report_v0.1.md",
]
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
DIRECTIVE_PATTERN = re.compile(r"\b(?:do not|must not|never)\b|不要|不得|禁止", re.IGNORECASE)


def test_readmes_cover_ga09_project_entry_sections():
    chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in ("项目简介", "环境依赖", "目录说明", "数据准备", "运行步骤", "当前结果"):
        assert f"## {heading}" in chinese
    for heading in ("Project Overview", "Environment", "Directory Structure", "Data Preparation", "Reproduction Steps", "Current Results"):
        assert f"## {heading}" in english


def test_project_directory_matches_ga09_layout():
    required = [
        "data/raw",
        "data/processed",
        "code/src",
        "code/scripts",
        "code/notebooks",
        "code/config",
        "code/tests",
        "code/results/mappings",
        "code/results/reports",
        "docs/notes",
        "docs/notes/standards",
        "docs/papers",
        "docs/slides",
        "warehouse",
    ]
    assert [path for path in required if not (ROOT / path).is_dir()] == []
    assert [path for path in ("config", "reports", "tests") if (ROOT / path).exists()] == []
    assert not (ROOT / "cohort_definition_v0.1.yaml").exists()


def test_design_notes_and_generated_reports_are_separated():
    assert not (ROOT / "docs" / "notes" / "data_feasibility_audit_v1.md").exists()
    assert (ROOT / "code" / "results" / "reports" / "data_feasibility_audit_v1.md").is_file()
    assert (ROOT / "docs" / "notes" / "pilot_label_validation_design_v0.1.md").is_file()
    assert (ROOT / "code" / "results" / "reports" / "pilot_label_validation_report_v0.1.md").is_file()


def test_active_documents_use_purpose_process_results_structure():
    for path in ACTIVE_DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        assert "## Purpose" in text, path
        assert "## Process" in text, path
        assert "## Results" in text, path


def test_active_project_documents_avoid_directive_style_language():
    paths = ACTIVE_DOCUMENTS + [ROOT / "README.md", ROOT / "README.zh-CN.md"]
    for path in paths:
        assert DIRECTIVE_PATTERN.search(path.read_text(encoding="utf-8")) is None, path


def test_markdown_relative_links_resolve():
    paths = sorted((ROOT / "docs").rglob("*.md"))
    paths += sorted((ROOT / "code" / "results" / "reports").rglob("*.md"))
    paths += [ROOT / "README.md", ROOT / "README.zh-CN.md"]
    failures: list[tuple[Path, str]] = []
    for path in paths:
        for link in LINK_PATTERN.findall(path.read_text(encoding="utf-8")):
            if not link or link.startswith(("http://", "https://", "#")):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            if not target.exists():
                failures.append((path.relative_to(ROOT), link))
    assert failures == []


def test_project_filenames_avoid_ga09_special_characters():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    scoped = [
        path
        for path in result.stdout.splitlines()
        if path.startswith(("code/", "docs/"))
    ]
    failures = [path for path in scoped if re.search(r"[ @#&()]", Path(path).name)]
    assert failures == []
