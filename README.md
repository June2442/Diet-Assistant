# Diet Assistant - 项目概览

智能饮食健康助手 - 基于多Agent协作的个性化营养管理系统

---

## 🎯 项目定位

Diet Assistant 是一个**多Agent协作系统**，通过专业化Agent的协同工作，提供基于用户身体状态的智能饮食决策和主动健康干预。

### 核心差异

**不是菜谱查询工具，而是懂你身体的饮食顾问**

```
传统应用: "番茄炒蛋怎么做？"
         ↓
Diet Assistant: "你今天蛋白质差65g，蔬菜不足320g，这个菜单建议：
                清蒸鱼 + 炒青菜 + 半碗米饭
                理由：鱼类补充蛋白质，青菜补充纤维，整体低钠适合你的血压管理"
```

---

## 🏗️ 架构概览

### 多Agent协作系统

```
用户输入 → Intent Classification → Agent Orchestrator
                                          ↓
        ┌──────────┬──────────┬──────────┬──────────┬──────────┐
        ↓          ↓          ↓          ↓          ↓          ↓
    Memory     Health      Meal      Recipe    Emotion    Safety
    Agent      Agent    Decision     Agent     Support    Agent
                         Agent                  Agent
```

### 核心Agent

1. **Memory Agent** ⭐ - 长短期记忆管理
   - 90天原始记忆 → 自动压缩为长期摘要
   - 识别饮食模式和健康趋势
   - 智能召回相关记忆

2. **Meal Decision Agent** ⭐ - 智能选菜决策
   - 基于营养缺口推荐
   - 多场景支持：餐厅菜单/外卖/用户照片
   - 动态Skill路由

3. **Health Agent** - 健康状态管理
   - 体重、血压、运动追踪
   - 营养缺口实时计算
   - 动态热量预算

4. **Recipe Agent** - 菜谱专家
   - 调用CookHero作为数据源
   - 基于Memory个性化过滤

5. **Emotion Support Agent** - 情绪支持
   - 不羞辱、不责备
   - 允许合理放纵
   - 识别饮食障碍风险

6. **Safety Agent** - 安全监测
   - 四层安全检查
   - 过敏原硬拦截
   - 疾病限制规则

---

## ✨ 核心功能

### 1. 🧠 四层记忆系统
```
Layer 0: 原始记忆（90天）→ 图片、对话
Layer 1: 语义记忆（长期）→ "用户午餐蛋白质长期不足"
Layer 2: 健康画像（当前）→ 体重趋势、营养特征
Layer 3: 事件记忆（标记）→ 聚餐、生病
```

**智能压缩**：3个月以上图片删除，保留摘要，节省90%存储

### 2. 🍱 智能选菜决策

**多场景支持**：
- 📷 餐厅菜单拍照 → Vision识别 → 推荐组合
- 📱 外卖平台截图 → OCR解析 → 筛选推荐
- 🍽️ 用户菜品照片 → 识别食材 → 营养评估

**动态Skill路由**：
```python
if input == "餐厅菜单照片":
    skills = ["vision_detection", "nutrition_calc", "combination_scorer"]
elif input == "外卖链接":
    skills = ["ocr_parser", "takeout_api", "price_filter"]
```

### 3. 📊 实时营养管理
- 今日摄入 vs 目标 → 营养缺口
- 运动消耗 → 动态热量预算
- 长期趋势分析

### 4. ⏰ 主动提醒
- 饭点提醒（30-60分钟前）
- 营养缺口提醒
- 食谱更新提醒（2个月未用）

### 5. 🛡️ 多层安全
- 过敏原自动排除
- 疾病限制（高血压、糖尿病）
- 风险分级（L0普通 → L4紧急）

---

## 📁 项目结构

```
Diet assistant/
├── ARCHITECTURE.md              # 完整架构设计（本目录）
├── README.md                    # 本文件
├── agents/                      # Agent实现
│   ├── orchestrator/           # 总调度器
│   ├── memory_agent/           # 记忆管理
│   ├── health_agent/           # 健康管理
│   ├── meal_decision_agent/    # 选菜决策
│   ├── recipe_agent/           # 菜谱专家
│   ├── emotion_support_agent/  # 情绪支持
│   └── safety_agent/           # 安全监测
├── skills/                      # Skill库
│   ├── vision/                 # Vision相关
│   ├── database/               # 数据库查询
│   ├── api/                    # 外部API
│   └── calculation/            # 计算引擎
├── CookHero/                    # CookHero子模块
│   └── docs/
│       ├── INTEGRATION_ARCHITECTURE.md
│       ├── MEMORY_SYSTEM_DESIGN.md
│       └── IMPLEMENTATION_PLAN.md
└── shared/                      # 共享资源
    ├── database/
    ├── models/
    └── utils/
```

---

## 🚀 快速开始

### 环境要求
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Milvus 2.3+

### 安装

```bash
# 1. 进入项目目录
cd "D:\coding Project\Diet assistant"

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填写配置

# 5. 初始化数据库
python scripts/init_db.py

# 6. 启动服务
python main.py
```

### Docker部署

```bash
docker-compose up -d
```

---

## 📚 核心文档

### 架构设计
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** ⭐ 完整多Agent架构设计
  - 6个核心Agent详解
  - 动态Skill路由机制
  - Memory Agent独立化设计
  - 与CookHero集成方案

### CookHero集成文档
- **[集成架构](./CookHero/docs/INTEGRATION_ARCHITECTURE.md)** - CookHero如何融入系统
- **[记忆系统](./CookHero/docs/MEMORY_SYSTEM_DESIGN.md)** - 四层记忆详细设计
- **[实施计划](./CookHero/docs/IMPLEMENTATION_PLAN.md)** - 开发路线图

---

## 🗺️ 开发路线

### Phase 1: 基础架构（3周）
- [ ] Agent Orchestrator
- [ ] Intent Classification
- [ ] Skill路由系统
- [ ] 数据库设计

### Phase 2: Memory Agent（3周）⭐
- [ ] 四层记忆架构
- [ ] 智能压缩服务
- [ ] 召回机制
- [ ] 定时任务

### Phase 3: 核心Agent（4周）⭐
- [ ] Health Agent（健康管理）
- [ ] Meal Decision Agent（选菜决策）
- [ ] Safety Agent（安全监测）

### Phase 4: 扩展Agent（3周）
- [ ] Recipe Agent（集成CookHero）
- [ ] Emotion Support Agent
- [ ] 提醒系统

### Phase 5: 前端与集成（3周）
- [ ] 前端界面
- [ ] Agent联调
- [ ] 性能优化

**总计**：约4个月完成MVP

---

## 💡 技术亮点

### 1. Memory Agent独立化
**传统做法**：记忆作为模块，被动存储
**我们的方案**：Memory是独立Agent，主动压缩、召回、维护

**优势**：
- 支持md文件中的分层记忆设计
- 智能压缩和趋势分析
- 独立扩展和优化

### 2. 动态Skill路由
**传统做法**：固定的工具调用链
**我们的方案**：根据输入类型动态选择Skill

**优势**：
- 高效：只调用必要的Skill
- 灵活：新场景只需添加路由规则
- 可扩展：Skill独立开发

### 3. 多Agent协作
**传统做法**：单一LLM处理所有任务
**我们的方案**：专业化Agent协同工作

**优势**：
- 专业：每个Agent专注特定领域
- 并行：多个Agent可并行工作
- 可维护：Agent独立迭代

---

## 🎯 与CookHero的关系

```
Diet Assistant (整个系统)
    │
    ├─ 6个专业Agent
    │   │
    │   └─ Recipe Agent
    │       │
    │       └─ 调用 CookHero (菜谱数据源)
```

**CookHero的角色**：
- 提供菜谱RAG检索
- 提供烹饪指导
- **不是**系统核心，而是Recipe Agent的数据源之一

**关键区别**：
- **CookHero**: "番茄炒蛋怎么做？"
- **Recipe Agent**: 基于Memory和营养缺口推荐菜谱
- **Meal Decision Agent**: "现在该吃什么？"（更高层决策）

---

## 📊 成功指标

### MVP（4个月）
- ✅ 用户每日记录 ≥ 2餐
- ✅ 智能选菜使用率 > 40%
- ✅ 推荐采纳率 > 30%
- ✅ 7日留存 > 40%

### 成熟期（8个月）
- ✅ 日活率 > 60%
- ✅ 使用周期 > 3个月
- ✅ NPS > 50
- ✅ 健康改善率 > 70%

---

## 🤝 贡献指南

### 开发规范
- 使用 Black 格式化
- 使用 mypy 类型检查
- 单元测试覆盖率 > 80%

### Git工作流
```bash
git checkout -b feature/your-feature
git commit -m "feat(agent): description"
git push origin feature/your-feature
```

---

## 🙏 致谢

- [CookHero](https://github.com/Decade-qiu/CookHero) - 菜谱数据源
- [HowToCook](https://github.com/Anduin2017/HowToCook) - 菜谱内容

---

## 📄 许可证

MIT License

---

**让我们一起构建真正"懂你身体"的智能饮食助手！** 🥗💪

---

## 📮 快速链接

- 📖 [完整架构设计](./ARCHITECTURE.md)
- 🔧 [CookHero集成方案](./CookHero/docs/INTEGRATION_ARCHITECTURE.md)
- 🧠 [Memory系统设计](./CookHero/docs/MEMORY_SYSTEM_DESIGN.md)
- 📋 [开发计划](./CookHero/docs/IMPLEMENTATION_PLAN.md)
