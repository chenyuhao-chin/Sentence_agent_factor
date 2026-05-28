"""
Agent Factory — 卡密管理器
===========================
闲鱼卡密校验 + 额度扣减。
使用本地加密 JSON 文件充当卡密库，零外部依赖。

卡密类型：
  - monthly（月卡）：激活后 30 天内无限使用
  - times（次卡）：激活后按次扣减，用完即止

使用方式：
    from core.card_manager import CardManager
    mgr = CardManager()
    ok, msg = mgr.verify_and_activate_card("FX-SEASON-8899")
    ok, msg = mgr.consume_quota()
"""

import base64
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("agent_factory.card_manager")

_BASE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_CARDS_PATH = _BASE_DIR / "cards.json"


class CardManager:
    """
    卡密管理器

    :param cards_path: cards.json 文件路径
    """

    def __init__(self, cards_path: Optional[str] = None):
        self.cards_path = Path(cards_path) if cards_path else _DEFAULT_CARDS_PATH
        self._cards = self._load_cards()

    # ------------------------------------------------------------------
    #  公开接口
    # ------------------------------------------------------------------

    def verify_and_activate_card(self, card_key: str) -> Tuple[bool, str]:
        """
        验证并激活卡密。

        :param card_key: 用户输入的卡密字符串
        :return: (成功与否, 提示消息)
        """
        card_key = card_key.strip().upper()
        if not card_key:
            return False, "请输入卡密"

        card = self._cards.get(card_key)
        if card is None:
            return False, "卡密无效，请检查是否输入正确"

        if card.get("status") != "active":
            return False, "该卡密已被使用或已失效"

        card_type = card.get("type", "")

        if card_type == "monthly":
            # 月卡：从激活时刻开始计算 30 天
            expire_time = card.get("expire_time", "")
            if not expire_time:
                # 首次激活，设置到期时间
                expire_dt = datetime.now() + timedelta(days=30)
                card["expire_time"] = expire_dt.strftime("%Y-%m-%d %H:%M:%S")
                card["activated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_cards()
                return True, f"月卡激活成功！有效期至 {card['expire_time']}"
            else:
                # 已激活过，检查是否过期
                expire_dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expire_dt:
                    card["status"] = "expired"
                    self._save_cards()
                    return False, "该月卡已过期，请购买新卡"
                return True, f"月卡验证通过！有效期至 {expire_time}"

        elif card_type == "times":
            # 次卡：检查剩余次数
            remaining = card.get("remaining_quota", 0)
            if remaining <= 0:
                card["status"] = "depleted"
                self._save_cards()
                return False, "该次卡额度已耗尽，请购买新卡"
            if not card.get("activated_at"):
                card["activated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_cards()
            return True, f"次卡激活成功！剩余次数：{remaining}"

        else:
            return False, f"未知卡密类型：{card_type}"

    def consume_quota(self, card_key: str = "") -> Tuple[bool, str]:
        """
        扣减一次额度（仅次卡需要调用）。
        月卡不扣减，仅检查是否过期。

        :param card_key: 指定要扣减的卡密。为空时自动查找。
        :return: (成功与否, 提示消息)
        """
        if card_key:
            card_key = card_key.strip().upper()
            card = self._cards.get(card_key)
            if not card or card.get("status") != "active":
                return False, "指定卡密无效或已失效"
        else:
            found = self._find_active_card()
            if not found:
                return False, "无有效卡密，请先激活"
            card_key, card = found

        card_type = card.get("type", "")

        if card_type == "monthly":
            # 月卡检查过期
            expire_time = card.get("expire_time", "")
            if expire_time:
                expire_dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expire_dt:
                    card["status"] = "expired"
                    self._save_cards()
                    return False, "月卡已过期，请续费"
            return True, "月卡有效，无需扣减"

        elif card_type == "times":
            remaining = card.get("remaining_quota", 0)
            if remaining <= 0:
                card["status"] = "depleted"
                self._save_cards()
                return False, "次卡额度已耗尽，请购买新卡"
            card["remaining_quota"] = remaining - 1
            self._save_cards()
            new_remaining = card["remaining_quota"]
            return True, f"扣减成功！剩余次数：{new_remaining}"

        return False, "未知卡密类型"

    def get_status(self, card_key: str = "") -> dict:
        """
        获取指定卡密或当前激活卡密的状态摘要。

        :param card_key: 指定卡密。为空时自动查找。
        :return: {"activated": bool, "type": str, "message": str, "remaining": int|None, "card_key": str}
        """
        if card_key:
            card_key = card_key.strip().upper()
            card = self._cards.get(card_key)
            if not card:
                return {"activated": False, "type": "", "message": "卡密无效", "remaining": None, "card_key": ""}
        else:
            found = self._find_active_card()
            if not found:
                return {"activated": False, "type": "", "message": "未激活", "remaining": None, "card_key": ""}
            card_key, card = found

        card_type = card.get("type", "")

        if card_type == "monthly":
            expire_time = card.get("expire_time", "")
            if expire_time:
                expire_dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expire_dt:
                    card["status"] = "expired"
                    self._save_cards()
                    return {"activated": False, "type": "monthly", "message": "月卡已过期", "remaining": None, "card_key": card_key}
                days_left = (expire_dt - datetime.now()).days
                return {"activated": True, "type": "monthly", "message": f"月卡有效（剩余 {days_left} 天）", "remaining": None, "card_key": card_key}
            return {"activated": True, "type": "monthly", "message": "月卡已激活", "remaining": None, "card_key": card_key}

        elif card_type == "times":
            remaining = card.get("remaining_quota", 0)
            if remaining <= 0:
                return {"activated": False, "type": "times", "message": "次卡额度已耗尽", "remaining": 0, "card_key": card_key}
            return {"activated": True, "type": "times", "message": f"次卡有效（剩余 {remaining} 次）", "remaining": remaining, "card_key": card_key}

        return {"activated": False, "type": "", "message": "未知状态", "remaining": None, "card_key": ""}

    # ------------------------------------------------------------------
    #  管理接口（供后台生成卡密）
    # ------------------------------------------------------------------

    def generate_card(self, card_key: str, card_type: str, quota: int = 10) -> bool:
        """
        生成新卡密（后台管理用）。

        :param card_key: 卡密字符串
        :param card_type: "monthly" 或 "times"
        :param quota: 次卡的次数（月卡忽略）
        :return: 是否成功
        """
        card_key = card_key.strip().upper()
        if not card_key or card_key in self._cards:
            return False

        if card_type == "monthly":
            self._cards[card_key] = {
                "type": "monthly",
                "expire_time": "",
                "status": "active",
            }
        elif card_type == "times":
            self._cards[card_key] = {
                "type": "times",
                "remaining_quota": quota,
                "status": "active",
            }
        else:
            return False

        self._save_cards()
        return True

    def list_cards(self) -> dict:
        """列出所有卡密（后台管理用）"""
        return dict(self._cards)

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------

    def _find_active_card(self) -> Optional[tuple]:
        """遍历查找第一个 active 的卡密"""
        for key, card in self._cards.items():
            if card.get("status") == "active":
                return (key, card)
        return None

    def _load_cards(self) -> dict:
        """加载卡密库（支持 Base64 编码的混淆格式）"""
        if not self.cards_path.exists():
            logger.info("卡密库文件不存在，创建空库: %s", self.cards_path)
            self._save_empty()
            return {}

        try:
            raw = self.cards_path.read_text(encoding="utf-8").strip()
            # 尝试直接 JSON 解析
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # 尝试 Base64 解码
                decoded = base64.b64decode(raw).decode("utf-8")
                return json.loads(decoded)
        except Exception as e:
            logger.error("卡密库加载失败: %s", e)
            return {}

    def _save_cards(self):
        """保存卡密库（明文 JSON + Base64 双份）"""
        try:
            self.cards_path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self._cards, ensure_ascii=False, indent=2)
            # 保存明文（方便调试）+ 注释说明
            self.cards_path.write_text(content, encoding="utf-8")
            logger.info("卡密库已保存: %s (%d 条)", self.cards_path, len(self._cards))
        except Exception as e:
            logger.error("卡密库保存失败: %s", e)

    def _save_empty(self):
        """初始化空卡密库"""
        self.cards_path.parent.mkdir(parents=True, exist_ok=True)
        self.cards_path.write_text("{}", encoding="utf-8")
