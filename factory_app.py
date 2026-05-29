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
from datetime import datetime as dt
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
#  配置持久化
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).resolve().parent / "data" / "factory_config.json"
_STATE_PATH = Path(__file__).resolve().parent / "data" / "session_state.json"


def _load_persisted_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_persisted_config(cfg: dict):
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_session_state() -> dict:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_session_state(state: dict):
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_PERSISTED = _load_persisted_config()
_SAVED_STATE = _load_session_state()

from core.llm_client import DeepSeekClient
from core.builder import AgentBuilder
from core.packager import AgentPackager
from core.card_manager import CardManager

# ---------------------------------------------------------------------------
#  页面配置
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Sentence Agent Factory",
    page_icon="S",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
#  全局 CSS —— 学术蓝 + 白色 + 去 Emoji
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }

/* ---- 全局 ---- */
.main > div { padding: 2rem 0.5rem; }
.stApp { background: #f0f4f8; }
h1, h2, h3 { font-weight: 700; color: #1e3a5f; }

/* ---- 卡片 ---- */
.card {
    background: #ffffff;
    border-radius: 14px;
    padding: 1.8rem 2rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 2px 8px rgba(30, 58, 95, 0.06);
    border: 1px solid #d6e4f0;
}
.card-title {
    font-size: 1rem;
    font-weight: 700;
    color: #1e3a5f;
    margin-bottom: 1rem;
    letter-spacing: 0.02em;
}

/* ---- 输入框：加大加宽 ---- */
.requirement-input textarea {
    font-size: 1.05rem !important;
    line-height: 1.8 !important;
    min-height: 160px !important;
    padding: 1rem 1.2rem !important;
    border: 1px solid #d6e4f0 !important;
    border-radius: 10px !important;
    background: #fafbfc !important;
}
.requirement-input textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1) !important;
    background: #ffffff !important;
}
.stTextArea textarea {
    font-size: 0.95rem; line-height: 1.6; min-height: 200px;
    border: 1px solid #d6e4f0 !important;
    border-radius: 10px !important;
}
.stTextArea textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
}
.stTextInput input {
    border: 1px solid #d6e4f0 !important;
    border-radius: 10px !important;
}
.stTextInput input:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
}

/* ---- 按钮 ---- */
.stButton button {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.6rem 2rem !important;
    transition: all 0.2s ease !important;
}
.stButton button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 16px rgba(37, 99, 235, 0.25) !important;
}
.stButton button:disabled {
    background: #c8d6e5 !important;
    color: #ffffff !important;
    transform: none !important;
    box-shadow: none !important;
}
.stDownloadButton button {
    background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.65rem 2rem !important;
    font-size: 0.95rem !important;
}

/* ---- 状态提示 ---- */
.success-badge {
    background: #dbeafe; color: #1e40af;
    padding: 0.3rem 0.8rem; border-radius: 8px;
    font-size: 0.85rem; display: inline-block; font-weight: 500;
}
.info-badge {
    background: #dbeafe; color: #1e40af;
    padding: 0.3rem 0.8rem; border-radius: 8px;
    font-size: 0.85rem; display: inline-block; font-weight: 500;
}

/* ---- 侧边栏 ---- */
section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #d6e4f0;
}
.sidebar-history {
    font-size: 0.85rem; color: #475569;
    padding: 0.5rem 0;
    border-bottom: 1px solid #e2e8f0;
}

/* ---- 架构图容器 ---- */
.arch-diagram {
    background: #ffffff;
    border: 1px solid #d6e4f0;
    border-radius: 14px;
    padding: 1.5rem;
    margin: 1rem 0 1.5rem;
}

/* ---- 分割线 ---- */
hr { border-color: #d6e4f0 !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Session State
# ---------------------------------------------------------------------------
_defaults = {
    "agent_config": _SAVED_STATE.get("agent_config"),
    "system_prompt": _SAVED_STATE.get("system_prompt", ""),
    "agent_name": _SAVED_STATE.get("agent_name", ""),
    "delivery_type": "CLI",
    "calling_architect": False,
    "architect_done": _SAVED_STATE.get("architect_done", False),
    "packing": False,
    "pack_done": _SAVED_STATE.get("pack_done", False),
    "last_zip_path": _SAVED_STATE.get("last_zip_path", ""),
    "last_script_path": "",
    "history": _SAVED_STATE.get("history", []),
    "card_activated": False, "card_key": "", "card_status": "", "card_remaining": None,
    "api_key": _PERSISTED.get("api_key", ""),
    "api_base_url": _PERSISTED.get("api_base_url", ""),
    "api_model": _PERSISTED.get("api_model", ""),
    "memory_config": _PERSISTED.get("memory_config", {"max_turns": 5, "persist_strategy": "session_only"}),
    "platforms": _PERSISTED.get("platforms", ["coze", "dify", "feishu", "openclaw"]),
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
#  侧边栏 — 卡密 + 历史
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Sentence Agent Factory")
    st.caption("智能体全自动生成")
    st.markdown("---")

    card_mgr = CardManager()

    with st.expander("卡密激活", expanded=not st.session_state.card_activated):
        if st.session_state.card_activated:
            status = card_mgr.get_status(st.session_state.card_key)
            st.session_state.card_status = status.get("message", "")
            st.session_state.card_remaining = status.get("remaining")

            if status.get("activated"):
                st.success(status["message"])
                st.caption(f"卡密: `{st.session_state.card_key}`")
            else:
                st.error(status["message"])
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
    st.markdown("**出货历史**")
    if st.session_state.history:
        for record in reversed(st.session_state.history[-10:]):
            st.markdown(
                f"<div class='sidebar-history'>"
                f"<strong>{record['agent_name']}</strong><br>"
                f"<span style='font-size:0.78rem;color:#9ca3af;'>{record['time']} | {record['delivery_type']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("暂无记录")


# ---------------------------------------------------------------------------
#  主页面 — Hero + Logo
# ---------------------------------------------------------------------------
# Logo
_logo_path = Path(__file__).resolve().parent / "assets" / "image.png"
if _logo_path.exists():
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image(str(_logo_path), width=80)
    with col_title:
        st.markdown("## Sentence Agent Factory")
        st.caption("描述需求 / AI 设计 / 一键交付完整的智能体")
else:
    st.markdown("## Sentence Agent Factory")
    st.caption("描述需求 / AI 设计 / 一键交付完整的智能体")

st.markdown("")


# ---------------------------------------------------------------------------
#  三层架构图（内联 SVG + 外部图片兼容）
# ---------------------------------------------------------------------------
_arch_img = Path(__file__).resolve().parent / "assets" / "architecture.png"
if _arch_img.exists():
    st.image(str(_arch_img), use_container_width=True)
else:
    st.markdown("""
<div class="arch-diagram">
<svg viewBox="0 0 680 260" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:680px;display:block;margin:0 auto;">
  <!-- Adapter Layer (top) -->
  <rect x="20" y="10" width="640" height="75" rx="8" fill="#f0fdf4" stroke="#22c55e" stroke-width="1.5"/>
  <text x="40" y="32" font-size="11" font-weight="700" fill="#1e3a5f">Adapter Layer</text>
  <text x="40" y="50" font-size="10" fill="#475569">adapters/{platform}/ = Dify / Coze / Feishu / OpenClaw</text>

  <rect x="40" y="58" width="90" height="20" rx="4" fill="#ffffff" stroke="#86efac" stroke-width="1"/>
  <text x="60" y="72" font-size="9" fill="#16a34a" font-weight="600">Dify</text>
  <rect x="140" y="58" width="90" height="20" rx="4" fill="#ffffff" stroke="#86efac" stroke-width="1"/>
  <text x="158" y="72" font-size="9" fill="#16a34a" font-weight="600">Coze</text>
  <rect x="240" y="58" width="90" height="20" rx="4" fill="#ffffff" stroke="#86efac" stroke-width="1"/>
  <text x="255" y="72" font-size="9" fill="#16a34a" font-weight="600">Feishu</text>
  <rect x="340" y="58" width="110" height="20" rx="4" fill="#ffffff" stroke="#86efac" stroke-width="1"/>
  <text x="355" y="72" font-size="9" fill="#16a34a" font-weight="600">OpenClaw</text>

  <rect x="400" y="22" width="100" height="28" rx="6" fill="#ffffff" stroke="#86efac" stroke-width="1"/>
  <text x="415" y="41" font-size="9" fill="#16a34a" font-weight="600">packager.py</text>
  <rect x="510" y="22" width="140" height="28" rx="6" fill="#ffffff" stroke="#86efac" stroke-width="1"/>
  <text x="530" y="41" font-size="9" fill="#16a34a" font-weight="600">card_manager.py</text>

  <!-- Middle Layer -->
  <rect x="20" y="100" width="640" height="55" rx="8" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.5"/>
  <text x="40" y="122" font-size="11" font-weight="700" fill="#1e3a5f">Middle Layer</text>
  <text x="40" y="140" font-size="10" fill="#475569">agent_meta.json = Agent Spec (name / skills / workflow / memory)</text>
  <rect x="400" y="110" width="100" height="28" rx="6" fill="#ffffff" stroke="#93c5fd" stroke-width="1"/>
  <text x="425" y="129" font-size="9" fill="#2563eb" font-weight="600">builder.py</text>
  <rect x="510" y="110" width="140" height="28" rx="6" fill="#ffffff" stroke="#93c5fd" stroke-width="1"/>
  <text x="530" y="129" font-size="9" fill="#2563eb" font-weight="600">workflow_engine.py</text>

  <!-- Kernel Layer (bottom) -->
  <rect x="20" y="170" width="640" height="75" rx="8" fill="#dbeafe" stroke="#2563eb" stroke-width="1.5"/>
  <text x="40" y="192" font-size="11" font-weight="700" fill="#1e3a5f">Kernel Layer</text>
  <text x="40" y="210" font-size="10" fill="#475569">prompt_pack = system / tool / memory / output</text>
  <rect x="400" y="185" width="100" height="28" rx="6" fill="#ffffff" stroke="#93c5fd" stroke-width="1"/>
  <text x="420" y="204" font-size="9" fill="#2563eb" font-weight="600">architect.md</text>
  <rect x="510" y="185" width="140" height="28" rx="6" fill="#ffffff" stroke="#93c5fd" stroke-width="1"/>
  <text x="525" y="204" font-size="9" fill="#2563eb" font-weight="600">prompt_loader.py</text>

  <!-- Arrows -->
  <line x1="340" y1="85" x2="340" y2="100" stroke="#94a3b8" stroke-width="1.5" marker-end="url(#arrow)"/>
  <line x1="340" y1="155" x2="340" y2="170" stroke="#94a3b8" stroke-width="1.5" marker-end="url(#arrow)"/>
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/></marker></defs>
</svg>
</div>
""", unsafe_allow_html=True)

st.markdown("---")


# ---------------------------------------------------------------------------
#  步骤 1：输入需求
# ---------------------------------------------------------------------------
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.markdown("<div class='card-title'>Step 1 / 输入客户需求</div>", unsafe_allow_html=True)

requirement = st.text_area(
    "需求描述",
    value="",
    height=180,
    label_visibility="collapsed",
    placeholder="请详细描述你想做的智能体，例如：\n\n帮我做一个挑战杯比赛路演PPT润色Agent，能分析PPT结构、优化叙事逻辑、\n生成评委可能提出的问题及回答预案。\n\n描述越详细，AI 设计越精准。",
    disabled=st.session_state.calling_architect,
    key="req_input",
)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    architect_btn = st.button(
        "开始设计",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.calling_architect or st.session_state.architect_done or not requirement.strip(),
    )

if architect_btn:
    st.session_state.calling_architect = True
    st.session_state.architect_done = False
    st.session_state.pack_done = False

    with st.spinner("AI 架构师正在设计中 ..."):
        try:
            client = DeepSeekClient(
                api_key=st.session_state.api_key or os.getenv("DEEPSEEK_API_KEY"),
                base_url=st.session_state.api_base_url or os.getenv("DEEPSEEK_BASE_URL"),
                model=st.session_state.api_model or os.getenv("DEEPSEEK_MODEL_NAME", ""),
            )
            config = client.architect(requirement)
            if config and config.get("agent_name"):
                st.session_state.agent_config = config
                st.session_state.system_prompt = config.get("system_prompt", "")
                st.session_state.agent_name = config.get("agent_name", "")
                st.session_state.architect_done = True
                _save_session_state({
                    "agent_config": config,
                    "system_prompt": config.get("system_prompt", ""),
                    "agent_name": config.get("agent_name", ""),
                    "architect_done": True,
                    "pack_done": False,
                    "last_zip_path": "",
                    "history": st.session_state.history,
                })
                st.rerun()
            else:
                st.error("架构师返回空配置，请稍后重试")
        except Exception as e:
            st.error(f"调用失败: {str(e)[:200]}")
        finally:
            st.session_state.calling_architect = False

st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  步骤 2：确认 & 微调
# ---------------------------------------------------------------------------
if st.session_state.architect_done and st.session_state.agent_config:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title'>Step 2 / 确认 & 微调</div>", unsafe_allow_html=True)
    st.caption("AI 已完成设计，你可以在下方调整任何细节")

    agent_name = st.text_input("智能体名称", value=st.session_state.agent_name, key="name_input")

    st.markdown(
        "<span class='info-badge'>交付包包含: CLI 终端版 + Streamlit 网页版 + 飞书/Coze/Dify/OpenClaw 部署文件</span>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    st.markdown("**System Prompt**")
    system_prompt = st.text_area(
        "System Prompt",
        value=st.session_state.system_prompt,
        height=280,
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("**记忆配置**")
    col_m1, col_m2 = st.columns([3, 2])
    with col_m1:
        max_turns = st.slider("最大记忆轮数", 1, 20,
                              st.session_state.memory_config.get("max_turns", 5), key="mem_turns")
    with col_m2:
        persist = st.selectbox("记忆策略", ["session_only", "windowed", "persistent"],
                               index=["session_only", "windowed", "persistent"].index(
                                   st.session_state.memory_config.get("persist_strategy", "session_only")),
                               key="mem_persist")
    st.session_state.memory_config = {"max_turns": max_turns, "persist_strategy": persist}

    st.markdown("---")
    st.markdown("**部署平台**")
    plat_opts = [("coze", "Coze"), ("dify", "Dify"), ("feishu", "飞书"), ("openclaw", "OpenClaw")]
    cols_p = st.columns(len(plat_opts))
    selected = []
    for idx, (k, label) in enumerate(plat_opts):
        with cols_p[idx]:
            if st.checkbox(label, value=k in st.session_state.platforms, key=f"p_{k}"):
                selected.append(k)
    st.session_state.platforms = selected or ["coze", "dify"]

    _save_persisted_config({
        "api_key": st.session_state.api_key,
        "api_base_url": st.session_state.api_base_url,
        "api_model": st.session_state.api_model,
        "memory_config": st.session_state.memory_config,
        "platforms": st.session_state.platforms,
    })

    st.markdown("</div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    #  步骤 3：打包
    # ------------------------------------------------------------------
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title'>Step 3 / 打包 & 下载</div>", unsafe_allow_html=True)

    card_mgr = CardManager()
    card_status = card_mgr.get_status(st.session_state.card_key)
    card_ok = card_status.get("activated", False)

    if not card_ok and st.session_state.card_key:
        st.warning("卡密无效或已过期，请在左侧重新激活或留空直接使用")
        pack_disabled = st.session_state.packing or st.session_state.pack_done
    elif card_ok and card_status.get("type") == "times" and card_status.get("remaining") is not None:
        st.info(f"当前次卡剩余 {card_status['remaining']} 次，每次打包扣减 1 次")
        pack_disabled = st.session_state.packing or st.session_state.pack_done
    else:
        pack_disabled = st.session_state.packing or st.session_state.pack_done

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pack_btn = st.button("一键打包", type="primary", use_container_width=True, disabled=pack_disabled)

    if pack_btn:
        st.session_state.packing = True
        try:
            config = dict(st.session_state.agent_config)
            config["agent_name"] = agent_name
            config["system_prompt"] = system_prompt

            with st.spinner("装配引擎工作中 ..."):
                builder = AgentBuilder(config=config, delivery_type="zip",
                    api_key=st.session_state.api_key, base_url=st.session_state.api_base_url,
                    model_name=st.session_state.api_model)
                script_path = builder.assemble()

            with st.spinner("打包器工作中 ..."):
                packager = AgentPackager(script_path=str(script_path), delivery_type="zip",
                    agent_name=agent_name,
                    agent_scenario=config.get("required_skills", ["通用任务"])[0] if config.get("required_skills") else requirement[:40])
                result = packager.package()

            if result.success:
                st.session_state.last_zip_path = result.output_path
                st.session_state.pack_done = True
                if st.session_state.card_key:
                    card_mgr.consume_quota(st.session_state.card_key)
                _save_session_state({
                    "agent_config": st.session_state.agent_config,
                    "system_prompt": st.session_state.system_prompt,
                    "agent_name": st.session_state.agent_name,
                    "architect_done": True,
                    "pack_done": True,
                    "last_zip_path": result.output_path,
                    "history": st.session_state.history,
                })
                st.rerun()
            else:
                st.error(f"打包失败: {result.message}")
        except Exception as e:
            st.error(f"异常: {str(e)[:200]}")
        finally:
            st.session_state.packing = False

    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  完成：下载 & 预览
# ---------------------------------------------------------------------------
if st.session_state.pack_done and st.session_state.last_zip_path:
    zip_path = Path(st.session_state.last_zip_path)
    if zip_path.exists():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='card-title'>交付完成</div>", unsafe_allow_html=True)

        import zipfile
        with zipfile.ZipFile(zip_path, "r") as zf:
            files = zf.namelist()

        with open(zip_path, "rb") as f:
            st.download_button("下载交付包", data=f.read(), file_name=zip_path.name,
                               mime="application/zip", use_container_width=True)

        st.caption(f"{zip_path.name} / {zip_path.stat().st_size / 1024:.1f} KB / {len(files)} 个文件")

        with st.expander("查看交付包内容", expanded=False):
            for f in files:
                st.text(f)

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("再做一个", use_container_width=True):
                for k in ("agent_config", "system_prompt", "agent_name", "architect_done", "pack_done", "last_zip_path"):
                    st.session_state[k] = _defaults[k]
                _save_session_state({})
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption("Sentence Agent Factory / Powered by AI")
