#!/usr/bin/env python3
"""
Agent Factory — CLI 智能体模板（带持久记忆 + 自动进化）
=====================================================
V3.0 架构特征：
  1. 对接任意 OpenAI 兼容 SDK（Qwen / GLM / Claude 中转 / vLLM 等）
  2. 内置持久记忆引擎（SQLite）— 跨会话记忆用户偏好和知识
  3. 自动进化：每 10 轮对话自动分析并积累新知识
  4. 单文件零外部依赖（除 openai + 标准库）

使用方式：
    export MY_API_KEY='sk-xxx'
    export MY_BASE_URL='https://api.deepseek.com/v1'
    python3 app.py "你的需求"
"""

import json
import os
import sys
import time

try:
    from openai import OpenAI
except ImportError:
    print("需要安装 openai 库：pip install openai")
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


# ═══════════════════════════════════════════════════════════════
#  记忆引擎（内置，零配置）
# ═══════════════════════════════════════════════════════════════
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MEMORY_DB = os.path.join(_SCRIPT_DIR, "data", "memory.db")

# 内联 MemoryEngine（避免外部依赖）
import sqlite3
import re
from datetime import datetime
from pathlib import Path


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
        except Exception as e:
            return None

    def get_stats(self):
        c = self._conn()
        conv = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        mem = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        evo = c.execute("SELECT COUNT(*) FROM evolution_log").fetchone()[0]
        c.close()
        return {"conversations": conv, "memories": mem, "evolutions": evo}


memory = MemoryEngine(agent_name=AGENT_NAME, db_path=_MEMORY_DB)


# ═══════════════════════════════════════════════════════════════
#  工具调用
# ═══════════════════════════════════════════════════════════════
def call_tool(tool_name: str, **kwargs) -> str:
    if tool_name not in TOOL_CONFIG:
        return f"[工具错误] 未知工具: {tool_name}，可用工具: {list(TOOL_CONFIG.keys())}"
    tool = TOOL_CONFIG[tool_name]
    base_url = tool.get("base_url", "")
    auth_header = tool.get("auth_header", "")
    params = {**tool.get("default_params", {}), **kwargs}
    try:
        import urllib.request, urllib.parse
        url = f"{base_url}?{urllib.parse.urlencode(params)}" if params else base_url
        req = urllib.request.Request(url)
        if auth_header: req.add_header("Authorization", auth_header)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        return f"[工具错误] {tool_name} 调用失败: {e}"


# ═══════════════════════════════════════════════════════════════
#  核心逻辑
# ═══════════════════════════════════════════════════════════════
def main():
    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not user_input:
        stats = memory.get_stats()
        print(f"{AGENT_NAME} 启动成功")
        print(f"   模型: {MODEL_NAME}")
        print(f"   记忆: {stats['memories']} 条知识 | {stats['conversations']} 条对话 | {stats['evolutions']} 次进化")
        print()
        print("请输入你的需求（或输入 /quit 退出，/stats 查看记忆统计）：")
        interactive_mode()
        return
    result = call_llm(user_input)
    print_report(result)


def interactive_mode():
    client = _build_client()
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    turn = 0

    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input: continue
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("再见！")
            break

        if user_input.lower() == "/stats":
            stats = memory.get_stats()
            print(f"\n记忆统计: {json.dumps(stats, ensure_ascii=False, indent=2)}\n")
            continue

        # 注入记忆上下文
        mem_ctx = memory.get_context(user_input)
        if mem_ctx:
            history[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + mem_ctx}

        history.append({"role": "user", "content": user_input})

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME, messages=history, temperature=0.3,
            )
            reply = response.choices[0].message.content
            print(f"\n{AGENT_NAME}:")
            print(reply)
            print()
            history.append({"role": "assistant", "content": reply})

            # 记录到持久记忆
            memory.record(user_input, reply)
            turn += 1

            # 自动进化
            if memory.should_evolve():
                print("[记忆进化中...]")
                summary = memory.evolve(client, MODEL_NAME)
                if summary:
                    print(f"[进化完成] {summary}\n")

        except Exception as e:
            print(f"\n调用失败: {e}\n")


def call_llm(user_input: str) -> str:
    client = _build_client()
    mem_ctx = memory.get_context(user_input)
    sys_prompt = SYSTEM_PROMPT + ("\n\n" + mem_ctx if mem_ctx else "")
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_input},
    ]
    response = client.chat.completions.create(
        model=MODEL_NAME, messages=messages, temperature=0.3,
    )
    reply = response.choices[0].message.content
    memory.record(user_input, reply)
    return reply


def print_report(report: str):
    separator = "=" * 60
    print(f"\n{separator}")
    print(f"  {AGENT_NAME} — 输出报告")
    print(f"{separator}\n")
    print(report)
    print(f"\n{separator}\n")


def _build_client() -> OpenAI:
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


if __name__ == "__main__":
    main()
