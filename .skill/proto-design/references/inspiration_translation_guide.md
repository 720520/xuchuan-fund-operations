# 灵感转译指南

本文档说明如何从设计灵感来源中提取元素，并将其转译为网页设计，而非简单模仿。

---

## 转译原则

### ✅ 应该做的

1. **提取气质与方法**
   - 理解设计师/艺术家的核心设计理念
   - 提取他们处理版式、色彩、形态的方法
   - 学习他们的构图逻辑和视觉语言

2. **结合现代技术**
   - 用 CSS/HTML 实现类似的效果
   - 用网页技术重新诠释设计理念
   - 适应交互媒介的特性

3. **创造独特组合**
   - 采样多位灵感来源
   - 融合不同风格创造新美学
   - 结合项目特性进行调整

### ❌ 禁止行为

1. **不可复制具体作品**
   - 不照搬具体海报的构图
   - 不模仿具体画作的配色
   - 不复制具体建筑的形态

2. **不可使用品牌元素**
   - 不使用原作品中的品牌标识
   - 不模仿特定产品的设计
   - 不再现著名作品的标题或标语

3. **不可生成相似布局**
   - 避免与原作高度相似的页面布局
   - 不使用与原作相同的元素组合
   - 不再现特定的视觉序列

---

## 转译维度

### 1. 版式转译

#### 非对称分栏
```
灵感来源：Jan Tschichold、Herbert Bayer
网页实现：
- 使用 CSS Grid 创建非对称布局
- 打破常规的等宽分栏
- 尝试 1:2、2:3、黄金比例等分栏
```

#### 超大标题
```
灵感来源：Dan Perri、Kyle Cooper
网页实现：
- 使用 font-size: clamp(3rem, 10vw, 8rem)
- 配合紧凑的字间距（letter-spacing: -0.02em）
- 添加视差滚动效果
```

#### 网格秩序与"破格"
```
灵感来源：Josef Müller-Brockmann、April Greiman
网页实现：
- 建立严格的 12 列网格
- 让某些元素突破网格边界
- 使用负边距（margin: -2rem）或绝对定位
```

#### 分镜式章节标题
```
灵感来源：Saul Bass 电影海报
网页实现：
- 每个章节使用全屏背景
- 大字标题居中或偏离中心
- 配合滚动触发的淡入效果
```

### 2. 色彩转译

#### 高对比撞色
```
灵感来源：Keith Haring、Jean-Michel Basquiat
网页实现：
--color-primary: #FF3B30;
--color-accent: #FFD60A;
--background: #000000;
```

#### 三原色几何
```
灵感来源：Piet Mondrian、Gerrit Rietveld
网页实现：
--color-red: #E53935;
--color-blue: #1E88E5;
--color-yellow: #FDD835;
--color-black: #212121;
--color-white: #FAFAFA;
```

#### 工业警示条
```
灵感来源：Dieter Rams Braun 产品
网页实现：
--color-warning: #FFC107;
--color-black: #1A1A1A;
--color-gray: #424242;
```

#### 渐变/光散射
```
灵感来源：Olafur Eliasson、James Turrell
网页实现：
background: radial-gradient(
  circle at 50% 50%,
  rgba(255, 255, 255, 0.1) 0%,
  rgba(0, 0, 0, 0.8) 100%
);
```

### 3. 形态转译

#### 曲线切割
```
灵感来源：Zaha Hadid、Alvar Aalto
网页实现：
.shape {
  border-radius: 50% 0 50% 50%;
  clip-path: ellipse(150% 100% at 50% 0%);
}
```

#### 体块叠合
```
灵感来源：László Moholy-Nagy、Herbert Bayer
网页实现：
.card {
  position: absolute;
  transform: rotate(-3deg) translate(1rem, 1rem);
  box-shadow: 0 20px 40px rgba(0,0,0,0.2);
}
```

#### 模块化卡片
```
灵感来源：Superstudio、Archizoom
网页实现：
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
}
```

#### 纸感与细微纹理
```
灵感来源：Wabi-sabi 美学、传统纸张
网页实现：
background: url('data:image/svg+xml;utf8,<svg ...>')
  repeat;
background-blend-mode: multiply;
```

### 4. 动效转译

#### 入场/勾勒/滚动反馈
```
灵感来源：Motion graphics、Kyle Cooper
网页实现：
@media (prefers-reduced-motion: no-preference) {
  .fade-in {
    animation: fadeIn 300ms ease-out;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }
}
```

#### 支持 prefers-reduced-motion
```
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 5. 语义转译

#### 极简图形符号
```
灵感来源：Otl Aicher、Gerd Arntz
网页实现：
<svg class="icon" aria-hidden="true">
  <use href="/icons.svg#search"/>
</svg>
```

#### 变量字体轴
```
灵感来源：现代字体设计
网页实现：
font-family: 'Inter', sans-serif;
font-variation-settings: 'wght' 400, 'wdth' 100;
transition: font-variation-settings 0.3s ease;
```

#### 数字/指标的等宽排版
```
灵感来源：Tabular numerals、数据可视化
网页实现：
font-variant-numeric: tabular-nums;
letter-spacing: 0.05em;
```

---

## 转译实例

### 实例 1：Saul Bass → 现代着陆页

**灵感提取**
- 非对称构图
- 剪纸风格
- 大胆的色彩对比
- 简洁的几何形状

**网页实现**
```css
/* 剪纸风格的阴影 */
.hero-shape {
  background: var(--color-accent);
  clip-path: polygon(0 0, 100% 0, 100% 80%, 0 100%);
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}

/* 大胆的色彩对比 */
:root {
  --color-primary: #D32F2F;  /* 深红 */
  --color-secondary: #FFD700; /* 金色 */
  --color-dark: #1A1A1A;
}

/* 非对称文字布局 */
.hero-text {
  text-align: left;
  padding-left: 10vw;
}
```

### 实例 2：Dieter Rams → SaaS 界面

**灵感提取**
- "少但更好"理念
- 功能层次清晰
- 克制的色彩（黑、白、灰、一抹橙色）
- 几何纯粹

**网页实现**
```css
/* 克制的色彩系统 */
:root {
  --color-primary: #1A1A1A;
  --color-secondary: #F5F5F5;
  --color-accent: #FF6B00;  /* Braun 橙 */
  --color-text: #212121;
  --color-border: #E0E0E0;
}

/* 功能层次 */
.sidebar {
  background: var(--color-secondary);
  border-right: 1px solid var(--color-border);
}
.main {
  background: var(--color-primary);
  color: white;
}

/* 几何纯粹的按钮 */
.btn {
  background: var(--color-accent);
  border: none;
  border-radius: 4px;  /* 小圆角 */
  padding: 0.75rem 1.5rem;
}
```

### 实例 3：Zaha Hadid → 展示网站

**灵感提取**
- 流体曲线
- 动态空间
- 层次流动
- 无缝过渡

**网页实现**
```css
/* 流体曲线形状 */
.curve {
  border-radius: 60% 40% 30% 70% / 60% 30% 70% 40%;
}

/* 动态背景 */
.background {
  background:
    radial-gradient(ellipse at 20% 50%, rgba(255,255,255,0.1) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 50%, rgba(255,255,255,0.05) 0%, transparent 50%);
}

/* 流畅的过渡 */
.section {
  clip-path: polygon(0 5%, 100% 0, 100% 95%, 0 100%);
}

/* 层次流动 */
.layer {
  transform: perspective(1000px) rotateY(-5deg);
  transition: transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
```

### 实例 4：Mondrian → 网格布局

**灵感提取**
- 黑色分割线
- 原色色块
- 直角构图
- 网格系统

**网页实现**
```html
<div class="mondrian-grid">
  <div class="cell red"></div>
  <div class="cell white">
    <h2>Content</h2>
  </div>
  <div class="cell blue"></div>
  <div class="cell yellow"></div>
  <div class="cell white">
    <p>More content</p>
  </div>
</div>
```

```css
.mondrian-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 200px 300px;
  gap: 8px;
  background: #000;
  padding: 8px;
}

.cell {
  background: #fff;
}

.cell.red { background: #E53935; }
.cell.blue { background: #1E88E5; }
.cell.yellow { background: #FDD835; }
```

### 实例 5：安藤忠雄 → 极简博客

**灵感提取**
- 清水混凝土质感
- 光与影的缝隙
- 禅意空间
- 极简色彩

**网页实现**
```css
/* 混凝土质感 */
body {
  background: #808080;
  background-image:
    linear-gradient(45deg, rgba(0,0,0,0.02) 25%, transparent 25%),
    linear-gradient(-45deg, rgba(0,0,0,0.02) 25%, transparent 25%);
}

/* 光的缝隙 */
.light-gap {
  border-top: 1px solid rgba(255,255,255,0.3);
  box-shadow: 0 1px 0 rgba(0,0,0,0.1);
}

/* 禅意留白 */
.content {
  max-width: 680px;
  margin: 0 auto;
  padding: 6rem 2rem;
}

/* 极简色彩 */
:root {
  --color-bg: #8C8C8C;
  --color-text: #1A1A1A;
  --color-accent: #FFFFFF;
}
```

---

## 检查清单

转译完成后，确认：

- [ ] 没有复制具体作品的构图
- [ ] 没有模仿具体作品的配色组合
- [ ] 没有使用原作的品牌元素
- [ ] 设计风格与灵感来源有关联但不相似
- [ ] 结合了至少 2-3 个灵感来源
- [ ] 适应了网页媒介的特性
- [ ] 创造了独特的视觉表达
- [ ] 符合项目的品牌和功能需求
