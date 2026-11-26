"""术语更正后的命中归并：场景回归测试。

覆盖编辑在术语抽取页多选同版词条、批量更正或撤回后，
媒体索引按转写版本与原段更新命中，以及检索人员从已打开试听位置取材的结论。
"""
from __future__ import annotations

import pytest

from app.pipeline.index_hit_merger import IndexHitMerger
from app.routers import term_index as term_index_router
from app.store import Store


@pytest.fixture()
def store_state(monkeypatch):
    """每个用例用独立仓库副本，避免更正污染其它测试的种子数据。"""
    fresh = Store()
    import app.store as store_module
    monkeypatch.setattr(store_module, "store", fresh)
    # 领域逻辑与路由都通过 app.store.store 取数，这里一并换成副本。
    monkeypatch.setattr("app.pipeline.index_hit_merger.store", fresh, raising=False)
    monkeypatch.setattr("app.services.term_extract.store", fresh, raising=False)
    monkeypatch.setattr("app.services.media_index.store", fresh, raising=False)
    return fresh


def _merger() -> IndexHitMerger:
    return IndexHitMerger()


def _positions(items: list[dict], media_id: str) -> list[str]:
    for item in items:
        if item["关联媒体源"] == media_id:
            return str(item["命中毫秒位置"]).split(", ")
    return []


def test_two_recordings_two_hits_and_a_repeat_counts_once(store_state):
    hits = _merger().merge_hits("v2")
    by_media = {hit["关联媒体源"]: hit for hit in hits if hit["术语文本"] == "蓝鲸"}
    assert set(by_media) == {"MEDI-0004", "MEDI-0005"}
    # A 段两条词条报的是同一原段同一词：命中仍只算一处，出现次数按原文算 2 次。
    assert by_media["MEDI-0004"]["出现次数"] == 2
    assert by_media["MEDI-0004"]["报数"] == 2
    index = _merger().search("蓝鲸", "v2")
    assert _positions(index, "MEDI-0004") == ["12000"]
    assert _positions(index, "MEDI-0005") == ["9000"]


def test_batch_correction_updates_hits_by_version_and_segment(store_state):
    batch, message = _merger().correct_batch([4, 5], "座头鲸")
    assert batch is not None, message
    assert batch["转写版本"] == "v2"
    assert batch["更正词数量"] == "2"

    assert _merger().search("座头鲸", "v2")[0]["命中毫秒位置"] == "12000"
    assert _positions(_merger().search("蓝鲸", "v2"), "MEDI-0004") == []
    # B 段没被这批更正覆盖（A、B 同版但原段不同），仍保留蓝鲸。
    assert _positions(_merger().search("蓝鲸", "v2"), "MEDI-0005") == ["9000"]
    origin = _merger().search("座头鲸", "v2")[0]["命中出处"][0]
    assert "座头鲸" in origin["引文"]
    assert origin["引文"].count("座头鲸") == 2
    assert origin["重报次数"] == "2"


def test_withdraw_restores_old_word_and_positions(store_state):
    batch, _ = _merger().correct_batch([4, 5], "座头鲸")
    withdrawn, message = _merger().withdraw_batch(batch["更正批次"])
    assert withdrawn is not None, message
    assert withdrawn["状态"] == "已撤回"

    assert _merger().search("座头鲸", "v2") == []
    restored = _merger().search("蓝鲸", "v2")
    assert _positions(restored, "MEDI-0004") == ["12000"]
    assert _positions(restored, "MEDI-0005") == ["9000"]
    quote = restored[0]["命中出处"][0]["引文"]
    assert "蓝鲸" in quote
    assert "座头鲸" not in quote


def test_switch_to_v1_keeps_old_word_and_old_positions(store_state):
    batch, _ = _merger().correct_batch([4, 5], "座头鲸")
    _merger().withdraw_batch(batch["更正批次"])
    v1 = _merger().search("蓝琼", "v1")
    assert _positions(v1, "MEDI-0004") == ["12000"]
    assert _positions(v1, "MEDI-0005") == ["9000"]
    assert _merger().search("蓝鲸", "v1") == []
    assert "蓝琼" in v1[0]["命中出处"][0]["引文"]


def test_citation_after_withdraw_returns_actual_recording(store_state):
    batch, _ = _merger().correct_batch([4, 5], "座头鲸")
    before = _merger().resolve_citation("座头鲸", "v2", "MEDI-0004", "SPCH-0004", "12000")
    assert before["decision"] == "used_recording"
    assert before["matched"] is True
    assert before["adopted"]["媒体标题"] == "近海鲸类声学记录 A 段"

    _merger().withdraw_batch(batch["更正批次"])
    after = _merger().resolve_citation("座头鲸", "v2", "MEDI-0004", "SPCH-0004", "12000")
    assert after["ok"] is True
    assert after["matched"] is False
    assert after["adopted"] is not None
    assert after["adopted"]["分段编号"] == "SPCH-0004"
    assert "蓝鲸" in after["adopted"]["引文"]
    assert "蓝鲸" in after["reason"]
    assert after["decisionLabel"]


def test_citation_after_position_drifts_out_of_segment(store_state):
    decision = _merger().resolve_citation("蓝鲸", "v2", "MEDI-0004", "SPCH-0004", "90000")
    assert decision["ok"] is False
    assert decision["adopted"] is None
    assert "终点" in decision["reason"]


def test_citation_for_other_version_uses_its_own_quote(store_state):
    decision = _merger().resolve_citation("蓝琼", "v1", "MEDI-0004", "SPCH-0004", "12000")
    assert decision["ok"] is True
    assert decision["matched"] is True
    assert "蓝琼" in decision["adopted"]["引文"]
    assert decision["adopted"]["版本编号"] == "TRSV-0004"


def test_citation_reports_reason_when_not_available(store_state):
    missing_media = _merger().resolve_citation("蓝鲸", "v2", "MEDI-9999", "SPCH-0004", "12000")
    assert missing_media["ok"] is False
    assert missing_media["adopted"] is None
    assert "不存在" in missing_media["reason"]

    bad_segment = _merger().resolve_citation("蓝鲸", "v2", "MEDI-0004", "SPCH-9999", "12000")
    assert bad_segment["ok"] is False
    assert "原段" in bad_segment["reason"]

    out_of_range = _merger().resolve_citation("蓝鲸", "v2", "MEDI-0004", "SPCH-0004", "50")
    assert out_of_range["ok"] is False
    assert "起点" in out_of_range["reason"]


def test_batch_rejects_mixed_versions(store_state):
    # 4/5 属 v2，8/9 属 v1，混选必须拒绝。
    batch, message = _merger().correct_batch([4, 8], "座头鲸")
    assert batch is None
    assert "同一转写版本" in message


def test_correction_is_scoped_to_one_version(store_state):
    _merger().correct_batch([4, 5], "座头鲸")
    # v1 的原段与索引不受 v2 更正影响。
    assert _positions(_merger().search("蓝琼", "v1"), "MEDI-0004") == ["12000"]


def test_citation_endpoint_contract(store_state):
    response = term_index_router.resolve_citation(
        word="蓝琼", version="v1", media="MEDI-0004", segment="SPCH-0004", position="12000")
    assert response["decision"] == "used_recording"
    assert response["citation"]["索引版本"] == "v1"


def test_withdraw_is_idempotent_and_restores_seed(store_state):
    _merger().correct_batch([4, 5], "座头鲸")
    first, _ = _merger().withdraw_batch("TCOR-0001")
    assert first is not None
    second, message = _merger().withdraw_batch("TCOR-0001")
    assert second is None
    assert "不能撤回" in message
    # 撤回后再重建也不应改变命中结果。
    rebuilt = _merger().rebuild_index("v2", "MEDI-0004")
    assert [entry["索引词"] for entry in rebuilt] == ["幼崽", "蓝鲸"]
    assert _positions(_merger().search("蓝鲸", "v2"), "MEDI-0004") == ["12000"]


def test_batch_rejects_evicted_term(store_state):
    for row in store_state.rows("term_extract"):
        if row["id"] == 4:
            row["status"] = "已剔除"
    batch, message = _merger().correct_batch([4], "座头鲸")
    assert batch is None
    assert "已剔除" in message


def test_rebuilding_one_cell_leaves_other_versions_alone(store_state):
    other_before = {
        (r["索引编号"], r["索引词"])
        for r in store_state.rows("media_index")
        if not (r["索引版本"] == "v2" and r["关联媒体源"] == "MEDI-0004")
    }
    _merger().rebuild_index("v2", "MEDI-0004")
    rows = store_state.rows("media_index")
    other_after = {
        (r["索引编号"], r["索引词"])
        for r in rows
        if not (r["索引版本"] == "v2" and r["关联媒体源"] == "MEDI-0004")
    }
    assert other_before == other_after
    v1_words = {(r["索引版本"], r["索引词"]) for r in rows if r["索引版本"] == "v1"}
    assert ("v1", "蓝琼") in v1_words
    assert ("v1", "蓝鲸") not in v1_words
    v2_b = [r for r in rows if r["索引版本"] == "v2" and r["关联媒体源"] == "MEDI-0005"]
    assert [r["索引词"] for r in v2_b] == ["蓝鲸"]
