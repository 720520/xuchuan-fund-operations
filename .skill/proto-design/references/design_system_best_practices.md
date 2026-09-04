# 设计系统最佳实践

本文档说明如何创建和使用 Design Tokens（设计令牌）系统。

---

## Design Tokens 简介

Design Tokens 是设计决策的最小单位，包括颜色、间距、字体、阴影等。它们将设计与代码连接起来。

### 为什么使用 Design Tokens？

1. **一致性**：确保整个产品的视觉一致
2. **可维护性**：集中管理，一处修改全局生效
3. **可扩展性**：轻松支持主题切换（如深色模式）
4. **跨平台**：Web、iOS、Android 共享设计语言

---

## 核心系统

### 1. 色彩系统

#### 语义化命名
```css
/* ❌ 避免：视觉命名 */
--color-red: #E53935;
--color-blue: #1E88E5;

/* ✅ 推荐：语义化命名 */
--color-primary: #E53935;
--color-secondary: #1E88E5;
--color-success: #4CAF50;
--color-warning: #FF9800;
--color-error: #F44336;
```

#### 色彩阶梯
```css
/* 主色阶梯 */
--color-primary-50: #E3F2FD;
--color-primary-100: #BBDEFB;
--color-primary-200: #90CAF9;
--color-primary-300: #64B5F6;
--color-primary-400: #42A5F5;
--color-primary-500: #2196F3;  /* 基准色 */
--color-primary-600: #1E88E5;
--color-primary-700: #1976D2;
--color-primary-800: #1565C0;
--color-primary-900: #0D47A1;
```

#### 深色模式支持
```css
/* 浅色模式 */
:root {
  --bg-primary: #FFFFFF;
  --text-primary: #1A1A1A;
}

/* 深色模式 */
@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: #1A1A1A;
    --text-primary: #F5F5F5;
  }
}

/* 或使用 class 切换 */
[data-theme="dark"] {
  --bg-primary: #1A1A1A;
  --text-primary: #F5F5F5;
}
```

### 2. 字体系统

#### 字体族
```css
:root {
  /* Display：标题、大字 */
  --font-display: 'Inter', -apple-system, sans-serif;

  /* Body：正文 */
  --font-body: 'Source Sans Pro', -apple-system, sans-serif;

  /* Mono：代码、数字 */
  --font-mono: 'SF Mono', 'Monaco', monospace;
}
```

#### 字号系统（次级数列）
```css
:root {
  --text-xs: 0.75rem;     /* 12px */
  --text-sm: 0.875rem;    /* 14px */
  --text-base: 1rem;      /* 16px */
  --text-lg: 1.125rem;    /* 18px */
  --text-xl: 1.25rem;     /* 20px */
  --text-2xl: 1.5rem;     /* 24px */
  --text-3xl: 1.875rem;   /* 30px */
  --text-4xl: 2.25rem;    /* 36px */
  --text-5xl: 3rem;       /* 48px */
  --text-6xl: 3.75rem;    /* 60px */
}
```

#### 字重
```css
:root {
  --font-light: 300;
  --font-normal: 400;
  --font-medium: 500;
  --font-semibold: 600;
  --font-bold: 700;
}
```

### 3. 间距系统（8pt 栅格）

```css
:root {
  --space-0: 0;
  --space-1: 0.25rem;   /* 4px */
  --space-2: 0.5rem;    /* 8px */
  --space-3: 0.75rem;   /* 12px */
  --space-4: 1rem;      /* 16px */
  --space-5: 1.25rem;   /* 20px */
  --space-6: 1.5rem;    /* 24px */
  --space-8: 2rem;      /* 32px */
  --space-10: 2.5rem;   /* 40px */
  --space-12: 3rem;     /* 48px */
  --space-16: 4rem;     /* 64px */
  --space-20: 5rem;     /* 80px */
  --space-24: 6rem;     /* 96px */
}
```

### 4. 圆角系统

```css
:root {
  --radius-none: 0;
  --radius-sm: 0.125rem;   /* 2px */
  --radius-base: 0.25rem;  /* 4px */
  --radius-md: 0.5rem;     /* 8px */
  --radius-lg: 0.75rem;    /* 12px */
  --radius-xl: 1rem;       /* 16px */
  --radius-2xl: 1.5rem;    /* 24px */
  --radius-full: 9999px;
}
```

### 5. 阴影系统

```css
:root {
  --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.1);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);
  --shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.15);
  --shadow-2xl: 0 25px 50px rgba(0, 0, 0, 0.25);
}
```

---

## 使用模式

### 模式 1：基础应用

```css
/* 直接使用 token */
.button {
  background: var(--color-primary);
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
}
```

### 模式 2：组件语义

```css
/* 为组件定义语义化的 token */
.card {
  background: var(--surface-primary);
  padding: var(--space-6);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}

/* 表面层级 */
:root {
  --surface-0: var(--color-white);
  --surface-1: var(--color-gray-50);
  --surface-2: var(--color-gray-100);
}
```

### 模式 3：复合 token

```css
/* 组合多个基础 token */
.btn-primary {
  /* 复合 token */
  --btn-bg: var(--color-primary-600);
  --btn-text: var(--color-white);
  --btn-padding: var(--space-3) var(--space-6);

  background: var(--btn-bg);
  color: var(--btn-text);
  padding: var(--btn-padding);
}

.btn-primary:hover {
  --btn-bg: var(--color-primary-700);
}
```

---

## 可访问性考虑

### 对比度检查

确保文字和背景的对比度符合 WCAG 标准：

- **AA 级**：普通文字 4.5:1，大文字 3:1
- **AAA 级**：普通文字 7:1，大文字 4.5:1

```css
/* 使用工具检查对比度 */
/* Chrome DevTools → Color picker → Contrast ratio */
```

### 语义化颜色

```css
/* 确保不仅仅依赖颜色传达信息 */
.error {
  color: var(--color-error);
  border-left: 3px solid var(--color-error);
  /* 添加图标 */
  &::before {
    content: "⚠️";
    margin-right: var(--space-2);
  }
}
```

### 动效偏好

```css
/* 尊重用户的动画偏好 */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 响应式系统

### 断点

```css
:root {
  --breakpoint-sm: 640px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1024px;
  --breakpoint-xl: 1280px;
}

/* 响应式间距 */
.container {
  padding: var(--space-4);
}

@media (min-width: 768px) {
  .container {
    padding: var(--space-8);
  }
}
```

### 流式字体

```css
/* 使用 clamp() 实现流式字体 */
h1 {
  font-size: clamp(2rem, 5vw, 4rem);
  /* 最小 2rem，首选 5vw，最大 4rem */
}
```

---

## 工具和资源

### Design Tokens 工具

1. **Style Dictionary**
   - 将 Design Tokens 转换为多平台代码
   - https://amzn.github.io/style-dictionary/

2. **Theo**
   - Salesforce 的 Design Tokens 工具
   - https://salesforce-ux.github.io/theo/

3. **Diez**
   - 设计系统工具链
   - https://diez.design/

### 在线检查工具

1. **Contrast Checker**
   - https://WebAIM.org/resources/contrastchecker/

2. **Color Oracle**
   - 色盲模拟工具
   - https://colororacle.org/

3. **CSS Variables DevTools**
   - Chrome 扩展，可视化 CSS 变量
   - https://chrome.google.com/webstore/detail/css-variables-devtools/

---

## 检查清单

创建 Design Tokens 时确认：

- [ ] 使用语义化命名
- [ ] 包含完整的色彩阶梯
- [ ] 支持深色模式
- [ ] 间距使用 8pt 栅格
- [ ] 字号使用次级数列
- [ ] 确保对比度符合 WCAG AA
- [ ] 定义响应式断点
- [ ] 包含动效时长和缓动
- [ ] 考虑可访问性需求
- [ ] 提供使用文档
