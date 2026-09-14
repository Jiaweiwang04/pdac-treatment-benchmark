"""Seal a development-derived catalog before held-out coverage inspection."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .source import sha256


def definition_paths(config):
    return ['code/config/v2.0/treatment_catalog.json', 'code/config/v2.0/treatment_labels.json',
            config['patient_split_lock'], *[config[k] for k in
            ['source_ledger', 'family_definitions', 'variant_definitions', 'alias_definitions', 'disposition_definitions']]]


def seal(base, config, summary, background):
    from .treatment_catalog import digest, load
    if summary['unresolved_screening_patterns']:
        raise ValueError('Cannot freeze unresolved development patterns')
    payload = dict(release_id=config['release_id'], project_version='v2.0',
        evidence_cutoff_date=config['evidence_cutoff_date'],
        definition_sha256={n:sha256(base/n) for n in definition_paths(config)},
        catalog_content_sha256=summary['catalog_content_sha256'],
        development_projection_sha256=summary['development_projection_sha256'],
        development_history_sha256=digest(background),
        source_population='development', core_treatments_used_for_construction=False)
    lock_path=base/config['freeze_lock']
    if lock_path.exists():
        lock=load(lock_path)
        if lock['payload']!=payload or lock['release_sha256']!=digest(payload):
            raise ValueError('Frozen catalog differs; same release cannot be overwritten')
    else:
        lock=dict(payload=payload,release_sha256=digest(payload),
                  frozen_at_utc=datetime.now(timezone.utc).isoformat())
        lock_path.parent.mkdir(parents=True,exist_ok=True)
        with lock_path.open('x',encoding='utf-8') as f:
            json.dump(lock,f,ensure_ascii=False,indent=2)
            f.write('\n')
    return lock


def verify(base, config):
    """Reject changed definitions or catalog products before opening Core records."""
    from .treatment_catalog import digest, load
    lock=load(base/config['freeze_lock']); payload=lock['payload']
    if lock['release_sha256']!=digest(payload) or payload['release_id']!=config['release_id']:
        raise ValueError('Invalid catalog release identity')
    if set(payload['definition_sha256'])!=set(definition_paths(config)):
        raise ValueError('Frozen definition inventory differs')
    for n,h in payload['definition_sha256'].items():
        if sha256(base/n)!=h:
            raise ValueError('Frozen definition changed: '+n)
    processed=base/config['processed_dir']
    def rows(name):
        return [json.loads(l) for l in (processed/(name+'_v2.0.jsonl')).read_text(encoding='utf-8').splitlines()]
    content=dict(families=rows('treatment_families'),variants=rows('treatment_variants'),sources=rows('treatment_evidence_sources'))
    if digest(content)!=payload['catalog_content_sha256']:
        raise ValueError('Frozen catalog products changed')
    if digest(rows('development_regimen_mapping'))!=payload['development_projection_sha256']:
        raise ValueError('Frozen development projection changed')
    if digest(rows('development_historical_regimen_context'))!=payload['development_history_sha256']:
        raise ValueError('Frozen development history changed')
    return lock
