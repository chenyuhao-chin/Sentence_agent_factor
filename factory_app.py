"""
Agent Factory — 内部专属控制台（Streamlit）
============================================
老板用的私人工作台：输入需求 → 微调提示词 → 一键打包出货。

使用方式：
    streamlit run factory_app.py
"""

import json
import os
import sys
from pathlib import Path

import streamlit as st

# 将项目根目录加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
#  配置持久化（本地 JSON 文件，刷新不丢）
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).resolve().parent / ".factory_config.json"


def _load_persisted_config() -> dict:
    """从本地文件加载持久化配置"""
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_persisted_config(cfg: dict):
    """保存配置到本地文件"""
    try:
        _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_PERSISTED = _load_persisted_config()

from core.llm_client import DeepSeekClient
from core.builder import AgentBuilder
from core.packager import AgentPackager
from core.card_manager import CardManager

# ---------------------------------------------------------------------------
# 页面配置 —— 极致简约、高级感
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Agent Factory 内部控制台",
    page_icon="🏭",
    layout="centered",
    initial_sidebar_state="expanded",
)

# 全局 CSS —— 学术蓝 + 白色主题
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
    /* 全局 */
    .main > div { padding: 2rem 0.5rem; }
    .stApp { background: #f0f4f8; }
    h1, h2, h3 { font-weight: 700; color: #1e3a5f; }
    /* 卡片模块 */
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
    /* 文本框 */
    .stTextArea textarea {
        font-size: 0.95rem; line-height: 1.6; min-height: 260px;
        border: 1px solid #d6e4f0 !important;
        border-radius: 10px !important;
    }
    .stTextArea textarea:focus {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
    }
    /* 输入框 */
    .stTextInput input {
        border: 1px solid #d6e4f0 !important;
        border-radius: 10px !important;
    }
    .stTextInput input:focus {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
    }
    /* 按钮 */
    .stButton button {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 0.55rem 1.8rem !important;
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
        padding: 0.6rem 2rem !important;
    }
    /* 状态提示 */
    .success-badge {
        background: #dbeafe; color: #1e40af;
        padding: 0.3rem 0.8rem; border-radius: 8px;
        font-size: 0.85rem; display: inline-block;
        font-weight: 500;
    }
    .info-badge {
        background: #dbeafe; color: #1e40af;
        padding: 0.3rem 0.8rem; border-radius: 8px;
        font-size: 0.85rem; display: inline-block;
        font-weight: 500;
    }
    /* 侧边栏 */
    section[data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #d6e4f0;
    }
    .sidebar-history {
        font-size: 0.85rem; color: #475569;
        padding: 0.5rem 0;
        border-bottom: 1px solid #e2e8f0;
    }
    /* 分割线 */
    hr { border-color: #d6e4f0 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session State 初始化
# ---------------------------------------------------------------------------
if "agent_config" not in st.session_state:
    st.session_state.agent_config = None
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = ""
if "agent_name" not in st.session_state:
    st.session_state.agent_name = ""
if "delivery_type" not in st.session_state:
    st.session_state.delivery_type = "CLI 命令行版"
if "history" not in st.session_state:
    st.session_state.history = []
if "last_zip_path" not in st.session_state:
    st.session_state.last_zip_path = ""
if "last_script_path" not in st.session_state:
    st.session_state.last_script_path = ""
if "calling_architect" not in st.session_state:
    st.session_state.calling_architect = False
if "architect_done" not in st.session_state:
    st.session_state.architect_done = False
if "packing" not in st.session_state:
    st.session_state.packing = False
if "pack_done" not in st.session_state:
    st.session_state.pack_done = False
if "api_key" not in st.session_state:
    st.session_state.api_key = _PERSISTED.get("api_key", "")
if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = _PERSISTED.get("api_base_url", "")
if "api_model" not in st.session_state:
    st.session_state.api_model = _PERSISTED.get("api_model", "deepseek-chat")
if "memory_config" not in st.session_state:
    st.session_state.memory_config = _PERSISTED.get("memory_config", {"max_turns": 5, "persist_strategy": "session_only"})
if "platforms" not in st.session_state:
    st.session_state.platforms = _PERSISTED.get("platforms", ["coze", "dify", "feishu", "openclaw"])
if "card_activated" not in st.session_state:
    st.session_state.card_activated = False
if "card_key" not in st.session_state:
    st.session_state.card_key = ""
if "card_status" not in st.session_state:
    st.session_state.card_status = ""
if "card_remaining" not in st.session_state:
    st.session_state.card_remaining = None

# ---------------------------------------------------------------------------
# 侧边栏 — 卡密激活 + 出货历史
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<h3 style='font-weight:600; margin-bottom:1rem;'>🏭 Agent Factory</h3>", unsafe_allow_html=True)
    st.caption("智能体全自动生成工厂")

    st.markdown("---")

    # ---------- 卡密激活区 ----------
    with st.expander("🎫 卡密激活", expanded=not st.session_state.card_activated):
        card_mgr = CardManager()

        if st.session_state.card_activated:
            # 已激活：显示状态
            status = card_mgr.get_status(st.session_state.card_key)
            st.session_state.card_status = status.get("message", "")
            st.session_state.card_remaining = status.get("remaining")

            if status.get("activated"):
                st.success(f"✅ {status['message']}")
                st.caption(f"卡密: `{st.session_state.card_key}`")
            else:
                st.error(f"❌ {status['message']}")
                st.session_state.card_activated = False
                st.session_state.card_key = ""
                st.session_state.card_status = ""
                st.session_state.card_remaining = None

            if st.button("🔄 切换卡密", use_container_width=True):
                st.session_state.card_activated = False
                st.session_state.card_key = ""
                st.session_state.card_status = ""
                st.session_state.card_remaining = None
                st.rerun()
        else:
            # 未激活：输入卡密
            card_input = st.text_input(
                "输入卡密",
                placeholder="FX-SEASON-8899 或 FX-10TIMES-1122",
                key="sidebar_card_input",
            )
            if st.button("🔓 激活卡密", type="primary", use_container_width=True):
                if not card_input.strip():
                    st.warning("请输入卡密")
                else:
                    ok, msg = card_mgr.verify_and_activate_card(card_input)
                    if ok:
                        st.session_state.card_activated = True
                        st.session_state.card_key = card_input.strip().upper()
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

    st.markdown("---")

    st.markdown("<div class='card-title'>📋 出货历史</div>", unsafe_allow_html=True)

    if st.session_state.history:
        for i, record in enumerate(reversed(st.session_state.history[-10:])):
            st.markdown(
                f"<div class='sidebar-history'>"
                f"  <strong>{record['agent_name']}</strong><br>"
                f"  <span style='font-size:0.78rem;color:#9ca3af;'>{record['time']} ｜ {record['delivery_type']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("还没有出货记录。完成一次装配打包后，记录会自动出现在这里。")

    st.markdown("---")
    st.caption("提示：控制台仅供内部使用，切勿对外展示。")

# ---------------------------------------------------------------------------
# 主页面
# ---------------------------------------------------------------------------
st.title("🏭 Agent Factory — 内部专属控制台")
st.markdown(
    "<p style='color:#6b7280; margin-top:-0.5rem; margin-bottom:2rem;'>"
    "输入客户需求 → 微调提示词 → 一键打包出货</p>",
    unsafe_allow_html=True,
)

# ===================================================================
# 步骤 1：召唤架构师
# ===================================================================
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.markdown("<div class='card-title'>📝 步骤 1 · 输入客户需求</div>", unsafe_allow_html=True)

col1, col2 = st.columns([4, 1])
with col1:
    requirement = st.text_input(
        "需求描述",
        value="帮我做一个挑战杯比赛路演PPT润色Agent",
        label_visibility="collapsed",
        placeholder="例：帮我做一个 C++ 代码审查 Agent",
        disabled=st.session_state.calling_architect,
    )
with col2:
    architect_btn = st.button(
        "🎯 召唤架构师",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.calling_architect or st.session_state.architect_done,
    )

if architect_btn:
    if not requirement.strip():
        st.warning("请先输入客户需求")
    else:
        st.session_state.calling_architect = True
        st.session_state.architect_done = False
        st.session_state.pack_done = False
        st.session_state.last_zip_path = ""
        st.session_state.last_script_path = ""

        with st.spinner("🧠 架构师正在思考中..."):
            try:
                client = DeepSeekClient(
                    api_key=st.session_state.get("api_key") or os.getenv("DEEPSEEK_API_KEY"),
                    base_url=st.session_state.get("api_base_url") or os.getenv("DEEPSEEK_BASE_URL"),
                    model=st.session_state.get("api_model") or "deepseek-chat",
                )
                config = client.architect(requirement)

                if config and config.get("agent_name"):
                    st.session_state.agent_config = config
                    st.session_state.system_prompt = config.get("system_prompt", "")
                    st.session_state.agent_name = config.get("agent_name", "未命名智能体")
                    st.session_state.architect_done = True
                    st.success(f"✅ 架构师已出图 — {config.get('agent_name')}")
                else:
                    st.error("架构师返回空配置，请稍后重试")
            except Exception as e:
                st.error(f"架构师调用异常：{str(e)[:200]}")
            finally:
                st.session_state.calling_architect = False

st.markdown("</div>", unsafe_allow_html=True)

# ===================================================================
# 步骤 2：微调拦截区
# ===================================================================
if st.session_state.architect_done and st.session_state.agent_config:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title'>✏️ 步骤 2 · 微调拦截区</div>", unsafe_allow_html=True)

    st.caption("架构师已出图，你可以在下面自由修改任何内容。改完确认后进入步骤 3。")

    # Agent 名称
    agent_name = st.text_input(
        "Agent 名称",
        value=st.session_state.agent_name,
        key="name_input",
    )

    # 交付模式：三种全提供
    st.markdown(
        "<span class='info-badge'>📦 交付包包含：终端版 (CLI) + Streamlit 网页版 (Web) + 飞书/Coze/Dify 部署文件</span>",
        unsafe_allow_html=True,
    )

    # 超大文本框：System Prompt 微调
    st.markdown("**System Prompt**（双击修改，可随意注入你的调教技法）")
    system_prompt = st.text_area(
        "system_prompt",
        value=st.session_state.system_prompt,
        height=320,
        label_visibility="collapsed",
        placeholder="架构师正在生成提示词...",
    )

    # --- 记忆配置 ---
    st.markdown("---")
    st.markdown("**🧠 记忆配置**（对话上下文长度）")
    col_mem1, col_mem2 = st.columns([3, 2])
    with col_mem1:
        max_turns = st.slider(
            "最大记忆轮数",
            min_value=1,
            max_value=20,
            value=st.session_state.memory_config.get("max_turns", 5),
            step=1,
            help="Agent 能记住前 N 轮对话。数值越大记忆越久，但 Token 消耗也越高。",
            key="memory_max_turns",
        )
    with col_mem2:
        persist_strategy = st.selectbox(
            "记忆策略",
            options=["session_only", "windowed", "persistent"],
            index=["session_only", "windowed", "persistent"].index(
                st.session_state.memory_config.get("persist_strategy", "session_only")
            ),
            help="session_only: 会话结束即清空 | windowed: 滑动窗口保留最近 N 轮 | persistent: 持久化到本地文件",
            key="memory_persist_strategy",
        )
    st.session_state.memory_config = {
        "max_turns": max_turns,
        "persist_strategy": persist_strategy,
    }

    # --- 多平台选择器 ---
    st.markdown("---")
    st.markdown("**🌐 目标平台**（勾选需要部署的平台，对应适配器文件将注入 ZIP）")
    platform_options = [
        ("coze", "Coze"),
        ("dify", "Dify"),
        ("feishu", "飞书"),
        ("openclaw", "OpenClaw"),
    ]
    cols_plat = st.columns(len(platform_options))
    selected_platforms = []
    for idx, (key, label) in enumerate(platform_options):
        with cols_plat[idx]:
            if st.checkbox(
                label,
                value=key in st.session_state.platforms,
                key=f"platform_{key}",
            ):
                selected_platforms.append(key)
    st.session_state.platforms = selected_platforms or ["coze", "dify"]

    # 持久化 memory_config 和 platforms
    _save_persisted_config({
        "api_key": st.session_state.api_key,
        "api_base_url": st.session_state.api_base_url,
        "api_model": st.session_state.api_model,
        "memory_config": st.session_state.memory_config,
        "platforms": st.session_state.platforms,
    })

    st.markdown("</div>", unsafe_allow_html=True)

    # ===================================================================
    # 步骤 3：一键装配打包出货
    # ===================================================================
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title'>📦 步骤 3 · 一键装配打包出货</div>", unsafe_allow_html=True)

    # 卡密前置校验
    card_mgr = CardManager()
    card_status = card_mgr.get_status(st.session_state.card_key)
    card_ok = card_status.get("activated", False)
    card_msg = card_status.get("message", "未激活")

    if not card_ok:
        st.warning(f"🎫 请先在左侧侧边栏激活卡密后再使用。当前状态：{card_msg}")
        pack_disabled = True
    elif card_status.get("type") == "times" and card_status.get("remaining") is not None:
        st.info(f"🎫 当前次卡剩余 {card_status['remaining']} 次，每次打包扣减 1 次")
        pack_disabled = st.session_state.packing or st.session_state.pack_done
    else:
        pack_disabled = st.session_state.packing or st.session_state.pack_done

    # 交付模式固定为 zip（内含 CLI + Web + 平台部署文件）
    delivery_type = "zip"

    pack_btn = st.button(
        "⚡ 一键装配打包出货",
        type="primary",
        use_container_width=True,
        disabled=pack_disabled,
    )

    if pack_btn:
        st.session_state.packing = True
        st.session_state.pack_done = False

        try:
            # 构建更新后的配置
            config = dict(st.session_state.agent_config)
            config["agent_name"] = agent_name
            config["system_prompt"] = system_prompt
            config["delivery_type"] = delivery_type

            # 1. 装配
            with st.spinner("🔧 装配引擎工作中..."):
                builder = AgentBuilder(
                    config=config,
                    delivery_type=delivery_type,
                    api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-your-api-key-here"),
                    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                    model_name=os.environ.get("DEEPSEEK_MODEL_NAME", "deepseek-chat"),
                )
                script_path = builder.assemble()
                st.session_state.last_script_path = str(script_path)
                st.success(f"✅ 智能体脚本已生成 → `{script_path.name}`")

            # 2. 打包
            with st.spinner("📦 打包器工作中..."):
                packager = AgentPackager(
                    script_path=str(script_path),
                    delivery_type="zip",
                    agent_name=agent_name,
                    agent_scenario=config.get("required_skills", ["通用任务"])[0] if config.get("required_skills") else requirement[:40],
                )
                result = packager.package()

                if result.success:
                    st.session_state.last_zip_path = result.output_path
                    st.session_state.pack_done = True

                    # 记录历史
                    from datetime import datetime as dt
                    st.session_state.history.append({
                        "agent_name": agent_name,
                        "delivery_type": "ZIP (CLI+Web+Platforms)",
                        "time": dt.now().strftime("%H:%M"),
                        "zip_path": result.output_path,
                    })

                    st.balloons()
                    st.success(f"✅ **打包完成！** 交付包已生成")
                    st.caption(result.message)

                    # 次卡扣减额度
                    consume_ok, consume_msg = card_mgr.consume_quota(st.session_state.card_key)
                    if consume_ok:
                        st.caption(f"🎫 {consume_msg}")
                    elif card_status.get("type") == "times":
                        st.warning(f"🎫 {consume_msg}")

                    # 显示下载按钮
                    zip_path = Path(result.output_path)
                    if zip_path.exists():
                        with open(zip_path, "rb") as f:
                            st.download_button(
                                label="⬇️ 下载 ZIP 交付包",
                                data=f.read(),
                                file_name=zip_path.name,
                                mime="application/zip",
                                use_container_width=True,
                            )

                        st.info(
                            f"📍 交付包位置：`{result.output_path}`  \n"
                            f"📎 文件大小：{zip_path.stat().st_size / 1024:.1f} KB  \n"
                            f"💡 你可以直接把这个 ZIP 发给买家了",
                        )
                else:
                    st.error(f"打包失败：{result.message}")

        except Exception as e:
            st.error(f"装配/打包异常：{str(e)[:300]}")
        finally:
            st.session_state.packing = False

    st.markdown("</div>", unsafe_allow_html=True)

    # ===================================================================
    # 打包完成后显示详细信息
    # ===================================================================
    if st.session_state.pack_done and st.session_state.last_zip_path:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='card-title'>✅ 出货确认</div>", unsafe_allow_html=True)

        zip_path = Path(st.session_state.last_zip_path)
        if zip_path.exists():
            # ZIP 内容预览
            import zipfile
            with zipfile.ZipFile(zip_path, "r") as zf:
                files_in_zip = zf.namelist()

            st.markdown("**ZIP 包内容清单：**")
            for f in files_in_zip:
                icon = "📄" if f.endswith(".py") else "📖" if "说明书" in f else "📦" if f.endswith(".txt") else "📃"
                st.markdown(f"{icon} `{f}`")

            st.caption(f"共 {len(files_in_zip)} 个文件 · {zip_path.stat().st_size / 1024:.1f} KB")

            # 平台部署文件预览
            st.markdown("---")
            st.markdown("**🚀 平台部署文件预览**")
            st.caption("以下配置文件已注入智能体灵魂，均可在 ZIP 中找到。按平台展开查看详情：")

            try:
                from core.builder import AgentBuilder
                config = dict(st.session_state.agent_config)
                config["agent_name"] = agent_name
                config["system_prompt"] = system_prompt
                builder = AgentBuilder(config=config, delivery_type="zip")
                platform_files = builder.build_platform_files()

                for arcname, content in platform_files.items():
                    with st.expander(f"{arcname}", expanded=False):
                        ext = arcname.rsplit(".", 1)[-1] if "." in arcname else ""
                        lang = "yaml" if ext in ("yml", "yaml") else "json" if ext == "json" else ""
                        st.code(content, language=lang)

                st.caption(f"✅ 平台部署文件已全部注入 ZIP 包（{len(platform_files)} 个）")
            except Exception as e:
                st.warning(f"平台文件预览生成失败（不影响 ZIP 交付）：{e}")

            # 重置按钮
            if st.button("🔄 重新开始", use_container_width=True):
                st.session_state.agent_config = None
                st.session_state.system_prompt = ""
                st.session_state.agent_name = ""
                st.session_state.architect_done = False
                st.session_state.pack_done = False
                st.session_state.last_zip_path = ""
                st.session_state.last_script_path = ""
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# ===================================================================
# 初始状态 — 没有调过架构师
# ===================================================================
if not st.session_state.architect_done:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#9ca3af; text-align:center; padding:2rem 0;'>"
        "👆 输入客户需求，点击「召唤架构师」开始生产</p>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption("Agent Factory 🏭 内部专属 · 切勿对外展示")
