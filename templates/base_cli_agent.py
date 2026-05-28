#!/usr/bin/env python3
"""
Agent Factory — CLI 智能体模板（模型无关版）
============================================
V2.0 架构特征：
  1. 对接任意 OpenAI 兼容 SDK（Qwen / GLM / Claude 中转 / vLLM 等）
  2. 买家自备 API_KEY、BASE_URL、MODEL_NAME，零代码切换
  3. 输出强制包含 Markdown 报告 + JSON 结语标记（V2.0 多 Agent 图谱就绪）
  4. 单文件零外部依赖（除 openai + 标准库）

使用方式：
    export MY_API_KEY='sk-xxx'
    export MY_BASE_URL='https://api.deepseek.com/v1'
    python3 {AGENT_FILENAME} "你的需求"
"""

import json
import os
import sys

try:
    from openai import OpenAI
except ImportError:
    print("❌ 需要安装 openai 库：pip install openai")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  运行时配置（买家自由修改）
# ═══════════════════════════════════════════════════════════════
API_KEY = os.getenv("MY_API_KEY") or "{API_KEY_SLOT}"
BASE_URL = os.getenv("MY_BASE_URL") or "{BASE_URL_SLOT}"
MODEL_NAME = os.getenv("MY_MODEL_NAME") or "{MODEL_NAME_SLOT}"

# ═══════════════════════════════════════════════════════════════
#  智能体人格（由 Agent Factory 生成）
# ═══════════════════════════════════════════════════════════════
AGENT_NAME = "{AGENT_NAME}"

SYSTEM_PROMPT = """{SYSTEM_PROMPT}"""

# ═══════════════════════════════════════════════════════════════
#  工具配置（由 Agent Factory 注入，买家可自行扩展）
# ═══════════════════════════════════════════════════════════════
TOOL_CONFIG = {TOOL_CONFIG_SLOT}


def call_tool(tool_name: str, **kwargs) -> str:
    """工具调用网关 — 统一入口，支持重试和错误处理"""
    if tool_name not in TOOL_CONFIG:
        return f"[工具错误] 未知工具: {tool_name}，可用工具: {list(TOOL_CONFIG.keys())}"

    tool = TOOL_CONFIG[tool_name]
    base_url = tool.get("base_url", "")
    auth_header = tool.get("auth_header", "")
    params = {**tool.get("default_params", {}), **kwargs}

    try:
        import urllib.request
        import urllib.parse

        url = f"{base_url}?{urllib.parse.urlencode(params)}" if params else base_url
        req = urllib.request.Request(url)
        if auth_header:
            req.add_header("Authorization", auth_header)

        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        return f"[工具错误] {tool_name} 调用失败: {e}"


def main():
    # -- 命令行参数支持 --
    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not user_input:
        print(f"🤖 {AGENT_NAME} 启动成功")
        print(f"   模型: {MODEL_NAME}")
        print(f"   端点: {BASE_URL}")
        print()
        print("请输入你的需求（或输入 /quit 退出）：")
        interactive_mode()
        return

    # -- 单次模式 --
    result = call_llm(user_input)
    print_report(result)


def interactive_mode():
    """交互式对话"""
    client = _build_client()
    history = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("👋 再见！")
            break

        history.append({"role": "user", "content": user_input})

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=history,
                temperature=0.3,
            )
            reply = response.choices[0].message.content
            print(f"\n🤖 {AGENT_NAME}:")
            print(reply)
            print()
            history.append({"role": "assistant", "content": reply})
        except Exception as e:
            print(f"\n⚠️ 调用失败: {e}\n")


def call_llm(user_input: str) -> str:
    """单次调用 LLM"""
    client = _build_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.3,
    )
    return response.choices[0].message.content


def print_report(report: str):
    """打印结构化的 Markdown 报告"""
    separator = "━" * 60
    print(f"\n{separator}")
    print(f"  📋 {AGENT_NAME} — 输出报告")
    print(f"{separator}\n")
    print(report)
    print(f"\n{separator}")
    print("  ✅ 输出完成（请检查上方 JSON 结语获取结构化数据）")
    print(f"{separator}\n")


def _build_client() -> OpenAI:
    """构建 OpenAI 兼容客户端"""
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


if __name__ == "__main__":
    main()
