from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ModelConfig:
    """
    存储每个模型提供商的调用参数信息，用于从数据库读取并动态构建 GPT 调用实例。
    """
    name: str                   # 展示名，如 "GPT-4 Turbo"（用于前端展示）
    provider: str               # 模型提供商，如 "openai"、"qwen"、"deepseek"
    api_key: str                # 调用该模型使用的 API Key
    base_url: str               # 模型 API 接口地址（OpenAI SDK兼容）
    model_name: str             # 实际请求用的模型名称，如 "gpt-4-turbo"
    created_at: Optional[datetime] = None  # 可选：创建时间（从 SQLite 自动生成）

    # spec 007：供应商级限流。三个字段默认为 None/空 = 不限流，
    # 这样「列出模型」「连通性测试」这类短调用不受影响，只有生成笔记时才带上。
    provider_key: Optional[str] = None      # 供应商 id，限流按它聚合
    max_concurrency: Optional[int] = None   # 该供应商同时在途的请求数上限
    max_rpm: Optional[float] = None         # 该供应商每分钟请求数上限