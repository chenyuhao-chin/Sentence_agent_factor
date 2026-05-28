"""
Agent Factory — 智能体全自动生成工厂
====================================
客户界面：输入卡密 → 描述需求 → 一键拿到智能体交付包

使用方式：
    streamlit run factory_app.py
"""

import json
import os
import sys
import zipfile
from datetime import datetime as dt
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
#  配置持久化
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).resolve().parent / ".factory_config.json"


def _load_persisted_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


_PERSISTED = _load_persisted_config()

from core.llm_client import DeepSeekClient
from core.builder import AgentBuilder
from core.packager import AgentPackager
from core.card_manager import CardManager

# ---------------------------------------------------------------------------
#  页面配置
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Agent Factory — 智能体工厂",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
#  全局 CSS — 极简深色主题
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ---- 全局 ---- */
* { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
.stApp {
    background: #0a0a0f;
    color: #e0e0e8;
}
.main .block-container {
    max-width: 720px;
    padding: 2rem 1.5rem 4rem;
}

/* ---- 隐藏 Streamlit 默认元素 ---- */
#MainMenu, footer, .stDeployButton, header { visibility: hidden; }

/* ---- Hero ---- */
.hero {
    text-align: center;
    padding: 2.5rem 0 2rem;
}
.hero h1 {
    font-size: 2.2rem;
    font-weight: 700;
    color: #ffffff;
    margin: 0;
    letter-spacing: -0.03em;
}
.hero h1 span { color: #6c63ff; }
.hero p {
    font-size: 0.95rem;
    color: #6b6b80;
    margin-top: 0.5rem;
}

/* ---- 状态条 ---- */
.status-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    font-size: 0.82rem;
    font-weight: 500;
    margin-bottom: 2rem;
}
.status-bar.active {
    background: rgba(108, 99, 255, 0.1);
    border: 1px solid rgba(108, 99, 255, 0.25);
    color: #a29bfe;
}
.status-bar.inactive {
    background: rgba(255, 107, 107, 0.08);
    border: 1px solid rgba(255, 107, 107, 0.2);
    color: #ff6b6b;
}
.status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
}
.status-dot.green { background: #6c63ff; box-shadow: 0 0 6px rgba(108,99,255,0.5); }
.status-dot.red { background: #ff6b6b; }

/* ---- 步骤卡片 ---- */
.step-card {
    background: #12121a;
    border: 1px solid #1e1e2e;
    border-radius: 14px;
    padding: 1.8rem 2rem;
    margin-bottom: 1.2rem;
}
.step-label {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #6c63ff;
    background: rgba(108, 99, 255, 0.1);
    padding: 0.2rem 0.7rem;
    border-radius: 6px;
    margin-bottom: 0.8rem;
}
.step-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #ffffff;
    margin-bottom: 0.3rem;
}
.step-desc {
    font-size: 0.82rem;
    color: #6b6b80;
    margin-bottom: 1.2rem;
}

/* ---- 输入框 ---- */
.stTextInput input, .stTextArea textarea {
    background: #1a1a28 !important;
    border: 1px solid #2a2a3e !important;
    border-radius: 10px !important;
    color: #e0e0e8 !important;
    font-size: 0.9rem !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #6c63ff !important;
    box-shadow: 0 0 0 2px rgba(108, 99, 255, 0.15) !important;
}
.stTextArea textarea { min-height: 180px !important; line-height: 1.6 !important; }

/* ---- 按钮 ---- */
.stButton > button {
    background: linear-gradient(135deg, #6c63ff 0%, #5a52d5 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    padding: 0.6rem 2rem !important;
    transition: all 0.2s ease !important;
    letter-spacing: 0.01em !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(108, 99, 255, 0.3) !important;
}
.stButton > button:disabled {
    background: #2a2a3e !important;
    color: #555 !important;
    transform: none !important;
    box-shadow: none !important;
}
.stDownloadButton > button {
    background: linear-gradient(135deg, #00b894 0%, #00a381 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    padding: 0.7rem 2rem !important;
}

/* ---- 侧边栏 ---- */
section[data-testid="stSidebar"] {
    background: #0e0e16;
    border-right: 1px solid #1e1e2e;
}
section[data-testid="stSidebar"] .stTextInput input {
    background: #1a1a28 !important;
    border: 1px solid #2a2a3e !important;
}

/* ---- 提示框 ---- */
.stAlert {
    border-radius: 10px !important;
    font-size: 0.85rem !important;
}

/* ---- 分割线 ---- */
hr {
    border-color: #1e1e2e !important;
    margin: 1.5rem 0 !important;
}

/* ---- 文件列表 ---- */
.file-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0;
    font-size: 0.82rem;
    color: #a0a0b0;
    font-family: 'SF Mono', 'Fira Code', monospace;
}
.file-icon { font-size: 0.9rem; }

/* ---- 底部 ---- */
.footer {
    text-align: center;
    padding: 2rem 0 1rem;
    font-size: 0.75rem;
    color: #3a3a4a;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Session State
# ---------------------------------------------------------------------------
_defaults = {
    "agent_config": None, "system_prompt": "", "agent_name": "",
    "architect_done": False, "packing": False, "pack_done": False,
    "last_zip_path": "", "last_script_path": "",
    "card_activated": False, "card_key": "", "card_status": "", "card_remaining": None,
    "memory_config": _PERSISTED.get("memory_config", {"max_turns": 5, "persist_strategy": "session_only"}),
    "platforms": _PERSISTED.get("platforms", ["coze", "dify", "feishu", "openclaw"]),
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
#  侧边栏 — 仅卡密
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚡ Agent Factory")
    st.caption("智能体全自动生成")

    st.markdown("---")

    card_mgr = CardManager()

    if st.session_state.card_activated:
        status = card_mgr.get_status(st.session_state.card_key)
        if status.get("activated"):
            st.success(f"{status['message']}")
            st.caption(f"卡密: `{st.session_state.card_key}`")
        else:
            st.error(f"{status['message']}")
            st.session_state.card_activated = False
            st.session_state.card_key = ""

        if st.button("切换卡密", use_container_width=True):
            st.session_state.card_activated = False
            st.session_state.card_key = ""
            st.rerun()
    else:
        card_input = st.text_input("输入卡密", placeholder="FX-SEASON-XXXX", key="sidebar_card")
        if st.button("激活", type="primary", use_container_width=True):
            if card_input.strip():
                ok, msg = card_mgr.verify_and_activate_card(card_input)
                if ok:
                    st.session_state.card_activated = True
                    st.session_state.card_key = card_input.strip().upper()
                    st.rerun()
                else:
                    st.error(msg)

    st.markdown("---")
    st.caption("购买卡密请访问闲鱼店铺")


# ---------------------------------------------------------------------------
#  Hero
# ---------------------------------------------------------------------------
card_mgr = CardManager()
card_status = card_mgr.get_status(st.session_state.card_key)
card_ok = card_status.get("activated", False)

st.markdown("""
<div class="hero">
    <h1>⚡ Agent <span>Factory</span></h1>
    <p>描述你的需求，AI 自动设计、装配、打包一个完整的智能体</p>
</div>
""", unsafe_allow_html=True)

# 状态条
if card_ok:
    msg = card_status.get("message", "")
    st.markdown(f'<div class="status-bar active"><span class="status-dot green"></span>{msg}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="status-bar inactive"><span class="status-dot red"></span>未激活 — 请在左侧侧边栏输入卡密</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  步骤 1：描述需求
# ---------------------------------------------------------------------------
st.markdown("""
<div class="step-card">
    <div class="step-label">Step 1</div>
    <div class="step-title">描述你的需求</div>
    <div class="step-desc">用一句话告诉 AI 你想做什么，它会自动设计智能体的全部细节</div>
</div>
""", unsafe_allow_html=True)

requirement = st.text_input(
    "需求",
    value="",
    placeholder="例：帮我做一个挑战杯比赛路演PPT润色Agent",
    label_visibility="collapsed",
    disabled=not card_ok,
)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    architect_btn = st.button(
        "🎯 开始设计",
        type="primary",
        use_container_width=True,
        disabled=not card_ok or not requirement.strip() or st.session_state.architect_done,
    )

if architect_btn:
    st.session_state.architect_done = False
    st.session_state.pack_done = False

    with st.spinner("AI 架构师正在设计中..."):
        try:
            client = DeepSeekClient(
                api_key=_PERSISTED.get("api_key") or os.getenv("DEEPSEEK_API_KEY"),
                base_url=_PERSISTED.get("api_base_url") or os.getenv("DEEPSEEK_BASE_URL"),
                model=_PERSISTED.get("api_model") or "deepseek-chat",
            )
            config = client.architect(requirement)
            if config and config.get("agent_name"):
                st.session_state.agent_config = config
                st.session_state.system_prompt = config.get("system_prompt", "")
                st.session_state.agent_name = config.get("agent_name", "未命名智能体")
                st.session_state.architect_done = True
                st.success(f"设计完成 — {config.get('agent_name')}")
                st.rerun()
            else:
                st.error("架构师返回空配置，请稍后重试")
        except Exception as e:
            st.error(f"调用失败：{str(e)[:200]}")


# ---------------------------------------------------------------------------
#  步骤 2：确认 & 微调
# ---------------------------------------------------------------------------
if st.session_state.architect_done and st.session_state.agent_config:
    st.markdown("""
    <div class="step-card">
        <div class="step-label">Step 2</div>
        <div class="step-title">确认 & 微调</div>
        <div class="step-desc">AI 已经设计好了，你可以在下方调整任何细节</div>
    </div>
    """, unsafe_allow_html=True)

    agent_name = st.text_input("智能体名称", value=st.session_state.agent_name, key="name_input")

    system_prompt = st.text_area(
        "System Prompt",
        value=st.session_state.system_prompt,
        height=200,
        label_visibility="collapsed",
    )

    # 平台选择
    st.markdown("**部署平台**")
    platform_options = [("coze", "Coze"), ("dify", "Dify"), ("feishu", "飞书"), ("openclaw", "OpenClaw")]
    cols = st.columns(len(platform_options))
    selected = []
    for idx, (key, label) in enumerate(platform_options):
        with cols[idx]:
            if st.checkbox(label, value=key in st.session_state.platforms, key=f"p_{key}"):
                selected.append(key)
    st.session_state.platforms = selected or ["coze", "dify"]


    # ---------------------------------------------------------------------------
    #  步骤 3：打包下载
    # ---------------------------------------------------------------------------
    st.markdown("""
    <div class="step-card">
        <div class="step-label">Step 3</div>
        <div class="step-title">打包 & 下载</div>
        <div class="step-desc">一键生成完整交付包，包含所有平台配置和使用说明</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pack_btn = st.button(
            "⚡ 一键打包",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.packing or st.session_state.pack_done,
        )

    if pack_btn:
        st.session_state.packing = True
        try:
            config = dict(st.session_state.agent_config)
            config["agent_name"] = agent_name
            config["system_prompt"] = system_prompt

            with st.spinner("装配引擎工作中..."):
                builder = AgentBuilder(config=config, delivery_type="zip",
                    api_key=_PERSISTED.get("api_key", ""),
                    base_url=_PERSISTED.get("api_base_url", ""),
                    model_name=_PERSISTED.get("api_model", "deepseek-chat"))
                script_path = builder.assemble()

            with st.spinner("打包器工作中..."):
                packager = AgentPackager(
                    script_path=str(script_path), delivery_type="zip",
                    agent_name=agent_name,
                    agent_scenario=config.get("required_skills", ["通用任务"])[0] if config.get("required_skills") else requirement[:40],
                )
                result = packager.package()

            if result.success:
                st.session_state.last_zip_path = result.output_path
                st.session_state.pack_done = True
                card_mgr.consume_quota(st.session_state.card_key)
                st.rerun()
            else:
                st.error(f"打包失败：{result.message}")
        except Exception as e:
            st.error(f"异常：{str(e)[:200]}")
        finally:
            st.session_state.packing = False


# ---------------------------------------------------------------------------
#  完成：下载 & 内容预览
# ---------------------------------------------------------------------------
if st.session_state.pack_done and st.session_state.last_zip_path:
    zip_path = Path(st.session_state.last_zip_path)
    if zip_path.exists():
        st.markdown("---")

        # 下载按钮
        with open(zip_path, "rb") as f:
            st.download_button(
                label="📦 下载交付包",
                data=f.read(),
                file_name=zip_path.name,
                mime="application/zip",
                use_container_width=True,
            )

        st.caption(f"{zip_path.name} · {zip_path.stat().st_size / 1024:.1f} KB")

        # 文件清单
        with zipfile.ZipFile(zip_path, "r") as zf:
            files = zf.namelist()

        with st.expander(f"📁 查看交付包内容（{len(files)} 个文件）", expanded=False):
            for f in files:
                if f.endswith(".py"):
                    icon = "📄"
                elif f.endswith(".md") or f.endswith(".docx"):
                    icon = "📖"
                elif f.endswith(".json"):
                    icon = "📋"
                elif f.endswith(".yaml") or f.endswith(".yml"):
                    icon = "⚙️"
                elif f.endswith(".env"):
                    icon = "🔑"
                elif f.endswith(".sh") or f.endswith(".bat"):
                    icon = "🚀"
                else:
                    icon = "📎"
                st.markdown(f'<div class="file-item"><span class="file-icon">{icon}</span>{f}</div>', unsafe_allow_html=True)

        # 重新开始
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔄 再做一个", use_container_width=True):
                for k in ("agent_config", "system_prompt", "agent_name", "architect_done", "pack_done", "last_zip_path"):
                    st.session_state[k] = _defaults[k]
                st.rerun()


# ---------------------------------------------------------------------------
#  Footer
# ---------------------------------------------------------------------------
st.markdown('<div class="footer">Agent Factory ⚡ Powered by AI</div>', unsafe_allow_html=True)
