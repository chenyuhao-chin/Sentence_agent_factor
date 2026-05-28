"""
Agent Factory — 管理后台（卡密管理 + API 配置）
================================================
独立页面，密码保护，仅卖家使用。
客户看不到这个页面的入口。

访问方式：侧边栏底部 → 「管理后台」
默认密码：admin888（请修改下方 ADMIN_PASSWORD 变量）
"""

import random
import string
import sys
import json
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.card_manager import CardManager

# 配置持久化路径（与 factory_app.py 共享）
_CONFIG_PATH = Path(__file__).resolve().parent.parent / ".factory_config.json"


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_config(cfg: dict):
    try:
        _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ═══════════════════════════════════════════
#  管理密码（请修改为你自己的密码）
# ═══════════════════════════════════════════
ADMIN_PASSWORD = "admin888"

st.set_page_config(
    page_title="管理后台 — Agent Factory",
    page_icon="A",
    layout="centered",
)

# ---------------------------------------------------------------------------
#  密码校验
# ---------------------------------------------------------------------------
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

if not st.session_state.admin_authenticated:
    st.markdown("## 管理后台")
    st.caption("此页面仅限管理员使用，请输入密码")
    pwd = st.text_input("管理密码", type="password", key="admin_pwd_input")
    if st.button("登录", type="primary"):
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("密码错误")
    st.stop()

# ---------------------------------------------------------------------------
#  已登录：管理面板
# ---------------------------------------------------------------------------
st.markdown("## 管理后台")
st.caption("卡密管理 + API 配置")

tab_api, tab_gen, tab_list, tab_stats, tab_logs = st.tabs(
    ["API 配置", "生成卡密", "卡密列表", "统计", "操作日志"]
)

# --- API 配置 ---
with tab_api:
    st.markdown("### API 配置")
    st.caption("配置大模型 API Key，用于召唤架构师生成智能体。支持 DeepSeek、小米 MiMo 等 OpenAI 兼容接口。")

    cfg = _load_config()

    api_key = st.text_input(
        "API Key",
        value=cfg.get("api_key", ""),
        type="password",
        placeholder="tp-xxxxxxxx 或 sk-xxxxxxxx",
        key="admin_api_key",
    )
    base_url = st.text_input(
        "Base URL",
        value=cfg.get("api_base_url", "https://token-plan-cn.xiaomimimo.com/v1"),
        placeholder="https://token-plan-cn.xiaomimimo.com/v1",
        key="admin_base_url",
    )
    model = st.text_input(
        "Model",
        value=cfg.get("api_model", "mimo-v2.5-pro"),
        placeholder="mimo-v2.5-pro",
        key="admin_model",
    )

    st.markdown("---")
    st.markdown("**常用模型配置参考：**")
    st.code(
        "小米 MiMo:  URL=https://token-plan-cn.xiaomimimo.com/v1  Model=mimo-v2.5-pro\n"
        "DeepSeek:   URL=https://api.deepseek.com/v1              Model=deepseek-chat\n"
        "通义千问:    URL=https://dashscope.aliyuncs.com/compatible-mode/v1  Model=qwen-plus\n"
        "智谱 GLM:   URL=https://open.bigmodel.cn/api/paas/v4     Model=glm-4-flash",
        language=None,
    )

    if st.button("保存 API 配置", type="primary", use_container_width=True):
        cfg["api_key"] = api_key
        cfg["api_base_url"] = base_url
        cfg["api_model"] = model
        _save_config(cfg)
        st.success("API 配置已保存，刷新主页后生效")

    if api_key:
        st.success("Key 已配置")
    else:
        st.warning("未填写 Key，主页的「开始设计」将无法使用")

# --- 生成卡密 ---
with tab_gen:
    st.markdown("### 批量生成卡密")
    col1, col2 = st.columns(2)
    with col1:
        gen_type = st.selectbox(
            "卡密类型",
            options=["monthly", "times"],
            format_func=lambda x: "月卡（30天无限用）" if x == "monthly" else "次卡（按次扣减）",
            key="gen_type",
        )
        gen_prefix = st.text_input("卡密前缀", value="FX", key="gen_prefix")
    with col2:
        gen_count = st.number_input("生成数量", min_value=1, max_value=100, value=5, key="gen_count")
        gen_quota = 10
        if gen_type == "times":
            gen_quota = st.number_input("每次卡次数", min_value=1, max_value=100, value=10, key="gen_quota")

    if st.button("生成卡密", type="primary", use_container_width=True):
        card_mgr = CardManager()
        generated = []
        for _ in range(gen_count):
            suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
            type_tag = "SEASON" if gen_type == "monthly" else f"{gen_quota}TIMES"
            key = f"{gen_prefix}-{type_tag}-{suffix}"
            if card_mgr.generate_card(key, gen_type, quota=gen_quota):
                generated.append(key)
        if generated:
            st.success(f"已生成 {len(generated)} 张卡密")
            st.code("\n".join(generated), language=None)
            st.caption("复制以上卡密，通过闲鱼发货给买家")

# --- 卡密列表 ---
with tab_list:
    st.markdown("### 所有卡密")
    card_mgr = CardManager()
    all_cards = card_mgr.list_cards()

    if not all_cards:
        st.info("暂无卡密，请先在「生成卡密」标签页生成")
    else:
        filter_status = st.selectbox("筛选状态", ["全部", "active", "expired", "depleted"], key="filter_status")
        search_key = st.text_input("搜索卡密", placeholder="输入卡密关键词", key="search_card")

        filtered = {}
        for k, v in all_cards.items():
            if filter_status != "全部" and v.get("status") != filter_status:
                continue
            if search_key and search_key.upper() not in k:
                continue
            filtered[k] = v

        st.caption(f"共 {len(filtered)} 张卡密")
        for k, v in filtered.items():
            ctype = "月卡" if v.get("type") == "monthly" else "次卡"
            cstatus = v.get("status", "")
            if v.get("type") == "monthly":
                expire = v.get("expire_time", "未激活")
                detail = f"到期: {expire}"
            else:
                detail = f"剩余: {v.get('remaining_quota', '?')}次"
            icon = "[OK]" if cstatus == "active" else "[X]"
            activated = v.get("activated_at", "未激活")
            created = v.get("created_at", "")
            st.markdown(
                f"{icon} **`{k}`** — {ctype} | {detail} | 状态: `{cstatus}` | "
                f"激活: {activated} | 创建: {created}"
            )

# --- 统计 ---
with tab_stats:
    st.markdown("### 卡密统计")
    card_mgr = CardManager()
    stats = card_mgr.get_stats()

    if stats["total"] == 0:
        st.info("暂无数据")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("总卡密数", stats["total"])
        col2.metric("有效", stats["active"])
        col3.metric("已过期", stats["expired"])
        col4.metric("已耗尽", stats["depleted"])

        col5, col6, col7 = st.columns(3)
        col5.metric("月卡", stats["monthly"])
        col6.metric("次卡", stats["times"])
        col7.metric("总消费次数", stats["total_consumed"])

# --- 操作日志 ---
with tab_logs:
    st.markdown("### 操作日志")
    card_mgr = CardManager()
    logs = card_mgr.get_card_logs(limit=100)

    if not logs:
        st.info("暂无操作日志")
    else:
        for log in logs:
            st.text(
                f"[{log['created_at']}] {log['action']} | {log['card_key']} | {log['detail']}"
            )
