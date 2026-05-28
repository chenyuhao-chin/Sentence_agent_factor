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

    # 不支持 response_format=json_object 的模型前缀
    _NO_JSON_FORMAT_MODELS = ("mimo", "qwen", "glm", "yi-", "moonshot")

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        prompt_loader: Optional[Callable[[], str]] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL")

        if not self.api_key:
            raise ValueError(
                "缺少 API Key。请在管理后台配置 API Key，"
                "或设置环境变量 DEEPSEEK_API_KEY。"
            )
        if not self.base_url:
            raise ValueError(
                "缺少 Base URL。请在管理后台配置 Base URL，"
                "或设置环境变量 DEEPSEEK_BASE_URL。"
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
    def _supports_json_format(self) -> bool:
        model_lower = self.model.lower()
        for prefix in self._NO_JSON_FORMAT_MODELS:
            if prefix in model_lower:
                return False
        return True

    def architect(self, user_requirement: str) -> dict:
        """
        总架构师模式：输入用户一句话需求，返回标准 agent_config 字典。
        
        :param user_requirement: 用户一句话需求
        :return: 符合 schema 的 dict（失败时返回空骨架，永不崩溃）
        """
        system_prompt = self._get_system_prompt()

        use_json_format = self._supports_json_format()

        # 对不支持 json_object 的模型，在 prompt 末尾追加 JSON 输出指令
        if not use_json_format:
            system_prompt += (
                "\n\n【重要】你必须且只能输出一个合法的 JSON 对象，不要输出任何其他文字、解释或 markdown 标记。"
                "输出格式必须严格符合 JSON 标准。"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_requirement},
        ]

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "调用 API [尝试 %d/%d]：model=%s, json_format=%s",
                    attempt, self.max_retries, self.model, use_json_format,
                )
                kwargs = dict(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=8192,
                )
                if use_json_format:
                    kwargs["response_format"] = {"type": "json_object"}

                response = self._client.chat.completions.create(**kwargs)

                msg = response.choices[0].message
                raw = msg.content

                # 推理模型可能把内容放在 reasoning_content 中
                if (not raw or not raw.strip()) and hasattr(msg, 'reasoning_content'):
                    reasoning = msg.reasoning_content or ""
                    if reasoning.strip():
                        logger.warning("content 为空，尝试从 reasoning_content 中提取 JSON")
                        raw = reasoning

                if not raw or not raw.strip():
                    logger.warning("API 返回空内容，尝试重试")
                    raise ValueError("API 返回空内容")

                logger.debug("原始响应内容长度：%d 字符", len(raw))

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
        if not raw_text:
            logger.error("API 返回空文本，返回空骨架")
            return dict(EMPTY_AGENT_CONFIG)

        cleaned = raw_text.strip()

        # 移除 markdown 代码块包裹
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        # 直接解析
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # 尝试提取文本中的第一个 JSON 对象
        try:
            import re
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
            if match:
                candidate = match.group(0)
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    logger.info("从文本中提取到 JSON 对象")
                    return parsed
        except (json.JSONDecodeError, Exception):
            pass

        # 修复常见问题（尾部多余逗号）
        try:
            import re
            fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
            parsed = json.loads(fixed)
            if isinstance(parsed, dict):
                logger.info("修复解析成功")
                return parsed
        except (json.JSONDecodeError, Exception):
            pass

        logger.error("JSON 解析失败，返回空骨架")
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
