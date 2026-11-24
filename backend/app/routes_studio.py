"""Prompt management, datasets and experiments.

Prompts are versioned (immutable versions, movable labels such as "production"); apps fetch the
version they should use and send X-AOBS-Prompt: name@version through the gateway so every call
records which prompt version produced it. Datasets hold test cases (written by hand or copied
from real calls); an experiment runs a dataset against a model and prompt version and scores it.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .auth import Ctx, require_access, role
from .db import get_db
from .llm.experiments import MAX_ITEMS, run_experiment
from .orm import PROVIDERS, ProviderCredential
from .orm_llm import Contract, Dataset, DatasetItem, Experiment, ExperimentResult, LLMCall, Prompt
from .services.analytics import _iso

router = APIRouter(prefix="/api")
member = role("member")
NAME = r"^[a-zA-Z0-9_.\-]{1,120}$"
LABEL = r"^[a-z0-9_\-]{1,32}$"
MAX_DATASET_ITEMS = 1000


# =========================================================================== prompts
class PromptIn(BaseModel):
    name: str = Field(pattern=NAME)
    system_prompt: str = Field("", max_length=100_000)
    template: str = Field("", max_length=100_000)
    model: str = Field("", max_length=120)
    config: Dict[str, Any] = Field(default_factory=dict)
    labels: List[str] = Field(default_factory=list)
    commit_message: str = Field("", max_length=500)


class LabelsIn(BaseModel):
    labels: List[str]


def _clean_labels(labels: List[str]) -> List[str]:
    out = sorted({x.strip() for x in labels if x.strip()})
    bad = [x for x in out if x == "latest" or not re.match(LABEL, x)]
    if bad:
        raise HTTPException(422, f"Invalid label(s): {', '.join(bad)}. Use lowercase letters, digits, - or _; "
                                 "'latest' is reserved (it always means the newest version).")
    return out


def _prompt_out(p: Prompt, latest: int) -> Dict[str, Any]:
    return {"name": p.name, "version": p.version, "system_prompt": p.system_prompt, "template": p.template,
            "model": p.model, "config": p.config, "labels": p.labels + (["latest"] if p.version == latest else []),
            "commit_message": p.commit_message, "created_by": p.created_by, "created_at": _iso(p.created_at)}


def _versions(db: Session, ws: int, name: str) -> List[Prompt]:
    return db.query(Prompt).filter(Prompt.workspace_id == ws, Prompt.name == name).order_by(Prompt.version.desc()).all()


def _move_labels(versions: List[Prompt], target: Prompt, labels: List[str]) -> None:
    """A label points at exactly one version: take it off the others."""
    for v in versions:
        if v is not target and set(v.labels) & set(labels):
            v.labels = [x for x in v.labels if x not in labels]
    target.labels = labels


@router.get("/llm/prompts", tags=["prompts"])
def list_prompts(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    rows = db.query(Prompt).filter(Prompt.workspace_id == ctx.workspace_id).order_by(Prompt.name, Prompt.version.desc()).all()
    out: Dict[str, Dict] = {}
    for p in rows:
        d = out.setdefault(p.name, {"name": p.name, "latest_version": p.version, "versions": 0, "labels": {},
                                    "updated_at": _iso(p.created_at), "model": p.model})
        d["versions"] += 1
        for label in p.labels:
            d["labels"][label] = p.version
    return list(out.values())


@router.get("/llm/prompts/{name}", tags=["prompts"])
def get_prompt(name: str, ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    versions = _versions(db, ctx.workspace_id, name)
    if not versions:
        raise HTTPException(404, "Prompt not found")
    crit = func.sum(case((LLMCall.severity == "critical", 1), else_=0))
    stats = {v: {"calls": n, "critical": int(c or 0), "cost_usd": round(cost or 0, 6), "avg_latency_ms": round(lat or 0, 1)}
             for v, n, c, cost, lat in db.query(LLMCall.prompt_version, func.count(LLMCall.id), crit,
                                                func.sum(LLMCall.cost_usd), func.avg(LLMCall.latency_ms))
             .filter(LLMCall.workspace_id == ctx.workspace_id, LLMCall.prompt_name == name)
             .group_by(LLMCall.prompt_version)}
    latest = versions[0].version
    return {"name": name, "versions": [{**_prompt_out(p, latest), "usage": stats.get(p.version)} for p in versions]}


@router.get("/llm/prompts/{name}/resolve", tags=["prompts"])
def resolve_prompt(name: str, label: Optional[str] = None, version: Optional[int] = None,
                   ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    """The version an app should use: by version, by label, else "production", else the newest."""
    versions = _versions(db, ctx.workspace_id, name)
    if not versions:
        raise HTTPException(404, "Prompt not found")
    if version is not None:
        pick = next((p for p in versions if p.version == version), None)
    elif label and label != "latest":
        pick = next((p for p in versions if label in p.labels), None)
    elif label == "latest":
        pick = versions[0]
    else:
        pick = next((p for p in versions if "production" in p.labels), versions[0])
    if pick is None:
        raise HTTPException(404, f"No version of '{name}' matches {'version ' + str(version) if version else 'label ' + label}")
    return _prompt_out(pick, versions[0].version)


@router.post("/llm/prompts", tags=["prompts"])
def create_prompt_version(body: PromptIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    labels = _clean_labels(body.labels)
    versions = _versions(db, ctx.workspace_id, body.name)
    p = Prompt(workspace_id=ctx.workspace_id, name=body.name, version=(versions[0].version + 1) if versions else 1,
               system_prompt=body.system_prompt, template=body.template, model=body.model, config=body.config,
               labels=[], commit_message=body.commit_message, created_by=ctx.user.email if ctx.user else "api key")
    db.add(p)
    _move_labels(versions, p, labels)
    db.commit()
    return _prompt_out(p, p.version)


@router.put("/llm/prompts/{name}/versions/{version}/labels", tags=["prompts"])
def set_labels(name: str, version: int, body: LabelsIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    labels = _clean_labels(body.labels)
    versions = _versions(db, ctx.workspace_id, name)
    target = next((p for p in versions if p.version == version), None)
    if target is None:
        raise HTTPException(404, "Prompt version not found")
    _move_labels(versions, target, labels)
    db.commit()
    return _prompt_out(target, versions[0].version)


@router.delete("/llm/prompts/{name}", tags=["prompts"])
def delete_prompt(name: str, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    n = db.query(Prompt).filter(Prompt.workspace_id == ctx.workspace_id, Prompt.name == name).delete(synchronize_session=False)
    if not n:
        raise HTTPException(404, "Prompt not found")
    db.commit()
    return {"ok": True, "deleted_versions": n}


# =========================================================================== datasets
class DatasetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=5000)


class ItemIn(BaseModel):
    system_prompt: str = Field("", max_length=100_000)
    input: str = Field(min_length=1, max_length=100_000)
    expected: str = Field("", max_length=100_000)


class FromCallIn(BaseModel):
    call_id: str
    expected: Optional[str] = Field(None, max_length=100_000)  # default: the call's answer


class ExperimentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider: str
    model: str = Field(min_length=1, max_length=120)
    credential_id: Optional[int] = None
    prompt_name: str = ""
    prompt_version: Optional[int] = None
    contract_id: Optional[int] = None


def _get_dataset(db: Session, ctx: Ctx, did: int) -> Dataset:
    d = db.get(Dataset, did)
    if d is None or d.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Dataset not found")
    return d


def _item_count(db: Session, did: int) -> int:
    return db.query(func.count(DatasetItem.id)).filter(DatasetItem.dataset_id == did).scalar() or 0


def _add_item(db: Session, d: Dataset, **fields) -> DatasetItem:
    if _item_count(db, d.id) >= MAX_DATASET_ITEMS:
        raise HTTPException(422, f"A dataset holds at most {MAX_DATASET_ITEMS} items")
    item = DatasetItem(dataset_id=d.id, **fields)
    db.add(item)
    db.commit()
    return item


def _item_out(i: DatasetItem) -> Dict[str, Any]:
    return {"id": i.id, "system_prompt": i.system_prompt, "input": i.input, "expected": i.expected,
            "source_call_id": i.source_call_id, "created_at": _iso(i.created_at)}


def _experiment_out(e: Experiment) -> Dict[str, Any]:
    return {"id": e.id, "dataset_id": e.dataset_id, "name": e.name, "provider": e.provider, "model": e.model,
            "prompt_name": e.prompt_name, "prompt_version": e.prompt_version, "contract_id": e.contract_id,
            "status": e.status, "detail": e.detail, "summary": e.summary,
            "created_at": _iso(e.created_at), "finished_at": _iso(e.finished_at)}


@router.get("/llm/datasets", tags=["datasets"])
def list_datasets(ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    rows = db.query(Dataset).filter(Dataset.workspace_id == ctx.workspace_id).order_by(Dataset.name).all()
    counts = dict(db.query(DatasetItem.dataset_id, func.count(DatasetItem.id))
                  .filter(DatasetItem.dataset_id.in_([d.id for d in rows])).group_by(DatasetItem.dataset_id)) if rows else {}
    last = {}
    for e in (db.query(Experiment).filter(Experiment.workspace_id == ctx.workspace_id).order_by(Experiment.id).all()):
        last[e.dataset_id] = e
    return [{"id": d.id, "name": d.name, "description": d.description, "items": counts.get(d.id, 0),
             "created_at": _iso(d.created_at), "last_experiment": _experiment_out(last[d.id]) if d.id in last else None}
            for d in rows]


@router.post("/llm/datasets", tags=["datasets"])
def create_dataset(body: DatasetIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    if db.query(Dataset).filter(Dataset.workspace_id == ctx.workspace_id, Dataset.name == body.name).first():
        raise HTTPException(409, "A dataset with this name already exists")
    d = Dataset(workspace_id=ctx.workspace_id, name=body.name, description=body.description)
    db.add(d)
    db.commit()
    return {"id": d.id, "name": d.name, "description": d.description, "items": 0}


@router.get("/llm/datasets/{did}", tags=["datasets"])
def get_dataset(did: int, ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    d = _get_dataset(db, ctx, did)
    items = db.query(DatasetItem).filter(DatasetItem.dataset_id == d.id).order_by(DatasetItem.id).limit(MAX_DATASET_ITEMS).all()
    exps = db.query(Experiment).filter(Experiment.dataset_id == d.id).order_by(Experiment.id.desc()).limit(50).all()
    return {"id": d.id, "name": d.name, "description": d.description, "items": [_item_out(i) for i in items],
            "experiments": [_experiment_out(e) for e in exps]}


@router.delete("/llm/datasets/{did}", tags=["datasets"])
def delete_dataset(did: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    db.delete(_get_dataset(db, ctx, did))  # items, experiments and results cascade
    db.commit()
    return {"ok": True}


@router.post("/llm/datasets/{did}/items", tags=["datasets"])
def add_item(did: int, body: ItemIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    return _item_out(_add_item(db, _get_dataset(db, ctx, did), **body.model_dump()))


@router.post("/llm/datasets/{did}/items/from-call", tags=["datasets"])
def add_item_from_call(did: int, body: FromCallIn, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    """Turn a real call into a test case: its prompt becomes the input, its answer the expected output."""
    d = _get_dataset(db, ctx, did)
    c = db.get(LLMCall, body.call_id)
    if c is None or c.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Call not found")
    if not c.content_stored or not c.last_user:
        raise HTTPException(422, "This call's content was not stored, so it can't become a test case")
    return _item_out(_add_item(db, d, system_prompt=c.system_prompt, input=c.last_user, source_call_id=c.id,
                               expected=c.response_text if body.expected is None else body.expected))


@router.delete("/llm/datasets/{did}/items/{item_id}", tags=["datasets"])
def delete_item(did: int, item_id: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    d = _get_dataset(db, ctx, did)
    n = db.query(DatasetItem).filter(DatasetItem.id == item_id, DatasetItem.dataset_id == d.id).delete(synchronize_session=False)
    if not n:
        raise HTTPException(404, "Item not found")
    db.commit()
    return {"ok": True}


# =========================================================================== experiments
@router.post("/llm/datasets/{did}/experiments", tags=["datasets"])
def start_experiment(did: int, body: ExperimentIn, background: BackgroundTasks,
                     ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    d = _get_dataset(db, ctx, did)
    if body.provider not in PROVIDERS:
        raise HTTPException(422, f"provider must be one of {', '.join(PROVIDERS)}")
    if not _item_count(db, d.id):
        raise HTTPException(422, "Add at least one item to the dataset first")
    if body.credential_id is not None:
        cred = db.get(ProviderCredential, body.credential_id)
        if cred is None or cred.workspace_id != ctx.workspace_id or cred.provider != body.provider:
            raise HTTPException(422, "Credential must belong to this workspace and match the provider")
    if body.contract_id is not None:
        c = db.get(Contract, body.contract_id)
        if c is None or c.workspace_id != ctx.workspace_id:
            raise HTTPException(404, "Contract not found")
    version = body.prompt_version
    if body.prompt_name:
        versions = _versions(db, ctx.workspace_id, body.prompt_name)
        if not versions:
            raise HTTPException(404, "Prompt not found")
        version = version or versions[0].version
        if not any(p.version == version for p in versions):
            raise HTTPException(404, "Prompt version not found")
    e = Experiment(workspace_id=ctx.workspace_id, dataset_id=d.id, name=body.name, provider=body.provider,
                   model=body.model, credential_id=body.credential_id, prompt_name=body.prompt_name,
                   prompt_version=version if body.prompt_name else None, contract_id=body.contract_id, summary={})
    db.add(e)
    db.commit()
    background.add_task(run_experiment, e.id)
    return {**_experiment_out(e), "max_items": MAX_ITEMS}


@router.get("/llm/experiments/{eid}", tags=["datasets"])
def get_experiment(eid: int, ctx: Ctx = Depends(require_access), db: Session = Depends(get_db)):
    e = db.get(Experiment, eid)
    if e is None or e.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Experiment not found")
    items = {i.id: i for i in db.query(DatasetItem).filter(DatasetItem.dataset_id == e.dataset_id)}
    results = db.query(ExperimentResult).filter(ExperimentResult.experiment_id == e.id).order_by(ExperimentResult.id).all()
    return {**_experiment_out(e), "results": [
        {"id": r.id, "item_id": r.item_id, "call_id": r.call_id, "status": r.status, "output": r.output,
         "passed": r.passed, "violations": r.violations, "similarity": r.similarity, "latency_ms": r.latency_ms,
         "cost_usd": r.cost_usd, "detail": r.detail,
         "input": items[r.item_id].input if r.item_id in items else "",
         "expected": items[r.item_id].expected if r.item_id in items else ""} for r in results]}


@router.delete("/llm/experiments/{eid}", tags=["datasets"])
def delete_experiment(eid: int, ctx: Ctx = Depends(member), db: Session = Depends(get_db)):
    e = db.get(Experiment, eid)
    if e is None or e.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Experiment not found")
    db.delete(e)
    db.commit()
    return {"ok": True}

