#!/usr/bin/env python3
"""
Agent Factory — Streamlit Web 智能体模板（模型无关版）
=======================================================
V2.0 架构特征：
  1. 极致简约高级感 UI — Apple/Linear 风格，大面积留白，核心交互一步到位
  2. 对接任意 OpenAI 兼容 SDK（Qwen / GLM / Claude 中转 / vLLM）
  3. 买家通过右侧 Sidebar 配置，零代码切换模型
  4. 输出强制 Markdown 报告 + JSON 结语标记（V2.0 多 Agent 图谱就绪）

运行方式：
    streamlit run {AGENT_FILENAME}

或者通过环境变量注入配置：
    export MY_API_KEY='sk-xxx'
    export MY_BASE_URL='https://api.deepseek.com/v1'
    export MY_MODEL_NAME='deepseek-chat'
    streamlit run {AGENT_FILENAME}
"""

import json
import os
from typing import Optional

# ---------------------------------------------------------------------------
#  🛠️ 自检安装 — 首次运行自动安装缺失依赖（买家双击即用）
# ---------------------------------------------------------------------------
import subprocess
import sys

_MISSING = []

try:
    from openai import OpenAI  # noqa: F401
except ImportError:
    _MISSING.append("openai")

try:
    import streamlit  # noqa: F401
except ImportError:
    _MISSING.append("streamlit")

try:
    from dotenv import load_dotenv  # noqa: F401
except ImportError:
    _MISSING.append("python-dotenv")

if _MISSING:
    print(f"📦 检测到缺失依赖：{', '.join(_MISSING)}")
    print("📥 自动安装中...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", *_MISSING,
         "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
         "--break-system-packages"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print("✅ 依赖安装完成，继续启动...\n")

# 重新导入（确保安装后可用）
from openai import OpenAI
import streamlit as st
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
#  运行时默认配置（由 Agent Factory 注入）
# ---------------------------------------------------------------------------
DEFAULT_API_KEY = "{API_KEY_SLOT}"
DEFAULT_BASE_URL = "{BASE_URL_SLOT}"
DEFAULT_MODEL_NAME = "{MODEL_NAME_SLOT}"
AGENT_NAME = "{AGENT_NAME}"
AGENT_SYSTEM_PROMPT = """{SYSTEM_PROMPT}"""

# ---------------------------------------------------------------------------
#  工具配置（由 Agent Factory 注入，买家可自行扩展）
# ---------------------------------------------------------------------------
TOOL_CONFIG = {TOOL_CONFIG_SLOT}


def call_tool(tool_name: str, **kwargs) -> str:
    """工具调用网关 — 统一入口，支持重试和错误处理"""
    if tool_name not in TOOL_CONFIG:
        return f"[工具错误] 未知工具: {tool_name}"

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


# ---------------------------------------------------------------------------
#  Streamlit 页面配置
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=AGENT_NAME,
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 全局 CSS — 极致简约高级感
st.markdown(
    """
<style>
    /* 字体 & 基础 */
    @import url('https://fonts.googleapis.com/css2?family=Inter:opsz@14..32&display=swap');
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
    .stApp {
        background: #f8f9fc;
        max-width: 880px;
        margin: 0 auto;
        padding: 2rem 1.5rem;
    }

    /* 头部 */
    .app-header {
        margin-bottom: 2.5rem;
    }
    .app-header h1 {
        font-size: 1.6rem;
        font-weight: 500;
        color: #1a1d23;
        margin: 0;
        letter-spacing: -0.02em;
    }
    .app-header p {
        font-size: 0.85rem;
        color: #8e8ea0;
        margin: 0.3rem 0 0 0;
    }
    .app-header .model-badge {
        display: inline-block;
        font-size: 0.7rem;
        background: #e8eaf0;
        color: #555;
        padding: 0.15rem 0.7rem;
        border-radius: 999px;
        margin-top: 0.4rem;
    }

    /* 输入区 */
    .input-card {
        background: #ffffff;
        border: 1px solid #eef0f4;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    .input-card label {
        font-size: 0.8rem;
        font-weight: 500;
        color: #3a3d4a;
        margin-bottom: 0.3rem;
        display: block;
    }

    /* 输出区 */
    .output-card {
        background: #ffffff;
        border: 1px solid #eef0f4;
        border-radius: 14px;
        padding: 1.5rem;
        margin-top: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    .output-card .json-boundary {
        margin-top: 1.5rem;
        padding-top: 1rem;
        border-top: 1px solid #f0f0f4;
        font-size: 0.78rem;
        color: #6b6b80;
    }

    /* 按钮 */
    .stButton button {
        background: #1a1d23;
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.45rem 1.8rem;
        font-size: 0.85rem;
        font-weight: 450;
        transition: opacity 0.15s;
    }
    .stButton button:hover {
        opacity: 0.85;
        color: white;
    }

    /* 侧栏配置 — 极简 */
    .sidebar-config label {
        font-size: 0.75rem;
        color: #8e8ea0;
    }
    .sidebar-config .stTextInput input {
        border: 1px solid #eef0f4;
        border-radius: 8px;
        font-size: 0.8rem;
    }

    /* 隐藏 Streamlit 默认装饰 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
#  Session 初始化
# ---------------------------------------------------------------------------
def init_session():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "api_key" not in st.session_state:
        st.session_state.api_key = os.getenv("MY_API_KEY") or DEFAULT_API_KEY
    if "base_url" not in st.session_state:
        st.session_state.base_url = os.getenv("MY_BASE_URL") or DEFAULT_BASE_URL
    if "model_name" not in st.session_state:
        st.session_state.model_name = os.getenv("MY_MODEL_NAME") or DEFAULT_MODEL_NAME


# ---------------------------------------------------------------------------
#  Sidebar — 运行时配置
# ---------------------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ 模型配置")
        st.caption("支持任意 OpenAI 兼容接口")

        st.session_state.api_key = st.text_input(
            "API Key",
            value=st.session_state.api_key,
            type="password",
            help="你的 API Key（支持 DeepSeek / Qwen / GLM / Claude 中转）",
        )
        st.session_state.base_url = st.text_input(
            "Base URL",
            value=st.session_state.base_url,
            help="例如 https://api.deepseek.com/v1",
        )
        st.session_state.model_name = st.text_input(
            "Model",
            value=st.session_state.model_name,
            help="例如 deepseek-chat / qwen-turbo / glm-4",
        )

        st.divider()
        st.markdown(f"**{AGENT_NAME}**")
        st.caption("V2.0 · 可组合节点架构")
        if st.button("🔄 清空对话", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


# ---------------------------------------------------------------------------
#  主界面
# ---------------------------------------------------------------------------
def main():
    init_session()
    render_sidebar()

    # 头部
    st.markdown(
        f"""
        <div class="app-header">
            <h1>🤖 {AGENT_NAME}</h1>
            <p>输入你的需求，智能体将自动处理并输出结构化报告</p>
            <span class="model-badge">🧠 {st.session_state.model_name or '未配置'}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 输入区
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    col1, col2 = st.columns([5, 1])
    with col1:
        user_input = st.text_area(
            "你的需求",
            placeholder="描述你需要解决的问题，越具体越好...",
            height=100,
            label_visibility="collapsed",
        )
    with col2:
        st.write("")  # 占位
        submitted = st.button("发送", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # 处理请求
    if submitted and user_input.strip():
        with st.spinner("🤔 思考中..."):
            client = OpenAI(
                api_key=st.session_state.api_key,
                base_url=st.session_state.base_url,
            )
            try:
                response = client.chat.completions.create(
                    model=st.session_state.model_name,
                    messages=[
                        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_input},
                    ],
                    temperature=0.3,
                )
                reply = response.choices[0].message.content
                st.session_state.messages.append(
                    {"role": "user", "content": user_input}
                )
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply}
                )
            except Exception as e:
                st.error(f"⚠️ 调用失败：{e}")

    # 输出区 — 对话历史
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div style="margin-bottom:0.3rem;font-size:0.85rem;color:#3a3d4a;">'
                f'<strong>🧑 你</strong></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="output-card" style="background:#f4f6fa;">{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="margin-top:0.8rem;margin-bottom:0.3rem;font-size:0.85rem;color:#3a3d4a;">'
                f'<strong>🤖 {AGENT_NAME}</strong></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="output-card">{msg["content"]}</div>',
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
