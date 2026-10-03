"""Locked training/validation overlay on the existing development/Core/Pilot split."""
import json
import os
import platform
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .audit import write_csv, write_json, write_jsonl
from .candidate_review import read_jsonl
from .layout import resolve_paths
from .patient_split import (
    check_identity_isolation, digest_object, earliest_main_candidates, quota_sample, verify_lock,
)
from .source import sha256

PHASE = "10_development_split"
CONFIG = "code/config/v2.0/development_split.json"
PARENT = "data/processed/v2.0/06_patient_split/"
PARENT_MANIFEST = "code/results/v2.0/06_patient_split/run_manifest.json"
EVENTS = "data/processed/v2.0/02_decision_points/timeline_events_v2.0.jsonl"
PILOT_CONFIG = "code/config/v2.0/pilot_review_selection.json"
NAMES = {"training": "训练侧", "validation": "验证侧", "core_test": "Core测试侧",
         "extension_only": "独立保留"}


def validate_config(config):
    expected = {
        "project_version": "v2.0", "phase": PHASE, "development_patients": 435,
        "training_patients": 348, "validation_patients": 87, "core_test_patients": 80,
        "pilot_patients": 25, "pilot_policy": "existing_locked_pilot_training_only",
        "sampling_algorithm": "sha256_order_with_largest_remainder_stratum_quotas",
        "stratification": ["institution", "earliest_main_candidate_scope_at_t0"],
        "outcomes_or_labels_used_for_selection": False, "molecular_features_used_for_selection": False,
        "expert_review_completed": False,
        "processed_dir": "data/processed/v2.0/10_development_split",
        "results_dir": "code/results/v2.0/10_development_split",
        "report_file": "docs/notes/v2.0/development_split/development_split_protocol_v2.0.md",
    }
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError("Development split configuration differs from the authorized scope")


def select_patients(rows, validation_count, seed, namespace):
    """Assign folds using only locked identities, strata and Pilot membership."""
    keys = [tuple(r["patient_key"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate patient assignment")
    if any(r["split"] not in {"development", "core_test", "extension_only"} for r in rows):
        raise ValueError("Unknown parent split")
    if any(r["pilot_member"] and r["split"] != "development" for r in rows):
        raise ValueError("Pilot must belong to the development set")
    development = [r for r in rows if r["split"] == "development"]
    if any(not r.get("stratum") or len(r["stratum"]) != 2 for r in development):
        raise ValueError("Missing locked development stratum")
    eligible = [r for r in development if not r["pilot_member"]]
    selected, quotas = quota_sample(eligible, validation_count, seed, namespace)
    result = []
    for r in sorted(rows, key=lambda r: tuple(r["patient_key"])):
        pk = tuple(r["patient_key"])
        fold = ("validation" if pk in selected else "training") if r["split"] == "development" else None
        result.append({**r, "development_fold": fold, "effective_split": fold or r["split"]})
    return result, quotas


def annotate_candidates(registry, assignments, version):
    """Retain every original fact; all roles inherit the patient's fold."""
    revised = []
    seen = set()
    for c in registry:
        if c["candidate_id"] in seen:
            raise ValueError("Duplicate candidate ID")
        seen.add(c["candidate_id"])
        a = assignments[tuple(c["patient_key"])]
        if c["patient_split_assignment"]["patient_split"] != a["split"]:
            raise ValueError("Candidate disagrees with the frozen parent assignment")
        revised.append({**c, "development_split_assignment": {
            "split_version": version, "parent_patient_split": a["split"],
            "development_fold": a["development_fold"], "effective_split": a["effective_split"],
            "pilot_patient": a["pilot_member"], "original_candidate_role": c["candidate_role"],
            "use_as_supervised_sample": "not_ready_labels_and_eligibility_unconfirmed",
        }})
    return revised


def load_context(base, config):
    inputs = {}

    def verified(name, expected=None):
        path = base / name
        actual = sha256(path)
        if expected is not None and actual != expected:
            raise ValueError("Input changed after its frozen upstream run: " + name)
        inputs[name] = actual
        return path

    manifest = json.loads(verified(PARENT_MANIFEST).read_text(encoding="utf-8"))
    if manifest["status"] != "completed":
        raise ValueError("Parent patient split is not completed")
    for name, checksum in {**manifest["input_sha256"], **manifest["output_sha256"]}.items():
        verified(name, checksum)
    parent_config = json.loads(verified(manifest["config_file"], manifest["config_sha256"]).read_text(encoding="utf-8"))
    lock = json.loads((base / PARENT / "patient_split_lock_v2.0.json").read_text(encoding="utf-8"))
    if lock["config_sha256"] != digest_object(parent_config):
        raise ValueError("Parent configuration disagrees with the frozen lock")
    if config["evidence_cutoff_date"] != parent_config["evidence_cutoff_date"]:
        raise ValueError("Knowledge cutoff must remain unchanged")
    rows = read_jsonl(base / PARENT / "patient_split_assignments_v2.0.jsonl")
    if sorted(rows, key=lambda r: tuple(r["patient_key"])) != lock["assignments"]:
        raise ValueError("Parent assignments disagree with the frozen lock")
    expected = {"development": config["development_patients"], "core_test": config["core_test_patients"]}
    counts = Counter(r["split"] for r in rows)
    if any(counts[k] != n for k, n in expected.items()):
        raise ValueError("Frozen development/Core population changed")
    pilot_rows = [r for r in rows if r["pilot_member"]]
    if len(pilot_rows) != config["pilot_patients"]:
        raise ValueError("Frozen Pilot population changed")
    pilot = json.loads(verified(PILOT_CONFIG).read_text(encoding="utf-8"))["selection"]
    if len(pilot) != len(pilot_rows) or {(r["patient_id"], r["candidate_id"]) for r in pilot} != {
        (r["patient_key"][1], r["index_candidate_id"]) for r in pilot_rows
    }:
        raise ValueError("Existing Pilot review package does not match the frozen Pilot indices")
    registry = read_jsonl(base / PARENT / "candidate_split_registry_v2.0.jsonl")
    indices = earliest_main_candidates(registry)
    by_key = {tuple(r["patient_key"]): r for r in rows}
    if set(indices) != {pk for pk, r in by_key.items() if r["split"] != "extension_only"}:
        raise ValueError("Main candidate patients differ from the frozen population")
    for pk, c in indices.items():
        if (c["candidate_id"], c["t0_day"], c["scope_at_t0"]) != (
            by_key[pk]["index_candidate_id"], by_key[pk]["index_t0_day"], by_key[pk]["stratum"][1]
        ):
            raise ValueError("Frozen patient index differs from earliest main candidate")
    for split, field in [("core_test", "core_index_candidate_ids"), ("pilot", "pilot_index_candidate_ids")]:
        actual = sorted(r["index_candidate_id"] for r in rows if (
            r["split"] == split if split != "pilot" else r["pilot_member"]
        ))
        if actual != lock[field]:
            raise ValueError("Frozen Core/Pilot index list changed")
    snapshots = read_jsonl(base / PARENT / "index_candidate_audit_snapshots_v2.0.jsonl")
    if len(snapshots) != len(indices) or {tuple(s["patient_key"]) for s in snapshots} != set(indices):
        raise ValueError("Audit snapshot population does not match frozen indices")
    for s in snapshots:
        a = by_key[tuple(s["patient_key"])]
        if (s["candidate_id"], s["split"], s["pilot_member"], s["institution"], s["scope_at_index"]) != (
            a["index_candidate_id"], a["split"], a["pilot_member"], a["institution"], a["stratum"][1]
        ):
            raise ValueError("Audit snapshot differs from frozen assignment")
    events = read_jsonl(base / EVENTS)
    return rows, registry, snapshots, events, inputs


def make_distribution(snapshots, assignments):
    groups = {"development": [], "training": [], "validation": [], "pilot": [], "training_non_pilot": []}
    for s in snapshots:
        a = assignments[tuple(s["patient_key"])]
        if a["split"] != "development":
            continue
        groups["development"].append(s)
        groups[a["development_fold"]].append(s)
        if a["pilot_member"]:
            groups["pilot"].append(s)
        elif a["development_fold"] == "training":
            groups["training_non_pilot"].append(s)
    features = defaultdict(set)
    counts = {}
    for group, rows in groups.items():
        tally = defaultdict(Counter)
        for s in rows:
            tally["institution"][s["institution"]] += 1
            tally["scope_at_index"][s["scope_at_index"]] += 1
            h = s["pancreatic_histologies_raw"]
            pathology = ("explicit_ductal_recorded" if "8500 Ductal adenocarcinoma" in h else
                         "NOS_recorded_without_explicit_ductal" if "8140 Adenocarcinoma NOS" in h else "other_or_unrecorded")
            tally["pathology_summary"][pathology] += 1
            tally["molecular_linkage"]["all_report_samples_linked" if s["ngs_sample_ids"] and not s["unlinked_sample_ids"]
                                       else "missing_or_partial_sample_link"] += 1
            tally["panel_id"].update(set(s["panel_ids"]))
            tally["recorded_mutation_gene"].update(set(s["recorded_mutation_genes"]))
        counts[group] = tally
        for feature, values in tally.items():
            features[feature].update(values)
    return [{"group": group, "feature": feature, "value": value,
             "patients": counts[group][feature][value], "denominator": len(groups[group]),
             "proportion": counts[group][feature][value] / len(groups[group]) if groups[group] else 0}
            for group in groups for feature in sorted(features) for value in sorted(features[feature])]


def prepare(base, config):
    validate_config(config)
    parent_rows, registry, snapshots, events, inputs = load_context(base, config)
    rows, quotas = select_patients(parent_rows, config["validation_patients"], config["split_seed"], config["sampling_namespace"])
    assignments = {tuple(r["patient_key"]): r for r in rows}
    isolation = check_identity_isolation(registry, {pk: {"split": r["effective_split"]} for pk, r in assignments.items()},
                                         {e["event_id"]: e for e in events})
    revised = annotate_candidates(registry, assignments, config["split_version"])
    counts = Counter(r["effective_split"] for r in rows)
    if counts["training"] != config["training_patients"] or counts["validation"] != config["validation_patients"]:
        raise ValueError("Internal split does not match the authorized counts")
    groups = {name: {tuple(r["patient_key"]) for r in rows if r["effective_split"] == name} for name in NAMES}
    if any(groups[a] & groups[b] for a in groups for b in groups if a != b):
        raise ValueError("Patient overlap between effective splits")
    if any(r["pilot_member"] and r["effective_split"] != "training" for r in rows):
        raise ValueError("Pilot escaped the training side")
    # Volatile upstream run timestamps belong in the run manifest, not the assignment lock.
    selection_names = [PARENT + name for name in ["patient_split_lock_v2.0.json", "patient_split_assignments_v2.0.jsonl",
                                                 "candidate_split_registry_v2.0.jsonl", "index_candidate_audit_snapshots_v2.0.jsonl"]]
    lock = {"split_version": config["split_version"], "config_sha256": digest_object(config),
            "selection_input_sha256": {n: inputs[n] for n in selection_names + [EVENTS, PILOT_CONFIG]},
            "assignments": [{k: r[k] for k in ["patient_key", "split", "pilot_member", "index_candidate_id",
                                               "development_fold", "effective_split"]} for r in rows]}
    distribution = make_distribution(snapshots, assignments)
    eligible = [r for r in rows if r["split"] == "development" and not r["pilot_member"]]
    strata = []
    for stratum in sorted({tuple(r["stratum"]) for r in rows if r["split"] == "development"}):
        rs = [r for r in rows if r["split"] == "development" and tuple(r["stratum"]) == stratum]
        strata.append({"institution": stratum[0], "index_scope": stratum[1], "development_patients": len(rs),
                       "pilot_training_patients": sum(r["pilot_member"] for r in rs),
                       "validation_eligible_patients": sum(not r["pilot_member"] for r in rs),
                       "training_patients": sum(r["effective_split"] == "training" for r in rs),
                       "validation_patients": quotas.get(stratum, 0)})
    main = Counter(c["development_split_assignment"]["effective_split"] for c in revised if c["candidate_role"] == "main_observed_regimen")
    def gene_set(group):
        return {r["value"] for r in distribution if r["group"] == group and r["feature"] == "recorded_mutation_gene" and r["patients"]}
    summary = {"project_version": "v2.0", "phase": PHASE, "split_version": config["split_version"],
               "execution_date": config["execution_date"], "evidence_cutoff_date": config["evidence_cutoff_date"],
               "patient_counts": dict(counts), "development_patients": len(groups["training"] | groups["validation"]),
               "pilot_training_patients": sum(r["pilot_member"] for r in rows),
               "training_non_pilot_patients": counts["training"] - config["pilot_patients"],
               "validation_eligible_patients": len(eligible), "validation_fraction_of_development": counts["validation"] / 435,
               "validation_fraction_of_non_pilot": counts["validation"] / len(eligible),
               "registry_patients": len(rows), "registry_records": len(revised),
               "registry_record_counts": dict(Counter(c["development_split_assignment"]["effective_split"] for c in revised)),
               "main_candidate_counts": dict(main), "strata": strata, "isolation": isolation,
               "train_validation_patient_overlap": 0, "pilot_validation_patient_overlap": 0,
               "development_core_patient_overlap": 0, "original_candidate_fields_preserved": True,
               "original_parent_files_preserved": True, "labels_or_outcomes_used_for_selection": False,
               "expert_labels_generated": False, "final_training_sample_count": None,
               "supervised_training_ready": False,
               "validation_prior_development_exposure": "all_435_development_patients_previously_used_for_catalog_construction",
               "development_recorded_genes_absent_from_validation": sorted(gene_set("development") - gene_set("validation")),
               "validation_recorded_genes_absent_from_training": sorted(gene_set("validation") - gene_set("training")),
               "identity_audit_scope": "existing_PANC_patient_source_event_NGS_sample_identifiers; not external_entity_deduplication_or_model_pretraining_audit"}
    return rows, revised, strata, distribution, summary, lock, inputs


def paths(base, config):
    source = json.loads((base / "code/config/v2.0/source.json").read_text(encoding="utf-8"))
    _, processed, out = resolve_paths(base, {**source, **config})
    report = (base / config["report_file"]).resolve()
    if not report.is_relative_to((base / "docs/notes/v2.0/development_split").resolve()):
        raise ValueError("Report must stay within its development split documentation directory")
    return processed, out, report


def render_report(base, config, summary, distribution):
    s = summary
    pc, mc, rc = s["patient_counts"], s["main_candidate_counts"], s["registry_record_counts"]
    report = base / config["report_file"]
    def link(label, target):
        return f"[{label}]({Path(os.path.relpath(base / target, report.parent)).as_posix()})"
    institution = []
    for institution_name in sorted({r["value"] for r in distribution if r["feature"] == "institution"}):
        values = {r["group"]: r["patients"] for r in distribution if r["feature"] == "institution" and r["value"] == institution_name}
        institution.append(f"| {institution_name} | {values['development']} | {values['training']} | {values['validation']} | {values['pilot']} |")
    stratum_table = "\n".join(f"| {r['institution']} | {r['index_scope']} | {r['development_patients']} | {r['pilot_training_patients']} | {r['training_patients']} | {r['validation_patients']} |" for r in s["strata"])
    return f"""# PDAC 开发集内部患者级训练／验证划分 v2.0

版本：{config['split_version']}

更新日期：{config['execution_date']}

状态：开发集划分及身份隔离检查已完成，名单已锁定并可复现；专家标签审核、裁定及模型评估待完成。

## 范围与当前结果

仅在已锁定的435名开发患者内实施80%／20%划分。原Core 80人、Pilot 25人及其索引候选不重抽、不覆盖；知识截止日仍为{config['evidence_cutoff_date']}。这是患者用途分配，不代表临床纳入资格或监督训练样本已确定。

| 用途 | 患者数 | 主候选点数 | 各类登记记录数 |
| --- | ---: | ---: | ---: |
| 训练侧（含25名Pilot） | {pc['training']} | {mc['training']} | {rc['training']} |
| 验证侧 | {pc['validation']} | {mc['validation']} | {rc['validation']} |
| Core测试侧（沿用原锁） | {pc['core_test']} | {mc['core_test']} | {rc['core_test']} |
| extension_only（沿用原归属） | {pc['extension_only']} | 0 | {rc['extension_only']} |

训练侧包含{s['training_non_pilot_patients']}名非Pilot患者和25名Pilot；Pilot是训练侧子集，不能重复相加。共{s['registry_patients']:,}名登记患者、{s['registry_records']:,}条候选登记全部保留。主候选点及背景登记数量都不等于最终训练样本数。

## 抽样与锁定

患者键为(cohort, record_id)，同一患者的全部候选、进展扩展、治疗附录、背景病理、NGS及后续记录继承同一归属。分层沿用原锁内的机构和最早主候选时点疾病情境，不将既有情境分类改称当前临床分期。

先将已有25名Pilot固定在训练侧，再从410名非Pilot开发患者中抽取87名验证患者。各层按非Pilot患者比例，以整数部分和最大余数分配87个名额；余数并列按层名称排序。层内用固定种子{config['split_seed']}、用途名`{config['sampling_namespace']}`及患者键计算SHA256，排序选取，算法沿用第06阶段。验证占整个开发集20%，占可抽样的非Pilot患者{s['validation_fraction_of_non_pilot']:.2%}；因Pilot预留，整体各层不保证恰为20%。不使用专家标签、预拟标签、实际用药、疗效、生存或分子特征选人，不按验证成绩换种子。

{link('配置', CONFIG)}和{link('内部划分锁', config['processed_dir'] + '/development_split_lock_v2.0.json')}记录政策与名单。重复运行只允许复现同一分配；输入或政策改变时，在任何结果写入前报错，不提供自动删除锁或重抽选项。旧Core/Pilot锁及第06阶段所有文件保持原字节内容。此锁是流程校验，不是操作系统权限或已完成盲法的证明。

## 分布及泄漏核查

| 机构 | 开发合计 | 训练 | 验证 | 其中训练Pilot |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(institution)}

| 机构 | 索引情境 | 开发 | 训练Pilot | 训练合计 | 验证 |
| --- | --- | ---: | ---: | ---: | ---: |
{stratum_table}

{link('完整分布审计', config['results_dir'] + '/development_distribution_audit_v2.0.csv')}包含开发合计、训练、验证、Pilot及非Pilot训练的机构、疾病情境、病理摘要、在先NGS样本关联、面板和已记录小变异基因，零计数也保留。分子及病理只作事后描述，不用于重抽。只使用原索引点严格在先NGS关联样本；基因记录不等于致病、胚系或可操作性，缺少记录不等于阴性，病理报告可用时间未确认的限制继续保留。

开发集有{len(s['development_recorded_genes_absent_from_validation'])}种已记录小变异基因未在验证索引样本出现；验证中有{len(s['validation_recorded_genes_absent_from_training'])}种未在训练索引样本出现。名称见{link('汇总', config['results_dir'] + '/development_split_summary_v2.0.json')}，不能据此宣称精准治疗亚组均衡或充分覆盖。

训练／验证、Pilot／验证、开发／Core患者交集均为0。遍历全候选登记及完整时间轴，按训练、验证、Core、extension_only四侧检查患者ID、源记录ID、事件ID、NGS样本ID；跨侧身份冲突为0，检查数见汇总。所有原候选字段及标签状态保持不变。范围限于既有PANC数据，不表示外部队列实体去重或通用模型预训练污染检查已完成。

## 使用规则与已有开发暴露

训练侧用于规则、提示词、特征及阈值开发；需要从患者数据学习的缺失值填补、标准化、特征选择及其他参数只能在训练侧拟合，然后固定应用到验证侧。所有衍生病例、方案对、问答及示例必须携带patient_key和candidate_id，按本阶段归属路由，不能只读取原第06阶段的development字段。

验证侧用于后续内部评估与方法选择；一旦用其结果调参，应记录使用历史，不能再宣称完全未接触。Pilot25人全部用于训练侧流程调试、病理展示、标签边界和审核规范；已有175条预拟标签不是专家金标准，独立专家及裁定字段不能由预拟标签补填。

此前冻结治疗目录由全部435名开发患者的药物记录投影整理，现验证患者已经参与该目录构建。因此本轮验证是在现有开发集合上新增的内部划分，不能宣称端到端从未参与开发的独立验证。沿用冻结公共证据目录，不按本轮验证分布扩充目录或重新选人；若以后要求从训练侧独立建立目录，应另设版本与实验。Core继续保持最终测试用途，不参与训练、提示词调整、规则开发或阈值选择。

正式专家标签及最终临床纳入资格尚未完成；本阶段不训练模型、不发布性能、不生成正式标签或最终训练样本数。后续获得标签后仍继承当前患者归属，报告标签缺失和排除原因，不按结果难易调换患者。

## 输出与复现

- {link('患者归属名单', config['processed_dir'] + '/development_patient_assignments_v2.0.csv')}及同名JSONL：全登记池身份与新的用途字段。
- {link('训练主候选', config['processed_dir'] + '/training_main_candidates_v2.0.csv')}、{link('验证主候选', config['processed_dir'] + '/validation_main_candidates_v2.0.csv')}：候选索引及用途，不是可直接输入模型的特征包。
- {link('全部候选归属登记', config['processed_dir'] + '/development_candidate_registry_v2.0.jsonl')}：保留原记录并附加development_split_assignment；包含后续及参考资料，禁止作为模型输入文件直接读取。
- {link('分层名额', config['results_dir'] + '/development_stratum_allocation_v2.0.csv')}、{link('运行清单', config['results_dir'] + '/run_manifest.json')}：输入、配置、代码、检查与输出校验和。

在项目根目录运行，数据处理只依赖标准库：

```powershell
python -B code/scripts/build_development_split_v2_0.py
python -B code/scripts/build_development_split_v2_0.py --check
python -B code/scripts/run_v2_0.py check
```

新阶段是第06阶段及既有Pilot之后的独立入口，原`run_v2_0.py all`不自动执行本阶段。`--check`为只读验证，重算名单与身份隔离、核对原文件、全部新产物及本报告的校验和与本地链接。Python版本、运行平台和运行时间记录在清单中。
"""


def run(base):
    base = Path(base).resolve()
    config_path = base / CONFIG
    config = json.loads(config_path.read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc).isoformat()
    rows, revised, strata, distribution, summary, lock, inputs = prepare(base, config)
    processed, out, report = paths(base, config)
    verify_lock(processed / "development_split_lock_v2.0.json", lock)
    # Recheck all frozen inputs before any output writes.
    if any(sha256(base / name) != h for name, h in inputs.items()):
        raise ValueError("Frozen input changed during preparation")
    processed.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    produced = []
    def save_json(directory, name, value):
        p = directory / name
        write_json(p, value)
        produced.append(p)
    def save_jsonl(name, value):
        p = processed / name
        write_jsonl(p, value)
        produced.append(p)
    def save_csv(directory, name, value, header=None):
        p = directory / name
        write_csv(p, header or list(value[0]), value)
        produced.append(p)
    save_json(processed, "development_split_lock_v2.0.json", lock)
    save_jsonl("development_patient_assignments_v2.0.jsonl", rows)
    flat = [{"patient_id": r["patient_key"][1], "cohort": r["patient_key"][0],
             "institution": r["institution"], "parent_split": r["split"], "development_fold": r["development_fold"],
             "effective_split": r["effective_split"], "pilot_member": r["pilot_member"],
             "index_candidate_id": r["index_candidate_id"], "index_t0_day": r["index_t0_day"],
             "index_scope": r["stratum"][1] if r["stratum"] else "",
             "main_candidates": r["main_candidates"], "all_registry_records": r["all_registry_records"],
             "expert_review_completed": r["expert_review_completed"], "training_labels_available": r["training_labels_available"]}
            for r in rows]
    save_csv(processed, "development_patient_assignments_v2.0.csv", flat)
    save_jsonl("development_candidate_registry_v2.0.jsonl", revised)
    candidates = [{"candidate_id": c["candidate_id"], "patient_id": c["patient_key"][1], "cohort": c["patient_key"][0],
                   "candidate_role": c["candidate_role"], "t0_day": c["t0_day"], "scope_at_t0": c["scope_at_t0"],
                   **c["development_split_assignment"], "expert_label": c["expert_label"]} for c in revised]
    save_csv(processed, "development_candidate_assignments_v2.0.csv", candidates)
    for fold in ["training", "validation"]:
        rs = [r for r in candidates if r["effective_split"] == fold and r["candidate_role"] == "main_observed_regimen"]
        save_csv(processed, fold + "_main_candidates_v2.0.csv", rs, list(candidates[0]))
    save_csv(out, "development_stratum_allocation_v2.0.csv", strata)
    save_csv(out, "development_distribution_audit_v2.0.csv", distribution)
    save_json(out, "development_split_summary_v2.0.json", summary)
    report.write_text(render_report(base, config, summary, distribution), encoding="utf-8")
    produced.append(report)
    if any(sha256(base / name) != h for name, h in inputs.items()):
        raise ValueError("Frozen input changed during generation")
    code_paths = [base / "code/src/pdac_benchmark/v2_0" / (name + ".py") for name in [
        "development_split", "patient_split", "source", "audit", "candidate_review", "layout"]]
    code_paths += [base / "code/scripts/build_development_split_v2_0.py", base / "code/tests/v2_0/test_development_split.py"]
    manifest = {"project_version": "v2.0", "phase": PHASE, "status": "completed", "started_utc": started,
                "finished_utc": datetime.now(timezone.utc).isoformat(),
                "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                            "third_party_runtime_dependencies": []},
                "config_file": CONFIG, "config_sha256": sha256(config_path), "input_sha256": inputs,
                "code_sha256": {p.relative_to(base).as_posix(): sha256(p) for p in code_paths},
                "output_sha256": {p.relative_to(base).as_posix(): sha256(p) for p in produced}, "summary": summary}
    write_json(out / "run_manifest.json", manifest)
    print(json.dumps({"status": "completed", "patient_counts": summary["patient_counts"],
                      "main_candidate_counts": summary["main_candidate_counts"], "pilot_training_patients": 25,
                      "report_file": config["report_file"]}, ensure_ascii=False, indent=2))
    return 0


def check(base):
    base = Path(base).resolve()
    config = json.loads((base / CONFIG).read_text(encoding="utf-8"))
    validate_config(config)
    processed, out, report = paths(base, config)
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "completed":
        raise ValueError("Development split run is not completed")
    recorded = {manifest["config_file"]: manifest["config_sha256"], **manifest["input_sha256"],
                **manifest["code_sha256"], **manifest["output_sha256"]}
    for name, expected in recorded.items():
        if sha256(base / name) != expected:
            raise ValueError("Development split provenance changed: " + name)
    rows, revised, strata, distribution, summary, lock, inputs = prepare(base, config)
    verify_lock(processed / "development_split_lock_v2.0.json", lock)
    if summary != manifest["summary"] or summary != json.loads((out / "development_split_summary_v2.0.json").read_text(encoding="utf-8")):
        raise ValueError("Development split summary changed")
    if rows != read_jsonl(processed / "development_patient_assignments_v2.0.jsonl") or revised != read_jsonl(processed / "development_candidate_registry_v2.0.jsonl"):
        raise ValueError("Derived rows do not exactly reproduce the frozen allocation")
    if report.read_text(encoding="utf-8") != render_report(base, config, summary, distribution):
        raise ValueError("Development split report does not reproduce current results")
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", report.read_text(encoding="utf-8"))
    for target in links:
        if not (report.parent / target).resolve().exists():
            raise ValueError("Broken development split report link: " + target)
    return {"status": "passed", "files_checked": len(recorded), "report_links_checked": len(links),
            "patient_counts": summary["patient_counts"], "isolation": summary["isolation"],
            "supervised_training_ready": False}
