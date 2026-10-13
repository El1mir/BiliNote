#!/usr/bin/env python3
"""spec 008 ticket 05：本地缓存与历史任务一次性重置。

用途
----
把本机跑出来的中间产物、截图、笔记产物、向量集合与历史任务记录清干净，
让用户可以「删掉重新生成」。**默认只干跑**，不做任何删除。

用法
----
    # 1) 干跑：只报告「将删除什么 + 合计多少字节」
    backend\\.venv\\Scripts\\python.exe scripts\\reset_local_state.py

    # 2) 确认无误后再真删
    backend\\.venv\\Scripts\\python.exe scripts\\reset_local_state.py --apply

    # 可选：连日志一起清（默认不动 app.log）
    ... --apply --include-logs

    # 可选：显式指定数据库（正常情况下不需要）
    ... --db backend\\bili_note.db

⚠️ DATABASE_URL 陷阱（本 ticket 最容易误判「脚本没生效」的地方）
--------------------------------------------------------------
`backend/app/db/engine.py:9` 的默认值是 `sqlite:///bili_note.db`，是**相对路径**，
且 `.env` 里没有设置它。从仓库根目录启动服务/脚本时，SQLAlchemy 会把相对路径
解析到**当前工作目录**，于是会连到一个全新的空库 `./bili_note.db`，
脚本便「成功」报告删了 0 行，而真正的 `backend/bili_note.db` 丝毫未动。

因此本脚本**不**导入 `app.db.engine`，而是自己解析出一个绝对路径：
  1. `--db` 显式参数优先；
  2. 否则读 `DATABASE_URL`（若为 sqlite 相对路径，按仓库根解析并打印出来）；
  3. 否则回落到 `backend/bili_note.db`。
无论走哪条路，**实际使用的数据库绝对路径都会被打印**；若 `video_tasks` 行数为 0
或表不存在，会给出显式警告而不是静默成功。

绝不触碰（硬性）
----------------
- `backend/models/`（whisper 模型，约 538MB）
- `.venv/`、`node_modules/`
- 数据库文件本身（`bili_note.db`）—— 只清表，不删库、不改 schema
- 用户配置（`.env`、`config/`）
- `backend/data/data/`（`get_data_dir()` 双重拼接 bug 产生的空目录，保留以免掩盖问题）
- `backend/static/uploads/` 等未列入目标的目录

每个删除步骤独立 try/except，单步失败不中断整体，最后汇总报告。
脚本可重复执行：第二次运行会报告 0 项且不报错。
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Windows 控制台默认编码是 GBK（cp936），而本脚本的提示里带 ⚠️ / → 这类符号。
# 直接 print 会在「恰好需要给出警告」的那条路径上抛 UnicodeEncodeError 并 exit 1，
# 也就是最该把话说清楚的时候反而崩掉。这里统一把输出切到 UTF-8，
# errors="replace" 兜底：宁可个别符号显示成问号，也不能让脚本中断。
# 用 getattr 取 reconfigure：它只在 Python 3.7+ 的真实文件流上存在，
# 被重定向成其它流对象时（测试、IDE 输出窗口）没有这个方法，直接取属性会报错。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        # 流已关闭 / 不支持该编码时静默跳过：这只是让输出更可读的尽力而为，
        # 失败也不该影响清理本身。
        with contextlib.suppress(ValueError, OSError):
            _reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"

# ---------------------------------------------------------------- 目标定义

# 目录类目标：清空内容，但保留目录本身（应用会继续往里写）
DIR_TARGETS: list[tuple[str, Path]] = [
    ("抽帧中间产物", BACKEND / "data" / "output_frames"),
    ("拼图中间产物", BACKEND / "data" / "grid_output"),
    ("生成的截图", BACKEND / "static" / "screenshots"),
    ("笔记产物", BACKEND / "note_results"),
    ("向量集合", BACKEND / "vector_db"),
]

# 日志是可选目标：默认不动
LOG_TARGETS: list[tuple[str, Path]] = [
    ("应用日志", BACKEND / "logs" / "app.log"),
]

# 表类目标：(分组, 表名)
TABLE_TARGETS: list[tuple[str, str]] = [
    ("历史任务", "video_tasks"),
    ("资源登记", "media_resources"),
    ("清理记录", "media_cleanup_runs"),
    # 分组归属：spec 007 起是**正式使用**的表（note_group_dao + note_group 路由），
    # 不是孤儿表 —— 清它是有意的，因为「移除所有任务」必须连归属一起清，否则会留下
    # 一堆没有成员的空组。
    ("分组归属", "note_groups"),
    # 孤儿表：无 ORM、无代码引用，明确的历史遗留
    ("孤儿表", "media_resource_refs"),
    ("孤儿表", "note_versions"),
    ("孤儿表", "note_migration_markers"),
    ("孤儿表", "note_migration_diagnostics"),
]

# 绝不允许被解析到这些路径之下
FORBIDDEN_ROOTS: list[Path] = [
    BACKEND / "models",
    BACKEND / "data" / "data",
    BACKEND / "config",
    REPO_ROOT / "config",
    REPO_ROOT / ".venv",
    BACKEND / ".venv",
    REPO_ROOT / "node_modules",
    BACKEND / "node_modules",
]


# ---------------------------------------------------------------- 安全校验


def ensure_safe(path: Path) -> Path:
    """把路径解析成绝对路径，并确认它不在受保护路径之下。"""
    resolved = path.resolve()

    if resolved in (REPO_ROOT.resolve(), BACKEND.resolve()):
        raise SystemExit(f"拒绝操作：{resolved} 是仓库/后端根目录本身")

    if REPO_ROOT.resolve() not in resolved.parents:
        raise SystemExit(f"拒绝操作：{resolved} 不在仓库 {REPO_ROOT} 之内")

    for bad in FORBIDDEN_ROOTS:
        bad_resolved = bad.resolve()
        if resolved == bad_resolved or bad_resolved in resolved.parents:
            raise SystemExit(f"拒绝操作：{resolved} 位于受保护路径 {bad_resolved} 之下")

    return resolved


# ---------------------------------------------------------------- 体量统计


def dir_stats(path: Path) -> tuple[int, int]:
    """返回 (文件数, 合计字节)。目录不存在返回 (0, 0)。"""
    if not path.is_dir():
        return 0, 0
    count = 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                count += 1
                total += item.stat().st_size
        except OSError:
            # 单个文件读不到不影响整体统计
            continue
    return count, total


def file_stats(path: Path) -> tuple[int, int]:
    if not path.is_file():
        return 0, 0
    try:
        return 1, path.stat().st_size
    except OSError:
        return 0, 0


def _safe_float(value, default: float = 0.0) -> float:
    """把任意值转成 float；转不了就返回 default，绝不抛异常。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """把任意值转成 int；转不了就返回 default，绝不抛异常。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def human(num_bytes: int) -> str:
    size = _safe_float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{_safe_int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


# ---------------------------------------------------------------- 数据库解析


def resolve_db_path(explicit: str | None) -> tuple[Path, str]:
    """返回 (绝对路径, 来源说明)。不导入 app.db.engine，避免相对路径陷阱。"""
    if explicit:
        return Path(explicit).resolve(), "--db 参数"

    url = os.getenv("DATABASE_URL")
    if url:
        if url.startswith("sqlite:///"):
            raw = url[len("sqlite:///") :]
            candidate = Path(raw)
            if not candidate.is_absolute():
                # SQLAlchemy 会相对「进程 cwd」解析；这里按仓库根解析并明确打印
                candidate = REPO_ROOT / candidate
            return candidate.resolve(), f"DATABASE_URL={url}（相对路径按仓库根解析）"
        print(
            f"⚠️  检测到非 sqlite 的 DATABASE_URL={url}，本脚本只处理 SQLite，将回落到 backend/bili_note.db"
        )

    return (BACKEND / "bili_note.db").resolve(), "默认 backend/bili_note.db"


def table_counts(db_path: Path) -> dict[str, int | None]:
    """返回 {表名: 行数}；表不存在则为 None。"""
    counts: dict[str, int | None] = {}
    if not db_path.is_file():
        return {name: None for _, name in TABLE_TARGETS}

    con = sqlite3.connect(str(db_path))
    try:
        existing = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for _, name in TABLE_TARGETS:
            if name not in existing:
                counts[name] = None
                continue
            try:
                counts[name] = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[
                    0
                ]
            except sqlite3.Error as exc:
                print(f"  · 表 {name} 行数读取失败，按未知处理：{exc}")
                counts[name] = None
    finally:
        con.close()
    return counts


# ---------------------------------------------------------------- 执行动作


def clear_dir(path: Path) -> tuple[int, int]:
    """清空目录内容但保留目录本身。返回 (删除条目数, 释放字节)。"""
    if not path.is_dir():
        return 0, 0

    removed = 0
    freed = 0
    for child in list(path.iterdir()):
        try:
            if child.is_dir() and not child.is_symlink():
                size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                shutil.rmtree(child)
            else:
                size = child.stat().st_size
                child.unlink()
            removed += 1
            freed += size
        except OSError as exc:
            print(f"    ⚠️  跳过 {child.name}：{exc}")
    return removed, freed


def clear_tables(db_path: Path) -> list[tuple[str, str, int]]:
    """清空目标表的行。返回 [(分组, 表名, 删除行数)]。"""
    results: list[tuple[str, str, int]] = []
    con = sqlite3.connect(str(db_path))
    try:
        existing = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for group, name in TABLE_TARGETS:
            if name not in existing:
                results.append((group, name, -1))
                continue
            try:
                before = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                con.execute(f'DELETE FROM "{name}"')
                con.commit()
                results.append((group, name, before))
            except sqlite3.Error as exc:
                print(f"    ⚠️  清表 {name} 失败：{exc}")
                results.append((group, name, -1))
    finally:
        con.close()
    return results


# ---------------------------------------------------------------- 主流程


def main() -> int:
    parser = argparse.ArgumentParser(
        description="spec 008 ticket 05：清空本地中间产物、截图、笔记产物、向量集合与历史任务记录。",
        epilog=(
            "默认干跑，只报告将删除什么；必须显式传 --apply 才真删。\n"
            "绝不触碰：backend/models/、.venv/、node_modules/、bili_note.db 文件本身、\n"
            ".env、config/、backend/data/data/。\n"
            "注意 DATABASE_URL 未设置时为相对路径 sqlite:///bili_note.db，\n"
            "本脚本会自己解析出绝对路径并打印，避免误连到空库。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply", action="store_true", help="真正执行删除（默认只干跑）"
    )
    parser.add_argument(
        "--include-logs", action="store_true", help="同时清理 backend/logs/app.log"
    )
    parser.add_argument("--db", default=None, help="显式指定 SQLite 数据库文件路径")
    args = parser.parse_args()

    apply_mode = args.apply

    print("=" * 78)
    print("spec 008 ticket 05 · 本地缓存与历史任务重置")
    print(
        f"模式：{'⚠️  APPLY（真删）' if apply_mode else 'DRY-RUN（干跑，不做任何删除）'}"
    )
    print(f"仓库根：{REPO_ROOT}")
    print("=" * 78)

    # ---------------- 目录类目标
    print("\n【目录类目标】")
    dir_plan: list[tuple[str, Path, int, int]] = []
    for label, raw_path in DIR_TARGETS:
        try:
            path = ensure_safe(raw_path)
        except SystemExit as exc:
            print(f"  ✗ {label}: {exc}")
            continue
        count, size = dir_stats(path)
        dir_plan.append((label, path, count, size))
        state = "存在" if path.is_dir() else "不存在"
        print(f"  {label:<14} {path}")
        print(f"  {'':<14} → {state}，{count} 个文件，{human(size)}")

    log_plan: list[tuple[str, Path, int, int]] = []
    if args.include_logs:
        print("\n【日志目标（--include-logs）】")
        for label, raw_path in LOG_TARGETS:
            try:
                path = ensure_safe(raw_path)
            except SystemExit as exc:
                print(f"  ✗ {label}: {exc}")
                continue
            count, size = file_stats(path)
            log_plan.append((label, path, count, size))
            print(f"  {label:<14} {path}")
            print(f"  {'':<14} → {count} 个文件，{human(size)}")

    # ---------------- 数据库
    db_path, db_origin = resolve_db_path(args.db)
    print("\n【数据库】")
    print(f"  来源：{db_origin}")
    print(f"  绝对路径：{db_path}")
    print(f"  文件存在：{'是' if db_path.is_file() else '否'}")
    if db_path.is_file():
        print(f"  文件大小：{human(db_path.stat().st_size)}")

    counts = table_counts(db_path)
    print(f"\n  {'分组':<10} {'表名':<32} {'行数':>8}")
    for group, name in TABLE_TARGETS:
        n = counts.get(name)
        shown = "表不存在" if n is None else str(n)
        print(f"  {group:<10} {name:<32} {shown:>8}")

    # 关键警告：避免「脚本没生效」被误判成成功
    warnings: list[str] = []
    if not db_path.is_file():
        warnings.append(
            f"数据库文件不存在：{db_path}\n"
            "    可能原因：DATABASE_URL 未设置（默认相对路径 sqlite:///bili_note.db），\n"
            "    而你在别的 cwd 下运行，导致 SQLAlchemy 连到了一个空库。\n"
            f"    请确认真正的库是 {BACKEND / 'bili_note.db'}，必要时用 --db 显式指定。"
        )
    elif counts.get("video_tasks") == 0 and (
        sum(c for _, _, c, _ in dir_plan + log_plan) > 0
    ):
        # 只在「库里没任务、磁盘上却还有产物」时才警告：那才是连错库的特征。
        # 库里 0 行 + 磁盘也 0 文件 = 已经清干净了（正常状态），不该报错吓人。
        warnings.append(
            "video_tasks 行数为 0，但磁盘上还有待清理的产物。\n"
            "    这通常意味着连到了错误的数据库（见 DATABASE_URL 相对路径陷阱），\n"
            "    而不是「本来就没有历史任务」。请核对上面打印的绝对路径。"
        )

    if warnings:
        print("\n⚠️  警告：")
        for w in warnings:
            print(f"  - {w}")

    # ---------------- 汇总
    total_files = sum(c for _, _, c, _ in dir_plan + log_plan)
    total_bytes = sum(s for _, _, _, s in dir_plan + log_plan)
    total_rows = sum(n for n in counts.values() if n)

    print("\n" + "-" * 78)
    print(f"合计：{total_files} 个文件（{human(total_bytes)}）、{total_rows} 行表记录")

    if not apply_mode:
        print("\nDRY-RUN 结束，未做任何删除。确认无误后加 --apply 真删。")
        print("-" * 78)
        return 0

    # ---------------- 真删
    print("\n开始执行删除……")
    failures: list[str] = []

    print("\n[1/2] 目录类目标")
    for label, path, _count, _size in dir_plan:
        try:
            removed, freed = clear_dir(path)
            print(f"  ✓ {label:<14} 删除 {removed} 项，释放 {human(freed)}")
        except Exception as exc:  # 单步失败不中断整体
            print(f"  ✗ {label:<14} 失败：{exc}")
            failures.append(f"{label} ({path}): {exc}")

    for label, path, _count, _size in log_plan:
        try:
            if path.is_file():
                size = path.stat().st_size
                path.unlink()
                print(f"  ✓ {label:<14} 删除日志，释放 {human(size)}")
            else:
                print(f"  · {label:<14} 不存在，跳过")
        except Exception as exc:
            print(f"  ✗ {label:<14} 失败：{exc}")
            failures.append(f"{label} ({path}): {exc}")

    print("\n[2/2] 数据库表")
    try:
        for group, name, deleted in clear_tables(db_path):
            if deleted < 0:
                print(f"  · {group:<10} {name:<32} 表不存在，跳过")
            else:
                print(f"  ✓ {group:<10} {name:<32} 删除 {deleted} 行")
    except Exception as exc:
        print(f"  ✗ 清表整体失败：{exc}")
        failures.append(f"数据库清表 ({db_path}): {exc}")

    # ---------------- 复核
    print("\n" + "-" * 78)
    print("复核：")
    for label, path, _c, _s in dir_plan:
        count, size = dir_stats(path)
        flag = "✓" if count == 0 else "✗"
        print(f"  {flag} {label:<14} {path} → {count} 个文件，{human(size)}")
    after = table_counts(db_path)
    for group, name in TABLE_TARGETS:
        n = after.get(name)
        if n is None:
            print(f"  · {group:<10} {name:<32} 表不存在")
        else:
            flag = "✓" if n == 0 else "✗"
            print(f"  {flag} {group:<10} {name:<32} {n} 行")

    print("\n确认未被触碰的受保护项：")
    for label, p in [
        ("whisper 模型", BACKEND / "models"),
        (".env", REPO_ROOT / ".env"),
        ("config/", REPO_ROOT / "config"),
        ("数据库文件", db_path),
        ("data/data（保留）", BACKEND / "data" / "data"),
    ]:
        if p.is_dir():
            _c, s = dir_stats(p)
            print(f"  ✓ {label:<18} {p} （{human(s)}）")
        elif p.is_file():
            print(f"  ✓ {label:<18} {p} （{human(p.stat().st_size)}）")
        else:
            print(f"  · {label:<18} {p} 不存在")

    if failures:
        print(f"\n⚠️  {len(failures)} 个步骤失败：")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\n全部完成。")
    print("-" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
