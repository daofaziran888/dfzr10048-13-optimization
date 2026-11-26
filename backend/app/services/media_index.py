"""媒体索引构建领域服务：为术语与标注文本建立到毫秒位置的反向索引，产出索引条目数据集供检索与版本同步消费。"""
from __future__ import annotations

from typing import Any

from app.pipeline.index_hit_merger import IndexHitMerger
from app.services.base import BaseModuleService
from app.store import store


class MediaIndexService(BaseModuleService):
    MODULE = "media_index"
    ENTITY = "索引条目"
    OPERATION_TERM = "关联"
    LIST_FIELDS = ["索引编号", "关联媒体源", "索引词", "命中分段数", "命中毫秒位置", "索引版本", "构建耗时", "构建时间"]
    REQUIRED_FIELDS = ["索引编号", "关联媒体源", "索引词"]
    STATUS_ORDER = ["构建中", "已就绪", "已过期", "构建失败"]
    ACTION_RULES = {"启动构建": "构建中", "标记就绪": "已就绪", "登记失败": "构建失败"}
    NEGATIVE_ACTIONS = []

    def __init__(self) -> None:
        self.merger = IndexHitMerger()

    def build_index(
        self, index_id: str, media_id: str, term: str,
        hit_count: int, position_ms: str, version: str,
    ) -> tuple[dict[str, Any] | None, str]:
        """构建索引条目。"""
        rows = store.rows(self.MODULE)
        entry = {
            "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
            "索引编号": index_id, "关联媒体源": media_id,
            "索引词": term, "命中分段数": str(hit_count),
            "命中毫秒位置": position_ms, "索引版本": version,
            "构建耗时": "0", "构建时间": "2026-11-01",
            "status": "已就绪", "pending": False, "abnormal": False,
        }
        rows.append(entry)
        return entry, f"索引 {index_id} 已构建"

    def get_by_version(self, version: str) -> list[dict[str, Any]]:
        """获取指定索引版本的所有条目。"""
        rows = store.rows(self.MODULE)
        return [r for r in rows if r.get("索引版本") == version]

    def check_version_sync(
        self, media_id: str, expected_version: str,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """检查索引版本是否与预期版本一致，返回不一致的条目。"""
        rows = store.rows(self.MODULE)
        mismatched = [
            r for r in rows
            if r.get("关联媒体源") == media_id
            and r.get("索引版本") != expected_version
        ]
        return len(mismatched) == 0, mismatched

    def mark_expired(self, version: str) -> int:
        """标记指定版本的索引为过期。"""
        rows = store.rows(self.MODULE)
        count = 0
        for r in rows:
            if r.get("索引版本") == version:
                r["status"] = "已过期"
                r["abnormal"] = True
                count += 1
        return count

    def rebuild(self, version_no: str, media_id: str) -> list[dict[str, Any]]:
        """按转写版本与原段重建某媒体的命中，保留可核对的引文出处。"""
        return self.merger.rebuild_index(version_no, media_id)

    def merge_hits(self, version_no: str, media_id: str | None = None) -> list[dict[str, Any]]:
        """归并命中：同一原段重复出现只算一处。"""
        return self.merger.merge_hits(version_no, media_id)

    def search(self, word: str, version_no: str) -> list[dict[str, Any]]:
        """按词与转写版本检索命中出处。"""
        return self.merger.search(word, version_no)

    def resolve_citation(
        self, word: str, version_no: str, media_id: str,
        segment_id: str, position_ms: str = "",
    ) -> dict[str, Any]:
        """就检索人员已打开的试听位置给出取材结论。"""
        return self.merger.resolve_citation(
            word, version_no, media_id, segment_id, position_ms)