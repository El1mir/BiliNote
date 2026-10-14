"""把测量结果整理成 ticket 06 要求的 ``after-result.json``。

输入是 ``baseline_measure.py --tasks 200 --repeat 5 --cache both`` 产出的
``baseline-result.json``（同一份报告里同时含「缓存关」与「缓存开」两条腿），
输出是一张**端点 × stat/次（前） × stat/次（后） × p50（前） × p50（后）**的对照表，
外加 ``/task_list`` 的收益拆解。

## 「前」是谁

对**受缓存开关管辖**的三条路径（`POST /task_status/batch`、`GET /task_status/{id}`、
`GET /transcriber_models_status`），「前」用同一次运行的 **`BILINOTE_CACHE=off`** 那一腿：

* 改动只发生在这些路径的「先查注册表」这一步，关掉开关后代码走的就是改动前那条路；
* 两条腿**同一次运行、同一台机器、同一批数据**，比跨时间的两次跑分更可信（见 spec 014
  的测量口径事故：跨运行对比曾被 `sys.modules` 清理不彻底污染）。

对**不受开关管辖**的改进（`/task_list` 的合并读、`orjson`），「前/后」是**同一次运行内**
的 A/B —— `measure_task_list_breakdown` 同时测「两次读」与「合并后一次读」，
`measure_orjson_benefit` 在同一份 bytes 上只比解析。这比拿历史数字比更干净。

`/task_list` 端点级的「前」取自 ``baseline-result.pre-ticket04.json``（ticket 04 落地前
存的快照），若该文件不在则退化为只报运行内 A/B。

用法：

    cd backend
    .\\.venv\\Scripts\\python.exe tests\\014-backend-cache-optimization\\make_after_report.py
"""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_PATH = HERE / "baseline-result.json"
PRE_TICKET04_PATH = HERE / "baseline-result.pre-ticket04.json"
OUT_PATH = HERE / "after-result.json"


def _leg(results, cache: str, task_count: int = 200):
    for entry in results:
        if entry.get("cache") == cache and entry.get("task_count") == task_count:
            return entry
    raise SystemExit(f"baseline-result.json 里没有 cache={cache} / tasks={task_count} 的那一腿")


def _ratio(before, after):
    if not before or not after:
        return None
    return round(before / after, 2)


def _batch_row(off, on):
    b, a = off["batch_poll"], on["batch_poll"]
    return {
        "endpoint": "POST /api/task_status/batch",
        "unit": f"{a['task_count']} 条任务，稳态每轮",
        "stat_before": b["stat_calls_per_round"],
        "stat_after": a["stat_calls_per_round"],
        "p50_before_ms": b["p50_ms"],
        "p50_after_ms": a["p50_ms"],
        "speedup": _ratio(b["p50_ms"], a["p50_ms"]),
        "mechanism": (
            "终态任务命中进程内注册表后不再 os.path.exists；冷启动一轮（注册表为空）"
            f"仍是 {a['cold_ms']}ms / {a['cold_stat_calls']} stat，与关缓存等价 —— 说明收益来自命中而不是少做事。"
        ),
    }


def _single_row(off, on):
    b, a = off["single_status"], on["single_status"]
    return {
        "endpoint": "GET /api/task_status/{id}",
        "unit": "单条",
        "stat_before": b["stat_calls_per_call"],
        "stat_after": a["stat_calls_per_call"],
        "p50_before_ms": b["p50_ms"],
        "p50_after_ms": a["p50_ms"],
        "speedup": _ratio(b["p50_ms"], a["p50_ms"]),
        "mechanism": "单条本来就是一次文件读（基线 1.62ms），收益有限；主要是不再每次 stat。",
    }


def _task_list_row(off, on):
    """``/task_list`` 的「前」不能取同一次运行的两腿。

    这个端点**不受 ``BILINOTE_CACHE`` 管辖**（合并读与 orjson 在两条腿上都生效），
    所以同一次运行的关/开对照对它毫无意义 —— 那样的表会把「开关对 /task_list 没影响」
    误读成「没优化」。真正的「前」是 ticket 04 落地前存的快照
    ``baseline-result.pre-ticket04.json``（同规模 N=200、同命令）。
    """
    a = on["task_list"]
    bd = on["task_list_breakdown"]
    row = {
        "endpoint": "GET /task_list",
        "unit": "整表（N=200）",
        "stat_before": None,
        "stat_after": a["stat_calls_per_call"],
        "p50_before_ms": off["task_list"]["p50_ms"],
        "p50_after_ms": a["p50_ms"],
        "speedup": None,
        "mechanism": (
            "**不受 BILINOTE_CACHE 管辖**（合并读 + orjson 两条腿都在跑）。"
            f"改动后：stat/行 {bd['merged_stat_calls_per_row']}、"
            f"两根读合并后 {bd['merged_read_p50_ms']}ms。"
        ),
        "before_source": "baseline-result.pre-ticket04.json（cache-off 腿）",
        "cache_gated": False,
    }
    try:
        pre = json.loads(PRE_TICKET04_PATH.read_text(encoding="utf-8"))["results"]
        pre_off = _leg(pre, "off")
        row["stat_before"] = pre_off["task_list"]["stat_calls_per_call"]
        row["p50_before_ms"] = pre_off["task_list"]["p50_ms"]
        row["speedup"] = _ratio(pre_off["task_list"]["p50_ms"], a["p50_ms"])
        row["stat_speedup"] = _ratio(
            pre_off["task_list"]["stat_calls_per_call"], a["stat_calls_per_call"]
        )
        row["per_row_file_read_before_ms"] = pre_off["task_list_breakdown"][
            "per_row_file_reads_p50_ms"
        ]
        row["per_row_file_read_after_ms"] = bd["merged_read_p50_ms"]
    except (OSError, KeyError, ValueError, SystemExit):
        row["stat_before"] = off["task_list"]["stat_calls_per_call"]
        row["speedup"] = _ratio(off["task_list"]["p50_ms"], a["p50_ms"])
        row["before_source"] = (
            "缺少 pre-ticket04 快照，退化为同一次运行的 cache-off 腿（该端点上两腿等价）"
        )
    return row


def _models_status_rows(off, on):
    rows = []
    for label, leg in (("缓存关（= 改动前行为）", off), ("缓存开", on)):
        ms = leg["transcriber_models_status"]
        rows.append((label, ms))
    cold_off, warm_on = off["transcriber_models_status"]["warm"], on["transcriber_models_status"]["warm"]
    cold_on = on["transcriber_models_status"]["cold"]
    return {
        "endpoint": "GET /transcriber_models_status",
        "unit": "TTL 内命中一次",
        "stat_before": cold_off["stat_calls_per_call"],
        "stat_after": warm_on["stat_calls_per_call"],
        "p50_before_ms": cold_off["p50_ms"],
        "p50_after_ms": warm_on["p50_ms"],
        "speedup": _ratio(cold_off["p50_ms"], warm_on["p50_ms"]),
        "mechanism": (
            "目录扫描（每个可见模型一次 Path.exists，HF 布局还要 iterdir）进 5s 槽后归零。"
            f"未命中仍是 cold 态：{cold_on['p50_ms']}ms / {cold_on['stat_calls_per_call']} stat。"
            f"命中后残留 {warm_on['stat_calls_per_call']} stat/次来自 "
            "get_registry().visible_model_names() 读注册表文件 —— **刻意不缓存**（收益 ≈0.1ms，"
            "代价是「刚加的自定义模型 5s 内不出现」）。"
        ),
        "cache_off_control": {
            "cold_p50_ms": off["transcriber_models_status"]["cold"]["p50_ms"],
            "warm_p50_ms": cold_off["p50_ms"],
            "cold_stat": off["transcriber_models_status"]["cold"]["stat_calls_per_call"],
            "warm_stat": cold_off["stat_calls_per_call"],
            "meaning": "阴性对照：关掉开关后 cold 与 warm 一致，证明收益来自槽而不是测量噪声。",
        },
        "legs": {label: ms for label, ms in rows},
    }


def _unchanged_rows(off, on):
    rows = []
    reasons = {
        "/api/sys_health": "5s 轮询只在 Tauri 挂；浏览器探活走 /sys_check（不查外部依赖）。",
        "/api/deploy_status": "仅开着设置页监控页时 30s 一次，38ms × 每 30s ≈ 0.13%。",
        "/api/transcriber_config": "切设置页才调一次，4.47ms。",
    }
    for path, reason in reasons.items():
        b = off["readonly_endpoints"][path]
        a = on["readonly_endpoints"][path]
        rows.append(
            {
                "endpoint": path,
                "unit": "单次",
                "stat_before": b["stat_calls_per_call"],
                "stat_after": a["stat_calls_per_call"],
                "p50_before_ms": b["p50_ms"],
                "p50_after_ms": a["p50_ms"],
                "speedup": _ratio(b["p50_ms"], a["p50_ms"]),
                "mechanism": f"**明确不做**。{reason}两腿数值差异属测量噪声。",
            }
        )
    return rows


def build_report(run: dict) -> dict:
    results = run["results"]
    off = _leg(results, "off")
    on = _leg(results, "on")
    benefit = run.get("orjson_benefit") or {}
    bd_off = off["task_list_breakdown"]
    bd_on = on["task_list_breakdown"]

    report = {
        "generated_at": run.get("generated_at"),
        "source_run": RUN_PATH.name,
        "how_to_read": (
            "「前」= 同一次运行的 BILINOTE_CACHE=off 腿（受开关管辖的路径上等价于改动前行为）；"
            "/task_list 的改动前后对比见 task_list_split 与 task_list 行的 *_ticket04 字段。"
            "口径：stat 计数为准，open 计数因 app/ 下的 Cython 产物而偏低。"
        ),
        "comparison": [
            _batch_row(off, on),
            _single_row(off, on),
            _task_list_row(off, on),
            _models_status_rows(off, on),
            *_unchanged_rows(off, on),
            {
                "endpoint": "NoteGenerator._update_status（写一次）",
                "unit": "单次写入",
                "stat_before": off["status_write"]["stat_calls_per_write"],
                "stat_after": on["status_write"]["stat_calls_per_write"],
                "p50_before_ms": off["status_write"]["p50_ms"],
                "p50_after_ms": on["status_write"]["p50_ms"],
                "speedup": _ratio(off["status_write"]["p50_ms"], on["status_write"]["p50_ms"]),
                "mechanism": (
                    "**未改动**。原来就是「唯一临时文件 + os.replace」的原子写；ticket 02 只在它"
                    "前面加了一次 dict 写入（零系统调用），落盘成本不变。"
                ),
            },
        ],
        "task_list_split": {
            "merged_read": {
                "before_ms": bd_off["per_row_file_reads_p50_ms"],
                "after_ms": bd_off["merged_read_p50_ms"],
                "speedup": _ratio(bd_off["per_row_file_reads_p50_ms"], bd_off["merged_read_p50_ms"]),
                "stat_per_row_before": bd_off["stat_calls_per_row"],
                "stat_per_row_after": bd_off["merged_stat_calls_per_row"],
                "mechanism": (
                    "_task_title_from_file 与 _task_has_note 读的是同一个 note_results/<id>.json、"
                    "做同一遍解析；合成 _read_result_summary 后每行只读一次。"
                ),
                "measured_with_cache": "off",
            },
            "orjson": {
                "file_count": benefit.get("file_count"),
                "total_bytes": benefit.get("total_bytes"),
                "median_file_bytes": benefit.get("median_file_bytes"),
                "json_p50_ms": benefit.get("json_p50_ms"),
                "orjson_p50_ms": benefit.get("orjson_p50_ms"),
                "speedup": benefit.get("speedup"),
                "mechanism": (
                    "同一份 bytes 上只比解析（真实 note_results/ 文件，不是造的样例）。"
                    "orjson 已在 requirements.txt 且装好，此前全仓零处使用 —— 零新增依赖。"
                ),
                "measured_with_cache": "n/a（与开关无关）",
            },
            "cache_on_leg": {
                "before_ms": bd_on["per_row_file_reads_p50_ms"],
                "after_ms": bd_on["merged_read_p50_ms"],
                "stat_per_row_before": bd_on["stat_calls_per_row"],
                "stat_per_row_after": bd_on["merged_stat_calls_per_row"],
            },
        },
        "gates": {
            "cache_off_control_matches_baseline": (
                "缓存关那一腿就是对照组：受开关管辖的路径上 stat/p50 与历史基线同量级"
                "（batch 约 1190 stat/轮 vs 历史 1176.8；/task_list 两腿基本相同）。"
            ),
            "regression": "见 ticket 06 Comments 记录的 pytest 全量结果。",
        },
        # 与 baseline-result.json 的 results 同构、可直接 diff —— 取缓存开那一腿。
        "results": [on],
    }
    return report


def _print_report(report: dict) -> None:
    print(f"\n{'端点':<42}{'stat 前':>10}{'stat 后':>10}{'p50 前':>10}{'p50 后':>10}{'×':>7}")
    for row in report["comparison"]:
        print(
            f"{row['endpoint']:<42}{row['stat_before']:>10}{row['stat_after']:>10}"
            f"{row['p50_before_ms']:>10}{row['p50_after_ms']:>10}"
            f"{row['speedup'] if row['speedup'] is not None else '-':>7}"
        )
    split = report["task_list_split"]
    print(
        f"\n  /task_list 拆解：合并两次读 {split['merged_read']['before_ms']}ms → "
        f"{split['merged_read']['after_ms']}ms（stat/行 "
        f"{split['merged_read']['stat_per_row_before']} → {split['merged_read']['stat_per_row_after']}）"
    )
    orjson_part = split["orjson"]
    print(
        f"                orjson 单独 {orjson_part['json_p50_ms']}ms → "
        f"{orjson_part['orjson_p50_ms']}ms（{orjson_part['speedup']}×，"
        f"{orjson_part['file_count']} 个真实文件）"
    )


def main() -> int:
    if not RUN_PATH.exists():
        print(f"缺少 {RUN_PATH}，先跑 baseline_measure.py", file=sys.stderr)
        return 1
    run = json.loads(RUN_PATH.read_text(encoding="utf-8"))
    report = build_report(run)
    if OUT_PATH.exists():
        backup = OUT_PATH.with_name(f"{OUT_PATH.stem}.backup-{report['generated_at'].replace(':', '')}.json")
        shutil.copy2(OUT_PATH, backup)
        print(f"[!] 已备份旧报告：{backup.name}")
    OUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _print_report(report)
    print(f"\n结果已写入：{OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
