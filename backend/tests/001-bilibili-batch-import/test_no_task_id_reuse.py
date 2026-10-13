"""spec 008 ticket 03：`task_id` 重试/复用入口必须彻底消失。

背景：`/generate_note` 原先接受客户端传入的 `task_id`，命中即复用同一个 task_id
重跑（前端叫「重新生成」，失败态还有个「重试」按钮）。这条链路已按 spec 008 整体
删除，`task_id` 一律由服务端 `uuid.uuid4()` 生成。

这个用例是防腐化断言：任何人把 `task_id` 重新加回请求模型、或让浏览器插件开始
在请求体里带 `task_id`，都会在这里失败。
"""
import ast
import re
from pathlib import Path

from app.routers.note import VideoRequest

REPO_ROOT = Path(__file__).resolve().parents[3]
NOTE_ROUTER = REPO_ROOT / "backend" / "app" / "routers" / "note.py"
EXTENSION_SRC = REPO_ROOT / "BillNote_extension" / "src"


def test_video_request_rejects_task_id():
    """VideoRequest 不再接受 task_id 字段。"""
    assert "task_id" not in VideoRequest.model_fields

    request = VideoRequest(
        video_url="https://www.bilibili.com/video/BV1xx411c7mD",
        platform="bilibili",
        quality="fast",
        model_name="m",
        provider_id="p",
    )
    assert not hasattr(request, "task_id")


def test_generate_note_reuse_branch_is_gone():
    """复用分支已删：不再读 data.task_id，且 task_id 只由服务端生成。"""
    source = NOTE_ROUTER.read_text(encoding="utf-8")

    # 旧分支的日志文案
    assert "重试模式" not in source

    # 精确匹配属性访问 data.task_id，避免误伤 data.task_ids（批量归档入参）
    assert not re.search(r"\bdata\.task_id\b(?!s)", source)
    assert "VideoRequest" in source and "task_id: Optional[str]" not in source

    # task_id 由服务端生成；generate_note 里必须有一条
    assert "task_id = str(uuid.uuid4())" in source


def test_generate_note_has_no_in_flight_task_id_guard():
    """依赖 task_id 的并发守卫已随重试入口一并删除。"""
    source = NOTE_ROUTER.read_text(encoding="utf-8")
    assert "_is_task_id_in_flight" not in source

    tree = ast.parse(source)
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "_is_task_id_in_flight" not in names
    # 视频级守卫仍在（它现在唯一的含义是同视频并发保护）
    assert "_is_task_in_flight" in names


def test_extension_never_sends_task_id_in_generate_request():
    """插件只读取响应里的 task_id；generate 请求体里绝不能带它。

    注意：`/api/chat/index` 的 `JSON.stringify({ task_id: taskId })` 是合法用法，
    因此只检查 generateNote 函数体内发出的请求体。
    """
    assert EXTENSION_SRC.is_dir(), f"插件源码目录不存在：{EXTENSION_SRC}"

    offenders = []
    for path in EXTENSION_SRC.rglob("*.ts"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"export async function generateNote\b", text):
            # 先从 ")" 之后定位函数体的第一个 "{"，再配对到闭合。
            # 不能直接找第一个 "{"：签名里的返回类型 `Promise<{ task_id: string }>`
            # 本身就含 task_id，会把类型注解误判成请求体。
            rest = text[match.end():]
            params_end = rest.find(")")
            if params_end < 0:
                continue
            start = rest.find("{", params_end)
            if start < 0:
                continue
            depth = 0
            for idx in range(start, len(rest)):
                if rest[idx] == "{":
                    depth += 1
                elif rest[idx] == "}":
                    depth -= 1
                    if depth == 0:
                        rest = rest[start: idx + 1]
                        break
            # 只看实际发出的请求体，避免把类型注解里的 task_id 算作回归
            body_payloads = re.findall(r"JSON\.stringify\(([^)]*)\)", rest)
            if any(re.search(r"\btask_id\b", payload) for payload in body_payloads):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: generateNote 请求体含 task_id")

    assert offenders == [], "插件 generate 请求不应包含 task_id：\n" + "\n".join(offenders)
