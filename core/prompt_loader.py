"""
Agent Factory — Prompt Loader（双模式热插拔加载器）
====================================================
商业护城河核心组件：
  开发阶段：从 prompts/ 目录加载明文 markdown 文件，方便调试
  生产交付：一键切换为远程加密加载（云端私服）或环境变量注入，
            确保核心微调 Prompt 绝不随源码交付

使用方式：
    loader = PromptLoader(source="local", prompt_dir="prompts")
    prompt = loader.load("architect")

    loader = PromptLoader(source="remote", remote_url="https://...")
    prompt = loader.load("architect")
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agent_factory.prompt_loader")


class PromptLoader:
    """
    Prompt 双模式加载器
    ---
    :param source:  "local" 从本地目录读取 | "remote" 从远程加载（骨架预留）
    :param prompt_dir: 本地 prompt 目录路径（source="local" 时生效）
    :param remote_url: 远程 Prompt 服务 URL（source="remote" 时生效，待实现）
    :param env_var: 环境变量名（可选，如果设置则优先从环境变量中读取）
    """

    def __init__(
        self,
        source: str = "local",
        prompt_dir: str = "prompts",
        remote_url: Optional[str] = None,
        env_var: Optional[str] = None,
    ):
        self.source = source
        self.prompt_dir = Path(prompt_dir)
        self.remote_url = remote_url
        self.env_var = env_var

    def load(self, prompt_name: str) -> str:
        """
        加载指定名称的 Prompt

        优先级：环境变量 > remote > local
        """
        # 第一优先级：环境变量注入（生产环境换 Key 不走磁盘）
        if self.env_var:
            env_content = os.getenv(self.env_var)
            if env_content:
                logger.info("从环境变量 %s 加载 Prompt '%s' 成功", self.env_var, prompt_name)
                return env_content

        # 第二优先级：远程加载（未来实现加密传输）
        if self.source == "remote":
            return self._load_remote(prompt_name)

        # 第三优先级：本地文件（开发阶段使用）
        return self._load_local(prompt_name)

    def _load_local(self, prompt_name: str) -> str:
        """从本地 prompts/ 目录加载 Prompt 文件"""
        # 尝试多种后缀
        for ext in [".md", ".txt", ""]:
            file_path = self.prompt_dir / f"{prompt_name}{ext}"
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8").strip()
                if content:
                    logger.info("从本地文件 %s 加载 Prompt 成功", file_path)
                    return content
                else:
                    logger.warning("本地文件 %s 内容为空", file_path)

        # 如果 prompts/ 目录下没有可用的文件，尝试内置 fallback
        logger.warning(
            "本地未找到 Prompt 文件 '%s'（已尝试 .md / .txt / 无后缀），"
            "将由调用方使用内置默认 Prompt", prompt_name
        )
        return ""

    def _load_remote(self, prompt_name: str) -> str:
        """
        远程加载 Prompt（骨架预留）
        TODO: 生产环境实现 HTTPS + 加密 Token 鉴权的 Prompt 私服拉取
        """
        if self.remote_url:
            logger.info(
                "远程 Prompt 加载器已配置但尚未实现（URL=%s, prompt=%s），"
                "回退到本地加载", self.remote_url, prompt_name
            )
        else:
            logger.warning(
                "远程加载模式下未配置 remote_url，回退到本地加载"
            )
        return self._load_local(prompt_name)
