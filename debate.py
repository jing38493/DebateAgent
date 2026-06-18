"""AutoGen 多 Agent 辩论赛模拟器（纯命令行，流式显示）。

流程（方案 A：自定义编排循环）：
  主持开场
  每轮：主持宣布 → 正方陈述 → 反方陈述 → 观众提问 → 正方回应 → 反方回应
  评委总结
所有发言实时流式打印，并存成 markdown 实录。

用法:
  python debate.py "人工智能的发展利大于弊"
  python debate.py            # 不带参数则交互式输入论题
"""

import asyncio
import datetime
import re
import sys

import config

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.messages import ModelClientStreamingChunkEvent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_core import CancellationToken

# ---- 各角色人设 ----
SYSTEM_MESSAGES = {
    "moderator": (
        "你是一场正式辩论赛的主持人。语言简洁、中立、有仪式感。"
        "负责开场介绍论题、宣布每一轮、以及在结尾收束全场。不发表自己的立场。不超过100字。"
    ),
    "affirmativeFirst": (
        "你是正方一辩，坚定支持给定论题。你的职责是：定框架、开定义、铺全场逻辑底线"
        "可以直接反驳对方观点和回应观众提问。不用严格按照开篇立论、攻辩、小结、总结的固定环节走，不用刻意搭建工整完整的论证框架；表达风格可以粗犷直接，不用字斟句酌，临场想到反驳点、新思路都可以随时输出，最大限度即兴发挥，重在激烈交锋，不强求章法规整。"
        f"每次发言不超过 {config.WORD_LIMIT} 字。"
    ),
    "affirmativeSecond": (
        "你是正方二辩，坚定支持给定论题。你的职责是：拆对方立论，补己方漏洞，短打交锋"
        "可以直接反驳对方观点和回应观众提问。不用严格按照开篇立论、攻辩、小结、总结的固定环节走，不用刻意搭建工整完整的论证框架；表达风格可以粗犷直接，不用字斟句酌，临场想到反驳点、新思路都可以随时输出，最大限度即兴发挥，重在激烈交锋，不强求章法规整。"
        f"每次发言不超过 {config.WORD_LIMIT} 字。"
    ),
    "affirmativeThird": (
        "你是正方三辩，坚定支持给定论题。你的职责是：集中强攻、打崩对方核心逻辑"
        "可以直接反驳对方观点和回应观众提问。不用严格按照开篇立论、攻辩、小结、总结的固定环节走，不用刻意搭建工整完整的论证框架；表达风格可以粗犷直接，不用字斟句酌，临场想到反驳点、新思路都可以随时输出，最大限度即兴发挥，重在激烈交锋，不强求章法规整。"
        f"每次发言不超过 {config.WORD_LIMIT} 字。"
    ),
    "affirmativeFourth": (
        "你是正方四辩，坚定支持给定论题。你的职责是：梳理全场战局、升华价值、盖棺定论"
        "可以直接反驳对方观点和回应观众提问。不用严格按照开篇立论、攻辩、小结、总结的固定环节走，不用刻意搭建工整完整的论证框架；表达风格可以粗犷直接，不用字斟句酌，临场想到反驳点、新思路都可以随时输出，最大限度即兴发挥，重在激烈交锋，不强求章法规整。"
        f"每次发言不超过 {config.WORD_LIMIT} 字。"
    ),
    "negativeFirst": (
        "你是反方一辩，坚定反对给定论题。你的职责是：定框架、开定义、铺全场逻辑底线"
        "可以直接反驳对方观点和回应观众提问。不用严格按照开篇立论、攻辩、小结、总结的固定环节走，不用刻意搭建工整完整的论证框架；表达风格可以粗犷直接，不用字斟句酌，临场想到反驳点、新思路都可以随时输出，最大限度即兴发挥，重在激烈交锋，不强求章法规整。"
        f"每次发言不超过 {config.WORD_LIMIT} 字。"
    ),
    "negativeSecond": (
        "你是反方二辩，坚定反对给定论题。你的职责是：拆对方立论，补己方漏洞，短打交锋"
        "可以直接反驳对方观点和回应观众提问。不用严格按照开篇立论、攻辩、小结、总结的固定环节走，不用刻意搭建工整完整的论证框架；表达风格可以粗犷直接，不用字斟句酌，临场想到反驳点、新思路都可以随时输出，最大限度即兴发挥，重在激烈交锋，不强求章法规整。"
        f"每次发言不超过 {config.WORD_LIMIT} 字。"
    ),
    "negativeThird": (
        "你是反方三辩，坚定反对给定论题。你的职责是：集中强攻、打崩对方核心逻辑"
        "可以直接反驳对方观点和回应观众提问。不用严格按照开篇立论、攻辩、小结、总结的固定环节走，不用刻意搭建工整完整的论证框架；表达风格可以粗犷直接，不用字斟句酌，临场想到反驳点、新思路都可以随时输出，最大限度即兴发挥，重在激烈交锋，不强求章法规整。"
        f"每次发言不超过 {config.WORD_LIMIT} 字。"
    ),
    "negativeFourth": (
        "你是反方四辩，坚定反对给定论题。你的职责是：梳理全场战局、升华价值、盖棺定论"
        "可以直接反驳对方观点和回应观众提问。不用严格按照开篇立论、攻辩、小结、总结的固定环节走，不用刻意搭建工整完整的论证框架；表达风格可以粗犷直接，不用字斟句酌，临场想到反驳点、新思路都可以随时输出，最大限度即兴发挥，重在激烈交锋，不强求章法规整。"
        f"每次发言不超过 {config.WORD_LIMIT} 字。"
    ),
    "audience1": (
        "你代表现场观众。针对本轮正反双方的发言，提出一个尖锐、具体、有启发性的问题，"
        "促使双方进一步交锋。只问一个问题，不超过 60 字，不要表态支持哪一方。"
    ),
    "audience2": (
        "你代表现场观众。针对本轮正反双方的发言，提出一个尖锐、具体、有启发性的问题，"
        "促使双方进一步交锋。只问一个问题，不超过 60 字，不要表态支持哪一方。"
    ),
    "audience3": (
        "你代表现场观众。针对本轮正反双方的发言，提出一个尖锐、具体、有启发性的问题，"
        "促使双方进一步交锋。只问一个问题，不超过 60 字，不要表态支持哪一方。"
    ),
    "judge": (
        "你是辩论赛评委。从【逻辑性、证据、表达、反驳力度】四个维度点评正反双方，"
        "指出各自亮点与不足，给出建设性评价。不必判定唯一胜负，可指出本场更具说服力的一方及理由。"
        "对每一方的点评不超过60字"
    ),
}

LABELS = {
    "moderator": "主持人",
    "affirmativeFirst": "正方一辩",
    "affirmativeSecond": "正方二辩",
    "affirmativeThird": "正方三辩",
    "affirmativeFourth": "正方四辩",
    "negativeFirst": "反方一辩",
    "negativeSecond": "反方二辩",
    "negativeThird": "反方三辩",
    "negativeFourth": "反方四辩",
    "audience1": "观众1",
    "audience2": "观众2",
    "audience3": "观众3",
    "judge": "评委",
}

# 参与自由辩论的 8 位辩手（按角色名）
DEBATERS = [
    "affirmativeFirst",
    "affirmativeSecond",
    "affirmativeThird",
    "affirmativeFourth",
    "negativeFirst",
    "negativeSecond",
    "negativeThird",
    "negativeFourth",
]

# 注意：selector_prompt 必须包含 {roles}、{participants}、{history} 三个占位符
SELECTOR_PROMPT = (
    "你是辩论赛自由辩论环节的裁判，负责决定下一句由谁来说。\n"
    "可选发言者及其职责：\n{roles}\n\n"
    "规则：正方与反方尽量交替发言；如果某位辩手点名向对方某位辩手提问，"
    "则下一句应由被点名的辩手回答；让更多辩手参与，不要总是同一个人说。\n\n"
    "以下是目前的对话：\n{history}\n\n"
    "请从 {participants} 中选择下一位发言者，只返回角色名。"
)

transcript: list[str] = []

# 推理模型会把思考过程包在这些标签里，显示和存档都要去掉
THINK_TAGS = [("<think>", "</think>"), ("<thinking>", "</thinking>")]


class ThinkStripper:
    """流式去除 <think>...</think> 思考块，能正确处理标签被切到两个 chunk 的情况。"""

    def __init__(self) -> None:
        self.in_think = False
        self.buf = ""

    @staticmethod
    def _hold_partial(s: str, tag: str) -> tuple[str, str]:
        # 把末尾可能是 tag 前缀的部分留住，等下个 chunk 再判断
        for k in range(min(len(tag) - 1, len(s)), 0, -1):
            if s[-k:] == tag[:k]:
                return s[:-k], s[-k:]
        return s, ""

    def feed(self, text: str) -> str:
        self.buf += text
        out: list[str] = []
        while self.buf:
            if not self.in_think:
                open_tag = (
                    THINK_TAGS[0][0]
                    if "<think>" in self.buf
                    else ("<thinking>" if "<thinking>" in self.buf else None)
                )
                if open_tag is None:
                    safe, hold = self._hold_partial(self.buf, "<thinking>")
                    self.buf = hold
                    out.append(safe)
                    break
                idx = self.buf.find(open_tag)
                out.append(self.buf[:idx])
                self.buf = self.buf[idx + len(open_tag) :]
                self.in_think = True
                self._close = "</think>" if open_tag == "<think>" else "</thinking>"
            else:
                idx = self.buf.find(self._close)
                if idx == -1:
                    _, hold = self._hold_partial(self.buf, self._close)
                    self.buf = hold
                    break
                self.buf = self.buf[idx + len(self._close) :]
                self.in_think = False
        return "".join(out)

    def flush(self) -> str:
        if not self.in_think:
            r, self.buf = self.buf, ""
            return r
        return ""


def _strip_think(text: str) -> str:
    """对完整文本做一次性清洗（用于兜底/存档）。"""
    for open_tag, close_tag in THINK_TAGS:
        text = re.sub(
            re.escape(open_tag) + r".*?" + re.escape(close_tag), "", text, flags=re.S
        )
    return text.strip()


def _context() -> str:
    return "\n".join(transcript) if transcript else "（暂无发言）"


async def _say(text: str, role: str) -> None:
    """用 macOS 自带 say 朗读，每个角色不同声音。非 macOS 自动跳过。"""
    if not config.ENABLE_TTS or sys.platform != "darwin" or not text:
        return
    # 角色名可能是 affirmativeFirst / audience1 等，按前缀归到对应声音
    voice = config.ROLE_VOICES.get(role)
    if not voice:
        for key, v in config.ROLE_VOICES.items():
            if role.startswith(key):
                voice = v
                break
    if not voice:
        return
    proc = await asyncio.create_subprocess_exec(
        "say",
        "-v",
        voice,
        "-r",
        str(config.TTS_RATE),
        text,
    )
    await proc.wait()


async def speak(agent: AssistantAgent, role: str, instruction: str) -> str:
    """让某个 agent 基于 instruction 发言，流式打印并记入实录。

    每次发言前 reset，使该 agent 的上下文 = 系统人设 + 本次 instruction（内含完整实录），
    从而所有角色共享同一份辩论上下文，又不会重复累积。
    """
    await agent.on_reset(CancellationToken())

    label = LABELS[role]
    model = config.ROLE_MODELS[role]
    print(f"\n\033[1m【{label}】\033[0m \033[2m({model})\033[0m")

    quiet = config.QUIET_TEXT  # 安静模式：不在屏幕上逐字显示，只靠听
    if quiet:
        print("\033[2m……\033[0m", end="", flush=True)

    stripper = ThinkStripper()
    collected = ""
    fallback = ""
    async for event in agent.run_stream(task=instruction):
        if isinstance(event, ModelClientStreamingChunkEvent):
            collected += event.content
            if not quiet:
                visible = stripper.feed(event.content)
                if visible:
                    sys.stdout.write(visible)
                    sys.stdout.flush()
        elif isinstance(event, TaskResult):
            last = event.messages[-1]
            fallback = getattr(last, "content", "") or fallback

    if not quiet:
        tail = stripper.flush()
        if tail:
            sys.stdout.write(tail)
            sys.stdout.flush()

    text = _strip_think(collected or fallback)
    if quiet:
        print("\r\033[K", end="")  # 清掉省略号那一行
    elif not collected:  # 流式没出内容（网关可能不支持流），补打一次完整结果
        print(text)
    else:
        print()

    transcript.append(f"{label}：{text}")
    await _say(text, role)
    return text


async def run_debate(topic: str) -> None:
    clients = {role: config.make_client(role) for role in config.ROLE_MODELS}
    agents = {
        role: AssistantAgent(
            name=role,
            model_client=clients[role],
            system_message=SYSTEM_MESSAGES[role],
            model_client_stream=True,  # 开启 token 级流式
        )
        for role in config.ROLE_MODELS
    }

    print(f"\n{'=' * 60}\n  辩论论题：{topic}\n{'=' * 60}")

    try:
        # 开场
        await speak(
            agents["moderator"],
            "moderator",
            f"请为本场辩论开场：介绍论题「{topic}」，说明正方支持、反方反对，"
            f"流程为：双方一辩开篇立论 → 二/三辩攻辩 → 一辩小结 → 自由辩论 → "
            f"四辩总结 → 观众提问 → 评委点评。简短有力。",
        )

        # 开篇论述
        await speak(
            agents["affirmativeFirst"],
            "affirmativeFirst",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（正方一辩）进行开篇论述。",
        )
        await speak(
            agents["negativeFirst"],
            "negativeFirst",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（反方一辩）进行开篇论述。",
        )

        # 二辩
        await speak(
            agents["negativeSecond"],
            "negativeSecond",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（反方二辩）针对正方的论述质问正方二辩。",
        )
        await speak(
            agents["affirmativeSecond"],
            "affirmativeSecond",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（正方二辩）针对反方的论述质问反方二辩。",
        )

        # 三辩
        await speak(
            agents["negativeThird"],
            "negativeThird",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（反方三辩）针对正方的论述质问正方三辩。",
        )
        await speak(
            agents["affirmativeThird"],
            "affirmativeThird",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（正方三辩）针对反方的论述质问反方三辩。",
        )

        # 一辩小结
        await speak(
            agents["affirmativeFirst"],
            "affirmativeFirst",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（正方一辩），梳理刚才攻辩交锋得失，弥补漏洞、重申己方优势",
        )
        await speak(
            agents["negativeFirst"],
            "negativeFirst",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（反方一辩），梳理刚才攻辩交锋得失，弥补漏洞、重申己方优势。",
        )

        # ---- 自由辩论（SelectorGroupChat 自动决定下一句谁说）----
        print("\n\033[1m===== 自由辩论 =====\033[0m")
        # 先把 8 位辩手上下文清干净，再交给团队统一管理
        for role in DEBATERS:
            await agents[role].on_reset(CancellationToken())

        selector_client = config.make_selector_client()
        team = SelectorGroupChat(
            participants=[agents[role] for role in DEBATERS],
            model_client=selector_client,
            termination_condition=MaxMessageTermination(config.FREE_DEBATE_TURNS),
            selector_prompt=SELECTOR_PROMPT,
            allow_repeated_speaker=False,
        )

        free_task = (
            f"论题：{topic}\n\n之前的辩论实录：\n{_context()}\n\n"
            f"现在进入自由辩论环节，请正方一辩先发言，随后双方自由交锋。"
        )

        debater_set = set(DEBATERS)
        current = None  # 当前发言者
        stripper = None  # 当前发言的 <think> 过滤器
        buf = ""  # 当前发言者已显示的干净文本

        def flush_speaker() -> None:
            nonlocal buf
            if current is None:
                return
            if stripper:
                tail = stripper.flush()
                if tail:
                    sys.stdout.write(tail)
                    buf += tail
            transcript.append(f"{LABELS.get(current, current)}：{buf.strip()}")
            print()

        try:
            async for event in team.run_stream(task=free_task):
                if not isinstance(event, ModelClientStreamingChunkEvent):
                    continue
                if event.source not in debater_set:  # 过滤裁判等非辩手来源
                    continue
                if event.source != current:
                    flush_speaker()  # 上一位收尾并落实录
                    current = event.source
                    buf = ""
                    stripper = ThinkStripper() if config.STRIP_THINK else None
                    print(
                        f"\n\033[1m【{LABELS.get(current, current)}】\033[0m ",
                        end="",
                        flush=True,
                    )
                visible = stripper.feed(event.content) if stripper else event.content
                if visible:
                    sys.stdout.write(visible)
                    sys.stdout.flush()
                    buf += visible
            flush_speaker()  # 最后一位收尾
        finally:
            await selector_client.close()
        print("\n\033[2m——自由辩论结束——\033[0m")

        # 四辩总结
        await speak(
            agents["affirmativeFourth"],
            "affirmativeFourth",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（正方四辩），盘点全场矛盾、指出对方整场逻辑漏洞、收拢己方论点、价值升华拔高。",
        )
        await speak(
            agents["negativeFourth"],
            "negativeFourth",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"现在轮到你（反方四辩），盘点全场矛盾、指出对方整场逻辑漏洞、收拢对方论点、价值升华拔高。",
        )

        # 全场结束 → 观众提问
        for aud in ("audience1", "audience2", "audience3"):
            await speak(
                agents[aud],
                aud,
                f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
                f"全场辩论已结束，请你作为观众提一个问题。",
            )

        # 双方回应观众
        await speak(
            agents["affirmativeFourth"],
            "affirmativeFourth",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"请正方回应刚才观众们的提问。",
        )
        await speak(
            agents["negativeFourth"],
            "negativeFourth",
            f"论题：{topic}\n\n当前辩论实录：\n{_context()}\n\n"
            f"请反方回应刚才观众们的提问。",
        )

        # 评委总结
        await speak(
            agents["judge"],
            "judge",
            f"论题：{topic}\n\n完整辩论实录：\n{_context()}\n\n"
            f"请你作为评委对本场辩论进行总结点评, 并给出最终谁获胜。",
        )

        # 主持收尾
        await speak(
            agents["moderator"],
            "moderator",
            "请为本场辩论致简短的结束语。",
        )
    finally:
        for client in clients.values():
            await client.close()

    if config.SAVE_TRANSCRIPT:
        _save(topic)


def _save(topic: str) -> None:
    import os

    os.makedirs("transcripts", exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join("transcripts", f"{stamp}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 辩论实录：{topic}\n\n")
        f.write(f"> 时间：{stamp}\n\n")
        for line in transcript:
            f.write(f"- {line}\n\n")
    print(f"\n\033[2m实录已保存到 {path}\033[0m")


def main() -> None:
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("请输入辩论论题：").strip()
    if not topic:
        print("论题不能为空")
        return
    asyncio.run(run_debate(topic))


if __name__ == "__main__":
    main()
