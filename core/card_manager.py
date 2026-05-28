"""
Agent Factory — 卡密管理器（SQLite 版）
======================================
闲鱼卡密校验 + 额度扣减。
使用 SQLite 数据库存储卡密，支持并发访问。

卡密类型：
  - monthly（月卡）：激活后 30 天内无限使用
  - times（次卡）：激活后按次扣减，用完即止
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("agent_factory.card_manager")

_BASE_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _BASE_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DATA_DIR / "cards.db"


class CardManager:
    """
    卡密管理器（SQLite 版）

    :param db_path: SQLite 数据库文件路径
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else _DB_PATH
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        # 防御：如果路径是目录（Docker 挂载残留），删除它
        if self.db_path.exists() and self.db_path.is_dir():
            import shutil
            shutil.rmtree(self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    card_key    TEXT PRIMARY KEY,
                    card_type   TEXT NOT NULL DEFAULT 'times',
                    status      TEXT NOT NULL DEFAULT 'active',
                    remaining   INTEGER NOT NULL DEFAULT 10,
                    expire_time TEXT DEFAULT '',
                    activated_at TEXT DEFAULT '',
                    created_at  TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS card_logs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_key   TEXT NOT NULL,
                    action     TEXT NOT NULL,
                    detail     TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    #  公开接口
    # ------------------------------------------------------------------

    def verify_and_activate_card(self, card_key: str) -> Tuple[bool, str]:
        card_key = card_key.strip().upper()
        if not card_key:
            return False, "请输入卡密"

        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM cards WHERE card_key = ?", (card_key,)
            ).fetchone()

            if row is None:
                return False, "卡密无效，请检查是否输入正确"

            card = dict(row)
            if card["status"] != "active":
                return False, "该卡密已被使用或已失效"

            card_type = card["card_type"]

            if card_type == "monthly":
                expire_time = card["expire_time"]
                if not expire_time:
                    expire_dt = datetime.now() + timedelta(days=30)
                    expire_str = expire_dt.strftime("%Y-%m-%d %H:%M:%S")
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute(
                        "UPDATE cards SET expire_time = ?, activated_at = ? WHERE card_key = ?",
                        (expire_str, now_str, card_key),
                    )
                    conn.execute(
                        "INSERT INTO card_logs (card_key, action, detail, created_at) VALUES (?, ?, ?, ?)",
                        (card_key, "activate", f"月卡激活，有效期至 {expire_str}", now_str),
                    )
                    conn.commit()
                    return True, f"月卡激活成功！有效期至 {expire_str}"
                else:
                    expire_dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() > expire_dt:
                        conn.execute(
                            "UPDATE cards SET status = 'expired' WHERE card_key = ?",
                            (card_key,),
                        )
                        conn.commit()
                        return False, "该月卡已过期，请购买新卡"
                    return True, f"月卡验证通过！有效期至 {expire_time}"

            elif card_type == "times":
                remaining = card["remaining"]
                if remaining <= 0:
                    conn.execute(
                        "UPDATE cards SET status = 'depleted' WHERE card_key = ?",
                        (card_key,),
                    )
                    conn.commit()
                    return False, "该次卡额度已耗尽，请购买新卡"
                if not card["activated_at"]:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute(
                        "UPDATE cards SET activated_at = ? WHERE card_key = ?",
                        (now_str, card_key),
                    )
                    conn.commit()
                return True, f"次卡激活成功！剩余次数：{remaining}"

            else:
                return False, f"未知卡密类型：{card_type}"
        finally:
            conn.close()

    def consume_quota(self, card_key: str = "") -> Tuple[bool, str]:
        if card_key:
            card_key = card_key.strip().upper()
        conn = self._get_conn()
        try:
            if card_key:
                row = conn.execute(
                    "SELECT * FROM cards WHERE card_key = ? AND status = 'active'",
                    (card_key,),
                ).fetchone()
                if not row:
                    return False, "指定卡密无效或已失效"
                card = dict(row)
            else:
                row = conn.execute(
                    "SELECT * FROM cards WHERE status = 'active' LIMIT 1"
                ).fetchone()
                if not row:
                    return False, "无有效卡密，请先激活"
                card = dict(row)
                card_key = card["card_key"]

            card_type = card["card_type"]

            if card_type == "monthly":
                expire_time = card["expire_time"]
                if expire_time:
                    expire_dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() > expire_dt:
                        conn.execute(
                            "UPDATE cards SET status = 'expired' WHERE card_key = ?",
                            (card_key,),
                        )
                        conn.commit()
                        return False, "月卡已过期，请续费"
                return True, "月卡有效，无需扣减"

            elif card_type == "times":
                remaining = card["remaining"]
                if remaining <= 0:
                    conn.execute(
                        "UPDATE cards SET status = 'depleted' WHERE card_key = ?",
                        (card_key,),
                    )
                    conn.commit()
                    return False, "次卡额度已耗尽，请购买新卡"
                new_remaining = remaining - 1
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    "UPDATE cards SET remaining = ? WHERE card_key = ?",
                    (new_remaining, card_key),
                )
                conn.execute(
                    "INSERT INTO card_logs (card_key, action, detail, created_at) VALUES (?, ?, ?, ?)",
                    (card_key, "consume", f"扣减1次，剩余{new_remaining}次", now_str),
                )
                conn.commit()
                return True, f"扣减成功！剩余次数：{new_remaining}"

            return False, "未知卡密类型"
        finally:
            conn.close()

    def get_status(self, card_key: str = "") -> dict:
        conn = self._get_conn()
        try:
            if card_key:
                card_key = card_key.strip().upper()
                row = conn.execute(
                    "SELECT * FROM cards WHERE card_key = ?", (card_key,)
                ).fetchone()
                if not row:
                    return {"activated": False, "type": "", "message": "卡密无效", "remaining": None, "card_key": ""}
                card = dict(row)
            else:
                row = conn.execute(
                    "SELECT * FROM cards WHERE status = 'active' LIMIT 1"
                ).fetchone()
                if not row:
                    return {"activated": False, "type": "", "message": "未激活", "remaining": None, "card_key": ""}
                card = dict(row)
                card_key = card["card_key"]

            card_type = card["card_type"]

            if card_type == "monthly":
                expire_time = card["expire_time"]
                if expire_time:
                    expire_dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() > expire_dt:
                        conn.execute(
                            "UPDATE cards SET status = 'expired' WHERE card_key = ?",
                            (card_key,),
                        )
                        conn.commit()
                        return {"activated": False, "type": "monthly", "message": "月卡已过期", "remaining": None, "card_key": card_key}
                    days_left = (expire_dt - datetime.now()).days
                    return {"activated": True, "type": "monthly", "message": f"月卡有效（剩余 {days_left} 天）", "remaining": None, "card_key": card_key}
                return {"activated": True, "type": "monthly", "message": "月卡已激活", "remaining": None, "card_key": card_key}

            elif card_type == "times":
                remaining = card["remaining"]
                if remaining <= 0:
                    return {"activated": False, "type": "times", "message": "次卡额度已耗尽", "remaining": 0, "card_key": card_key}
                return {"activated": True, "type": "times", "message": f"次卡有效（剩余 {remaining} 次）", "remaining": remaining, "card_key": card_key}

            return {"activated": False, "type": "", "message": "未知状态", "remaining": None, "card_key": ""}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    #  管理接口（供后台生成卡密）
    # ------------------------------------------------------------------

    def generate_card(self, card_key: str, card_type: str, quota: int = 10) -> bool:
        card_key = card_key.strip().upper()
        if not card_key:
            return False

        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT 1 FROM cards WHERE card_key = ?", (card_key,)
            ).fetchone()
            if existing:
                return False

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if card_type == "monthly":
                conn.execute(
                    "INSERT INTO cards (card_key, card_type, status, remaining, created_at) VALUES (?, ?, ?, ?, ?)",
                    (card_key, "monthly", "active", 0, now_str),
                )
            elif card_type == "times":
                conn.execute(
                    "INSERT INTO cards (card_key, card_type, status, remaining, created_at) VALUES (?, ?, ?, ?, ?)",
                    (card_key, "times", "active", quota, now_str),
                )
            else:
                return False

            conn.execute(
                "INSERT INTO card_logs (card_key, action, detail, created_at) VALUES (?, ?, ?, ?)",
                (card_key, "create", f"生成{card_type}卡密", now_str),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def list_cards(self) -> dict:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM cards").fetchall()
            result = {}
            for row in rows:
                card = dict(row)
                key = card.pop("card_key")
                result[key] = {
                    "type": card["card_type"],
                    "status": card["status"],
                    "remaining_quota": card["remaining"],
                    "expire_time": card["expire_time"],
                    "activated_at": card["activated_at"],
                    "created_at": card["created_at"],
                }
            return result
        finally:
            conn.close()

    def get_card_logs(self, card_key: str = "", limit: int = 50) -> list:
        conn = self._get_conn()
        try:
            if card_key:
                rows = conn.execute(
                    "SELECT * FROM card_logs WHERE card_key = ? ORDER BY id DESC LIMIT ?",
                    (card_key.strip().upper(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM card_logs ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_stats(self) -> dict:
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM cards WHERE status = 'active'").fetchone()[0]
            expired = conn.execute("SELECT COUNT(*) FROM cards WHERE status = 'expired'").fetchone()[0]
            depleted = conn.execute("SELECT COUNT(*) FROM cards WHERE status = 'depleted'").fetchone()[0]
            monthly = conn.execute("SELECT COUNT(*) FROM cards WHERE card_type = 'monthly'").fetchone()[0]
            times = conn.execute("SELECT COUNT(*) FROM cards WHERE card_type = 'times'").fetchone()[0]
            total_consumed = conn.execute(
                "SELECT COUNT(*) FROM card_logs WHERE action = 'consume'"
            ).fetchone()[0]
            return {
                "total": total,
                "active": active,
                "expired": expired,
                "depleted": depleted,
                "monthly": monthly,
                "times": times,
                "total_consumed": total_consumed,
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    #  兼容旧接口
    # ------------------------------------------------------------------

    def _find_active_card(self) -> Optional[tuple]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM cards WHERE status = 'active' LIMIT 1"
            ).fetchone()
            if row:
                card = dict(row)
                return (card["card_key"], card)
            return None
        finally:
            conn.close()
