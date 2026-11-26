"""术语更正后的命中归并：按转写版本与原段重建媒体索引，并保留可核对的引文出处。

约定：
- 一个原段内同一术语重复出现（重报）只算一处命中，出现次数单独记录；
- 索引只按（转写版本, 媒体源）重建，其它版本与其它媒体源的条目原样保留；
- 每条命中都带原段、毫秒区间和原段引文，取材时据此回到录音核对；
- 批量更正与撤回按批次处理，一批词条必须属于同一转写版本。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

TERM_MODULE = "term_extract"
INDEX_MODULE = "media_index"
LINE_MODULE = "transcript_line"
BATCH_MODULE = "term_correction"
MEDIA_MODULE = "media_source"
VERSION_MODULE = "transcript_version"

BATCH_SUBMITTED = "已提交"
BATCH_WITHDRAWN = "已撤回"


def _find_row(module: str, **match: str) -> dict[str, Any] | None:
    for row in store.rows(module):
        if all(str(row.get(key, "")) == str(value) for key, value in match.items()):
            return row
    return None


def _next_id(module: str) -> int:
    return max((int(row.get("id", 0)) for row in store.rows(module)), default=0) + 1


def _today() -> str:
    return date.today().isoformat()


class IndexHitMerger:
    """按版本与原段归并术语命中，并维护批量的更正与撤回。"""

    # ---------- 命中归并 ----------

    def _line_for(self, version_no: str, media_id: str, segment_id: str) -> dict[str, Any] | None:
        return _find_row(
            LINE_MODULE, 转写版本=version_no,
            关联媒体源=media_id, 分段编号=segment_id,
        )

    def merge_hits(self, version_no: str, media_id: str | None = None) -> list[dict[str, Any]]:
        """归并某版本（可按媒体源收窄）的命中：同一原段重复出现只保留一处命中。

        返回的每一项是一条可取材的命中，带原段毫秒区间与引文。
        """
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for term in store.rows(TERM_MODULE):
            if str(term.get("转写版本", "")) != version_no:
                continue
            term_text = str(term.get("术语文本", "")).strip()
            segment_id = str(term.get("原段编号", ""))
            term_media = str(term.get("关联媒体源", ""))
            if not term_text or not segment_id or not term_media:
                continue
            if media_id and term_media != media_id:
                continue
            line = self._line_for(version_no, term_media, segment_id)
            if line is None:
                continue
            quote = str(line.get("原文本", ""))
            occurrences = quote.count(term_text)
            if occurrences == 0:
                continue
            key = (term_media, term_text, segment_id)
            hit = grouped.get(key)
            if hit is None:
                hit = {
                    "术语文本": term_text,
                    "转写版本": version_no,
                    "版本编号": str(term.get("版本编号", "")),
                    "关联任务": str(term.get("关联任务", "")),
                    "关联媒体源": term_media,
                    "媒体标题": self._media_title(term_media),
                    "分段编号": segment_id,
                    "起始毫秒": int(line.get("起始毫秒", "0") or 0),
                    "结束毫秒": int(line.get("结束毫秒", "0") or 0),
                    "引文": quote,
                    "出现次数": occurrences,
                    "报数": 1,
                }
                grouped[key] = hit
            else:
                # 同一原段同一词的重复报数只累计重报次数，命中仍只算一处；
                # 出现次数以原段实际文本为准，不随抽取重复而翻倍。
                hit["报数"] += 1
                hit["出现次数"] = max(hit["出现次数"], occurrences)
        hits = list(grouped.values())
        hits.sort(key=lambda item: (item["关联媒体源"], item["起始毫秒"], item["术语文本"]))
        return hits

    def _media_title(self, media_id: str) -> str:
        media = _find_row(MEDIA_MODULE, 媒体源编号=media_id)
        return str(media.get("媒体标题", "")) if media else ""

    def _media_verifiable(self, media_id: str) -> tuple[bool, str]:
        media = _find_row(MEDIA_MODULE, 媒体源编号=media_id)
        if media is None:
            return False, f"媒体源 {media_id} 不存在，已打开的试听位置无法回到录音核对"
        if media.get("status") == "拉取失败":
            return False, f"媒体源 {media_id} 拉取失败，录音当前不可核验"
        return True, ""

    # ---------- 索引重建 ----------

    def rebuild_index(self, version_no: str, media_id: str) -> list[dict[str, Any]]:
        """只重建（版本, 媒体源）这一格的索引，其它版本与媒体源的条目保持原样。"""
        hits = self.merge_hits(version_no, media_id)
        rows = store.rows(INDEX_MODULE)
        rows[:] = [
            row for row in rows
            if not (
                str(row.get("索引版本", "")) == version_no
                and str(row.get("关联媒体源", "")) == media_id
            )
        ]
        by_word: dict[str, list[dict[str, Any]]] = {}
        for hit in hits:
            by_word.setdefault(hit["术语文本"], []).append(hit)

        rebuilt: list[dict[str, Any]] = []
        for word, word_hits in by_word.items():
            word_hits.sort(key=lambda item: item["起始毫秒"])
            positions = [str(hit["起始毫秒"]) for hit in word_hits]
            entry = {
                "id": _next_id(INDEX_MODULE),
                "索引编号": f"MDIX-{_next_id(INDEX_MODULE):04d}",
                "关联媒体源": media_id,
                "索引词": word,
                "命中分段数": str(len(word_hits)),
                "命中毫秒位置": ", ".join(positions),
                "索引版本": version_no,
                "构建耗时": "0",
                "构建时间": _today(),
                "status": "已就绪",
                "pending": False,
                "abnormal": False,
                "命中出处": [
                    {
                        "分段编号": hit["分段编号"],
                        "起始毫秒": str(hit["起始毫秒"]),
                        "结束毫秒": str(hit["结束毫秒"]),
                        "引文": hit["引文"],
                        "重报次数": str(hit["报数"]),
                    }
                    for hit in word_hits
                ],
            }
            rows.append(entry)
            rebuilt.append(entry)
        return rebuilt

    def sync_term_counts(self, version_no: str) -> None:
        """更正后按当前原段回写术语的出现次数与首次出现位置。"""
        for term in store.rows(TERM_MODULE):
            if str(term.get("转写版本", "")) != version_no:
                continue
            line = self._line_for(
                version_no, str(term.get("关联媒体源", "")), str(term.get("原段编号", "")))
            if line is None:
                continue
            text = str(term.get("术语文本", ""))
            quote = str(line.get("原文本", ""))
            count = quote.count(text)
            if count == 0:
                continue
            term["出现次数"] = str(count)
            term["首次出现毫秒"] = str(line.get("起始毫秒", "0"))

    # ---------- 批量更正 ----------

    def list_batches(self) -> list[dict[str, Any]]:
        return sorted(
            store.rows(BATCH_MODULE),
            key=lambda row: int(row.get("id", 0)),
            reverse=True,
        )

    def find_batch(self, batch_id: str) -> dict[str, Any] | None:
        return _find_row(BATCH_MODULE, 更正批次=batch_id)

    def correct_batch(
        self, term_ids: list[int], corrected_text: str,
        operator: str = "编辑", remark: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """把同版多条术语一次改成同一个词，提交后立即更新媒体索引命中。"""
        corrected_text = corrected_text.strip()
        if not term_ids:
            return None, "请先勾选需要更正的词条"
        if not corrected_text:
            return None, "纠正后的术语文本不能为空"

        terms: list[dict[str, Any]] = []
        for term_id in term_ids:
            term = store.find(TERM_MODULE, int(term_id))
            if term is None:
                return None, f"术语条目 {term_id} 不存在"
            terms.append(term)

        version_ids = {str(term.get("版本编号", "")) for term in terms}
        version_nos = {str(term.get("转写版本", "")) for term in terms}
        if len(version_ids) != 1 or len(version_nos) != 1 or "" in version_ids:
            return None, "只能勾选同一转写版本的词条批量更正"
        version_id = version_ids.pop()
        version_no = version_nos.pop()

        for term in terms:
            if term.get("status") == "已剔除":
                return None, f"术语 {term.get('术语编号')} 已剔除，不能更正"
            if term.get("更正状态") == "已更正":
                batch_id = str(term.get("更正批次", ""))
                if self.find_batch(batch_id) and self.find_batch(batch_id).get("状态") == BATCH_SUBMITTED:
                    return None, f"术语 {term.get('术语编号')} 已在批次 {batch_id} 更正，请先撤回该批次"

        # 先按原段归并：选中同一段的多条词条只对原段做一次替换，
        # 段内重复出现（重报）一次性改掉，撤回时也只恢复一次。
        line_snapshots: dict[tuple[str, str], dict[str, Any]] = {}
        items: list[dict[str, Any]] = []
        for term in terms:
            old_text = str(term.get("术语文本", ""))
            media_id = str(term.get("关联媒体源", ""))
            segment_id = str(term.get("原段编号", ""))
            line = self._line_for(version_no, media_id, segment_id)
            if line is None:
                return None, f"术语 {term.get('术语编号')} 缺少 {version_no} 原段，无法更正"
            old_quote = str(line.get("原文本", ""))
            if old_text not in old_quote:
                return None, f"术语 {term.get('术语编号')} 的原文未出现在原段中，无法更正"
            line_snapshots.setdefault((media_id, segment_id), {
                "关联媒体源": media_id,
                "原段编号": segment_id,
                "原段": old_quote,
                "旧词": set(),
            })["旧词"].add(old_text)
            items.append({
                "术语条目id": int(term["id"]),
                "术语编号": str(term.get("术语编号", "")),
                "关联媒体源": media_id,
                "原段编号": segment_id,
                "原术语文本": old_text,
                "新术语文本": corrected_text,
                "更正前原段": old_quote,
            })

        batch_id = f"TCOR-{_next_id(BATCH_MODULE):04d}"
        # 先改原段再改术语，保证引文与词条同步。
        for (media_id, segment_id), snapshot in line_snapshots.items():
            line = self._line_for(version_no, media_id, segment_id)
            assert line is not None
            new_quote = str(line.get("原文本", ""))
            for old_word in snapshot["旧词"]:
                new_quote = new_quote.replace(old_word, corrected_text)
            line["原文本"] = new_quote
        for item in items:
            term = store.find(TERM_MODULE, item["术语条目id"])
            assert term is not None
            term["术语文本"] = corrected_text
            term["更正状态"] = "已更正"
            term["更正批次"] = batch_id

        batch = {
            "id": _next_id(BATCH_MODULE),
            "更正批次": batch_id,
            "状态": BATCH_SUBMITTED,
            "版本编号": version_id,
            "转写版本": version_no,
            "更正词数量": str(len(items)),
            "纠正文本": corrected_text,
            "操作者": operator,
            "备注": remark,
            "提交时间": _today(),
            "撤回时间": "-",
            "明细": items,
            "原段快照": [
                {"关联媒体源": snap["关联媒体源"], "原段编号": snap["原段编号"], "原段": snap["原段"]}
                for snap in line_snapshots.values()
            ],
        }
        store.rows(BATCH_MODULE).append(batch)
        self.sync_term_counts(version_no)
        rebuilt = self._rebuild_affected(items, version_no)
        return batch, (
            f"批次 {batch_id} 已提交：{len(items)} 条词条更正为「{corrected_text}」，"
            f"媒体索引已更新 {len(rebuilt)} 条"
        )

    def withdraw_batch(
        self, batch_id: str, operator: str = "编辑", remark: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """撤回整批更正：原段与术语回退，媒体索引按版本与原段恢复命中。"""
        batch = self.find_batch(batch_id)
        if batch is None:
            return None, f"更正批次 {batch_id} 不存在"
        if batch.get("状态") != BATCH_SUBMITTED:
            return None, f"更正批次 {batch_id} 当前状态为「{batch.get('状态')}」，不能撤回"

        version_no = str(batch.get("转写版本", ""))
        items = list(batch.get("明细") or [])
        snapshots = list(batch.get("原段快照") or [])
        # 撤回以提交前的原段快照为准，整段还原，不受重报次数影响。
        for snapshot in snapshots:
            line = self._line_for(version_no, snapshot["关联媒体源"], snapshot["原段编号"])
            if line is not None:
                line["原文本"] = snapshot["原段"]
        for item in items:
            term = store.find(TERM_MODULE, int(item["术语条目id"]))
            if term is not None:
                term["术语文本"] = item["原术语文本"]
                term["更正状态"] = "已撤回"
                term["更正批次"] = batch_id

        batch["状态"] = BATCH_WITHDRAWN
        batch["撤回时间"] = _today()
        batch["撤回操作者"] = operator
        batch["撤回备注"] = remark

        self.sync_term_counts(version_no)
        rebuilt = self._rebuild_affected(items, version_no)
        return batch, (
            f"批次 {batch_id} 已撤回：{len(items)} 条词条恢复原词，"
            f"媒体索引已按 {version_no} 原段更新 {len(rebuilt)} 条"
        )

    def _rebuild_affected(
        self, items: list[dict[str, Any]], version_no: str,
    ) -> list[dict[str, Any]]:
        affected: list[str] = []
        for item in items:
            media_id = str(item["关联媒体源"])
            if media_id not in affected:
                affected.append(media_id)
        rebuilt: list[dict[str, Any]] = []
        for media_id in affected:
            rebuilt.extend(self.rebuild_index(version_no, media_id))
        return rebuilt

    # ---------- 检索与取材 ----------

    def search(self, word: str, version_no: str) -> list[dict[str, Any]]:
        """按词与版本查索引；只返回该版本下仍然成立的命中。"""
        word = word.strip()
        results: list[dict[str, Any]] = []
        for entry in store.rows(INDEX_MODULE):
            if str(entry.get("索引词", "")) != word:
                continue
            if str(entry.get("索引版本", "")) != version_no:
                continue
            results.append({
                "索引编号": entry.get("索引编号"),
                "关联媒体源": entry.get("关联媒体源"),
                "媒体标题": self._media_title(str(entry.get("关联媒体源", ""))),
                "索引词": entry.get("索引词"),
                "命中分段数": entry.get("命中分段数"),
                "命中毫秒位置": entry.get("命中毫秒位置"),
                "索引版本": entry.get("索引版本"),
                "状态": entry.get("status"),
                "命中出处": entry.get("命中出处", []),
            })
        results.sort(key=lambda item: str(item["关联媒体源"]))
        return results

    def resolve_citation(
        self, word: str, version_no: str, media_id: str,
        segment_id: str, position_ms: str = "",
    ) -> dict[str, Any]:
        """就检索人员已打开的试听位置给出取材结论。

        位置本身仍落在可核验的录音原段上时，返回实际采用的录音与引文；
        录音或原段不成立时，给出当前不能取材的理由。
        """
        word = word.strip()
        decision: dict[str, Any] = {
            "ok": False,
            "decision": "unavailable",
            "decisionLabel": "当前不能取材",
            "word": word,
            "requestedVersion": version_no,
            "matched": False,
            "currentWord": "",
            "adopted": None,
            "citation": None,
            "reason": "",
        }

        verifiable, reason = self._media_verifiable(media_id)
        if not verifiable:
            decision["reason"] = reason
            return decision

        line = self._line_for(version_no, media_id, segment_id)
        if line is None:
            decision["reason"] = (
                f"已打开位置所在的 {segment_id} 不在 {version_no} 原段中，无法回到录音核对")
            return decision

        line_start = int(line.get("起始毫秒", "0") or 0)
        line_end = int(line.get("结束毫秒", "0") or 0)
        if position_ms and str(position_ms).isdigit():
            position = int(position_ms)
            if position < line_start:
                decision["reason"] = (
                    f"已打开位置 {position}ms 早于原段 {segment_id} 的起点 {line_start}ms，不属于该原段")
                return decision
            if line_end and position > line_end:
                decision["reason"] = (
                    f"已打开位置 {position}ms 晚于原段 {segment_id} 的终点 {line_end}ms，不属于该原段")
                return decision

        quote = str(line.get("原文本", ""))
        matched = word in quote
        version = _find_row(VERSION_MODULE, 版本编号=str(line.get("版本编号", ""))) or {}
        adopted = {
            "关联媒体源": media_id,
            "媒体标题": self._media_title(media_id),
            "分段编号": segment_id,
            "起始毫秒": str(line_start),
            "结束毫秒": str(line.get("结束毫秒", "")),
            "版本编号": str(line.get("版本编号", "")),
            "转写版本": version_no,
            "版本状态": str(version.get("status", "")),
            "引文": quote,
            "可核验": True,
        }
        decision.update({
            "ok": True,
            "decision": "used_recording",
            "decisionLabel": "可按已打开位置取材",
            "matched": matched,
            "currentWord": word if matched else "",
            "adopted": adopted,
            "citation": {
                "关联媒体源": media_id,
                "分段编号": segment_id,
                "起始毫秒": str(line_start),
                "结束毫秒": str(line.get("结束毫秒", "")),
                "引文": quote,
                "索引版本": version_no,
                "版本编号": str(line.get("版本编号", "")),
            },
        })
        if matched:
            decision["reason"] = (
                f"命中仍成立，取自 {media_id} 的 {segment_id} 原段，引文与录音可逐字核对")
        else:
            replacement = self._word_in_segment(media_id, segment_id, version_no, quote)
            hint = f"当前原段里对应的是「{replacement}」" if replacement else "当前原段已不含该词"
            decision["reason"] = (
                f"「{word}」的更正已撤回，{hint}；"
                f"已打开位置仍落在可核验的 {media_id} {segment_id} 上，可按当前版本原段取材，"
                f"引文以本页给出的原段文本为准")
            decision["decisionLabel"] = "可从已打开位置取材（引文按当前版本）"
        return decision

    def _word_in_segment(
        self, media_id: str, segment_id: str, version_no: str, quote: str,
    ) -> str:
        """找回当前版本里该原段换算后的术语词，供撤回后的取材说明使用。"""
        for term in store.rows(TERM_MODULE):
            if (
                str(term.get("转写版本", "")) == version_no
                and str(term.get("关联媒体源", "")) == media_id
                and str(term.get("原段编号", "")) == segment_id
            ):
                text = str(term.get("术语文本", ""))
                if text and text in quote:
                    return text
        return ""
