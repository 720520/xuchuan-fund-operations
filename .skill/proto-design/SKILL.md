---
name: proto-design
description: 根据用户提供的需求，设计高保真的原型图。采用三重角色（产品经理+设计师+前端工程师）工作流程，使用设计灵感采样法打造设计出色的UI。使用 HTML + Tailwind CSS（或 Bootstrap）生成所有原型界面，并使用现代UI组件库让界面精美、接近真实App设计。
---

## 技能概述

本技能采用三重角色协作模式，将产品设计、视觉美学和工程实现完美结合，打造设计出色、用户体验优秀的高保真原型。


## 第一阶段：产品经理工作流程

### 1.1 逆向工作法 - PRFAQ 撰写

在开始设计前，先深入思考产品本质，撰写 1000 字的 PRFAQ（Press Release FAQ）：

**PRFAQ 结构：**
- **产品标题**：一句话描述产品核心价值
- **目标用户**：清晰定义用户画像和使用场景
- **痛点解决**：阐述产品解决的核心问题
- **关键功能**：列出 3-5 个核心功能点
- **差异化优势**：与竞品的区别
- **成功指标**：如何衡量产品成功

### 1.2 需求洞察 - 显性与隐性需求清单

穿透用户表面表述，深入挖掘完整需求：

**需求清单维度：**
| 维度 | 说明 |
|------|------|
| **功能需求** | 核心功能、辅助功能、高级功能 |
| **用户角色** | 主要用户、次要用户、管理员等 |
| **使用场景** | 日常场景、异常场景、边界场景 |
| **核心任务路径** | 用户完成主要目标的关键步骤 |
| **边界与异常** | 错误处理、空态、加载态、极限情况 |
| **数据结构** | 需要展示和交互的数据类型 |

### 1.3 PRD 文档与信息架构

**输出内容：**
- **目标用户**：清晰的用户画像
- **功能列表**：使用 MoSCoW 优先级法
  - Must have：必须有
  - Should have：应该有
  - Could have：可以有
  - Won't have：本次不做
- **信息架构**：绘制站点地图和任务流程图
- **页面清单**：列出所有需要设计的页面

---

## 第二阶段：设计师工作流程

### 2.1 设计灵感采样法

**灵感来源池**（随机采样 2-3 位）：

#### 平面设计师
- Saul Bass, Maurice Binder, Pablo Ferro, Dan Perri, Kyle Cooper
- Paula Scher, Neville Brody, April Greiman, David Carson, Jamie Reid
- Push Pin Studios (Seymour Chwast), Massimo Vignelli

#### 瑞士国际主义风格
- Josef Müller-Brockmann, Otl Aicher, Armin Hofmann, Karl Gerstner
- Muriel Cooper

#### 艺术家（抽象/几何/光学艺术）
- Piet Mondrian, Sonia Delaunay, Josef Albers, Victor Vasarely
- Bridget Riley, M.C. Escher, Paul Klee, Kazimir Malevich
- Joan Miró, Henri Matisse, Mark Rothko, René Magritte, Salvador Dalí

#### 亚洲当代艺术家
- Yayoi Kusama, Takashi Murakami, Katsushika Hokusai（葛饰北斋）
- Xu Bing（徐冰）, Zao Wou-Ki（赵无极）

#### 生成艺术/新媒体
- John Maeda, Casey Reas, Zach Lieberman, Vera Molnár
- Manfred Mohr, Refik Anadol, Sougwen Chung

#### 建筑师
- Zaha Hadid, Bjarke Ingels (BIG), Thomas Heatherwick, Olafur Eliasson
- Le Corbusier, Mies van der Rohe, Frank Lloyd Wright, Alvar Aalto
- Louis Kahn, Norman Foster, Renzo Piano, Herzog & de Meuron
- OMA/Rem Koolhaas, Tadao Ando（安藤忠雄）, SANAA
- Kengo Kuma（隈研吾）, Kenzo Tange（丹下健三）

#### 工业设计师
- Dieter Rams（Braun）, Jony Ive（Apple）, Naoto Fukasawa（无印良品）
- Jasper Morrison, Marc Newson, Yves Béhar
- Hartmut Esslinger（frog）, Raymond Loewy, Richard Sapper（ThinkPad）
- Charles & Ray Eames, Sori Yanagi, Kenji Ekuan
- Nendo（Oki Sato）, Philippe Starck, F.A. Porsche（Porsche Design）
- James Dyson, Teenage Engineering（Jesper Kouthoofd）
- Susan Kare（界面图标语义）

### 2.2 灵感转译原则

**⚠️ 转译而非模仿（必须遵守）**

借鉴气质与方法，禁止临摹或再现具体作品：

| 设计维度 | 转译方向 |
|----------|----------|
| **版式** | 非对称分栏、超大标题、网格秩序与"破格"、分镜式章节标题 |
| **色彩** | 高对比撞色、三原色几何、工业警示条、渐变/光散射 |
| **形态** | 曲线切割、体块叠合、模块化卡片、纸感与细微纹理 |
| **动态** | 200-300ms 的入场/勾勒/滚动反馈；支持 `prefers-reduced-motion` 的静态回退 |
| **语义** | 极简图形符号、变量字体轴、数字/指标的等宽排版 |

**禁止行为：**
- ❌ 复刻具体作品的构图
- ❌ 复刻配色、字体组合
- ❌ 生成与原作高度相似的布局
- ❌ 使用原作的品牌元素

### 2.3 交互与视觉方案

**输出内容：**

1. **页面结构**：每个页面的布局骨架
2. **组件清单**：按钮、卡片、表单、导航等
3. **状态设计**：
   - 默认态
   - 悬停态
   - 激活态
   - 禁用态
   - 错误态
   - 空态
   - 加载态
4. **可访问性**：对比度、焦点状态、ARIA 标签
5. **动效规范**：过渡时长、缓动函数、触发条件
6. **响应式策略**：
  - 移动端：< 768px
  - 平板端：768px - 1024px
  - 桌面端：> 1024px

### 2.4 设计系统（Design Tokens）

**输出设计系统：**

```css
/* 色彩系统 */
--color-primary: #...;
--color-secondary: #...;
--color-accent: #...;
--color-success: #...;
--color-warning: #...;
--color-error: #...;
--color-neutral: #...;

/* 字体系统 */
--font-display: '...', sans-serif;
--font-body: '...', sans-serif;
--font-mono: '...', monospace;

/* 间距系统（8pt 栅格） */
--space-xs: 4px;
--space-sm: 8px;
--space-md: 16px;
--space-lg: 24px;
--space-xl: 32px;
--space-2xl: 48px;

/* 圆角系统 */
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 16px;
--radius-full: 9999px;

/* 阴影系统 */
--shadow-sm: ...;
--shadow-md: ...;
--shadow-lg: ...;
```

**关键页面线框描述**：用文字描述 2-3 个核心页面的布局结构

---

## 第三阶段：前端实现

### 3.1 技术栈选择

- **HTML5**：语义化结构
- **CSS 框架**：Tailwind CSS 或 Bootstrap
- **图标库**（选其一）：
  - Lucide Icons
  - Heroicons
  - Tabler Icons
  - Phosphor Icons
- **字体**：Google Fonts（通过 CDN）

### 3.2 代码结构要求

**文件组织：**
```
prototype/
├── index.html          # 主入口（平铺展示所有页面）
├── pages/
│   ├── home.html       # 首页
│   ├── profile.html    # 个人资料
│   ├── settings.html   # 设置页
│   └── ...
├── assets/
│   ├── css/
│   │   └── styles.css
│   └── js/
│       └── main.js
└── README.md           # 设计说明文档
```

**index.html 规范：**
- 使用 iframe 嵌入各页面
- 平铺展示所有页面（非跳转链接）
- 添加页面标题说明

### 3.3 HTML5 语义结构

使用正确的语义标签：
```html
<header>    <!-- 页头 -->
<nav>       <!-- 导航 -->
<main>      <!-- 主内容 -->
  <article> <!-- 文章内容 -->
  <section> <!-- 内容区块 -->
<aside>     <!-- 侧边栏 -->
<footer>    <!-- 页脚 -->
```

标题层级规范：
- 每页只有一个 `<h1>`
- 标题层级递增，不跳跃（h1 → h2 → h3）

### 3.4 响应式设计

**三断点策略：**
```css
/* 移动端优先 */
@media (min-width: 768px) { /* 平板 */ }
@media (min-width: 1024px) { /* 桌面 */ }
```

**可点击区域**：最小 44×44px（移动端友好）

### 3.5 图片资源规范

**必须使用真实图片，禁止占位符：**

| 来源 | 示例 |
|------|------|
| Picsum | `https://picsum.photos/id/157/800/600` |
| Unsplash Source | `https://source.unsplash.com/800x600/?nature` |

**必备 meta 标签：**
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
```

### 3.6 主题与风格指南

**色彩与可读性：**
- ✅ 避免千篇一律的紫色/纯蓝主色
- ✅ 选择有辨识度的中性色或高品质品牌色
- ✅ 确保对比度符合 WCAG AA 标准（4.5:1）

**图标使用：**
- ❌ 禁止使用 emoji
- ✅ 使用 SVG 图标库（Lucide/Heroicons/Tabler）
- ✅ 或生成自定义 SVG 图标

**禁止行为：**
- ❌ 留下空白占位符
- ❌ 使用 lorem ipsum（如无实际内容，用真实场景文案替代）
- ❌ 使用通用 AI 审美（紫色渐变、Inter 字体、千篇一律布局）

---

## 设计质量检查清单

交付前确认：

- [ ] PRFAQ 已完成，产品方向清晰
- [ ] 需求清单完整（显性+隐性）
- [ ] 设计灵感已采样并转译
- [ ] 设计系统已定义（色彩/字体/间距）
- [ ] 所有页面使用真实图片
- [ ] 代码结构清晰，文件分离
- [ ] 响应式三断点已实现
- [ ] 无 emoji，使用图标库
- [ ] 对比度符合可访问性标准
- [ ] 设计风格独特，避免通用 AI 审美

---

## 使用示例

**用户输入：**
```
我需要一个健身追踪 App 的原型设计
```

**技能执行流程：**
1. 撰写健身 App 的 PRFAQ
2. 分析用户需求（运动记录、数据可视化、社交功能等）
3. 从灵感池采样（如：Dieter Rams + Refik Anadol）
4. 设计视觉方案（极简数据可视化 + 动态光效）
5. 输出 Design Tokens
6. 生成 HTML 原型代码
