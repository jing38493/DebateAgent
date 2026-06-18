# DebateAgent — AutoGen 多 Agent 辩论赛模拟器

给一个论题，正方 / 反方辩手（**各用不同模型**）多轮对辩，每轮结束后由 AI 观众提问、双方回应，评委收尾。全程流式打印在命令行，并存成 markdown 实录。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

编辑 `config.py`：

1. `ROLE_MODELS`：把各角色的 `<...模型>` 占位符换成网关上实际可用的模型名（每个辩手可不同）。
2. API key：`export LLM_API_KEY=你的key`（网关不校验则可不设，默认用占位串）。
3. 若网关根路径不带 `/v1`，把 `BASE_URL` 改成 `https://***`。
4. 流程参数：`ROUNDS`（轮数）、`WORD_LIMIT`（每次发言字数上限）。

## 运行

```bash
python debate.py "人工智能的发展利大于弊"
# 或不带参数，交互式输入论题
python debate.py
```

## 结构

- `config.py` — 网关接入 + 每角色模型配置（可插拔，换模型只改这里）
- `debate.py` — 角色人设 + 辩论编排循环 + 流式打印 + 实录存档
- `transcripts/` — 自动生成的辩论实录

## 设计要点

- 用 AutoGen v0.4 `AssistantAgent` + `OpenAIChatCompletionClient`（指向自建 OpenAI 兼容网关）。
- 自定义编排循环精确控制「多轮 + 每轮结束观众提问」的辩论协议。
- 每个角色一个独立 model client，**支持每个辩手用不同模型**。
- 每次发言前 `on_reset`，把完整实录作为上下文喂入，保证所有角色共享同一份辩论上下文又不重复累积。
