"""术语更正后的命中归并接口：批量更正 / 撤回、按版本检索命中、按已打开试听位置取材。

这些接口跨越术语抽取、转写原段与媒体索引三个模块，业务判断全部落在
``app.pipeline.index_hit_merger.IndexHitMerger``，路由层只做参数校验和序列化。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.pipeline.index_hit_merger import IndexHitMerger

router = APIRouter(prefix="/api/term-index", tags=["术语更正与命中归并"])

merger = IndexHitMerger()


class BatchCorrectionPayload(BaseModel):
    termIds: list[int] = Field(default_factory=list)
    correctedText: str = ""
    remark: str = ""


class BatchWithdrawPayload(BaseModel):
    remark: str = ""


@router.get("/batches")
def list_batches() -> dict[str, Any]:
    """更正批次列表：同版多条更正一次提交，也支持整批撤回。"""
    batches = merger.list_batches()
    return {"items": batches, "total": len(batches)}


@router.post("/batches")
def submit_batch(payload: BatchCorrectionPayload) -> dict[str, Any]:
    """把同一转写版本的多条词条一次更正，并立即更新媒体索引命中。"""
    batch, message = merger.correct_batch(
        payload.termIds, payload.correctedText, remark=payload.remark)
    return {"ok": batch is not None, "message": message, "entry": batch}


@router.post("/batches/{batch_id}/withdraw")
def withdraw_batch(batch_id: str, payload: BatchWithdrawPayload) -> dict[str, Any]:
    """撤回整批更正：原段与术语回退，媒体索引按版本与原段恢复命中。"""
    batch, message = merger.withdraw_batch(batch_id, remark=payload.remark)
    return {"ok": batch is not None, "message": message, "entry": batch}


@router.get("/hits")
def search_hits(
    word: str = Query(..., min_length=1),
    version: str = Query(..., min_length=1),
) -> dict[str, Any]:
    """按词与转写版本检索命中；切到旧版本时只返回旧版本自己的命中。"""
    items = merger.search(word, version)
    return {"items": items, "total": len(items), "word": word, "version": version}


@router.get("/citation")
def resolve_citation(
    word: str = Query(..., min_length=1),
    version: str = Query(..., min_length=1),
    media: str = Query(..., min_length=1),
    segment: str = Query(..., min_length=1),
    position: str = Query(default=""),
) -> dict[str, Any]:
    """检索人员就已打开的试听位置取材：返回实际采用的录音，或当前不能取材的理由。"""
    decision = merger.resolve_citation(word, version, media, segment, position)
    if decision.get("decision") == "unavailable" and not decision.get("reason"):
        raise HTTPException(status_code=400, detail="取材位置信息不完整")
    return decision
