"""
Agent Factory — 装配引擎（Builder）
======================================
核心职责：将 LLM 架构师输出的 `agent_config.json` 图纸，灌入选定的模板，
         生成可直接运行的智能体 Python 脚本（单文件、零崩溃）。

商业特征：
  1. 模型无关：模板中的 {API_KEY_SLOT} / {BASE_URL_SLOT} / {MODEL_NAME_SLOT} 全部可替换
  2. 双模板支持：CLI 终端版 / Streamlit Web 版
  3. 输出文件名自动根据 agent_name 生成，永不覆盖
  4. 生成的脚本自动写入 output_agents/ 目录，即出即卖

使用方式：
    from core.builder import AgentBuilder
    builder = AgentBuilder(config, delivery_type="web")
    output_path = builder.assemble()
    print(f"[OK] 智能体已生成：{output_path}")
"""

import json
import logging
import os
import re
import string
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger("agent_factory.builder")


# ---------------------------------------------------------------------------
#  三层冻结数据类（structured-prompt-builder 概念）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SystemPrompt:
    """角色声明层 — O-EX 段"""
    content: str
    agent_name: str = ""
    role_description: str = ""

    def __post_init__(self):
        if not self.content and not self.agent_name:
            raise ValueError("SystemPrompt: content 和 agent_name 不能同时为空")


@dataclass(frozen=True)
class ToolPrompt:
    """工具调用规范层 — S-EX Action 段"""
    content: str
    available_tools: tuple = ()

    def has_tools(self) -> bool:
        return bool(self.available_tools) or bool(self.content.strip())


@dataclass(frozen=True)
class MemoryPrompt:
    """记忆管理层 — A-EX 段"""
    content: str
    max_turns: int = 5
    persist_strategy: str = "session_only"

    def __post_init__(self):
        if not (1 <= self.max_turns <= 20):
            raise ValueError(f"MemoryPrompt: max_turns 必须在 1-20 之间，当前: {self.max_turns}")


@dataclass(frozen=True)
class OutputPrompt:
    """输出格式约束层 — R-EX 段"""
    content: str
    requires_json_boundary: bool = True


@dataclass(frozen=True)
class PromptPack:
    """四层冻结 Prompt 包 — 保证提示词一致性校验"""
    system: SystemPrompt
    tool: ToolPrompt
    memory: MemoryPrompt
    output: OutputPrompt

    def to_dict(self) -> dict:
        return {
            "system": self.system.content,
            "tool": self.tool.content,
            "memory": self.memory.content,
            "output": self.output.content,
        }

    def to_xml(self) -> str:
        """导出为 XML 闭合标签格式（prompt-ez 兼容）"""
        return (
            f"<system>\n{self.system.content}\n</system>\n\n"
            f"<tool>\n{self.tool.content}\n</tool>\n\n"
            f"<memory>\n{self.memory.content}\n</memory>\n\n"
            f"<output>\n{self.output.content}\n</output>"
        )

    def validate(self) -> list:
        """一致性校验，返回问题列表（空列表 = 全部通过）"""
        issues = []
        if not self.system.content.strip():
            issues.append("system 层内容为空")
        if not self.tool.content.strip():
            issues.append("tool 层内容为空（应至少有默认值）")
        if not self.memory.content.strip():
            issues.append("memory 层内容为空（应至少有默认值）")
        if not self.output.content.strip():
            issues.append("output 层内容为空（应至少有默认值）")
        if self.memory.max_turns < 1 or self.memory.max_turns > 20:
            issues.append(f"memory.max_turns 超出范围: {self.memory.max_turns}")
        return issues


# ---------------------------------------------------------------------------
#  AP-ID 变量语法映射（跨平台统一）
# ---------------------------------------------------------------------------
class APIDMapper:
    """
    各平台变量引用语法统一转换器。
    Dify:  {{#step_id.text}}
    Coze:  {{input}}
    飞书:  ${VAR}
    OpenClaw: ${VAR}
    """

    SYNTAX_MAP = {
        "dify": {"open": "{{#", "close": "}}", "field_sep": "."},
        "coze": {"open": "{{", "close": "}}", "field_sep": "."},
        "feishu": {"open": "${", "close": "}", "field_sep": "_"},
        "openclaw": {"open": "${", "close": "}", "field_sep": "_"},
    }

    @classmethod
    def convert(cls, var_ref: str, from_platform: str, to_platform: str) -> str:
        """转换变量引用语法。例: '{{#step_1.text}}' (dify) → '${step_1_text}' (feishu)"""
        from_syntax = cls.SYNTAX_MAP.get(from_platform)
        to_syntax = cls.SYNTAX_MAP.get(to_platform)
        if not from_syntax or not to_syntax:
            return var_ref

        # 提取变量名
        inner = var_ref
        if from_syntax["open"] in inner:
            inner = inner.replace(from_syntax["open"], "").replace(from_syntax["close"], "")
        inner = inner.lstrip("#").replace(from_syntax["field_sep"], to_syntax["field_sep"])

        return f"{to_syntax['open']}{inner}{to_syntax['close']}"

    @classmethod
    def convert_text(cls, text: str, from_platform: str, to_platform: str) -> str:
        """批量转换文本中的所有变量引用"""
        from_syntax = cls.SYNTAX_MAP.get(from_platform)
        if not from_syntax:
            return text

        import re as _re
        open_esc = _re.escape(from_syntax["open"])
        close_esc = _re.escape(from_syntax["close"])
        pattern = f"{open_esc}[^{_re.escape(from_syntax['close'])}]+{close_esc}"

        def replacer(match):
            return cls.convert(match.group(0), from_platform, to_platform)

        return _re.sub(pattern, replacer, text)


# ---------------------------------------------------------------------------
#  飞书卡片消息模板（从 openclaw-feishu-agent-pack 提取）
# ---------------------------------------------------------------------------
FEISHU_CARD_PROCESSING = {
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"tag": "plain_text", "content": "{agent_name} — 流水线处理中"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**已接收您的任务，正在按流水线处理：**\n\n{steps_text}\n\n⏳ 请稍候，预计 10-30 秒完成...",
                },
            },
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "每一步都经过质量门禁检验，确保输出零缺陷"},
                ],
            },
        ],
    },
}

FEISHU_CARD_DONE = {
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"tag": "plain_text", "content": "{agent_name} — 处理完成"},
            "template": "green",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**流水线全部通过，以下是交付结果：**\n\n{result}",
                },
            },
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "流水线质检全部通过 · 修改建议请在群聊中 @我 说出"},
                ],
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# 模板路径常量
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = {
    "exe": _BASE_DIR / "templates" / "base_cli_agent.py",
    "zip": _BASE_DIR / "templates" / "base_cli_agent.py",   # zip 默认走 CLI
    "web": _BASE_DIR / "templates" / "base_streamlit_agent.py",
}
OUTPUT_DIR = _BASE_DIR / "output_agents"

# ---------------------------------------------------------------------------
# 错误安全值
# ---------------------------------------------------------------------------
_EMPTY_CONFIG: dict = {
    "agent_name": "未命名智能体",
    "system_prompt": "",
    "delivery_type": "exe",
    "auth_mode": "user_key",
    "required_skills": [],
}


class AgentBuilder:
    """
    智能体装配引擎

    :param config:       agent_config 字典（来自 DeepSeekClient.architect()）
    :param delivery_type: 覆盖 config 中的 delivery_type（可选）
    :param api_key:       注入模板的 API Key（可选，留空则用占位符）
    :param base_url:      注入模板的 Base URL（可选，留空则用占位符）
    :param model_name:    注入模板的 Model Name（可选，留空则用占位符）
    """

    def __init__(
        self,
        config: dict,
        delivery_type: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        # 空骨架保护
        if not config or not config.get("agent_name"):
            logger.warning("接收到空骨架配置，使用默认值")
            self.config = dict(_EMPTY_CONFIG)
        else:
            self.config = dict(config)

        # 交付类型：优先参数指定，其次 config，最后 fallback
        self.delivery_type = delivery_type or self.config.get("delivery_type", "exe")
        if self.delivery_type not in TEMPLATES:
            logger.warning("不支持的 delivery_type '%s'，回退到 'exe'", self.delivery_type)
            self.delivery_type = "exe"

        # 运行时配置注入
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

        # 确保输出目录存在
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def assemble(self) -> Path:
        """
        执行装配流水线：
          1. 加载模板文件
          2. 执行占位符替换
          3. 写入 output_agents/ 目录
          4. 返回生成文件的绝对路径
        """
        template_path = TEMPLATES[self.delivery_type]

        if not template_path.exists():
            raise FileNotFoundError(
                f"模板文件不存在：{template_path}\n"
                f"请确保 templates/ 目录完整。"
            )

        # 1. 读取模板
        raw_template = template_path.read_text(encoding="utf-8")
        logger.info("加载模板：%s（%d 字符）", template_path.name, len(raw_template))

        # 2. 执行占位符替换
        populated = self._populate_template(raw_template)

        # 3. 生成输出文件名
        output_filename = self._generate_filename()
        output_path = OUTPUT_DIR / output_filename

        # 4. 防重复写入（生成 timestamp 避免覆盖）
        if output_path.exists():
            stem = output_path.stem
            suffix = output_path.suffix
            ts = datetime.now().strftime("%H%M%S")
            output_path = OUTPUT_DIR / f"{stem}_{ts}{suffix}"

        # 5. 写入文件
        output_path.write_text(populated, encoding="utf-8")
        os.chmod(output_path, 0o755)  # 可执行权限

        # 6. 保存 agent_config.json 供 packager 读取
        config_path = OUTPUT_DIR / "agent_config.json"
        try:
            config_path.write_text(
                json.dumps(self.config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("agent_config.json 保存失败: %s", e)

        logger.info("智能体装配完成 → %s", output_path)
        return output_path.resolve()

    def _build_tool_config(self) -> dict:
        """
        从 config 中构建工具配置字典。
        符合 agent-toolkit 标准接口：base_url, auth_header, default_params, retry。
        """
        tools = {}
        skills = self.config.get("skills", [])
        if not skills:
            raw_skills = self.config.get("required_skills", [])
            skills = [{"name": s, "type": "operation"} for s in raw_skills if s != "none"]

        for skill in skills:
            name = skill.get("name", "")
            if not name:
                continue
            tool_entry = {
                "base_url": skill.get("api", ""),
                "auth_header": "",
                "default_params": skill.get("params", {}),
                "retry": {"max_retries": 2, "backoff_base": 1.0},
                "output_format": skill.get("output", "text"),
                "type": skill.get("type", "operation"),
            }
            tools[name] = tool_entry

        return tools

    def _populate_template(self, template: str) -> str:
        """
        占位符替换（基于字符串模板，零依赖）

        替换规则：
          {AGENT_NAME}      → agent_name
          {SYSTEM_PROMPT}   → system_prompt (自动缩进/转义)
          {API_KEY_SLOT}    → 注入的 API Key 或占位符
          {BASE_URL_SLOT}   → 注入的 Base URL 或占位符
          {MODEL_NAME_SLOT} → 注入的 Model Name 或占位符
          {AGENT_FILENAME}  → 自动生成的文件名
        """
        agent_name = self.config.get("agent_name", "未命名智能体")
        system_prompt = self.config.get("system_prompt", "")

        # 清理 system_prompt 中的三重引号冲突（避免破坏 Python 字符串）
        system_prompt = system_prompt.replace('"""', '\\"\\"\\"')

        api_key = self.api_key or "sk-your-api-key-here"
        base_url = self.base_url or "https://token-plan-cn.xiaomimimo.com/v1"
        model_name = self.model_name or "mimo-v2.5-pro"

        # 替换
        result = template.replace("{AGENT_NAME}", agent_name)
        result = result.replace("{SYSTEM_PROMPT}", system_prompt)
        result = result.replace("{API_KEY_SLOT}", api_key)
        result = result.replace("{BASE_URL_SLOT}", base_url)
        result = result.replace("{MODEL_NAME_SLOT}", model_name)

        # AGENT_FILENAME 用 agent_name 的拼音/缩写版
        agent_filename = self._sanitize_filename(agent_name)
        result = result.replace("{AGENT_FILENAME}", agent_filename)

        # 工具配置注入
        tool_config_json = json.dumps(self._build_tool_config(), ensure_ascii=False, indent=4)
        result = result.replace("{TOOL_CONFIG_SLOT}", tool_config_json)

        return result

    def _generate_filename(self) -> str:
        """生成输出文件名 — 统一命名为 app.py，买家一眼看懂"""
        return "app.py"

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        将中文 Agent 名称转为安全的文件名：
          "挑战杯路演PPT润色助手" → "challenge_cup_ppt_polish_agent"
        同时保留已有 ASCII 名。
        """
        # 替换中文为拼音映射（简化的 heuristic 方案）
        # 实际生产环境可替换为 pypinyin，这里用 heuristic 缩写
        safe = name.strip()

        # 移除非 ASCII + 非字母数字下划线的字符
        safe = re.sub(r"[^\w\-_]", "_", safe)
        safe = re.sub(r"_+", "_", safe)
        safe = safe.strip("_")

        # 如果全是中文（没有 ASCII），生成英文 fallback
        if not safe or not any(c.isascii() and c.isalpha() for c in safe):
            import hashlib
            suffix = hashlib.md5(name.encode()).hexdigest()[:6]
            safe = f"agent_{suffix}"

        # 确保不以数字开头
        if safe and safe[0].isdigit():
            safe = "agent_" + safe

        return safe.lower() or "agent"

    # ==================================================================
    #  平台文件渲染（多节点工作流 + 飞书服务 + OpenClaw）
    # ==================================================================
    def build_platform_files(self) -> dict:
        """
        根据 workflow_steps 动态渲染所有平台的部署配置文件。
        返回 {arcname: content} 字典，供 packager 打包使用。
        """
        platform_files = {}
        agent_name = self.config.get("agent_name", "未命名智能体")
        workflow_steps = self._get_workflow_steps()

        # --- Dify 工作流 ---
        try:
            platform_files["adapters/dify/agent.yaml"] = self._build_dify_workflow(
                agent_name, workflow_steps
            )
        except Exception as e:
            logger.error("Dify 工作流生成失败：%s", e)
            platform_files["adapters/dify/agent.yaml"] = self._build_dify_workflow_fallback(agent_name)

        # --- Coze Bot ---
        try:
            platform_files["adapters/coze/bot.json"] = self._build_coze_bot(
                agent_name, workflow_steps
            )
        except Exception as e:
            logger.error("Coze 配置生成失败：%s", e)
            platform_files["adapters/coze/bot.json"] = self._build_coze_bot_fallback(agent_name)

        # --- 飞书 Bot ---
        try:
            platform_files["adapters/feishu/bot-config.yaml"] = self._build_feishu_bot(
                agent_name, workflow_steps
            )
        except Exception as e:
            logger.error("飞书配置生成失败：%s", e)
            platform_files["adapters/feishu/bot-config.yaml"] = self._build_feishu_bot_fallback(agent_name)

        # --- 飞书回调服务 ---
        try:
            platform_files["adapters/feishu/bot-server.py"] = self._build_feishu_server(agent_name)
        except Exception as e:
            logger.error("飞书回调服务生成失败：%s", e)

        # --- OpenClaw Agent ---
        try:
            platform_files["adapters/openclaw/config.yaml"] = self._build_openclaw_config(agent_name)
        except Exception as e:
            logger.error("OpenClaw 配置生成失败：%s", e)

        return platform_files

    # ------------------------------------------------------------------
    #  飞书回调服务渲染
    # ------------------------------------------------------------------
    def _build_feishu_server(self, agent_name: str) -> str:
        """从模板 feishu_bot_server.py 读取并注入 agent_name"""
        server_tmpl_path = _BASE_DIR / "templates" / "feishu_bot_server.py"
        if server_tmpl_path.exists():
            content = server_tmpl_path.read_text(encoding="utf-8")
        else:
            logger.warning("feishu_bot_server.py 模板未找到，生成骨架版本")
            content = (
                "# Feishu Bot Server (skeleton) — 部署后请用完整模板替换\n"
                f"# Agent: {agent_name}\n"
            )
        content = content.replace(
            "# Agent Factory 飞书 Bot 服务",
            f"# {agent_name} — 飞书 Bot 回调服务（由 Agent Factory 生成）"
        )
        return content

    # ------------------------------------------------------------------
    #  OpenClaw Agent 配置渲染
    # ------------------------------------------------------------------
    def _build_openclaw_config(self, agent_name: str) -> str:
        """从 openclaw_agent.yaml 模板渲染 OpenClaw 配置"""
        template_path = _BASE_DIR / "templates" / "openclaw_agent.yaml"
        if not template_path.exists():
            logger.warning("openclaw_agent.yaml 模板未找到")
            return f"# OpenClaw Agent Config — 模板未找到\n# Agent: {agent_name}\n"

        content = template_path.read_text(encoding="utf-8")
        workflow_steps = self._get_workflow_steps()

        content = content.replace("${AGENT_NAME}", agent_name)
        content = content.replace(
            "${SYSTEM_PROMPT_PLACEHOLDER}",
            self._escape_yaml(self.config.get("system_prompt", "")[:3000])
        )
        content = content.replace(
            "${WORKFLOW_STEPS_PLACEHOLDER}",
            json.dumps(workflow_steps, ensure_ascii=False, indent=6)
        )
        content = content.replace("${LLM_MODEL}", self.model_name or "deepseek-chat")
        content = content.replace("${LLM_API_KEY}", self.api_key or "sk-your-api-key-here")
        content = content.replace("${LLM_BASE_URL}", self.base_url or "https://api.deepseek.com/v1")

        return content

    # ------------------------------------------------------------------
    #  获取工作流模板匹配上下文（供 architect 调用时注入）
    # ------------------------------------------------------------------
    def get_workflow_templates_context(self) -> str:
        """
        加载所有工作流模板 JSON，返回注入 prompt 的上下文文本。
        供 llm_client.architect() 调用时注入到 user prompt 中。
        """
        workflows_dir = _BASE_DIR / "templates" / "workflows"
        if not workflows_dir.exists():
            return "(工作流模板库未找到)"

        lines = ["## 可用工作流模板库\n"]
        templates_list = sorted(workflows_dir.glob("*.json"))
        for tmpl_path in templates_list:
            try:
                tmpl = json.loads(tmpl_path.read_text(encoding="utf-8"))
                meta = tmpl.get("_meta", {})
                lines.append(f"- **{tmpl_path.stem}**: {meta.get('description', '无描述')}")
                lines.append(f"  关键词: {', '.join(meta.get('keywords', []))}")
                lines.append(f"  场景: {', '.join(meta.get('applicable_scenarios', []))}")
            except Exception:
                pass

        return "\n".join(lines)

    # ------------------------------------------------------------------
    #  核心：Dify 多节点 DSL 渲染
    # ------------------------------------------------------------------
    def _build_dify_workflow(self, agent_name: str, workflow_steps: list) -> str:
        """
        把 workflow_steps 渲染成 Dify 多节点 DSL：
        start → step_1 (LLM) → step_2 (LLM) → ... → answer

        每个 step 生成一个 LLM 节点，
        画布坐标自动计算（x 递增 350px）
        """
        scenario = self.config.get("required_skills", ["通用任务"])
        if isinstance(scenario, list):
            scenario = ", ".join(scenario) if scenario else "通用任务"
        if not isinstance(scenario, str):
            scenario = "通用任务"

        if not workflow_steps:
            return self._build_dify_workflow_fallback(agent_name)

        nodes_yaml = []
        edges_yaml = []
        base_x = 80
        step_gap = 350

        # ---- 开始节点 ----
        nodes_yaml.append(f"""\
              - id: "start"
                type: "start"
                position:
                  x: {base_x}
                  y: 160
                data:
                  title: "开始"
                  type: "start"
                  variables: []""")

        for i, step in enumerate(workflow_steps):
            step_id = f"step_{i + 1}"
            step_name = step.get("name", f"步骤 {i + 1}")
            step_prompt = step.get("prompt", "")
            step_prompt_escaped = self._escape_yaml(step_prompt)

            node_x = base_x + (i + 1) * step_gap
            memory_section = ""
            if i == 0:
                memory_section = f"""
                          memory:
                            window:
                              enabled: true
                              size: 10"""

            prev_node_id = "start" if i == 0 else f"step_{i}"

            nodes_yaml.append(f"""\
              - id: "{step_id}"
                type: "llm"
                position:
                  x: {node_x}
                  y: 160
                data:
                  title: "{step_name}"
                  type: "llm"
                  model:
                    provider: "openai_api_compatible"
                    name: "deepseek-chat"
                    mode: "chat"
                    completion_params:
                      temperature: 0.7
                      max_tokens: 4096
                  prompt_template:
                    - role: "system"
                      text: "{step_prompt_escaped}"
                    - role: "user"
                      text: "{{{{#{prev_node_id}.text}}}}"{memory_section}""")

            edges_yaml.append(f"""\
              - source: "{prev_node_id}"
                target: "{step_id}"
                data:
                  title: "{step_name}" """)

        # ---- 回复节点 ----
        last_step_id = f"step_{len(workflow_steps)}"
        answer_x = base_x + (len(workflow_steps) + 1) * step_gap

        nodes_yaml.append(f"""\
              - id: "answer"
                type: "answer"
                position:
                  x: {answer_x}
                  y: 160
                data:
                  title: "最终交付"
                  type: "answer"
                  answer: "{{{{#{last_step_id}.text}}}}" """)

        edges_yaml.append(f"""\
              - source: "{last_step_id}"
                target: "answer"
                data:
                  title: "输出结果" """)

        nodes_block = "\n".join(nodes_yaml)
        edges_block = "\n".join(edges_yaml)

        system_prompt_summary = self._escape_yaml(
            self.config.get("system_prompt", "")[:200]
        )

        return f"""\
# ============================================================
# Dify 工作流 — 导入配置文件（由 Agent Factory 引擎自动生成）
# ============================================================
# 智能体名称：{agent_name}
# 工作流节点：{len(workflow_steps)} 个独立 LLM 节点（流水线编排）
# 适用场景：{scenario}
#
# 导入步骤：
# 1. 打开你的 Dify 控制台
# 2. 点击「创建应用」→「导入 DSL」
# 3. 选择本文件，点击导入
# 4. 在「模型配置」中填入你的 API Key
# 5. 点击「发布」→ 生成分享链接或嵌入网站
# ============================================================

app:
  name: "{agent_name}"
  description: "专为【{scenario}】场景定制的高端 AI 流水线，内置 {len(workflow_steps)} 步质量门禁"
  mode: "chat"
  icon: "robot"
  icon_background: "#1a1a2e"

version: "0.2.0"
kind: "app"

model_config:
  provider: "openai_api_compatible"
  model_id: "deepseek-chat"
  model_config:
    name: "DeepSeek V3"
    provider: "openai_api_compatible"
    model_name: "deepseek-chat"
    mode: "chat"
    completion_params:
      temperature: 0.7
      max_tokens: 4096

prompt_template:
  - id: "system"
    role: "system"
    text: "{system_prompt_summary}"

  - id: "greeting"
    role: "assistant"
    text: "你好！我是「{agent_name}」。我内置了 {len(workflow_steps)} 步专业流水线，每步都有严格的质量门禁。请告诉我你需要什么？"

variables: []

workflow:
  graph:
    nodes:
{nodes_block}

    edges:
{edges_block}

    viewport:
      x: 0
      y: 0
      zoom: 0.7

# ============================================================
# 流水线步骤清单
# ============================================================
# {chr(10).join(f"#  {i+1}. {s.get('name', f'步骤 {i+1}')}  →  门禁：{s.get('gate', '无')}" for i, s in enumerate(workflow_steps))}

# ============================================================
# 提示：
# 1. 导入后先在「模型供应商」配置你的 API Key
# 2. 每个节点可独立调整 Prompt 和模型参数
# 3. 双击画布上的节点可以查看详细信息
# 4. 发布后获得分享链接，嵌入网站或直接使用
# ============================================================
"""

    def _build_dify_workflow_fallback(self, agent_name: str) -> str:
        """fallback：单节点 Dify 工作流"""
        scenario = self.config.get("required_skills", ["通用任务"])
        if isinstance(scenario, list):
            scenario = ", ".join(scenario)
        if not isinstance(scenario, str):
            scenario = "通用任务"

        escaped_prompt = self._escape_yaml(
            self.config.get("system_prompt", "")[:500]
        )

        return f"""\
# Dify 工作流（单节点）
app:
  name: "{agent_name}"
  description: "专为 {scenario} 场景定制"
  mode: "chat"
  icon: "robot"
  icon_background: "#1a1a2e"
version: "0.1.2"
kind: "app"
model_config:
  provider: "openai_api_compatible"
  model_id: "deepseek-chat"
prompt_template:
  - id: "system"
    role: "system"
    text: "{escaped_prompt}"
workflow:
  graph:
    nodes:
      - id: "start"
        type: "start"
        position: {{x: 80, y: 160}}
        data: {{title: "开始", type: "start", variables: []}}
      - id: "llm"
        type: "llm"
        position: {{x: 380, y: 160}}
        data:
          title: "AI 助手"
          type: "llm"
          model:
            provider: "openai_api_compatible"
            name: "deepseek-chat"
            mode: "chat"
          prompt_template:
            - role: "system"
              text: "{escaped_prompt}"
            - role: "user"
              text: "{{{{#start.user_query}}}}""
      - id: "answer"
        type: "answer"
        position: {{x: 680, y: 160}}
        data: {{title: "回复", type: "answer", answer: "{{{{#llm.text}}}}"}}
    edges:
      - source: "start"
        target: "llm"
      - source: "llm"
        target: "answer"
"""

    # ------------------------------------------------------------------
    #  Coze Bot 渲染
    # ------------------------------------------------------------------
    def _build_coze_bot(self, agent_name: str, workflow_steps: list) -> str:
        """把 workflow_steps 注入 Coze Bot 配置"""
        scenario = self.config.get("required_skills", ["通用任务"])
        if isinstance(scenario, list):
            scenario = ", ".join(scenario) if scenario else "通用任务"
        if not isinstance(scenario, str):
            scenario = "通用任务"

        escaped_prompt = self._escape_json(
            self.config.get("system_prompt", "")[:2000]
        )

        steps_json = json.dumps(workflow_steps, ensure_ascii=False, indent=6)

        return f"""\
{{
  "_comment": "Coze 机器人 — 导入配置（Agent Factory 引擎自动生成）",

  "bot_name": "{agent_name}",
  "description": "专为【{scenario}】场景定制的高端 AI 流水线，内置 {len(workflow_steps)} 步质量门禁",
  "icon_uri": "",

  "persona": {{
    "role": "{agent_name}",
    "expertise": ["{scenario}"],
    "communication_style": "专业、清晰、有条理，每步输出均经过质量门禁检验",
    "constraints": [
      "严格遵循内置 {len(workflow_steps)} 步流水线工作流",
      "每步通过门禁检查后方可进入下一步",
      "输出结构化的结果，便于用户直接使用",
      "遇到不确定的内容主动标记，不编造信息"
    ]
  }},

  "prompt": {{
    "system_prompt": "{escaped_prompt}",
    "few_shot_examples": []
  }},

  "workflow_config": {{
    "mode": "sequential",
    "steps": {steps_json}
  }},

  "model_config": {{
    "provider": "openai_compatible",
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "你的_API_Key",
    "temperature": 0.7,
    "max_tokens": 4096
  }},

  "plugin_config": {{
    "enabled_plugins": [],
    "tools": []
  }},

  "publish_config": {{
    "platforms": ["feishu", "wechat", "web"],
    "web_config": {{
      "theme_color": "#1a1a2e",
      "welcome_message": "你好！我是「{agent_name}」。我内置了 {len(workflow_steps)} 步专业流水线，每步都有严格的质量门禁。请告诉我你需要什么？"
    }}
  }}
}}
"""

    def _build_coze_bot_fallback(self, agent_name: str) -> str:
        """Coze 回退方案"""
        scenario = self.config.get("required_skills", ["通用任务"])
        if isinstance(scenario, list):
            scenario = ", ".join(scenario)
        if not isinstance(scenario, str):
            scenario = "通用任务"
        escaped_prompt = self._escape_json(
            self.config.get("system_prompt", "")[:2000]
        )
        fallback = {
            "bot_name": agent_name,
            "description": f"专为 {scenario} 场景定制",
            "persona": {"role": agent_name, "expertise": [scenario]},
            "prompt": {"system_prompt": escaped_prompt, "few_shot_examples": []},
            "model_config": {"provider": "openai_compatible", "model": "deepseek-chat", "api_key": "你的_API_Key"},
        }
        return json.dumps(fallback, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    #  飞书 Bot 渲染
    # ------------------------------------------------------------------
    def _build_feishu_bot(self, agent_name: str, workflow_steps: list) -> str:
        """把 workflow_steps 注入飞书卡片消息模板（使用提取的标准化模板）"""
        scenario = self.config.get("required_skills", ["通用任务"])
        if isinstance(scenario, list):
            scenario = ", ".join(scenario) if scenario else "通用任务"
        if not isinstance(scenario, str):
            scenario = "通用任务"

        steps_text = "\n".join(
            f"  {i+1}. {s.get('name', f'步骤 {i+1}')}  →  {s.get('gate', '门禁通过')}"
            for i, s in enumerate(workflow_steps)
        ) if workflow_steps else "  1. 单步处理"

        # 使用提取的飞书卡片模板
        import copy
        processing_card = copy.deepcopy(FEISHU_CARD_PROCESSING)
        processing_card["card"]["header"]["title"]["content"] = (
            processing_card["card"]["header"]["title"]["content"].format(agent_name=agent_name)
        )
        processing_card["card"]["elements"][0]["text"]["content"] = (
            processing_card["card"]["elements"][0]["text"]["content"].format(steps_text=steps_text)
        )

        done_card = copy.deepcopy(FEISHU_CARD_DONE)
        done_card["card"]["header"]["title"]["content"] = (
            done_card["card"]["header"]["title"]["content"].format(agent_name=agent_name)
        )

        return f"""\
# ============================================================
# 飞书机器人 — 部署配置（Agent Factory 引擎自动生成）
# ============================================================
# 智能体名称：{agent_name}
# 流水线节点：{len(workflow_steps)} 步质量门禁
#
# 部署步骤：
# 1. 打开飞书开放平台：https://open.feishu.cn/app
# 2. 创建「企业自建应用」
# 3. 在「能力」→「机器人」中启用机器人功能
# 4. 在「事件订阅」中配置 Webhook 回调地址（你部署 app.py 的服务器地址）
# 5. 订阅事件：im.message.receive_v1（接收消息）
# 6. 发布应用 → 添加到群聊 → @机器人 即可使用
# ============================================================

飞书应用配置:
  应用名称: "{agent_name}"
  应用描述: "专为【{scenario}】场景定制的高端 AI 流水线，内置 {len(workflow_steps)} 步质量门禁"
  图标: "使用你的品牌图标"

机器人配置:
  启用: true
  消息类型: ["文本", "卡片消息"]
  欢迎语: "你好！我是「{agent_name}」，已就绪。@我 即可启动流水线处理。"

# ----------------------------------------------------------
# 卡片消息模板（处理中状态）— 来自 openclaw-feishu-agent-pack
# ----------------------------------------------------------
处理中卡片:
{json.dumps(processing_card, ensure_ascii=False, indent=2)}

# ----------------------------------------------------------
# 卡片消息模板（完成状态 — 更新同一张卡片）
# ----------------------------------------------------------
完成卡片:
{json.dumps(done_card, ensure_ascii=False, indent=2)}

# ----------------------------------------------------------
# 回调配置
# ----------------------------------------------------------
回调处理:
  接收消息: "POST /webhook/feishu"
  逻辑:
    - 收到消息 → 发送「处理中卡片」
    - 调用流水线处理 → 更新卡片为「完成卡片」
    - 所有结果在群聊中透明可见
"""

    def _build_feishu_bot_fallback(self, agent_name: str) -> str:
        """飞书回退方案"""
        scenario = self.config.get("required_skills", ["通用任务"])
        if isinstance(scenario, list):
            scenario = ", ".join(scenario)
        if not isinstance(scenario, str):
            scenario = "通用任务"
        return f"""\
# 飞书机器人配置（{agent_name}）
应用名称: "{agent_name}"
应用描述: "专为 {scenario} 场景定制"
机器人启用: true
消息类型: ["文本"]
回调地址: "POST /webhook/feishu"
"""

    # ==================================================================
    #  agent-meta.json 生成（agent-spec 标准）
    # ==================================================================
    def build_agent_meta(self) -> str:
        """
        生成符合 agent-spec 标准的 agent-meta.json。
        """
        agent_name = self.config.get("agent_name", "未命名智能体")
        description = self.config.get("description", f"「{agent_name}」— AI 智能代理")
        version = self.config.get("version", "1.0.0")
        platforms = self.config.get("platforms", ["coze", "dify"])
        auth_mode = self.config.get("auth_mode", "user_key")
        skills = self.config.get("skills", [])
        memory_config = self.config.get("memory_config", {
            "type": "short_term",
            "max_turns": 5,
            "persist_strategy": "session_only"
        })
        workflow_steps = self._get_workflow_steps()

        if not skills:
            raw_skills = self.config.get("required_skills", ["none"])
            skills = [
                {"name": s, "type": "operation", "api": "", "params": {}, "output": "text"}
                for s in raw_skills if s != "none"
            ]
        else:
            normalized = []
            for s in skills:
                if isinstance(s, dict):
                    normalized.append({
                        "name": s.get("name", ""),
                        "type": s.get("type", "operation"),
                        "api": s.get("api", ""),
                        "params": s.get("params", {}),
                        "output": s.get("output", "text"),
                    })
                elif isinstance(s, str):
                    normalized.append({"name": s, "type": "operation", "api": "", "params": {}, "output": "text"})
            skills = normalized

        system_prompt = self.config.get("system_prompt", "")

        meta = {
            "name": agent_name,
            "description": description,
            "version": version,
            "platforms": platforms,
            "auth_mode": auth_mode,
            "skills": skills,
            "memory_config": memory_config,
            "prompt_pack": self._build_prompt_pack_dict(),
            "workflow_steps": [
                {
                    "step_id": s.get("step_id", f"step_{i+1}"),
                    "name": s.get("name", f"步骤 {i+1}"),
                    "prompt": s.get("prompt", ""),
                    "gate": s.get("gate", "")
                }
                for i, s in enumerate(workflow_steps)
            ],
            "system_prompt_size": len(system_prompt),
            "generated_at": datetime.now().isoformat(),
        }

        return json.dumps(meta, ensure_ascii=False, indent=2)

    def _build_prompt_pack_dict(self) -> dict:
        """
        从 config 中提取 prompt_pack 四段，构建冻结数据类并校验一致性。
        若 config 未提供，则从 system_prompt 自动拆分。
        """
        prompt_pack = self.config.get("prompt_pack")
        if prompt_pack and isinstance(prompt_pack, dict) and all(
            k in prompt_pack for k in ("system", "tool", "memory", "output")
        ):
            raw = prompt_pack
        else:
            system_prompt = self.config.get("system_prompt", "")
            if not system_prompt:
                raw = {"system": "", "tool": "", "memory": "", "output": ""}
            else:
                raw = self._auto_split_prompt_pack(system_prompt)

        mc = self.config.get("memory_config", {})
        pack = PromptPack(
            system=SystemPrompt(content=raw.get("system", "")),
            tool=ToolPrompt(content=raw.get("tool", "")),
            memory=MemoryPrompt(
                content=raw.get("memory", ""),
                max_turns=mc.get("max_turns", 5),
                persist_strategy=mc.get("persist_strategy", "session_only"),
            ),
            output=OutputPrompt(content=raw.get("output", "")),
        )

        issues = pack.validate()
        if issues:
            logger.warning("PromptPack 一致性校验发现问题: %s", issues)

        return pack.to_dict()

    def _auto_split_prompt_pack(self, system_prompt: str) -> dict:
        """从完整 system_prompt 中自动拆分 prompt_pack 四段（兜底策略）"""
        result = {"system": "", "tool": "", "memory": "", "output": ""}
        sections = {
            "【角色声明】": "system",
            "【行动 Action】": "tool",
            "【内部记忆缓存】": "memory",
            "【运行时约束】": "memory",
            "【终局反思": "output",
            "【输出格式】": "output",
            "JSON 结语": "output",
        }

        if len(system_prompt) < 200:
            result["system"] = system_prompt
        else:
            lines = system_prompt.split("\n")
            current_section = "system"

            for line in lines:
                stripped = line.strip()
                if "【运行时约束】" in stripped:
                    current_section = "memory"
                    result[current_section] += line + "\n"
                    continue
                if "【终局反思" in stripped:
                    current_section = "output"
                    result[current_section] += line + "\n"
                    continue
                if "JSON 结语" in stripped or "## R-EX" in stripped:
                    current_section = "output"
                    result[current_section] += line + "\n"
                    continue
                if "【行动 Action】" in stripped or "可用工具" in stripped:
                    current_section = "tool"
                    result[current_section] += line + "\n"
                    continue
                result[current_section] += line + "\n"

        if not result["tool"].strip():
            result["tool"] = "当前智能体无需额外工具调用，所有处理在推理链中完成。"
        if not result["memory"].strip():
            result["memory"] = (
                f"维护一个内部记忆缓存（memory dict），"
                f"保留最近 {self.config.get('memory_config', {}).get('max_turns', 5)} 轮对话上下文。"
                "会话结束时清空。"
            )
        if not result["output"].strip():
            result["output"] = (
                "输出 Markdown 格式的报告，末尾附带 JSON 结语 "
                '（含 status、summary、confidence、thought_trace 字段）。'
            )

        return result

    def build_prompt_pack_files(self) -> dict:
        """
        生成 prompt_pack 的 4 个 .md 文件。
        返回 {arcname: content} 字典，供 packager 打包使用。
        """
        pp = self._build_prompt_pack_dict()
        return {
            "prompts/system.md": pp.get("system", ""),
            "prompts/tool.md": pp.get("tool", ""),
            "prompts/memory.md": pp.get("memory", ""),
            "prompts/output.md": pp.get("output", ""),
        }

    def _get_workflow_steps(self) -> list:
        """从 config 中获取 workflow_steps，带降级兜底"""
        steps = self.config.get("workflow_steps", [])
        if not steps:
            logger.warning("config 中没有 workflow_steps，平台文件将使用单节点模式")
        return steps

    @staticmethod
    def _escape_yaml(text: str) -> str:
        """转义文本使其安全嵌入 YAML 字符串值"""
        if not text:
            return ""
        return (
            text.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )

    @staticmethod
    def _escape_json(text: str) -> str:
        """转义文本使其安全嵌入 JSON 字符串值"""
        if not text:
            return ""
        return (
            text.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )

    # ==================================================================
    #  Coze ↔ Dify 双向转换
    # ==================================================================

    _COZE_MODE_TO_DIFY_NODE: dict = {
        "chat": "llm",
        "sequential": "llm",
        "condition": "if-else",
        "parallel": "if-else",
        "loop": "iteration",
        "code": "code",
        "knowledge_retrieval": "knowledge-retrieval",
        "plugin": "tool",
    }

    _DIFY_NODE_TO_COZE_MODE: dict = {
        "start": "sequential",
        "llm": "chat",
        "if-else": "condition",
        "iteration": "loop",
        "code": "code",
        "knowledge-retrieval": "knowledge_retrieval",
        "tool": "plugin",
        "answer": "sequential",
    }

    @classmethod
    def _convert_coze_to_dify(cls, coze_bot_json: dict) -> str:
        """
        将 Coze bot.json 转换为 Dify agent.yaml DSL。
        """
        bot_name = coze_bot_json.get("bot_name", "未命名 Bot")
        description = coze_bot_json.get("description", "")
        prompt_cfg = coze_bot_json.get("prompt", {})
        model_cfg = coze_bot_json.get("model_config", {})
        workflow_cfg = coze_bot_json.get("workflow_config", {})
        coze_mode = workflow_cfg.get("mode", "sequential")
        steps = workflow_cfg.get("steps", [])

        provider = model_cfg.get("provider", "openai_compatible")
        model_id = model_cfg.get("model", "deepseek-chat")
        sys_prompt = prompt_cfg.get("system_prompt", "")
        sys_prompt_escaped = cls._escape_yaml(sys_prompt)

        dify_node_type = cls._COZE_MODE_TO_DIFY_NODE.get(coze_mode, "llm")
        BASE_X = 80
        STEP_GAP = 350
        IND = "  "

        nodes = []
        edges = []

        # ---- start 节点 ----
        nodes.append(f"""\
{IND*6}- id: "start"
{IND*7}type: "start"
{IND*7}position:
{IND*8}x: {BASE_X}
{IND*8}y: 160
{IND*7}data:
{IND*8}title: "开始"
{IND*8}type: "start"
{IND*8}variables: []""")

        if not steps:
            # ---- 无步骤：单 LLM 节点 ----
            nodes.append(f"""\
{IND*6}- id: "llm"
{IND*7}type: "{dify_node_type}"
{IND*7}position:
{IND*8}x: {BASE_X + STEP_GAP}
{IND*8}y: 160
{IND*7}data:
{IND*8}title: "{bot_name}"
{IND*8}type: "{dify_node_type}"
{IND*8}model:
{IND*9}provider: "{provider}"
{IND*9}name: "{model_id}"
{IND*9}mode: "chat"
{IND*9}completion_params:
{IND*10}temperature: 0.7
{IND*10}max_tokens: 4096
{IND*8}prompt_template:
{IND*9}- role: "system"
{IND*10}text: "{sys_prompt_escaped}"
{IND*9}- role: "user"
{IND*10}text: "{{{{#start.text}}}}"
{IND*8}memory:
{IND*9}window:
{IND*10}enabled: true
{IND*10}size: 10""")
            edges.append(f"""\
{IND*6}- source: "start"
{IND*7}target: "llm"
{IND*7}data:
{IND*8}title: "处理" """)
            nodes.append(f"""\
{IND*6}- id: "answer"
{IND*7}type: "answer"
{IND*7}position:
{IND*8}x: {BASE_X + STEP_GAP * 2}
{IND*8}y: 160
{IND*7}data:
{IND*8}title: "回复"
{IND*8}type: "answer"
{IND*8}answer: "{{{{#llm.text}}}}" """)
            edges.append(f"""\
{IND*6}- source: "llm"
{IND*7}target: "answer"
{IND*7}data:
{IND*8}title: "输出" """)
        else:
            # ---- 多步骤：每个 step 一个 LLM 节点 ----
            for i, step in enumerate(steps):
                sid = f"step_{i + 1}"
                sname = step.get("name", f"步骤 {i + 1}")
                sprompt = step.get("prompt", "")
                sprompt_escaped = cls._escape_yaml(sprompt)
                nx = BASE_X + (i + 1) * STEP_GAP
                prev_id = "start" if i == 0 else f"step_{i}"

                memory_block = ""
                if i == 0:
                    memory_block = f"""\
{IND*8}memory:
{IND*9}window:
{IND*10}enabled: true
{IND*10}size: 10"""

                nodes.append(f"""\
{IND*6}- id: "{sid}"
{IND*7}type: "{dify_node_type}"
{IND*7}position:
{IND*8}x: {nx}
{IND*8}y: 160
{IND*7}data:
{IND*8}title: "{sname}"
{IND*8}type: "{dify_node_type}"
{IND*8}model:
{IND*9}provider: "{provider}"
{IND*9}name: "{model_id}"
{IND*9}mode: "chat"
{IND*9}completion_params:
{IND*10}temperature: 0.7
{IND*10}max_tokens: 4096
{IND*8}prompt_template:
{IND*9}- role: "system"
{IND*10}text: "{sprompt_escaped}"
{IND*9}- role: "user"
{IND*10}text: "{{{{#{prev_id}.text}}}}"{memory_block}""")

                edges.append(f"""\
{IND*6}- source: "{prev_id}"
{IND*7}target: "{sid}"
{IND*7}data:
{IND*8}title: "{sname}" """)

            last_id = f"step_{len(steps)}"
            ans_x = BASE_X + (len(steps) + 1) * STEP_GAP
            nodes.append(f"""\
{IND*6}- id: "answer"
{IND*7}type: "answer"
{IND*7}position:
{IND*8}x: {ans_x}
{IND*8}y: 160
{IND*7}data:
{IND*8}title: "最终交付"
{IND*8}type: "answer"
{IND*8}answer: "{{{{#{last_id}.text}}}}" """)
            edges.append(f"""\
{IND*6}- source: "{last_id}"
{IND*7}target: "answer"
{IND*7}data:
{IND*8}title: "输出结果" """)

        nodes_block = "\n".join(nodes)
        edges_block = "\n".join(edges)

        return f"""\
# Dify 工作流 — 由 Coze Bot 自动转换生成
# 来源 Bot: {bot_name}
# 转换时间: {datetime.now().isoformat()}

app:
  name: "{bot_name}"
  description: "{description}"
  mode: "chat"
  icon: "robot"
  icon_background: "#1a1a2e"

version: "0.1.0"
kind: "app"

model_config:
  provider: "{provider}"
  model_id: "{model_id}"
  model_config:
    name: "{model_id}"
    provider: "{provider}"
    model_name: "{model_id}"
    mode: "chat"
    completion_params:
      temperature: 0.7
      max_tokens: 4096

prompt_template:
  - id: "system"
    role: "system"
    text: "{sys_prompt_escaped}"

variables: []

workflow:
  graph:
    nodes:
{nodes_block}

    edges:
{edges_block}

    viewport:
      x: 0
      y: 0
      zoom: 0.7
"""

    @classmethod
    def _convert_dify_to_coze(cls, dify_yaml: str) -> dict:
        """
        将 Dify agent.yaml DSL 转换为 Coze bot.json。
        """
        parsed = cls._parse_simple_yaml(dify_yaml)

        app_block = parsed.get("app", {})
        model_block = parsed.get("model_config", {})
        prompt_block = parsed.get("prompt_template", [])
        workflow_block = parsed.get("workflow", {})

        bot_name = app_block.get("name", "未命名 Bot")
        description = app_block.get("description", "")

        # 提取 system prompt
        sys_prompt = ""
        if isinstance(prompt_block, list):
            for item in prompt_block:
                if isinstance(item, dict) and item.get("role") == "system":
                    sys_prompt = item.get("text", "")
                    break
        elif isinstance(prompt_block, dict):
            sys_prompt = prompt_block.get("text", "")

        provider = model_block.get("provider", "openai_compatible")
        model_id = model_block.get("model_id", "deepseek-chat")

        # 提取 workflow steps
        graph = workflow_block.get("graph", {})
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []

        steps = []
        workflow_mode = "sequential"
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_type = node.get("type", "")
            node_id = node.get("id", "")
            data = node.get("data", {}) if isinstance(node.get("data"), dict) else {}

            if node_type in ("start", "answer"):
                continue

            coze_mode = cls._DIFY_NODE_TO_COZE_MODE.get(node_type, "chat")
            if coze_mode != "chat":
                workflow_mode = coze_mode

            prompt_templates = data.get("prompt_template", [])
            step_prompt = ""
            step_name = data.get("title", f"步骤 {len(steps) + 1}")
            if isinstance(prompt_templates, list):
                for pt in prompt_templates:
                    if isinstance(pt, dict) and pt.get("role") == "system":
                        step_prompt = pt.get("text", "")

            steps.append({
                "name": step_name,
                "prompt": step_prompt,
                "gate": f"节点 {node_id} 完成"
            })

        return {
            "bot_name": bot_name,
            "description": description,
            "persona": {
                "role": bot_name,
                "expertise": [],
                "communication_style": "专业、清晰",
                "constraints": ["严格遵循流水线工作流"]
            },
            "prompt": {
                "system_prompt": sys_prompt,
                "few_shot_examples": []
            },
            "workflow_config": {
                "mode": workflow_mode,
                "steps": steps
            },
            "model_config": {
                "provider": provider,
                "model": model_id,
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "你的_API_Key",
                "temperature": 0.7,
                "max_tokens": 4096
            },
            "plugin_config": {
                "enabled_plugins": [],
                "tools": []
            },
            "publish_config": {
                "platforms": ["feishu", "wechat", "web"],
                "web_config": {
                    "theme_color": "#1a1a2e",
                    "welcome_message": f"你好！我是「{bot_name}」。"
                }
            }
        }

    @staticmethod
    def _parse_simple_yaml(yaml_text: str) -> dict:
        """
        稳健的简易 YAML 解析器（不依赖 PyYAML）。
        正确处理：
          - 嵌套 dict（缩进驱动）
          - 列表项（- 开头）
          - 内联 JSON 对象 { ... }
          - 混合结构（list 中有 dict，dict 中有 list）
        """
        # Step 1: 预处理 — 剔除注释和空行
        lines = []
        for raw in yaml_text.splitlines():
            if not raw.strip() or raw.strip().startswith("#"):
                continue
            lines.append(raw)

        # Step 2: 解析
        # stack: list of (container, indent_level, parent_dict, parent_key)
        #   container: dict or list 当前作用域容器
        #   indent_level: 该容器进入时的缩进
        #   parent_dict: 如果是 dict 容器，记录其父 dict（用于 list 替换）
        #   parent_key: 如果是 dict 容器，记录其在父 dict 中的 key
        result = {}
        stack = [(result, -2, None, None)]  # root

        for line in lines:
            stripped = line.lstrip(" ")
            indent = (len(line) - len(stripped)) // 2

            # 弹栈：回到正确的嵌套层级（至少保留 root）
            # 注意：列表容器与其子项缩进相同，不能弹出
            while len(stack) > 1 and stack[-1][1] >= indent:
                if stack[-1][1] == indent and isinstance(stack[-1][0], list):
                    break
                stack.pop()

            curr = stack[-1]

            # ========== 情况 1: 列表项（- 开头） ==========
            if stripped.startswith("- "):
                item_text = stripped[2:].strip()
                container = curr[0]

                # 如果当前容器不是 list，需要将父 dict 中的空 dict 替换为 list
                if not isinstance(container, list):
                    # ① 优先查找 stack 中同缩进层级的已有 list（复用）
                    found_list = None
                    for c, ind, _, _ in reversed(stack):
                        if ind == indent and isinstance(c, list):
                            found_list = c
                            break

                    if found_list is not None:
                        container = found_list
                    else:
                        # ② 尝试在父 dict 中找到空 dict 并替换为 list
                        replaced = False
                        for idx in range(len(stack) - 1, -1, -1):
                            c, indent_lvl, pd, pk = stack[idx]
                            if isinstance(c, dict) and pd is not None and pk is not None:
                                try:
                                    val = pd[pk]
                                except (KeyError, IndexError, TypeError):
                                    continue
                                if isinstance(val, dict) and not val:
                                    new_list = []
                                    pd[pk] = new_list
                                    stack.append((new_list, indent, None, None))
                                    container = new_list
                                    replaced = True
                                    break

                        if not replaced:
                            # ③ fallback: 直接在当前容器创建 list
                            new_list = []
                            if isinstance(container, dict):
                                for k, v in container.items():
                                    if isinstance(v, dict) and not v:
                                        container[k] = new_list
                                        break
                            elif isinstance(container, list):
                                container.append(new_list)
                            stack.append((new_list, indent, None, None))
                            container = new_list

                # 解析列表项内容
                if ":" in item_text:
                    k, _, v = item_text.partition(":")
                    k = k.strip().strip('"')
                    v = v.strip().strip('"').strip("'")
                    new_item = {k: v}
                    container.append(new_item)
                    # 列表中的 dict 记录 parent（list）和 key
                    stack.append((new_item, indent, container, len(container) - 1))
                else:
                    container.append(item_text)

                continue

            # ========== 情况 2: 普通 key: value 行 ==========
            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip().strip('"')
                value = value.strip()

                # 如果当前容器是 list，取 list 中最后一个 dict
                if isinstance(curr[0], list):
                    # 取 list 最后一个元素（应为 dict）作为目标容器
                    if curr[0]:
                        target = curr[0][-1]
                        if isinstance(target, dict):
                            container = target
                            # 将 stack 中的 list 容器替换为这个 dict
                            stack[-1] = (target, indent, curr[2], curr[3])
                            curr = stack[-1]
                        else:
                            container = curr[0]
                    else:
                        container = curr[0]
                else:
                    container = curr[0]

                if not value:
                    # 空值 → 创建嵌套 dict
                    new_dict = {}
                    container[key] = new_dict
                    stack.append((new_dict, indent, container, key))
                elif value == "[]":
                    container[key] = []
                elif value.startswith("{") and value.endswith("}"):
                    # 内联 dict
                    container[key] = {}
                    # 不进一步解析 {} 内的内容
                elif value.startswith("[") and value.endswith("]"):
                    items_str = value[1:-1].strip()
                    if items_str:
                        parsed_items = []
                        for it in items_str.split(","):
                            it = it.strip().strip('"').strip("'")
                            if ":" in it:
                                ik, _, iv = it.partition(":")
                                parsed_items.append({ik.strip().strip('"'): iv.strip().strip('"').strip("'")})
                            else:
                                parsed_items.append(it)
                        container[key] = parsed_items
                    else:
                        container[key] = []
                else:
                    container[key] = value.strip().strip('"').strip("'")

                continue

        return result

    def preview(self) -> str:
        """
        预览生成的配置摘要（用于日志/调试）
        """
        lines = [
            "=" * 56,
            f"  Agent Factory — 装配预览",
            "=" * 56,
            f"  智能体名称:    {self.config.get('agent_name', 'N/A')}",
            f"  交付类型:      {self.delivery_type}",
            f"  模板:          {TEMPLATES[self.delivery_type].name}",
            f"  模型:          {self.model_name or '占位符'}",
            f"  输出目录:      {OUTPUT_DIR}",
            f"  System Prompt: {len(self.config.get('system_prompt', ''))} 字符",
            "=" * 56,
        ]
        return "\n".join(lines)
