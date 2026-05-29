#!/usr/bin/env python3
"""
Agent Factory — Streamlit Web 智能体模板（带持久记忆 + 自动进化）
================================================================
V3.0 架构特征：
  1. 内置持久记忆引擎 — 跨会话记忆用户偏好和知识
  2. 自动进化：定期分析对话并积累新知识
  3. 记忆检索：每次对话前自动注入相关历史
  4. 极致简约 UI

运行方式：
    streamlit run app.py
"""

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import subprocess
import sys

_MISSING = []
try:
    from openai import OpenAI
except ImportError:
    _MISSING.append("openai")
try:
    import streamlit as st
except ImportError:
    _MISSING.append("streamlit")
try:
    from dotenv import load_dotenv
except ImportError:
    _MISSING.append("python-dotenv")

if _MISSING:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", *_MISSING,
         "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", "--break-system-packages"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

from openai import OpenAI
import streamlit as st
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
#  运行时默认配置
# ---------------------------------------------------------------------------
DEFAULT_API_KEY = "{API_KEY_SLOT}"
DEFAULT_BASE_URL = "{BASE_URL_SLOT}"
DEFAULT_MODEL_NAME = "{MODEL_NAME_SLOT}"
AGENT_NAME = "{AGENT_NAME}"
AGENT_SYSTEM_PROMPT = """{SYSTEM_PROMPT}"""
TOOL_CONFIG = {TOOL_CONFIG_SLOT}


# ---------------------------------------------------------------------------
#  Memory Engine（内联版）
# ---------------------------------------------------------------------------
class MemoryEngine:
    def __init__(self, agent_name, db_path, max_context=5, evolve_interval=10):
        self.agent_name = agent_name
        self.db_path = db_path
        self.max_context = max_context
        self.evolve_interval = evolve_interval
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        c = self._conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL DEFAULT 'general',
                key TEXT NOT NULL, value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5, hit_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evolution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                changes_summary TEXT, created_at TEXT NOT NULL);
        """)
        c.commit(); c.close()

    def record(self, user_input, reply):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c = self._conn()
        c.execute("INSERT INTO conversations (role,content,created_at) VALUES (?,?,?)", ("user", user_input, now))
        c.execute("INSERT INTO conversations (role,content,created_at) VALUES (?,?,?)", ("assistant", reply, now))
        c.commit(); c.close()

    def add_memory(self, category, key, value, confidence=0.5):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c = self._conn()
        ex = c.execute("SELECT id,confidence FROM memories WHERE category=? AND key=?", (category, key)).fetchone()
        if ex:
            c.execute("UPDATE memories SET value=?,confidence=?,hit_count=hit_count+1,updated_at=? WHERE id=?",
                      (value, min(1.0, ex["confidence"]+0.1), now, ex["id"]))
        else:
            c.execute("INSERT INTO memories (category,key,value,confidence,hit_count,created_at,updated_at) VALUES (?,?,?,?,0,?,?)",
                      (category, key, value, confidence, now, now))
        c.commit(); c.close()

    def search(self, query, limit=5):
        kws = [w for w in query.split() if len(w) > 1]
        if not kws: return []
        c = self._conn()
        cond = " OR ".join(["key LIKE ? OR value LIKE ?"] * len(kws))
        params = []
        for kw in kws: params.extend([f"%{kw}%", f"%{kw}%"])
        rows = c.execute(f"SELECT category,key,value,confidence FROM memories WHERE {cond} ORDER BY confidence DESC LIMIT ?",
                         params + [limit]).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def get_context(self, user_input):
        parts = []
        mems = self.search(user_input, self.max_context)
        if mems:
            lines = [f"- [{m['category']}] {m['key']}: {m['value']}" for m in mems]
            parts.append("【已积累的知识】\n" + "\n".join(lines))
        c = self._conn()
        recent = c.execute("SELECT role,content FROM conversations ORDER BY id DESC LIMIT 6").fetchall()
        c.close()
        if recent:
            hist = []
            for r in reversed(recent):
                role = "用户" if r["role"] == "user" else "助手"
                content = r["content"][:100] + "..." if len(r["content"]) > 100 else r["content"]
                hist.append(f"{role}: {content}")
            parts.append("【最近对话】\n" + "\n".join(hist))
        return "\n\n".join(parts)

    def should_evolve(self):
        c = self._conn()
        count = c.execute("SELECT COUNT(*) FROM conversations WHERE role='user'").fetchone()[0]
        c.close()
        return count > 0 and count % self.evolve_interval == 0

    def evolve(self, client, model):
        c = self._conn()
        recent = c.execute("SELECT role,content FROM conversations ORDER BY id DESC LIMIT 20").fetchall()
        c.close()
        if len(recent) < 4: return None
        conv = "\n".join(f"{'用户' if r['role']=='user' else '助手'}: {r['content'][:200]}" for r in recent)
        prompt = f"分析对话提取新知识，JSON格式输出：\n{{\"facts\":[{{\"key\":\"\",\"value\":\"\",\"confidence\":0.7}}],\"preferences\":[{{\"key\":\"\",\"value\":\"\",\"confidence\":0.7}}],\"summary\":\"\"}}\n\n对话：\n{conv}"
        try:
            resp = client.chat.completions.create(model=model, messages=[
                {"role":"system","content":"只输出JSON"}, {"role":"user","content":prompt}
            ], temperature=0.1, max_tokens=1024)
            raw = resp.choices[0].message.content or ""
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if not m: return None
            data = json.loads(m.group(0))
            for f in data.get("facts", []):
                self.add_memory("知识", f["key"], f["value"], f.get("confidence", 0.5))
            for p in data.get("preferences", []):
                self.add_memory("偏好", p["key"], p["value"], p.get("confidence", 0.5))
            summary = data.get("summary", "记忆已更新")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cc = self._conn()
            cc.execute("INSERT INTO evolution_log (changes_summary,created_at) VALUES (?,?)", (summary, now))
            cc.commit(); cc.close()
            return summary
        except:
            return None

    def get_stats(self):
        c = self._conn()
        conv = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        mem = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        evo = c.execute("SELECT COUNT(*) FROM evolution_log").fetchone()[0]
        cats = c.execute("SELECT category,COUNT(*) as cnt FROM memories GROUP BY category").fetchall()
        c.close()
        return {"conversations": conv, "memories": mem, "evolutions": evo,
                "categories": {r["category"]: r["cnt"] for r in cats}}


# ---------------------------------------------------------------------------
#  初始化
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MEMORY_DB = os.path.join(_SCRIPT_DIR, "data", "memory.db")

st.set_page_config(page_title=AGENT_NAME, page_icon="A", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:opsz@14..32&display=swap');
* { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
.stApp { background: #f8f9fc; max-width: 880px; margin: 0 auto; padding: 2rem 1.5rem; }
.app-header h1 { font-size: 1.6rem; font-weight: 500; color: #1a1d23; margin: 0; }
.app-header p { font-size: 0.85rem; color: #8e8ea0; }
.model-badge { display: inline-block; font-size: 0.7rem; background: #e8eaf0; color: #555; padding: 0.15rem 0.7rem; border-radius: 999px; }
.input-card { background: #fff; border: 1px solid #eef0f4; border-radius: 14px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem; }
.output-card { background: #fff; border: 1px solid #eef0f4; border-radius: 14px; padding: 1.5rem; margin-top: 1rem; }
.stButton button { background: #1a1d23; color: white; border: none; border-radius: 10px; padding: 0.45rem 1.8rem; }
.memory-info { background: #f0f7ff; border: 1px solid #d0e3ff; border-radius: 10px; padding: 0.8rem 1rem; margin: 0.5rem 0; font-size: 0.8rem; color: #2563eb; }
#MainMenu {visibility: hidden;} footer {visibility: hidden;} .stDeployButton {display:none;}
</style>""", unsafe_allow_html=True)


def init_session():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "api_key" not in st.session_state:
        st.session_state.api_key = os.getenv("MY_API_KEY") or DEFAULT_API_KEY
    if "base_url" not in st.session_state:
        st.session_state.base_url = os.getenv("MY_BASE_URL") or DEFAULT_BASE_URL
    if "model_name" not in st.session_state:
        st.session_state.model_name = os.getenv("MY_MODEL_NAME") or DEFAULT_MODEL_NAME
    if "memory" not in st.session_state:
        st.session_state.memory = MemoryEngine(AGENT_NAME, _MEMORY_DB)
    if "evolve_msg" not in st.session_state:
        st.session_state.evolve_msg = ""


def render_sidebar():
    with st.sidebar:
        st.markdown("### 模型配置")
        st.session_state.api_key = st.text_input("API Key", value=st.session_state.api_key, type="password")
        st.session_state.base_url = st.text_input("Base URL", value=st.session_state.base_url)
        st.session_state.model_name = st.text_input("Model", value=st.session_state.model_name)

        st.divider()
        stats = st.session_state.memory.get_stats()
        st.markdown(f"**{AGENT_NAME}**")
        st.caption(f"记忆: {stats['memories']} 条 | 对话: {stats['conversations']} 条 | 进化: {stats['evolutions']} 次")

        if stats["categories"]:
            for cat, cnt in stats["categories"].items():
                st.caption(f"  {cat}: {cnt} 条")

        st.divider()
        if st.button("清空对话", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


def main():
    init_session()
    render_sidebar()
    memory = st.session_state.memory

    st.markdown(f"""
    <div class="app-header">
        <h1>{AGENT_NAME}</h1>
        <p>带持久记忆的智能体 — 越用越懂你</p>
        <span class="model-badge">{st.session_state.model_name or '未配置'}</span>
    </div>
    """, unsafe_allow_html=True)

    # 进化提示
    if st.session_state.evolve_msg:
        st.markdown(f'<div class="memory-info">{st.session_state.evolve_msg}</div>', unsafe_allow_html=True)

    # 记忆上下文提示
    if memory.get_stats()["memories"] > 0:
        with st.expander("查看已学习的记忆", expanded=False):
            all_mems = memory.get_context("")
            if all_mems:
                st.text(all_mems)

    # 输入区
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    col1, col2 = st.columns([5, 1])
    with col1:
        user_input = st.text_area("你的需求", placeholder="描述你需要解决的问题...", height=100, label_visibility="collapsed")
    with col2:
        st.write("")
        submitted = st.button("发送", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # 处理请求
    if submitted and user_input.strip():
        with st.spinner("思考中..."):
            client = OpenAI(api_key=st.session_state.api_key, base_url=st.session_state.base_url)
            try:
                # 注入记忆上下文
                mem_ctx = memory.get_context(user_input)
                sys_prompt = AGENT_SYSTEM_PROMPT + ("\n\n" + mem_ctx if mem_ctx else "")

                response = client.chat.completions.create(
                    model=st.session_state.model_name,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        * [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[-10:]],
                        {"role": "user", "content": user_input},
                    ],
                    temperature=0.3,
                )
                reply = response.choices[0].message.content
                st.session_state.messages.append({"role": "user", "content": user_input})
                st.session_state.messages.append({"role": "assistant", "content": reply})

                # 记录到持久记忆
                memory.record(user_input, reply)

                # 自动进化
                if memory.should_evolve():
                    summary = memory.evolve(client, st.session_state.model_name)
                    if summary:
                        st.session_state.evolve_msg = f"记忆进化完成: {summary}"

                st.rerun()

            except Exception as e:
                st.error(f"调用失败: {e}")

    # 对话历史
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div style="margin-bottom:0.3rem;font-size:0.85rem;color:#3a3d4a;"><strong>你</strong></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="output-card" style="background:#f4f6fa;">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="margin-top:0.8rem;margin-bottom:0.3rem;font-size:0.85rem;color:#3a3d4a;"><strong>{AGENT_NAME}</strong></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="output-card">{msg["content"]}</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
