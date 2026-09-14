"""Generate the canonical aggregate report and check current v2.0 documentation."""

import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

BASE = Path(__file__).resolve().parents[4]
DOC_DIR = "docs/notes/v2.0"
REPORT = DOC_DIR + "/source_data_audit_report_v2.0.md"
DOCS = {
    "README.md": ["项目简介", "环境依赖", "目录说明", "数据准备", "运行步骤", "当前结果", "常见问题排查", "联系人"],
    "README.zh-CN.md": [],
    "code/results/v2.0/README.md": [],
    DOC_DIR + "/project_document_index_v2.0.md": ["文档索引"],
    DOC_DIR + "/project_status_v2.0.md": ["处理阶段", "结果与局限", "后续工作"],
    DOC_DIR + "/data_processing_protocol_v2.0.md": ["目的与范围", "输入及来源", "原始值保留", "主键与关联", "病理报告与标本", "输出与定位", "验证及失败处理", "局限与下一步"],
    DOC_DIR + "/decision_point_protocol_v2.0.md": ["研究范围与标签口径", "输入与来源", "候选锚点定义", "时间与信息可用性", "情境与组织学分层", "信息充分性与验证", "输出与复现"],
    DOC_DIR + "/source_usage_report_v2.0.md": ["目的与来源", "临床数据用途", "分子及辅助文件用途", "临床与时间风险", "治疗标签如何使用这些数据"],
    DOC_DIR + "/decision_point_audit_report_v2.0.md": ["目的与范围", "方法与来源", "结果", "输出与追溯", "局限与下一步"],
    DOC_DIR + "/screening_candidate_report_v2.0.md": ["目的与规则", "方法与来源", "当前数量", "输出与结局使用", "复现与边界"],
    DOC_DIR + "/candidate_review_report_v2.0.md": ["范围与依据", "分组规则", "当前结果", "研究局限", "输出与复现"],
    DOC_DIR + "/candidate_cohort_report_v2.0.md": ["范围与分组规则", "筛选流程与数量", "逐点证据与边界", "候选表与输出", "复现与下一步"],
    DOC_DIR + "/treatment_label_definition_v2.0.md": ["目的与标注对象", "四类主标签", "判定顺序与边界", "研究性方案的标记", "缺失信息与时间规则", "知识截止日与证据要求", "边界案例", "结构化字段与专家审核", "文件位置、版本与下一步"],
    DOC_DIR + "/patient_split_protocol_v2.0.md": ["目的与范围", "划分规则与复现", "当前划分结果", "分布与泄漏核查", "Pilot与Core使用规则", "输出与后续工作"],
    DOC_DIR + "/treatment_catalog_report_v2.0.md": ["目的与范围", "数据整理规则", "当前结果", "方案目录", "证据使用与冻结规则", "待核查与输出"],
    DOC_DIR + "/treatment_evidence_ledger_v2.0.md": ["来源与读取范围", "证据冲突与版本边界"],
    DOC_DIR + "/treatment_screening_report_v2.0.md": ["范围与判定", "逐项结果", "文件与复现"],
    DOC_DIR + "/core_coverage_report_v2.0.md": ["范围与方法", "覆盖结果", "未覆盖记录", "输出与后续使用"],
    REPORT: ["目的与范围", "输入与运行记录", "处理与验证方法", "结果", "输出与追溯", "局限与下一步"],
}
TABLE_NAMES = {
    "patient_level_dataset": "患者",
    "cancer_level_dataset_index": "目标癌症",
    "cancer_level_dataset_non_index": "非目标癌症",
    "pathology_report_level_dataset": "病理报告",
    "cancer_panel_test_level_dataset": "NGS临床记录",
    "regimen_cancer_level_dataset": "系统治疗",
    "ca_radtx_dataset": "放疗",
    "imaging_level_dataset": "影像评估",
    "med_onc_note_level_dataset": "肿瘤内科评估",
    "tm_level_dataset": "血清肿瘤标志物",
}


def write_audit_report(base, out, processed, report_path, summary, schemas, manifest):
    """Write aggregate counts and actual provenance, without patient-level records."""
    def link(label, target):
        return f"[{label}]({Path(os.path.relpath(target, report_path.parent)).as_posix()})"

    s = summary
    date = datetime.fromisoformat(manifest["finished_utc"]).strftime("%Y%m%d")
    rows = "\n".join(f"| {TABLE_NAMES[t['table']]} | {t['table']} | {t['rows']:,} | {t['column_count']} |" for t in schemas)
    issue_text = "\n".join(f"- {name}：{count}" for name, count in s["quality_issue_counts"].items()) or "未发现当前检查范围内的主键、关联或病理标本数量异常。"
    config_link = link("源配置", base / "code/config/v2.0/source.json")
    manifest_link = link("运行清单", out / "run_manifest.json")
    inventory_link = link("原文件清单", out / "source_inventory.json")
    issues_link = link("逐条质量问题", out / "quality_issues.csv")
    runtime = manifest["runtime"]
    text = f"""# PANC 原始数据审计报告 v2.0

版本：v2.0

更新日期：{date}

状态：{manifest['status']}；仅表示本阶段执行状态。

## 目的与范围

核实PANC 1.0-public原始文件、临床表结构、字段完整性、关联键、病理标本及全部治疗记录，为下一阶段决策点整理提供可追溯的起点。统计范围为原始发布集，输出用于后续候选决策点构建。

## 输入与运行记录

| 项目 | 当前记录 |
| --- | --- |
| 数据版本 | {manifest['source_release']} |
| 原始路径 | 由{config_link}指定，完整路径见{manifest_link} |
| 文件范围 | {s['source_files']}个原文件；其中解析{s['clinical_tables']}张临床表 |
| 开始时间UTC | {manifest['started_utc']} |
| 完成时间UTC | {manifest['finished_utc']} |
| Python与平台 | {runtime['python']}；{runtime['platform']} |
| 第三方运行依赖 | 本阶段无第三方依赖 |
| 原始文件版本依据 | {inventory_link}中的SHA-256 |
| 配置、实现和检查代码依据 | {manifest_link}中的配置、代码和检查代码SHA-256 |

## 处理与验证方法

按原CSV字符串逐字段保留，包括空值、明确未知和真实0。按患者、癌症及事件的复合键核查关联；展开病理报告全部已填标本槽位，与声明标本数比较；登记全部方案开始记录，区分目标与非目标癌症。

导出后重新读取原CSV，与JSONL逐行核对全部原字段。运行结束前再次核对原文件内容。具体键、时间换算、异常处理与尚未实现的内容见[数据处理规则](data_processing_protocol_v2.0.md)。

## 结果

临床记录共{s['clinical_records']:,}条，涉及{s['patients']:,}名患者、{s['index_cancers']:,}条目标癌症诊断。字段逐值不一致为{s['clinical_field_roundtrip_mismatches']}，运行前后原文件变化为{len(s['source_files_changed'])}。

病理共{s['pathology_reports']:,}份报告，每份{s['pathology_source_columns']}个原字段，展开{s['pathology_specimens']:,}个标本，单份最多{s['maximum_specimens_per_report']}个标本。阴性、其他癌症、原位癌及浸润癌均保留。

系统治疗记录共{s['all_regimen_records']:,}条，其中目标癌症{s['index_cancer_regimen_records']:,}条、非目标癌症{s['non_index_cancer_regimen_records']:,}条。同患者、同癌症、同开始日多记录组共{s['same_cancer_same_day_groups']}组，其中目标癌症{s['same_day_groups_index_cancer']}组、非目标癌症{s['same_day_groups_non_index_cancer']}组。以上都是记录计数，不能直接当成独立决策点数量。

### 各表规模

| 数据类别 | 原表名称 | 记录数 | 字段数 |
| --- | --- | ---: | ---: |
{rows}

### 质量问题

{issue_text}

具体检查结果见{issues_link}。当前检查通过仅支持表结构、原值保留及所列关联的一致性，不证明临床语义、时间可用性或治疗适用性已经正确。

## 输出与追溯

| 产物 | 使用方式 |
| --- | --- |
| {link('审计汇总', out/'audit_summary.json')} | 本报告汇总数值的结构化来源 |
| {link('表结构', out/'table_schemas.json')}和{link('字段概况', out/'field_profile.csv')} | 查看字段、主键、空值、明确缺失编码和0值 |
| {link('临床保真记录', processed/'clinical_records')} | 每条记录包含所有原字段与来源定位 |
| {link('病理报告索引', processed/'pathology_reports.jsonl')}和{link('标本明细', processed/'pathology_specimens.jsonl')} | 逐报告和逐标本回连完整病理字段 |
| {link('治疗登记CSV', processed/'treatment_record_registry.csv')}和{link('治疗登记JSONL', processed/'treatment_record_registry.jsonl')} | 全部方案记录，训练／测试可用性仍为not_evaluated |
| {manifest_link} | 运行状态、环境及输入和实现校验和 |

从项目根目录运行 `python -B code/scripts/run_v2_0.py audit --config code/config/v2.0/source.json` 可重新生成本报告及当前阶段结果。

## 局限与下一步

本阶段没有解析完整分子结果，也没有完成病理及临床观察的报告可用时间核实。取材日不等于病理签发日；全字段保留不等于临床信息充分。最终可用决策点和专家标签仍未确定，没有模型性能指标。

下一步对照发布指南和变量字典建立时间轴，核实PDAC支持程度、多癌症归属、方案变化和治疗情境，再定义质量分层。当前计划见[项目进度](project_status_v2.0.md)。
"""
    report_path.write_text(text, encoding="utf-8")


def check_documents(base=BASE):
    errors, links_checked = [], 0
    for name, headings in DOCS.items():
        path = base / name
        if not path.is_file():
            errors.append(f"Missing document: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("# ") or "v2.0" not in text.splitlines()[0]:
            errors.append(f"Missing versioned title: {name}")
        if "版本：v2.0" not in text or not re.search(r"更新日期：\d{8}", text) or "状态：" not in text:
            errors.append(f"Missing document metadata: {name}")
        for heading in headings:
            if "## " + heading not in text:
                errors.append(f"Missing section {heading}: {name}")
        if name.startswith(DOC_DIR) and not re.fullmatch(r"[a-z][a-z0-9_]*_v2\.0\.md", path.name):
            errors.append(f"Nonconforming narrative filename: {name}")
        prose = re.sub(r"```.*?```", "", text, flags=re.S)
        for label, url in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", prose):
            if urlsplit(url).scheme or url.startswith("#"):
                continue
            target = (path.parent / unquote(url.split("#", 1)[0])).resolve()
            links_checked += 1
            if not target.exists():
                errors.append(f"Broken link in {name}: {label} -> {url}")
        # A wrapped Markdown table must retain the same column count on every row.
        columns = None
        for line in prose.splitlines():
            if line.startswith("|"):
                count = len(re.split(r"(?<!\\)\|", line))
                if columns is not None and columns != count:
                    errors.append(f"Inconsistent table width: {name}: {line[:65]}")
                columns = count
            else:
                columns = None
    for old in ["docs/v2.0/STATUS.md", "docs/v2.0/DATA_PROTOCOL.md", "docs/v2.0/CLEANUP.md", "outputs/v2.0/01_source_audit/REPORT.md"]:
        if (base / old).exists():
            errors.append(f"Duplicate outdated narrative document: {old}")
    for old in ["src", "tests", "configs", "outputs", "archive"]:
        if (base / old).exists():
            errors.append(f"Nonstandard active root directory: {old}")
    for required in ["data/raw", "data/processed", "code/src", "code/scripts", "code/notebooks", "code/results", "code/config", "code/tests", "docs/notes", "docs/papers", "docs/slides", "warehouse"]:
        if not (base / required).is_dir():
            errors.append(f"Missing standard directory: {required}")
    if not (base / "code/requirements.txt").is_file():
        errors.append("Missing code/requirements.txt")
    unregistered = sorted(p.relative_to(base).as_posix() for p in (base / DOC_DIR).glob("*.md") if p.relative_to(base).as_posix() not in DOCS)
    errors.extend(f"Document missing from registry: {name}" for name in unregistered)
    out = base / "code/results/v2.0/01_source_audit"
    try:
        summary = json.loads((out / "audit_summary.json").read_text(encoding="utf-8"))
        manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
        report = (base / REPORT).read_text(encoding="utf-8")
        if manifest["summary"] != summary:
            errors.append("Run manifest and audit summary disagree")
        for field in ["clinical_records", "patients", "index_cancers", "pathology_reports", "pathology_specimens", "all_regimen_records", "index_cancer_regimen_records", "non_index_cancer_regimen_records"]:
            if f"{summary[field]:,}" not in report:
                errors.append(f"Report missing current count: {field}")
        for field in ["started_utc", "finished_utc"]:
            if manifest[field] not in report:
                errors.append(f"Report run provenance is stale: {field}")
        if manifest["runtime"]["python"] not in report:
            errors.append("Report Python version is stale")
        config_path = base / manifest["config_file"]
        if hashlib.sha256(config_path.read_bytes()).hexdigest() != manifest["config_sha256"]:
            errors.append("Config changed after report generation")
        processed = base / manifest["processed_dir"]
        for item in ["clinical_records", "pathology_reports.jsonl", "pathology_specimens.jsonl", "treatment_record_registry.csv", "treatment_record_registry.jsonl"]:
            if not (processed / item).exists() or (out / item).exists():
                errors.append(f"Intermediate data misplaced or absent: {item}")
        for name, expected in {**manifest["code_sha256"], **manifest["test_sha256"]}.items():
            actual = hashlib.sha256((base / name).read_bytes()).hexdigest()
            if actual != expected:
                errors.append(f"Source changed after report generation: {name}")
    except (OSError, KeyError, ValueError) as error:
        errors.append(f"Cannot validate report provenance: {error}")
    try:
        phase2 = base / "code/results/v2.0/02_decision_points"
        manifest2 = json.loads((phase2 / "run_manifest.json").read_text(encoding="utf-8"))
        summary2 = json.loads((phase2 / "decision_point_summary_v2.0.json").read_text(encoding="utf-8"))
        if manifest2["status"] != "completed" or summary2 != manifest2["summary"]:
            errors.append("Phase 02 execution is incomplete or inconsistent")
        if summary2["final_eligible_decision_points"] is not None or summary2["expert_labels"] is not None:
            errors.append("Phase 02 must not publish unadjudicated eligibility or labels")
        config2 = base / manifest2["config_file"]
        if hashlib.sha256(config2.read_bytes()).hexdigest() != manifest2["config_sha256"]:
            errors.append("Phase 02 config changed after execution")
        for name, expected in {**manifest2["code_sha256"], **manifest2["input_sha256"], **manifest2["output_sha256"]}.items():
            if hashlib.sha256((base/name).read_bytes()).hexdigest() != expected:
                errors.append(f"Phase 02 provenance changed: {name}")
        report2 = (base / DOC_DIR / "decision_point_audit_report_v2.0.md").read_text(encoding="utf-8")
        for field in ["clinical_records_rechecked", "timeline_events", "regimen_records", "candidate_anchors"]:
            if f"{summary2[field]:,}" not in report2:
                errors.append(f"Phase 02 report count missing: {field}")
    except (OSError, KeyError, ValueError) as error:
        errors.append(f"Cannot validate phase 02: {error}")
    try:
        phase3 = base / "code/results/v2.0/03_screening_candidates"
        manifest3 = json.loads((phase3 / "run_manifest.json").read_text(encoding="utf-8"))
        summary3 = json.loads((phase3 / "screening_summary_v2.0.json").read_text(encoding="utf-8"))
        if manifest3["status"] != "completed" or manifest3["summary"] != summary3:
            errors.append("screening run is incomplete or inconsistent")
        config3 = base / manifest3["config_file"]
        if hashlib.sha256(config3.read_bytes()).hexdigest() != manifest3["config_sha256"]:
            errors.append("screening config changed after execution")
        for name, expected in {**manifest3["code_sha256"], **manifest3["input_sha256"], **manifest3["output_sha256"]}.items():
            if hashlib.sha256((base/name).read_bytes()).hexdigest() != expected:
                errors.append(f"screening provenance changed: {name}")
        if summary3["final_eligible_decision_points"] is not None or summary3["expert_labels"] is not None:
            errors.append("screening must not claim unadjudicated final labels or eligibility")
        report3 = (base / DOC_DIR / "screening_candidate_report_v2.0.md").read_text(encoding="utf-8")
        for field in ["upstream_treatment_anchors", "progression_evidence_records", "new_progression_review_groups", "registry_records", "registry_patients"]:
            if f"{summary3[field]:,}" not in report3:
                errors.append(f"screening report count missing: {field}")
        for bucket in summary3["buckets"].values():
            if f"{bucket['candidates']:,}" not in report3 or f"{bucket['patients']:,}" not in report3:
                errors.append("screening report bucket count missing")
    except (OSError, KeyError, ValueError) as error:
        errors.append(f"Cannot validate screening: {error}")
    try:
        phase4 = base / "code/results/v2.0/04_candidate_review"
        manifest4 = json.loads((phase4 / "run_manifest.json").read_text(encoding="utf-8"))
        summary4 = json.loads((phase4 / "candidate_review_summary_v2.0.json").read_text(encoding="utf-8"))
        if manifest4["status"] != "completed" or summary4 != manifest4["summary"]:
            errors.append("Candidate review execution incomplete or inconsistent")
        if hashlib.sha256((base/manifest4["config_file"]).read_bytes()).hexdigest() != manifest4["config_sha256"]:
            errors.append("Candidate review config changed after execution")
        for name, expected in {**manifest4["code_sha256"], **manifest4["input_sha256"], **manifest4["output_sha256"]}.items():
            if hashlib.sha256((base/name).read_bytes()).hexdigest() != expected:
                errors.append(f"Candidate review provenance changed: {name}")
        if summary4["final_eligible_decision_points"] is not None or summary4["expert_labels"] is not None:
            errors.append("Candidate review must not fabricate final eligibility or labels")
        report4 = (base/DOC_DIR/"candidate_review_report_v2.0.md").read_text(encoding="utf-8")
        for field in ["registry_records", "evidence_inventory_records", "same_day_progression_linked", "regimen_independence_review_added"]:
            if f"{summary4[field]:,}" not in report4:
                errors.append(f"Candidate review report count missing: {field}")
        for bucket in summary4["buckets"].values():
            if f"{bucket['records']:,}" not in report4 or f"{bucket['patients']:,}" not in report4:
                errors.append("Candidate review report bucket count missing")
    except (OSError, KeyError, ValueError) as error:
        errors.append(f"Cannot validate candidate review: {error}")
    try:
        phase5 = base / "code/results/v2.0/05_candidate_cohort"
        manifest5 = json.loads((phase5 / "run_manifest.json").read_text(encoding="utf-8"))
        summary5 = json.loads((phase5 / "candidate_cohort_summary_v2.0.json").read_text(encoding="utf-8"))
        if manifest5["status"] != "completed" or summary5 != manifest5["summary"]:
            errors.append("Candidate cohort execution incomplete or inconsistent")
        if hashlib.sha256((base/manifest5["config_file"]).read_bytes()).hexdigest() != manifest5["config_sha256"]:
            errors.append("Candidate cohort config changed after execution")
        for name, expected in {**manifest5["code_sha256"], **manifest5["input_sha256"], **manifest5["output_sha256"]}.items():
            if hashlib.sha256((base/name).read_bytes()).hexdigest() != expected:
                errors.append(f"Candidate cohort provenance changed: {name}")
        if summary5["final_eligible_decision_points"] is not None or summary5["expert_labels"] is not None:
            errors.append("Candidate cohort must not fabricate final eligibility or labels")
        if sum(v["records"] for v in summary5["roles"].values()) != summary5["registry_records"]:
            errors.append("Candidate roles do not partition the registry")
        report5 = (base/DOC_DIR/"candidate_cohort_report_v2.0.md").read_text(encoding="utf-8")
        for bucket in summary5["roles"].values():
            if f"{bucket['records']:,}" not in report5 or f"{bucket['patients']:,}" not in report5:
                errors.append("Candidate cohort report count missing")
    except (OSError, KeyError, ValueError) as error:
        errors.append(f"Cannot validate candidate cohort: {error}")
    try:
        labels = json.loads((base/"code/config/v2.0/treatment_labels.json").read_text(encoding="utf-8"))
        scope = json.loads((base/"code/config/v2.0/decision_points.json").read_text(encoding="utf-8"))["research_scope"]
        if set(labels["labels"]) != {"SUPPORTED", "CONDITIONAL", "MISMATCH", "INDETERMINATE"}:
            errors.append("Treatment label categories differ from confirmed definitions")
        if (labels["evidence_cutoff_date"], labels["evidence_cutoff_status"]) != (scope["evidence_cutoff_date"], scope["evidence_cutoff_status"]):
            errors.append("Label and research knowledge cutoffs disagree")
        definition = (base/labels["definition_document"]).read_text(encoding="utf-8")
        if labels["evidence_cutoff_date"] not in definition or any(code not in definition for code in labels["labels"]):
            errors.append("Label definition document and configuration disagree")
        if not labels["research_candidates_included"] or not labels["research_candidates_must_be_explicitly_marked"]:
            errors.append("Research candidate policy differs from confirmed rule")
    except (OSError, KeyError, ValueError) as error:
        errors.append(f"Cannot validate treatment label definitions: {error}")
    try:
        phase6 = base/"code/results/v2.0/06_patient_split"
        manifest6 = json.loads((phase6/"run_manifest.json").read_text(encoding="utf-8"))
        summary6 = json.loads((phase6/"patient_split_summary_v2.0.json").read_text(encoding="utf-8"))
        if manifest6["status"] != "completed" or manifest6["summary"] != summary6:
            errors.append("Patient split execution incomplete or inconsistent")
        if hashlib.sha256((base/manifest6["config_file"]).read_bytes()).hexdigest() != manifest6["config_sha256"]:
            errors.append("Patient split configuration changed after execution")
        for name, expected in {**manifest6["code_sha256"], **manifest6["input_sha256"], **manifest6["output_sha256"]}.items():
            if hashlib.sha256((base/name).read_bytes()).hexdigest() != expected:
                errors.append(f"Patient split provenance changed: {name}")
        if summary6["core_pilot_patient_overlap"] or summary6["isolation"]["cross_split_identity_collisions"]:
            errors.append("Patient split identity leakage detected")
        if summary6["expert_labels"] is not None or summary6["final_training_sample_count"] is not None:
            errors.append("Patient split must not invent labels or final training sample counts")
    except (OSError, KeyError, ValueError) as error:
        errors.append(f"Cannot validate patient split: {error}")
    try:
        phase7=base/"code/results/v2.0/07_treatment_catalog"
        m=json.loads((phase7/"run_manifest.json").read_text(encoding="utf-8"))
        s=json.loads((phase7/"treatment_catalog_summary_v2.0.json").read_text(encoding="utf-8"))
        if m["status"]!="completed" or m["summary"]!=s:
            errors.append("Treatment catalog execution incomplete")
        for name, expected in {m["config_file"]:m["config_sha256"],**m["code_sha256"],**m["input_sha256"],**m["output_sha256"]}.items():
            if hashlib.sha256((base/name).read_bytes()).hexdigest()!=expected:
                errors.append(f"Treatment catalog provenance changed: {name}")
        if s["patient_labels_generated"] or s["observed_variants_assigned"]:
            errors.append("Catalog must not infer patient labels or unrecorded variants")
        if s["core_coverage_audit_performed"] and not s["catalog_frozen"]:
            errors.append("Core coverage audit precedes catalog freeze")
    except (OSError, KeyError, ValueError) as error:
        errors.append(f"Cannot validate treatment catalog: {error}")
    try:
        from .catalog_release import verify
        config=json.loads((base/"code/config/v2.0/treatment_catalog.json").read_text(encoding="utf-8"))
        lock=verify(base,config)
        p=base/"code/results/v2.0/08_core_coverage"
        m=json.loads((p/"run_manifest.json").read_text(encoding="utf-8"))
        s=json.loads((p/"core_coverage_summary_v2.0.json").read_text(encoding="utf-8"))
        if m["status"]!="completed" or s!=m["summary"] or s["release_sha256"]!=lock["release_sha256"]:
            errors.append("Core coverage release or summary inconsistent")
        for name,h in {**m["code_sha256"],**m["input_sha256"],**m["output_sha256"]}.items():
            if hashlib.sha256((base/name).read_bytes()).hexdigest()!=h:
                errors.append("Core coverage provenance changed: "+name)
        if s["catalog_modified_by_audit"] or s["patient_labels_generated"]:
            errors.append("Core audit must not expand catalog or assign labels")
    except (OSError,KeyError,ValueError) as error:
        errors.append(f"Cannot validate frozen catalog/Core coverage: {error}")
    return {"project_version": "v2.0", "documents_checked": len(DOCS), "local_links_checked": links_checked,
            "errors": errors, "status": "passed" if not errors else "failed",
            "scope": "GA09 section 2.1 directory layout, current narrative documents, and report provenance; clinical eligibility is not evaluated"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    result = check_documents()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
