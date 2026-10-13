from openai import OpenAI

from app.gpt.base import GPT
from app.gpt.provider.OpenAI_compatible_provider import OpenAICompatibleProvider
from app.gpt.universal_gpt import UniversalGPT
from app.models.model_config import ModelConfig


class GPTFactory:
    @staticmethod
    def from_config(config: ModelConfig) -> GPT:
        client = OpenAICompatibleProvider(api_key=config.api_key, base_url=config.base_url).get_client
        # spec 007：把供应商级限流额度一并交给 UniversalGPT，由它在
        # _do_create 这个唯一出站咽喉处排队。
        return UniversalGPT(
            client=client,
            model=config.model_name,
            provider_key=config.provider_key,
            max_concurrency=config.max_concurrency,
            max_rpm=config.max_rpm,
        )