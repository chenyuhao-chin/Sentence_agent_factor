# -*- coding: utf-8 -*-
"""
飞书 Bot 回调服务 — 可直接部署运行的 FastAPI 服务器，消费 Agent Factory 生成的 workflow_steps。

将本文件与 agent_config.json 放在同一目录下，安装依赖后启动：
    pip install fastapi uvicorn httpx
    python feishu_bot_server.py

然后配置飞书应用的「事件订阅」URL 为: http://你的服务器:8000/webhook/event
"""

import json
import hashlib
import hmac
import time
import os
from typing import Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# ========== 配置区 ==========
# 从环境变量读取（部署时务必设置）
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")

# LLM API 配置
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

app = FastAPI(title="Agent Factory Feishu Bot")

# ========== 工作流加载 ==========
def load_workflow() -> list:
    """从 agent_config.json 加载工作流步骤"""
    config_path = os.path.join(os.path.dirname(__file__), "agent_config.json")
    if not os.path.exists(config_path):
        print(f"[WARN] agent_config.json 未找到于 {config_path}，使用默认空工作流")
        return []
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config.get("workflow_steps", [])


# ========== 工作流执行引擎 ==========
async def call_llm(system_prompt: str, user_message: str, step_name: str) -> dict:
    """调用 LLM 执行单个步骤"""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "step": step_name,
            "content": data["choices"][0]["message"]["content"],
            "usage": data.get("usage", {}),
        }


async def execute_workflow(steps: list, user_message: str, send_card_update) -> str:
    """顺序执行工作流，每完成一步发送卡片更新"""
    results = []
    cumulative_content = ""  # 上下文累积
    
    for step in steps:
        # 发送进度卡片
        await send_card_update(f"正在执行: {step['name']} ...")
        
        # 构建上下文
        context = user_message
        if cumulative_content:
            context = f"用户原始需求: {user_message}\n\n上一步结果:\n{cumulative_content}"
        
        result = await call_llm(step["prompt"], context, step["name"])
        cumulative_content = result["content"]
        results.append({
            "step_id": step["step_id"],
            "step_name": step["name"],
            "output": result["content"][:2000],  # 截断防止卡片过长
            "gate": step["gate"],
        })
    
    # 生成最终摘要
    final_card = build_final_card(results)
    return final_card


def build_final_card(results: list) -> str:
    """构建最终结果卡片"""
    lines = ["**工作流执行完成**\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"**步骤{i}: {r['step_name']}**")
        lines.append(f"门禁: {r['gate']}")
        lines.append(f"输出摘要: {r['output'][:300]}...\n")
    return "\n".join(lines)


# ========== 飞书消息处理 ==========
async def get_tenant_access_token() -> str:
    """获取飞书 tenant_access_token"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        )
        data = resp.json()
        return data["tenant_access_token"]


async def send_feishu_card(open_id: str, content: str, token: str):
    """发送飞书卡片消息"""
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "Agent 工作流执行结果"},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": content},
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "由 Agent Factory 生成"}]},
            ],
        },
    }
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "open_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={"receive_id": open_id, "msg_type": "interactive", "content": json.dumps(card)},
        )


# ========== HTTP API ==========
@app.get("/health")
async def health():
    return {"status": "ok", "service": "Agent Factory Feishu Bot"}


@app.post("/webhook/event")
async def feishu_event(request: Request):
    """飞书事件回调入口"""
    body = await request.json()

    # 1. URL 验证（飞书首次配置回调地址时触发）
    if body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        return JSONResponse({"challenge": challenge})

    # 2. 消息事件处理
    if body.get("header", {}).get("event_type") == "im.message.receive_v1":
        event = body.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})

        # 只处理文本消息
        if message.get("message_type") != "text":
            return JSONResponse({"code": 0})

        content = json.loads(message.get("content", "{}"))
        user_text = content.get("text", "")

        if not user_text.strip():
            return JSONResponse({"code": 0})

        user_open_id = sender.get("sender_id", {}).get("open_id", "")

        # 获取 token
        try:
            token = await get_tenant_access_token()
        except Exception as e:
            print(f"[ERROR] 获取飞书 Token 失败: {e}")
            return JSONResponse({"code": 0})

        # 先发送"处理中"消息
        await send_feishu_card(user_open_id, "正在处理你的请求，请稍候 ...", token)

        # 加载并执行工作流
        steps = load_workflow()
        if not steps:
            await send_feishu_card(user_open_id, "未找到工作流配置，请联系管理员。", token)
            return JSONResponse({"code": 0})

        async def update_card(msg: str):
            """更新卡片内容"""
            await send_feishu_card(user_open_id, msg, token)

        try:
            final_card = await execute_workflow(steps, user_text, update_card)
        except Exception as e:
            final_card = f"工作流执行出错: {str(e)}"

        await send_feishu_card(user_open_id, final_card, token)

    return JSONResponse({"code": 0})


@app.post("/chat")
async def chat(request: Request):
    """通用对话接口 — 允许飞书以外的客户端直接调用"""
    body = await request.json()
    user_message = body.get("message", "")
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    steps = load_workflow()
    if not steps:
        return {"status": "error", "message": "no workflow configured"}

    results = []
    cumulative = ""
    for step in steps:
        context = user_message
        if cumulative:
            context = f"{user_message}\n\n上一步结果:\n{cumulative}"
        try:
            result = await call_llm(step["prompt"], context, step["name"])
        except Exception as e:
            results.append({"step": step["name"], "status": "error", "error": str(e)})
            continue
        cumulative = result["content"]
        results.append({
            "step": step["name"],
            "status": "ok",
            "output": result["content"][:3000],
            "gate": step["gate"],
        })
    return {"status": "ok", "results": results}


if __name__ == "__main__":
    import uvicorn
    print("Agent Factory 飞书 Bot 服务启动")
    print("=" * 50)
    print(f"LLM: {LLM_MODEL}  @ {LLM_BASE_URL}")
    print(f"飞书 App ID: {FEISHU_APP_ID or '(未设置)'}")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
