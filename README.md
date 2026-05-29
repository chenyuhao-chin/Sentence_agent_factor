# Sentence Agent Factory

> 一句话生成你的专属 AI 智能体。无需编程、无需部署、即开即用。

---

## 产品简介

**Sentence Agent Factory** 是一套 AI 智能体全自动生成系统。用户只需用一句话描述需求，系统即可自动生成包含完整工作流、多平台部署配置、持久记忆引擎的智能体交付包。

### 核心能力

| 能力 | 说明 |
|------|------|
| 一句话生成 | 输入需求 → AI 架构师设计 → 一键打包交付 |
| 多模型支持 | 兼容 DeepSeek / 通义千问 / 智谱GLM / 小米MiMo / Claude 中转等所有 OpenAI 兼容接口 |
| 多平台部署 | 自动生成飞书 / Coze / Dify / OpenClaw 四大平台部署配置 |
| 持久记忆 | 内置 SQLite 记忆引擎，跨会话记忆用户偏好，自动进化 |
| 工作流引擎 | 支持多步骤流水线编排，每步独立质量门禁 |
| 卡密系统 | 内置卡密管理后台，支持月卡/次卡，适配知识付费交付场景 |

### 交付物结构

```
智能体名称_v1.0/
├── app.py                    # CLI 版主程序
├── 配置_API_Key.env           # API Key 配置模板
├── 一键启动_Windows.bat        # Windows 双击启动
├── 一键启动_Mac.sh             # Mac/Linux 启动脚本
├── requirements.txt           # Python 依赖清单
├── 使用说明书.docx             # Word 格式说明书
├── 使用说明书.md               # Markdown 说明书
├── agent-meta.json           # 智能体元数据
├── prompts/                  # 提示词文件（system/tool/memory/output）
├── adapters/                 # 多平台部署配置
│   ├── coze/bot.json
│   ├── dify/agent.yaml
│   ├── feishu/bot-config.yaml
│   └── openclaw/config.yaml
└── import.sh                 # 一键导入脚本
```

---

## 快速开始

### 1. 环境要求

- Python 3.10+
- Docker（可选，推荐用于生产部署）

### 2. 配置 API Key

```bash
cp .env.example .env
vim .env
```

填入你的模型平台 API Key：

```bash
DEEPSEEK_API_KEY=sk-your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL_NAME=deepseek-chat
```

支持的模型平台：

| 平台 | Base URL | 推荐模型 |
|------|---------|---------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| 小米 MiMo | `https://token-plan-cn.xiaomimimo.com/v1` | `mimo-v2.5-pro` |

### 3. 启动服务

**Docker 一键启动（推荐）：**

```bash
./run.sh start
```

**直接运行：**

```bash
pip install -r requirements.txt
streamlit run factory_app.py --server.port 8080
```

启动后访问 http://localhost:8080

---

## 系统架构

```
┌─────────────────────────────────────────────────┐
│ Kernel Layer（内核层）                            │
│ prompt_pack = system / tool / memory / output    │
├─────────────────────────────────────────────────┤
│ Middle Layer（中间层）                            │
│ agent-meta.json = Agent Spec                     │
├─────────────────────────────────────────────────┤
│ Adapter Layer（适配层）                           │
│ adapters/{platform}/ = Dify / Coze / Feishu /    │
│                        OpenClaw                  │
└─────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| LLM 客户端 | `core/llm_client.py` | 统一封装 OpenAI 兼容 API 调用，JSON 防爆舱解析，指数退避重试 |
| 装配引擎 | `core/builder.py` | 将 agent_config 渲染为各平台部署文件，Coze/Dify 双向转换 |
| 打包器 | `core/packager.py` | ZIP 交付包生成，含 Word 说明书、启动脚本、平台配置 |
| 卡密管理 | `core/card_manager.py` | SQLite 卡密系统，支持月卡/次卡、额度扣减、操作日志 |
| 工作流引擎 | `core/workflow_engine.py` | 多步骤流水线编排，上下文累积，质量门禁 |
| 提示词加载 | `core/prompt_loader.py` | 热插拔 Prompt 加载，支持本地/远程源 |
| 记忆引擎 | `templates/memory_engine.py` | 持久化对话历史、自动提取知识、定期进化 |

---

## 管理后台

访问方式：侧边栏底部 → 「管理后台」
默认密码：`admin888`

功能：
- **API 配置**：配置大模型 API Key / Base URL / Model
- **生成卡密**：批量生成月卡或次卡
- **卡密列表**：查看/筛选所有卡密状态
- **统计**：卡密使用数据统计
- **操作日志**：卡密操作审计

---

## 飞书部署

### 方式一：OpenClaw 网关（推荐，无需公网IP）

```yaml
channels:
  feishu:
    enabled: true
    appId: "cli_xxx"
    appSecret: "xxx"
    verificationToken: "xxx"
    encryptKey: "xxx"
    connectionMode: "websocket"
    domain: "feishu"
```

### 方式二：直接部署回调服务

```bash
pip install fastapi uvicorn httpx
python feishu_bot_server.py
```

飞书事件订阅连接方式选择 WebSocket（推荐）或 Webhook。

---

## 目录结构

```
agent_factory/
├── factory_app.py              # Streamlit 主界面
├── build_release.py            # 发布构建脚本
├── run.sh                      # Docker 一键管理脚本
├── Dockerfile                  # Docker 镜像定义
├── docker-compose.yml          # Docker 编排配置
├── requirements.txt            # Python 依赖
├── core/                       # 核心引擎
│   ├── llm_client.py           # LLM API 客户端
│   ├── builder.py              # 装配引擎
│   ├── packager.py             # 打包器
│   ├── card_manager.py         # 卡密管理
│   ├── workflow_engine.py      # 工作流引擎
│   └── prompt_loader.py        # 提示词加载器
├── templates/                  # 模板文件
│   ├── base_cli_agent.py       # CLI 智能体模板
│   ├── base_streamlit_agent.py # Web 智能体模板
│   ├── openclaw_agent.yaml     # OpenClaw 配置模板
│   ├── feishu_bot.yaml         # 飞书部署指南模板
│   ├── feishu_bot_server.py    # 飞书回调服务模板
│   └── workflows/              # 工作流模板库（16+ 种）
├── prompts/                    # 架构师 Prompt
├── pages/                      # Streamlit 子页面
│   └── 管理后台.py              # 卡密管理 + API 配置
├── docs/                       # 文档
├── data/                       # 运行时数据（gitignore）
├── output_agents/              # 生成的智能体输出（gitignore）
└── nginx/                      # Nginx 反代配置
```

---

## 许可证

本项目采用 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.zh-hans) 许可证。

**您可以自由地：**
- **共享** — 在任何媒介以任何形式复制、发行本作品
- **演绎** — 修改、转换或以本作品为基础进行创作

**惟须遵守下列条件：**
- **署名** — 您必须给出适当的署名，提供指向本许可协议的链接
- **非商业性使用** — 您不得将本作品用于商业目的

![CC BY-NC 4.0](https://licensebuttons.net/l/by-nc/4.0/88x31.png)

---

## 技术支持

- 遇到问题请提交 Issue
- 获取更多智能体模板，请关注项目更新
