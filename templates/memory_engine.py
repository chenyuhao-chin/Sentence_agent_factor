"""
Memory Engine — 智能体持久记忆 + 自动进化引擎
==============================================
自包含模块，零外部依赖（仅 sqlite3 + json + 标准库）。

能力：
  1. 持久化对话历史（SQLite）
  2. 自动提取用户偏好和关键事实
  3. 基于积累的知识自动进化 System Prompt
  4. 每次对话前检索相关记忆注入上下文

使用方式（集成到智能体中）：
    engine = MemoryEngine(agent_name="我的助手", db_path="memory.db")
    
    # 对话前：获取记忆上下文
    context = engine.get_context(user_input)
    
    # 对话后：记录并进化
    engine.record(user_input, assistant_reply)
    engine.evolve(client, model)  # 可选，定期进化
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("memory_engine")


class MemoryEngine:
    """
    持久记忆 + 自动进化引擎
    
    :param agent_name: 智能体名称（用于隔离不同智能体的记忆）
    :param db_path: SQLite 数据库路径
    :param max_context_memories: 每次注入的最大记忆条数
    :param evolve_interval: 每隔 N 次对话触发一次进化
    """

    def __init__(
        self,
        agent_name: str = "agent",
        db_path: str = "memory.db",
        max_context_memories: int = 5,
        evolve_interval: int = 10,
    ):
        self.agent_name = agent_name
        self.db_path = db_path
        self.max_context_memories = max_context_memories
        self.evolve_interval = evolve_interval
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                );
                
                CREATE TABLE IF NOT EXISTS memories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    category    TEXT NOT NULL DEFAULT 'general',
                    key         TEXT NOT NULL,
                    value       TEXT NOT NULL,
                    confidence  REAL NOT NULL DEFAULT 0.5,
                    hit_count   INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );
                
                CREATE TABLE IF NOT EXISTS evolution_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    old_prompt_hash TEXT,
                    new_prompt_hash TEXT,
                    changes_summary TEXT,
                    created_at      TEXT NOT NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
                CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
                CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);
            """)
            conn.commit()
        finally:
            conn.close()

    # ==================================================================
    #  对话记录
    # ==================================================================

    def record(self, user_input: str, assistant_reply: str):
        """记录一轮对话"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO conversations (role, content, created_at) VALUES (?, ?, ?)",
                ("user", user_input, now),
            )
            conn.execute(
                "INSERT INTO conversations (role, content, created_at) VALUES (?, ?, ?)",
                ("assistant", assistant_reply, now),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_conversations(self, limit: int = 10) -> list:
        """获取最近的对话记录"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT role, content, created_at FROM conversations "
                "ORDER BY id DESC LIMIT ?",
                (limit * 2,),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    # ==================================================================
    #  记忆管理
    # ==================================================================

    def add_memory(self, category: str, key: str, value: str, confidence: float = 0.5):
        """添加或更新一条记忆"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT id, confidence FROM memories WHERE category = ? AND key = ?",
                (category, key),
            ).fetchone()

            if existing:
                new_conf = min(1.0, max(confidence, existing["confidence"]) + 0.1)
                conn.execute(
                    "UPDATE memories SET value = ?, confidence = ?, hit_count = hit_count + 1, updated_at = ? WHERE id = ?",
                    (value, new_conf, now, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO memories (category, key, value, confidence, hit_count, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (category, key, value, confidence, now, now),
                )
            conn.commit()
        finally:
            conn.close()

    def search_memories(self, query: str, limit: int = 5) -> list:
        """按关键词搜索记忆（简单匹配）"""
        conn = self._get_conn()
        try:
            keywords = [w for w in query.split() if len(w) > 1]
            if not keywords:
                return []

            conditions = " OR ".join(["key LIKE ? OR value LIKE ?"] * len(keywords))
            params = []
            for kw in keywords:
                params.extend([f"%{kw}%", f"%{kw}%"])

            rows = conn.execute(
                f"SELECT category, key, value, confidence, hit_count FROM memories "
                f"WHERE {conditions} "
                f"ORDER BY confidence DESC, hit_count DESC LIMIT ?",
                params + [limit],
            ).fetchall()

            # 更新命中次数
            for r in rows:
                conn.execute(
                    "UPDATE memories SET hit_count = hit_count + 1 WHERE key = ?",
                    (r["key"],),
                )
            conn.commit()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all_memories(self) -> dict:
        """获取所有记忆，按类别分组"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT category, key, value, confidence FROM memories ORDER BY category, confidence DESC"
            ).fetchall()
            result = {}
            for r in rows:
                cat = r["category"]
                if cat not in result:
                    result[cat] = []
                result[cat].append(dict(r))
            return result
        finally:
            conn.close()

    # ==================================================================
    #  上下文注入（对话前调用）
    # ==================================================================

    def get_context(self, user_input: str) -> str:
        """
        根据用户输入检索相关记忆，生成上下文字符串。
        在调用 LLM 前注入到 system prompt 中。
        """
        parts = []

        # 1. 搜索相关记忆
        memories = self.search_memories(user_input, limit=self.max_context_memories)
        if memories:
            mem_lines = []
            for m in memories:
                mem_lines.append(f"- [{m['category']}] {m['key']}: {m['value']}")
            parts.append("【已积累的知识】\n" + "\n".join(mem_lines))

        # 2. 获取最近对话摘要
        recent = self.get_recent_conversations(limit=3)
        if recent:
            hist_lines = []
            for r in recent:
                role = "用户" if r["role"] == "user" else "助手"
                content = r["content"][:100] + "..." if len(r["content"]) > 100 else r["content"]
                hist_lines.append(f"{role}: {content}")
            parts.append("【最近对话】\n" + "\n".join(hist_lines))

        if not parts:
            return ""

        return "\n\n".join(parts)

    # ==================================================================
    #  自动进化（定期调用）
    # ==================================================================

    def should_evolve(self) -> bool:
        """判断是否应该触发进化"""
        conn = self._get_conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM conversations WHERE role = 'user'").fetchone()[0]
            last_evolution = conn.execute(
                "SELECT id FROM evolution_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            last_evo_id = last_evolution["id"] if last_evolution else 0

            # 每隔 evolve_interval 次用户输入触发一次
            return count > 0 and count % self.evolve_interval == 0 and count != last_evo_id * self.evolve_interval
        finally:
            conn.close()

    def evolve(self, client, model: str) -> Optional[str]:
        """
        自动进化：分析最近对话，提取新知识，更新记忆库。
        
        :param client: OpenAI 兼容客户端
        :param model: 模型名称
        :return: 进化摘要（无进化返回 None）
        """
        recent = self.get_recent_conversations(limit=20)
        if len(recent) < 4:
            return None

        # 构建分析 prompt
        conv_text = "\n".join(
            f"{'用户' if r['role'] == 'user' else '助手'}: {r['content'][:200]}"
            for r in recent
        )

        existing_memories = self.get_all_memories()
        memory_text = json.dumps(existing_memories, ensure_ascii=False, indent=2) if existing_memories else "暂无"

        analyze_prompt = f"""你是一个记忆分析引擎。分析以下对话，提取有价值的信息。

## 最近对话
{conv_text}

## 已有记忆
{memory_text}

请以 JSON 格式输出分析结果：
{{
    "user_preferences": [{{"key": "偏好名", "value": "偏好内容", "confidence": 0.8}}],
    "learned_facts": [{{"key": "事实名", "value": "事实内容", "confidence": 0.7}}],
    "user_patterns": [{{"key": "模式名", "value": "模式描述", "confidence": 0.6}}],
    "evolution_summary": "本次进化的简要总结"
}}

只提取新发现的信息，不要重复已有记忆。如果没有新发现，返回空数组。"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是记忆分析引擎，只输出JSON。"},
                    {"role": "user", "content": analyze_prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
            )

            raw = response.choices[0].message.content or ""
            # 提取 JSON
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                return None

            analysis = json.loads(match.group(0))

            # 写入记忆库
            for item in analysis.get("user_preferences", []):
                self.add_memory("偏好", item["key"], item["value"], item.get("confidence", 0.5))

            for item in analysis.get("learned_facts", []):
                self.add_memory("知识", item["key"], item["value"], item.get("confidence", 0.5))

            for item in analysis.get("user_patterns", []):
                self.add_memory("模式", item["key"], item["value"], item.get("confidence", 0.5))

            summary = analysis.get("evolution_summary", "记忆已更新")

            # 记录进化日志
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO evolution_log (changes_summary, created_at) VALUES (?, ?)",
                    (summary, now),
                )
                conn.commit()
            finally:
                conn.close()

            return summary

        except Exception as e:
            logger.warning("进化失败: %s", e)
            return None

    # ==================================================================
    #  统计
    # ==================================================================

    def get_stats(self) -> dict:
        conn = self._get_conn()
        try:
            conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            memory_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            evolution_count = conn.execute("SELECT COUNT(*) FROM evolution_log").fetchone()[0]
            categories = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM memories GROUP BY category"
            ).fetchall()
            return {
                "conversations": conv_count,
                "memories": memory_count,
                "evolutions": evolution_count,
                "categories": {r["category"]: r["cnt"] for r in categories},
            }
        finally:
            conn.close()
