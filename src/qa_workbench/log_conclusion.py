"""Readable conclusions from measured job metadata; never infer missing results."""
from __future__ import annotations

import re

MAX_CONCLUSION_BYTES = 32768
_STATUS = {"completed": "PASS", "failed": "FAIL", "pending": "NOT RUN",
           "running": "INCOMPLETE", "cancelled": "CANCELLED", "timed_out": "TIMED OUT",
           "incomplete": "INCOMPLETE", "queued": "NOT RUN"}
_MODES = {"offline_regression": "離線回歸（固定測試資料）",
          "es_integration": "真實資料庫與服務整合",
          "real_es_llm_e2e": "真實資料庫、模型與 RAG 完整流程",
          "live_llm_evaluation": "真模型評測（合成檢索資料）"}
_STEPS = {"indexer": "資料索引", "crawler": "爬蟲", "storage": "儲存",
          "retrieval": "檢索", "retrieval-evaluator": "檢索評分器",
          "agent-behavior": "Agent 行為", "trajectory-evaluator": "工具軌跡評分器",
          "identity_and_restricted_es": "登入身分與資料庫權限",
          "news_mapping_category_vectors": "新聞、分類與向量資料",
          "record_and_recommendation": "點擊紀錄與推薦回應",
          "seeded_two_turn_storage_api": "固定對話的儲存與讀回",
          "real_chat_turn_1": "真模型第一輪對話", "real_chat_turn_2": "真模型第二輪對話",
          "feedback_and_history_readback": "回饋儲存與歷史紀錄",
          "exact_owned_document_cleanup": "清理本次測試資料"}
_GAPS = {"live_llm_quality_not_evaluated": "尚未驗證真模型回答品質",
         "es_integration_not_executed": "尚未執行真實資料庫整合",
         "human_semantic_review_pending": "回答正確性與來源支持度仍待人工審查",
         "crawler_ingestion_not_executed": "尚未驗證爬蟲擷取與資料匯入",
         "public_ingress_not_exercised": "尚未驗證公開入口與路由",
         "mutation_outcome_unknown": "資料變更結果未確認，需檢查本次測試資料清理"}


def _text(value, limit=160):
    return str(value).replace("\r", " ").replace("\n", " ")[:limit]


def _count(value):
    return type(value) is int and value >= 0


def _counts(row):
    values = [row.get(key) for key in ("tests", "failed", "errors", "skipped")]
    if not all(_count(value) for value in values) or sum(values[1:]) > values[0]:
        return None
    total, failed, errors, skipped = values
    return total - failed - errors - skipped, failed, errors, skipped


def _totals(rows):
    measured = [counts for row in rows if (counts := _counts(row)) is not None]
    return [sum(counts[index] for counts in measured) for index in range(4)], len(measured)


def render_conclusion(job, *, step=None, truncated=False, legacy=False):
    """Terminal snapshot only. Capture completeness and test success are separate."""
    if job.get("finished_at") is None:
        return ""
    all_rows = job.get("steps", [])
    rows = [row for row in all_rows if step is None or row.get("name") == step]
    mode = job.get("mode")
    is_model = mode == "live_llm_evaluation"
    totals, measured = _totals(rows)
    checks = [check for row in rows for check in row.get("checks", [])]
    check_pass = sum(check.get("status") == "passed" for check in checks)
    check_fail = sum(check.get("status") == "failed" for check in checks)
    structural = job.get("structural", {})
    structural_pass, structural_fail = structural.get("passed"), structural.get("failed")
    status = job.get("status") if step is None else (rows[0].get("status") if rows else None)
    result = _STATUS.get(status or "", "INCONCLUSIVE")
    if status == "completed":
        if is_model:
            known = _count(structural_pass) and _count(structural_fail)
            result = ("FAIL" if _count(structural_fail) and structural_fail else
                      "PASS" if known and structural_pass > 0 else "INCONCLUSIVE")
        elif mode == "offline_regression":
            result = "FAIL" if totals[1] + totals[2] else "PASS" if totals[0] > 0 and measured == len(rows) else "INCONCLUSIVE"
        else:
            result = "FAIL" if check_fail else "PASS" if check_pass else "INCONCLUSIVE"
    lines = ["", "", "=" * 64, "TEST RESULT CONCLUSION / 測試結果結論", "=" * 64,
             "本次測試結果：" + result,
             "執行狀態：" + _text(job.get("status", "UNKNOWN")).upper(),
             "驗證範圍：" + _MODES.get(mode, _text(mode or "UNKNOWN")),
             "執行編號：" + _text(job.get("id", "UNKNOWN"))]
    sha = job.get("source_sha", "")
    lines += ["程式版本：" + (sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-fA-F]{40}", sha) else "UNKNOWN"),
              "開始時間：" + _text(job.get("started_at", "UNKNOWN")),
              "結束時間：" + _text(job["finished_at"])]
    if step is not None:
        lines += ["此摘要僅涵蓋步驟：" + _text(step), "整次執行狀態：" + _STATUS.get(job.get("status"), "UNKNOWN")]
    if mode == "offline_regression":
        if measured:
            lines += ["測試案例（已取得的報告）：PASS {} | FAIL {} | ERROR {} | SKIP {}".format(*totals)]
        else:
            lines += ["測試案例（已取得的報告）：UNKNOWN"]
        if measured != len(rows):
            lines += [f"缺少完整測試報告的步驟：{len(rows) - measured}；未將未知結果算成 PASS 或 SKIP。"]
    elif is_model:
        known = _count(structural_pass) and _count(structural_fail)
        lines += [f"模型：{_text(job.get('model', 'UNKNOWN'))}",
                  f"結構檢查：PASS {structural_pass} | FAIL {structural_fail}" if known else "結構檢查：UNKNOWN",
                  "案例完成數：{} / {}".format(_text(job.get("completed_cases", "UNKNOWN")), _text(job.get("total_cases", "UNKNOWN"))),
                  "結構檢查只確認已定義的行為規則，不能代表回答品質通過。"]
    else:
        lines += [f"整合檢查：PASS {check_pass} | FAIL {check_fail}", "整合檢查數是細項檢查數，不是品質分數。"]
    if not is_model:
        planned = job.get("total_steps") if step is None else len(rows)
        missing = max(0, planned - len(rows)) if _count(planned) else 0
        not_run = missing + sum(row.get("status") == "pending" for row in rows)
        stage_pass = sum(row.get("status") == "completed" for row in rows)
        stage_fail = sum(row.get("status") == "failed" for row in rows)
        lines += [f"步驟結果：PASS {stage_pass} | FAIL {stage_fail} | NOT RUN {not_run}",
                  f"未執行步驟：NOT RUN {not_run}", "逐步結果："]
        remaining_failures = 12
        for row in rows[:16]:
            name = _text(row.get("name", "UNKNOWN"))
            title = _STEPS.get(name)
            line = "- " + _STATUS.get(row.get("status"), "UNKNOWN") + " | " + (f"{title} ({name})" if title else name)
            if row.get("error"):
                line += " | 原因：" + _text(row["error"])
            if row.get("exit_code") is not None:
                line += " | exit_code=" + _text(row["exit_code"])
            lines.append(line)
            counts = _counts(row)
            if mode == "offline_regression" and counts is not None:
                if counts[1] or counts[2]:
                    lines.append(f"  失敗原因：{counts[1]} 個測試 FAIL、{counts[2]} 個 ERROR；個別案例與錯誤詳見上方原始輸出。")
                elif counts[0] == 0:
                    lines.append("  沒有實際通過的測試；空測試或全部 SKIP 不能視為 PASS。")
            failed_checks = [item for item in row.get("checks", []) if item.get("status") == "failed"]
            for check in failed_checks[:remaining_failures]:
                lines.append("  FAIL 檢查：" + _text(check.get("name", "UNKNOWN")))
            remaining_failures = max(0, remaining_failures - len(failed_checks))
        if len(rows) > 16:
            lines.append("- 其餘步驟詳見上方原始輸出；上方統計包含全部步驟。")
    else:
        for case in [row for row in job.get("cases", []) if row.get("structural_pass") is False][:12]:
            lines.append("FAIL 案例：" + _text(case.get("case_id", "UNKNOWN")))
            for reason in (case.get("hard_failures", []) + case.get("failures", []))[:3]:
                lines.append("  原因：" + _text(reason))
    if job.get("error"):
        lines.append("執行異常原因：" + _text(job["error"]))
    lines += ["紀錄完整性：" + ("INCOMPLETE" if truncated or legacy else "COMPLETE")]
    if legacy:
        lines.append("僅保留舊版尾端紀錄；摘要來自執行結果資料，不代表缺失的原始紀錄已恢復。")
    elif truncated:
        lines.append("部分原始紀錄遺失或超過上限；下列結論不代表 log 已完整保存。")
    lines += ["模型回答品質：" + _text(job.get("semantic_status", "pending")).upper(),
              "人工語意審查與發布驗收：尚未由這次執行單獨確認。", "尚未驗證／待確認："]
    gaps = job.get("gaps", [])
    lines.extend("- " + _GAPS.get(code, _text(code)) for code in gaps[:16])
    if len(gaps) > 16:
        lines.append("- 其餘待確認項目請見完整執行報告。")
    if not gaps:
        lines.append("- 未提供額外範圍資訊；不能視為所有範圍皆已驗證。")
    lines += ["下一步：" + ("先處理上述失敗或異常，再重跑本次範圍。" if result == "FAIL" else
                             "本次未完整執行，請確認原因後重跑。" if result != "PASS" else
                             "本次範圍通過；發布前仍需確認上述缺口與人工審查。"), "=" * 64, ""]
    return "\n".join(lines)
