"""
Agent Factory — DeepSeek LLM Client
====================================
核心 LLM 连接器，承担以下职责：
  1. 统一封装 DeepSeek API 调用（OpenAI SDK）
  2. 强制 JSON 输出模式 + 防爆舱安全解析（双层保险）
  3. 指数退避重试（3次），防止网络抖动击穿产线
  4. 预留 Prompt 热插拔接口（支持未来加密/远程加载）

商业护城河：
  - 核心微调 Prompt 在最终交付时可一键替换为普通开源版
  - 通过 prompt_loader 参数实现热插拔，不对上层暴露 Prompt 源文件
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI

from core.prompt_loader import PromptLoader

# ---------------------------------------------------------------------------
# 日志（为未来车间调度可观测性预留）
# ---------------------------------------------------------------------------
logger = logging.getLogger("agent_factory.llm_client")

# ---------------------------------------------------------------------------
# 防爆舱空骨架 — 当 API 吐出不可解析的垃圾时，返回此安全值
# ---------------------------------------------------------------------------
EMPTY_AGENT_CONFIG: dict = {
    "agent_name": "",
    "system_prompt": "",
    "delivery_type": "exe",
    "auth_mode": "user_key",
    "required_skills": [],
    "prompt_pack": {
        "system_prompt": "",
        "user_prompt_template": "",
        "opening_remark": "",
        "closing_remark": "",
    },
    "platforms": ["coze", "dify"],
    "memory_config": {
        "max_turns": 5,
        "persist_strategy": "session_only",
    },
    "agent_meta": {
        "display_name": "",
        "icon": "",
        "category": "",
        "tags": [],
        "description": "",
        "version": "1.0.0",
        "author": "Agent Factory",
    },
}

class DeepSeekClient:
    """
    DeepSeek API 客户端
    ---
    用法:
        client = DeepSeekClient()
        config = client.architect("帮我做一个挑战杯比赛路演PPT润色Agent")
        print(config)  # => 符合 agent_config.json Schema 的字典
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        prompt_loader: Optional[Callable[[], str]] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        """
        :param api_key:         DeepSeek API Key。为 None 时从环境变量 DEEPSEEK_API_KEY 读取
        :param base_url:        DeepSeek API Base URL。为 None 时从环境变量 DEEPSEEK_BASE_URL 读取
        :param model:           模型名称，默认 deepseek-chat
        :param prompt_loader:   Prompt 加载回调函数。为 None 时使用内置默认 Prompt（调试用）
        :param max_retries:     最大重试次数（默认 3）
        :param base_delay:      退避基数秒数（默认 1.0）
        """
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL")

        if not self.api_key:
            raise ValueError(
                "缺少 DEEPSEEK_API_KEY。请设置环境变量 DEEPSEEK_API_KEY，"
                "或在初始化时传入 api_key 参数。"
            )
        if not self.base_url:
            raise ValueError(
                "缺少 DEEPSEEK_BASE_URL。请设置环境变量 DEEPSEEK_BASE_URL，"
                "或在初始化时传入 base_url 参数。"
            )

        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay

        # Prompt 热插拔：如果传入了 prompt_loader 回调，就用它获取 Prompt
        # 如果未传入，自动使用 PromptLoader 尝试加载 prompts/architect.md
        if prompt_loader is None:
            loader = PromptLoader(source="local", prompt_dir="prompts")
            self._prompt_loader = lambda: loader.load("architect")
        else:
            self._prompt_loader = prompt_loader

        # 初始化 OpenAI 客户端
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------
    def architect(self, user_requirement: str) -> dict:
        """
        总架构师模式：输入用户一句话需求，返回标准 agent_config 字典。
        
        :param user_requirement: 用户一句话需求
        :return: 符合 schema 的 dict（失败时返回空骨架，永不崩溃）
        """
        system_prompt = self._get_system_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_requirement},
        ]

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "调用 DeepSeek API [尝试 %d/%d]：model=%s",
                    attempt, self.max_retries, self.model,
                )
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.3,  # 低温度确保结构化稳定性
                )

                raw = response.choices[0].message.content
                logger.debug("原始响应内容长度：%d 字符", len(raw or ""))

                parsed = self._safe_json_parse(raw)
                self._validate_config(parsed)
                return parsed

            except Exception as e:
                logger.warning("第 %d 次尝试失败：%s", attempt, e)
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    logger.info("等待 %.1f 秒后重试...", delay)
                    time.sleep(delay)
                else:
                    logger.error("所有重试均已耗尽，返回空骨架配置")
                    return dict(EMPTY_AGENT_CONFIG)

        # 保险返回（不会执行到这里，但满足类型检查）
        return dict(EMPTY_AGENT_CONFIG)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _get_system_prompt(self) -> str:
        """
        【Prompt 热插拔 — V3 解耦版】
        加载链：prompt_loader 回调 → prompts/architect.md → prompts/architect_opensource.md → prompts/architect_fallback.md
        四层全部为空则抛出 RuntimeError，绝不静默降级。
        
        护城河：代码中零行 Prompt 业务逻辑，所有调教内容在 prompts/ 目录的 .md 文件中。
        交付时一键替换 prompts/ 目录即可切换产品线。
        """
        # 第一优先级：外部注入的 prompt_loader 回调
        if self._prompt_loader is not None:
            loaded = self._prompt_loader()
            if loaded:
                logger.info("使用外部注入的 prompt_loader 提供的 System Prompt")
                return loaded
            logger.warning("prompt_loader 返回空字符串，继续尝试文件加载")

        # 第二优先级：prompts/architect.md（商业版）
        loader = PromptLoader(source="local", prompt_dir="prompts")
        architect_prompt = loader.load("architect")
        if architect_prompt:
            logger.info("从 prompts/architect.md 加载 System Prompt 成功（商业版）")
            return architect_prompt

        # 第三优先级：prompts/architect_opensource.md（开源版）
        opensource_prompt = loader.load("architect_opensource")
        if opensource_prompt:
            logger.info("从 prompts/architect_opensource.md 加载 System Prompt 成功（开源版）")
            return opensource_prompt

        # 第四优先级：prompts/architect_fallback.md（兜底文件）
        fallback_prompt = loader.load("architect_fallback")
        if fallback_prompt:
            logger.warning("architect.md 不可用，使用 architect_fallback.md 兜底")
            return fallback_prompt

        # 四层全部为空 — 绝不静默降级，让调用方感知配置缺失
        raise RuntimeError(
            "无法加载 System Prompt：prompts/ 目录下无可用 Prompt 文件。"
            "请确保 prompts/ 目录完整，或通过 prompt_loader 参数注入有效的 System Prompt。"
        )

    @staticmethod
    def _safe_json_parse(raw_text: Optional[str]) -> dict:
        """
        防爆舱安全解析：双层保险
        第一层：尝试标准 JSON 解析
        第二层：捕获 json.JSONDecodeError 及一切异常，返回空骨架
        """
        if not raw_text:
            logger.error("API 返回空文本，返回空骨架")
            return dict(EMPTY_AGENT_CONFIG)

        # 尝试提取被 markdown 代码块包裹的 JSON（模型有时会加 ```json ... ```）
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            # 移除开头的 ```json 或 ``` 以及结尾的 ```
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                logger.error("JSON 解析结果不是 dict 类型，返回空骨架")
                return dict(EMPTY_AGENT_CONFIG)
            return parsed
        except json.JSONDecodeError as e:
            logger.error("JSON 解析失败 (第一层)：%s", e)
            # 第二层保险：尝试修复常见问题（尾部多余逗号等）
            try:
                import re
                fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
                parsed = json.loads(fixed)
                if isinstance(parsed, dict):
                    logger.info("第二层修复解析成功")
                    return parsed
            except (json.JSONDecodeError, Exception) as e2:
                logger.error("JSON 解析失败 (第二层)：%s", e2)
            return dict(EMPTY_AGENT_CONFIG)
        except Exception as e:
            logger.error("非 JSON 异常：%s，返回空骨架", e)
            return dict(EMPTY_AGENT_CONFIG)

    @staticmethod
    def _validate_config(config: dict) -> None:
        """
        校验关键字段是否存在并合法，缺失时自动填充骨架默认值。
        注意：这是软校验，不抛出异常，仅补全。

        V2 升级：新增 prompt_pack、platforms、memory_config、agent_meta 支持。
        """
        # ---- 基础字段 ----
        defaults = {
            "agent_name": "",
            "system_prompt": "",
            "delivery_type": "exe",
            "auth_mode": "user_key",
            "required_skills": [],
        }
        for key, default in defaults.items():
            if key not in config or config[key] is None:
                config[key] = default
                logger.warning("字段 '%s' 缺失，已自动补全为默认值", key)

        # delivery_type 约束
        if config["delivery_type"] not in ("exe", "zip", "web"):
            logger.warning(
                "delivery_type='%s' 不合法，已重置为 'exe'", config["delivery_type"]
            )
            config["delivery_type"] = "exe"

        # required_skills 必须是 list
        if not isinstance(config["required_skills"], list):
            config["required_skills"] = ["none"]

        # ---- V2 扩展字段：prompt_pack ----
        if "prompt_pack" not in config or not isinstance(config.get("prompt_pack"), dict):
            config["prompt_pack"] = {
                "system_prompt": config.get("system_prompt", ""),
                "user_prompt_template": "",
                "opening_remark": "",
                "closing_remark": "",
            }
        else:
            pp = config["prompt_pack"]
            pp.setdefault("system_prompt", config.get("system_prompt", ""))
            pp.setdefault("user_prompt_template", "")
            pp.setdefault("opening_remark", "")
            pp.setdefault("closing_remark", "")

        # ---- V2 扩展字段：platforms ----
        if "platforms" not in config or not isinstance(config.get("platforms"), list):
            config["platforms"] = ["coze", "dify"]
        else:
            valid_platforms = {"coze", "dify", "feishu", "openclaw"}
            config["platforms"] = [p for p in config["platforms"] if p in valid_platforms]
            if not config["platforms"]:
                config["platforms"] = ["coze", "dify"]

        # ---- V2 扩展字段：memory_config ----
        if "memory_config" not in config or not isinstance(config.get("memory_config"), dict):
            config["memory_config"] = {
                "max_turns": 5,
                "persist_strategy": "session_only",
            }
        else:
            mc = config["memory_config"]
            mc.setdefault("max_turns", 5)
            mc.setdefault("persist_strategy", "session_only")

        # ---- V2 扩展字段：agent_meta ----
        if "agent_meta" not in config or not isinstance(config.get("agent_meta"), dict):
            config["agent_meta"] = {
                "display_name": config.get("agent_name", ""),
                "icon": "",
                "category": "",
                "tags": config.get("required_skills", []),
                "description": "",
                "version": "1.0.0",
                "author": "Agent Factory",
            }
        else:
            am = config["agent_meta"]
            am.setdefault("display_name", config.get("agent_name", ""))
            am.setdefault("icon", "")
            am.setdefault("category", "")
            am.setdefault("tags", config.get("required_skills", []))
            am.setdefault("description", "")
            am.setdefault("version", "1.0.0")
            am.setdefault("author", "Agent Factory")
