# Agent Factory — 商业版使用教程

> **让每个人都能在 30 秒内，用一句话生成自己的专属智能体。**
> 无需编程、无需部署、无需理解任何技术原理。

---

## 一、产品简介

**Agent Factory（智能体工厂）** 是一款 AI 智能体自动生成系统。你只需要**说一句话描述你想要什么**，它就能在几秒钟内为你生成一个可以直接运行的智能体程序。

### 核心卖点

| 特性 | 说明 |
|------|------|
| **一句话生成** | 输入需求，直接出成品，全过程自动化 |
| **多模型支持** | 兼容 DeepSeek、通义千问、智谱GLM、小米MiMo、Claude 中转等所有主流模型 |
| **开箱即用** | ZIP 包解压 → 填 Key → 运行，三步搞定 |
| **双模式交付** | CLI 命令行版（极速轻量） + Web 网页版（图形界面） |
| **多平台部署** | 自动生成飞书/Coze/Dify/OpenClaw 部署配置 |
| **场景无限** | PPT 润色、文献管理、代码审查、日志分析……任何你能想到的任务 |

### 适用场景

- 创新创业比赛：快速产出可演示的智能体作品
- 闲鱼/知识付费交付：低成本批量生产 AI 工具
- 科研辅助：文献管理、数据整理 Agent
- 工作效率：日报生成、邮件润色、文档总结

---

## 二、访问地址

- **本地访问**：http://localhost:8080
- **外网访问**：http://103.236.98.149:29187

---

## 三、部署指南

### 3.1 你需要准备什么？

- 一台能上网的电脑（Windows / Mac / Linux 都可以）
- 一个 AI 模型的 API Key（后面会教你怎么获取）
- 基本操作能力（会解压文件、会打开终端）

### 3.2 获取 API Key

本系统支持所有 OpenAI 兼容接口，任选一个即可：

| 模型平台 | 注册地址 | 推荐模型 | 费用 |
|---------|---------|---------|------|
| DeepSeek | https://platform.deepseek.com | deepseek-chat | 注册送额度 |
| 通义千问 Qwen | https://dashscope.aliyun.com | qwen-plus / qwen-turbo | 新用户免费额度大 |
| 智谱 GLM | https://open.bigmodel.cn | glm-4-flash | 注册送体验金 |
| 小米 MiMo | https://xiaomi-mimo.com | mimo-v2.5-pro | 按量付费 |

**获取步骤（以 DeepSeek 为例）：**
1. 打开 https://platform.deepseek.com
2. 注册账号 → 登录
3. 进入「API Keys」页面
4. 点击「创建 API Key」，复制生成的密钥

### 3.3 配置 .env 文件

1. 在项目根目录中，找到 `.env.example` 文件
2. **复制一份**，重命名为 `.env`（注意文件名前面有个点）
3. 用文本编辑器打开 `.env`，填入你的信息：

```bash
# 模型配置（支持任意 OpenAI 兼容 API）
DEEPSEEK_API_KEY=sk-your-api-key-here        # 改成你的 API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1  # 改成模型官方地址
DEEPSEEK_MODEL_NAME=deepseek-chat              # 改成模型名称
```

**各种模型的具体填法：**

```bash
# ─── DeepSeek ───
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL_NAME=deepseek-chat

# ─── 通义千问 Qwen ───
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEEPSEEK_MODEL_NAME=qwen-plus

# ─── 智谱 GLM ───
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://open.bigmodel.cn/api/paas/v4
DEEPSEEK_MODEL_NAME=glm-4-flash

# ─── 小米 MiMo ───
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
DEEPSEEK_MODEL_NAME=mimo-v2.5-pro

# ─── 自定义中转 API ───
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=你的中转地址
DEEPSEEK_MODEL_NAME=你购买的模型名
```

> **重要**：`.env` 文件包含你的 API Key，**绝对不要**分享给任何人！

---

## 四、启动服务

### 方式一：Docker 一键启动（推荐）

```bash
# 启动
./run.sh start

# 停止
./run.sh stop

# 重启
./run.sh restart

# 查看日志
./run.sh logs

# 查看状态
./run.sh status
```

启动后访问：http://localhost:8080 或 http://103.236.98.149:29187

### 方式二：直接运行 Streamlit

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
streamlit run factory_app.py --server.port 8080
```

---

## 五、使用流程

### 5.1 卡密激活（可选）

1. 打开网页后，左侧侧边栏有「卡密激活」区域
2. 输入卡密后点击「激活」
3. 激活后可以使用打包功能

> **注意**：即使不输入卡密，也可以使用智能体设计和生成功能。卡密仅用于控制打包次数。

### 5.2 生成智能体

**Step 1：输入需求**
- 在文本框中描述你想要的智能体
- 描述越详细，AI 设计越精准
- 例如："帮我做一个挑战杯比赛路演PPT润色Agent，能分析PPT结构、优化叙事逻辑、生成评委可能提出的问题及回答预案"

**Step 2：确认 & 微调**
- AI 架构师会自动设计智能体的 System Prompt、工作流步骤等
- 你可以在 Step 2 中调整任何细节
- 包括：智能体名称、System Prompt、记忆配置、部署平台选择

**Step 3：打包 & 下载**
- 点击「一键打包」
- 等待装配引擎和打包器完成
- 下载 ZIP 交付包

### 5.3 交付包结构

生成的 ZIP 包结构如下：

```
智能体名称_v1.0/
├── app.py                              # CLI 版主程序
├── 配置_API_Key.env                     # API Key 配置模板
├── 一键启动_Windows.bat                  # Windows 启动脚本
├── 一键启动_Mac.sh                       # Mac/Linux 启动脚本
├── requirements.txt                     # Python 依赖清单
├── 使用说明书.docx                       # Word 格式说明书
├── 使用说明书.md                         # Markdown 说明书
├── agent-meta.json                     # 智能体元数据
├── prompts/                            # 提示词文件
│   ├── system.md
│   ├── tool.md
│   ├── memory.md
│   └── output.md
├── adapters/                           # 多平台部署配置
│   ├── coze/
│   │   └── bot.json
│   ├── dify/
│   │   └── agent.yaml
│   ├── feishu/
│   │   ├── bot-config.yaml
│   │   └── bot-server.py
│   └── openclaw/
│       └── config.yaml
└── import.sh                           # 一键导入脚本
```

---

## 六、管理后台

访问方式：侧边栏底部 → 「管理后台」
默认密码：`admin888`（请修改 `pages/管理后台.py` 中的 `ADMIN_PASSWORD` 变量）

### 功能：

1. **API 配置**：配置大模型 API Key、Base URL、Model Name
2. **生成卡密**：批量生成月卡或次卡
3. **卡密列表**：查看所有卡密状态
4. **统计**：查看卡密使用统计
5. **操作日志**：查看卡密操作记录

---

## 七、飞书部署详细指南

### 方式一：通过 OpenClaw 网关接入（推荐）

**优势**：无需公网IP、无需回调地址、WebSocket 长连接自动维护

1. 打开生成的 `adapters/openclaw/config.yaml`
2. 找到 `channels.feishu` 段，填入你的飞书应用凭证
3. 将配置提供给 OpenClaw 部署方
4. OpenClaw 自动通过 WebSocket 连接飞书

**配置示例（OpenClaw 官方格式）：**
```yaml
channels:
  feishu:
    enabled: true
    appId: "cli_xxxxxxxxxxxxxxxx"
    appSecret: "xxxxxxxxxxxxxxxxxxxxxxxx"
    verificationToken: "xxxxxxxxxxxxxxxx"
    encryptKey: "xxxxxxxxxxxxxxxxxxxxxxxx"
    connectionMode: "websocket"
    domain: "feishu"
```

> **注意**：字段名必须用 camelCase（如 `appId`），不是 `app_id`

### 方式二：直接部署飞书回调服务

1. 打开飞书开放平台：https://open.feishu.cn/app
2. 创建「企业自建应用」
3. 启用机器人功能
4. 配置事件订阅：
   - 连接方式选择 **WebSocket**（推荐）或 Webhook
   - 如选 Webhook，回调地址填：`http://你的服务器:8000/webhook/event`
5. 订阅事件：`im.message.receive_v1`
6. 发布应用 → 添加到群聊 → @机器人 即可使用

---

## 八、常见问题

**Q：运行报错 `ModuleNotFoundError: No module named 'openai'`？**
A：忘记安装依赖了。运行 `pip install -r requirements.txt`。

**Q：运行后没有输出任何内容？**
A：检查 `.env` 文件中的 API Key 和 Base URL 是否正确填写。

**Q：提示 `Authentication Error`？**
A：API Key 可能已过期或填错了。回到官网重新生成一个 Key。

**Q：输出结果质量不好？**
A：可以试试换成更强的模型，或者把你的需求写得更具体一些。

**Q：卡密不输入也能用？**
A：是的，卡密仅用于控制打包次数。即使不输入卡密，也可以使用智能体设计和生成功能。

**Q：刷新页面后生成的内容没了？**
A：系统已支持会话持久化。生成的智能体配置和打包结果会自动保存到服务器，刷新后会自动恢复。

**Q：如何切换模型？**
A：在管理后台的「API 配置」标签页中修改 Base URL 和 Model 即可。支持所有 OpenAI 兼容接口。

**Q：能不能在手机上运行？**
A：本地程序需要电脑运行。建议部署到飞书或 Coze 平台，然后通过手机上的飞书/微信访问。

---

## 九、技术支持

- 遇到问题请向你的卖家反馈
- 获取更多智能体模板，请关注我们的最新发布

---

*Generated by **Agent Factory** — 让智能触手可及*
