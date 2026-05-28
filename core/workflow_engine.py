# -*- coding: utf-8 -*-
"""
统一工作流运行时引擎 — 消费 agent_config.json 中的 workflow_steps，在任意 Agent 中顺序执行。

使用方式（在生成的 Agent 中）:
    from workflow_engine import WorkflowEngine
    engine = WorkflowEngine(agent_config)
    result = engine.run(user_message, llm_client)

此运行时支持：
  1. 步骤顺序执行，上下文累积传递
  2. 门禁条件检查（gate function）
  3. 容错重试（max_retries）
  4. 知识库节点预留（knowledge_retrieval 步骤自动标记）
  5. 思考链追踪（thought_trace）
  6. JSON 结语自动生成
"""

import json
import re
from typing import Callable, Optional, Any
from dataclasses import dataclass, field


@dataclass
class WorkflowConfig:
    """工作流配置"""
    agent_name: str = ""
    system_prompt: str = ""
    workflow_steps: list = field(default_factory=list)
    max_retries: int = 2
    context_mode: str = "cumulative"  # cumulative / step_only / none


@dataclass
class StepResult:
    """单步执行结果"""
    step_id: str
    step_name: str
    prompt: str
    gate: str
    output: str = ""
    status: str = "pending"  # pending / running / pass / partial / fail
    retries: int = 0
    error: Optional[str] = None


@dataclass
class WorkflowResult:
    """工作流总体执行结果"""
    status: str = "pending"  # pending / running / success / partial / failed
    agent_name: str = ""
    summary: str = ""
    structured_output: dict = field(default_factory=dict)
    confidence: float = 0.0
    thought_trace: list = field(default_factory=list)
    self_correction_applied: list = field(default_factory=list)
    step_results: list = field(default_factory=list)
    next_steps_suggestion: str = ""


class WorkflowEngine:
    """
    统一工作流运行时引擎。
    
    Args:
        config: WorkflowConfig 工作流配置
        gate_fn: 可选的门禁检查函数，签名为 (step_result: StepResult) -> bool
        knowledge_search_fn: 可选的知识库检索函数，签名为 (query_text: str) -> str
    """
    
    def __init__(
        self,
        config: WorkflowConfig,
        gate_fn: Optional[Callable[[StepResult], bool]] = None,
        knowledge_search_fn: Optional[Callable[[str], str]] = None,
    ):
        self.config = config
        self._gate_fn = gate_fn or self._default_gate_check
        self._knowledge_search_fn = knowledge_search_fn
        self._memory_cache: dict = {}  # 会话级内部记忆缓存
    
    # ==================== 公共接口 ====================
    
    def run(self, user_message: str, llm_call_fn: Callable) -> WorkflowResult:
        """
        执行完整工作流。
        
        Args:
            user_message: 用户原始输入
            llm_call_fn: LLM 调用函数，签名为 (system_prompt: str, user_message: str) -> str
        
        Returns:
            WorkflowResult 工作流执行结果
        """
        if not self.config.workflow_steps:
            return self._empty_result()
        
        result = WorkflowResult(
            agent_name=self.config.agent_name,
            status="running",
        )
        cumulative_content = ""
        
        for step_config in self.config.workflow_steps:
            step_result = self._run_step(
                step_config, user_message, cumulative_content, llm_call_fn
            )
            result.step_results.append(step_result)
            result.thought_trace.append(
                f"[{step_result.status.upper()}] {step_result.step_name}: {step_result.output[:200]}..."
            )
            
            if step_result.status == "fail":
                result.status = "failed"
                result.summary = f"步骤 {step_result.step_name} 失败"
                return result
            
            # 更新累积上下文
            if self.config.context_mode == "cumulative":
                cumulative_content = step_result.output
            elif self.config.context_mode == "step_only":
                cumulative_content = step_result.output
        
        # 生成最终结语
        result.status = "success"
        result.summary = self._generate_summary(result.step_results)
        result.confidence = self._calculate_confidence(result.step_results)
        result.self_correction_applied = self._collect_corrections(result.step_results)
        result.next_steps_suggestion = self._suggest_next_steps(result)
        result.structured_output = self._build_structured_output(result)
        
        return result
    
    def run_step_by_step(
        self, user_message: str, llm_call_fn: Callable
    ):
        """
        生成器模式 — 逐步执行工作流，每步 yield StepResult。
        适合流式 UI（如 Streamlit）实时展示执行进度。
        """
        cumulative_content = ""
        
        for step_config in self.config.workflow_steps:
            step_result = self._run_step(
                step_config, user_message, cumulative_content, llm_call_fn
            )
            yield step_result
            
            if step_result.status == "fail":
                break
            
            if self.config.context_mode == "cumulative":
                cumulative_content = step_result.output
            elif self.config.context_mode == "step_only":
                cumulative_content = step_result.output
    
    # ==================== 内部方法 ====================
    
    def _run_step(
        self,
        step_config: dict,
        user_message: str,
        previous_output: str,
        llm_call_fn: Callable,
    ) -> StepResult:
        """执行单个步骤，含重试逻辑"""
        step_result = StepResult(
            step_id=step_config.get("step_id", ""),
            step_name=step_config.get("name", ""),
            prompt=step_config.get("prompt", ""),
            gate=step_config.get("gate", ""),
            status="running",
        )
        
        # 构建上下文
        context = user_message
        if previous_output and self.config.context_mode != "none":
            context = (
                f"用户原始需求: {user_message}\n\n"
                f"--- 上一步输出 ---\n{previous_output}\n---\n\n"
                f"请基于以上信息执行当前步骤。"
            )
        
        # 检查是否为知识库步骤
        if "【此步骤由平台知识库节点执行】" in step_result.prompt:
            step_result = self._run_knowledge_step(step_result, context)
            return step_result
        
        # 执行步骤，支持重试
        for attempt in range(self.config.max_retries + 1):
            try:
                raw_output = llm_call_fn(step_result.prompt, context)
                step_result.output = raw_output
            except Exception as e:
                step_result.retries = attempt + 1
                step_result.error = str(e)
                if attempt < self.config.max_retries:
                    continue
                step_result.status = "fail"
                return step_result
            
            # 门禁检查
            if self._gate_fn(step_result):
                step_result.status = "pass"
                break
            else:
                step_result.status = "partial"
                step_result.retries = attempt + 1
                if attempt < self.config.max_retries:
                    context = f"{context}\n\n[门禁检查未通过，请重试]\n门禁条件: {step_result.gate}\n上一轮输出: {raw_output[:500]}..."
        
        return step_result
    
    def _run_knowledge_step(self, step_result: StepResult, context: str) -> StepResult:
        """执行知识库检索步骤"""
        query = context
        if self._knowledge_search_fn:
            try:
                kb_result = self._knowledge_search_fn(query)
                step_result.output = kb_result
                step_result.status = "pass" if kb_result else "partial"
            except Exception as e:
                step_result.status = "partial"
                step_result.error = f"知识库检索失败: {e}"
                step_result.output = "知识库检索遇到问题，请人工提供相关资料。"
        else:
            step_result.status = "partial"
            step_result.output = (
                f"[知识库节点未接入] 需要检索关键词: {query[:200]}...\n"
                "请将相关文档作为上下文提供。"
            )
        return step_result
    
    def _default_gate_check(self, step_result: StepResult) -> bool:
        """默认门禁检查：输出非空且足够长"""
        return bool(step_result.output) and len(step_result.output.strip()) > 20
    
    def _generate_summary(self, step_results: list) -> str:
        """生成任务完成摘要"""
        pass_count = sum(1 for r in step_results if r.status == "pass")
        total = len(step_results)
        
        lines = [f"工作流执行完成: {pass_count}/{total} 步骤通过"]
        for r in step_results:
            status_icon = "✅" if r.status == "pass" else "⚠️" if r.status == "partial" else "❌"
            summary_line = r.output[:150].replace("\n", " ")
            lines.append(f"  {status_icon} {r.step_name}: {summary_line}...")
        
        return "\n".join(lines)
    
    def _calculate_confidence(self, step_results: list) -> float:
        """计算整体置信度"""
        if not step_results:
            return 0.0
        weights = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "pending": 0.0, "running": 0.0}
        scores = [weights.get(r.status, 0.0) for r in step_results]
        return round(sum(scores) / len(scores), 2)
    
    def _collect_corrections(self, step_results: list) -> list:
        """收集重试/修正记录"""
        corrections = []
        for r in step_results:
            if r.retries > 0:
                corrections.append(
                    f"{r.step_name}: 经过 {r.retries} 次重试后{'通过' if r.status == 'pass' else '未通过'}"
                )
        return corrections
    
    def _suggest_next_steps(self, result: WorkflowResult) -> str:
        """建议下一步操作"""
        if result.status == "success" and result.confidence >= 0.8:
            return "所有步骤已完成且置信度高，建议将结果交付用户。"
        elif result.status == "success" and result.confidence < 0.8:
            return "部分步骤置信度较低，建议人工审核后交付。"
        else:
            return "工作流部分失败，建议检查失败步骤并补充输入信息后重试。"
    
    def _build_structured_output(self, result: WorkflowResult) -> dict:
        """构建结构化输出"""
        return {
            "step_count": len(result.step_results),
            "pass_count": sum(1 for r in result.step_results if r.status == "pass"),
            "partial_count": sum(1 for r in result.step_results if r.status == "partial"),
            "fail_count": sum(1 for r in result.step_results if r.status == "fail"),
            "steps": [
                {
                    "step_id": r.step_id,
                    "name": r.step_name,
                    "status": r.status,
                    "output_length": len(r.output),
                    "retries": r.retries,
                }
                for r in result.step_results
            ],
        }
    
    def _empty_result(self) -> WorkflowResult:
        """空工作流结果"""
        return WorkflowResult(
            status="failed",
            summary="没有配置工作流步骤",
            thought_trace=["无工作流步骤可执行"],
        )
    
    # ==================== 便利方法 ====================
    
    def to_agent_output_json(self, result: WorkflowResult) -> str:
        """
        将 WorkflowResult 转换为 OSCAR-EX 格式的 JSON 结语。
        可直接作为 Agent 最终输出的结语部分。
        """
        return json.dumps(
            {
                "agent_name": result.agent_name or self.config.agent_name,
                "status": result.status,
                "summary": result.summary,
                "structured_output": result.structured_output,
                "confidence": result.confidence,
                "thought_trace": result.thought_trace,
                "next_steps_suggestion": result.next_steps_suggestion,
                "self_correction_applied": result.self_correction_applied,
            },
            ensure_ascii=False,
            indent=2,
        )
    
    def to_dify_dsl(self, result: WorkflowResult) -> dict:
        """
        将工作流步骤转为 Dify DSL 所需的节点配置。
        详见 dify_workflow.yml 模板。
        """
        nodes = []
        for i, step in enumerate(self.config.workflow_steps):
            node = {
                "id": f"node_{i+1}",
                "type": "llm" if "【此步骤由平台知识库节点执行】" not in step["prompt"] else "knowledge_retrieval",
                "title": step["name"],
                "data": {
                    "prompt": step["prompt"],
                    "gate": step["gate"],
                },
            }
            nodes.append(node)
        return {"nodes": nodes, "step_count": len(nodes)}


# ==================== 便捷工厂函数 ====================

def create_engine_from_config(
    agent_config: dict,
    gate_fn: Optional[Callable] = None,
    knowledge_search_fn: Optional[Callable] = None,
) -> WorkflowEngine:
    """从 agent_config JSON 直接创建引擎"""
    config = WorkflowConfig(
        agent_name=agent_config.get("agent_name", ""),
        system_prompt=agent_config.get("system_prompt", ""),
        workflow_steps=agent_config.get("workflow_steps", []),
    )
    return WorkflowEngine(config, gate_fn=gate_fn, knowledge_search_fn=knowledge_search_fn)
