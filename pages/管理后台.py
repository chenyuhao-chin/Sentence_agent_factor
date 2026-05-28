"""
Agent Factory — 管理后台（卡密管理）
====================================
独立页面，密码保护，仅卖家使用。
客户看不到这个页面的入口。

访问方式：侧边栏底部 → 「管理后台」
默认密码：admin888（请修改下方 ADMIN_PASSWORD 变量）
"""

import random
import string
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.card_manager import CardManager

# ═══════════════════════════════════════════
#  管理密码（请修改为你自己的密码）
# ═══════════════════════════════════════════
ADMIN_PASSWORD = "admin888"

st.set_page_config(
    page_title="管理后台 — Agent Factory",
    page_icon="🔐",
    layout="centered",
)

# ---------------------------------------------------------------------------
#  密码校验
# ---------------------------------------------------------------------------
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

if not st.session_state.admin_authenticated:
    st.markdown("## 🔐 管理后台")
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
#  已登录：卡密管理面板
# ---------------------------------------------------------------------------
st.markdown("## 🔧 卡密管理")
st.caption("生成和管理闲鱼卡密，客户无法访问此页面")

tab_gen, tab_list, tab_stats = st.tabs(["🎲 生成卡密", "📋 卡密列表", "📊 统计"])

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

    if st.button("🎲 生成卡密", type="primary", use_container_width=True):
        card_mgr = CardManager()
        generated = []
        for _ in range(gen_count):
            suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
            type_tag = "SEASON" if gen_type == "monthly" else f"{gen_quota}TIMES"
            key = f"{gen_prefix}-{type_tag}-{suffix}"
            if card_mgr.generate_card(key, gen_type, quota=gen_quota):
                generated.append(key)
        if generated:
            st.success(f"✅ 已生成 {len(generated)} 张卡密")
            st.code("\n".join(generated), language=None)
            st.caption("👆 复制以上卡密，通过闲鱼发货给买家")

# --- 卡密列表 ---
with tab_list:
    st.markdown("### 所有卡密")
    card_mgr = CardManager()
    all_cards = card_mgr.list_cards()

    if not all_cards:
        st.info("暂无卡密，请先在「生成卡密」标签页生成")
    else:
        # 过滤
        filter_status = st.selectbox("筛选状态", ["全部", "active", "expired", "depleted"], key="filter_status")
        for k, v in all_cards.items():
            if filter_status != "全部" and v.get("status") != filter_status:
                continue
            ctype = "月卡" if v.get("type") == "monthly" else "次卡"
            cstatus = v.get("status", "")
            if v.get("type") == "monthly":
                expire = v.get("expire_time", "未激活")
                detail = f"到期: {expire}"
            else:
                detail = f"剩余: {v.get('remaining_quota', '?')}次"
            icon = "🟢" if cstatus == "active" else "🔴"
            activated = v.get("activated_at", "未激活")
            st.markdown(f"{icon} **`{k}`** — {ctype} · {detail} · 状态: `{cstatus}` · 激活时间: {activated}")

# --- 统计 ---
with tab_stats:
    st.markdown("### 卡密统计")
    card_mgr = CardManager()
    all_cards = card_mgr.list_cards()

    if not all_cards:
        st.info("暂无数据")
    else:
        total = len(all_cards)
        active = sum(1 for v in all_cards.values() if v.get("status") == "active")
        expired = sum(1 for v in all_cards.values() if v.get("status") == "expired")
        depleted = sum(1 for v in all_cards.values() if v.get("status") == "depleted")
        monthly = sum(1 for v in all_cards.values() if v.get("type") == "monthly")
        times = sum(1 for v in all_cards.values() if v.get("type") == "times")

        col1, col2, col3 = st.columns(3)
        col1.metric("总卡密数", total)
        col2.metric("有效", active)
        col3.metric("已失效", expired + depleted)

        col4, col5 = st.columns(2)
        col4.metric("月卡", monthly)
        col5.metric("次卡", times)
