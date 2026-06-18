"""辩论赛模拟器配置。

通过自建的 OpenAI 兼容网关 https://llm.sca.im 接入各模型。
每个角色用哪个模型，都在 ROLE_MODELS 里改——换/加模型不用动逻辑。
"""

import os

from autogen_core.models import ModelFamily, ModelInfo
from autogen_ext.models.openai import OpenAIChatCompletionClient

# ---- 网关 ----
BASE_URL = (
    ""  # ⚠️ 只给到 /v1！SDK 会自动拼 /chat/completions，不要在这里加 /chat/completions
)
# 优先读环境变量；没有就用占位串（很多网关不校验 key，但 SDK 必须给一个非空值）
API_KEY = ""

# ---- 每个角色用的模型（先占位，按网关上实际可用的模型名替换）----
# 需求：每个辩论选手模型不一样。
ROLE_MODELS = {
    "moderator": "bailian/qwen3.7-plus",  # 例: "gpt-4o"
    "affirmativeFirst": "MiniMax-M3",  # 例: "claude-opus-4-8"
    "affirmativeSecond": "MiniMax-M3",  # 例: "claude-opus-4-8"
    "affirmativeThird": "MiniMax-M3",  # 例: "claude-opus-4-8"
    "affirmativeFourth": "MiniMax-M3",  # 例: "claude-opus-4-8"
    "negativeFirst": "deepseek/deepseek-v4-pro",  # 例: "deepseek-chat"
    "negativeSecond": "deepseek/deepseek-v4-pro",  # 例: "deepseek-chat"
    "negativeThird": "deepseek/deepseek-v4-pro",  # 例: "deepseek-chat"
    "negativeFourth": "deepseek/deepseek-v4-pro",  # 例: "deepseek-chat"
    "audience1": "zai/glm-5.1",  # 例: "claude-haiku-4-5"（便宜的即可）
    "audience2": "zai/glm-5.1",
    "audience3": "zai/glm-5.1",
    "judge": "kimi-latest",  # 例: "claude-opus-4-8"
}

# ---- 辩论流程参数 ----
WORD_LIMIT = 50  # 每次发言字数上限
FREE_DEBATE_TURNS = 10  # 自由辩论环节最多发言多少句后结束
STRIP_THINK = True  # 是否过滤推理模型的 <think> 思考过程
SAVE_TRANSCRIPT = True  # 是否把全程存成 markdown

# 每次请求的 max_tokens（必须设：部分模型要求在 [1, 65536] 内，不设会报错）。
# 给推理型模型留足空间（它们会先输出思考过程），4096 一般够。
MAX_TOKENS = 4096

# ---- 语音播报（macOS 自带 say，零依赖）----
ENABLE_TTS = False  # 开/关语音
QUIET_TEXT = False  # True = 屏幕只显示角色名+省略号，发言内容只靠听（更清爽）
TTS_RATE = 200  # 语速（约 字/分钟），想快/慢就调这里
# 每个角色一个不同声音（中文语音，name 来自 `say -v '?'`）
ROLE_VOICES = {
    "moderator": "Shelley",  # 主持人（普通话女声）
    "affirmative": "Tingting",  # 正方（婷婷·普通话女声）
    "negative": "Eddy",  # 反方（普通话男声）
    "audience": "Grandpa",  # 观众（爷爷，有现场感）
    "judge": "Reed",  # 评委（沉稳）
}

# SelectorGroupChat 用来决定「下一句谁说」的裁判模型（可以便宜点）
SELECTOR_MODEL = "kimi-latest"


def _model_info() -> ModelInfo:
    """网关上的自定义模型名 SDK 不认识，必须显式声明能力，否则报错。

    辩论不需要工具/视觉，全部按最小能力声明即可。
    """
    return ModelInfo(
        vision=False,
        function_calling=False,
        json_output=False,
        family=ModelFamily.UNKNOWN,
        structured_output=False,  # 老版本 autogen 若报错可删掉这一行
    )


def make_client_for_model(model: str) -> OpenAIChatCompletionClient:
    """按模型名创建 model client。"""
    return OpenAIChatCompletionClient(
        model=model,
        base_url=BASE_URL,
        api_key=API_KEY,
        model_info=_model_info(),
        max_tokens=MAX_TOKENS,
    )


def make_client(role: str) -> OpenAIChatCompletionClient:
    """按角色创建 model client。"""
    return make_client_for_model(ROLE_MODELS[role])


def make_selector_client() -> OpenAIChatCompletionClient:
    """自由辩论环节「决定下一句谁说」的裁判 client。"""
    return make_client_for_model(SELECTOR_MODEL)
