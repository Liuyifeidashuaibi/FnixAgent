# Brand Usage / 品牌使用规范

> 何时用哪个资产,以及**绝不能**做什么。

---

## 资产总览 / Assets

| 资产 | 文件 | 用途 |
| --- | --- | --- |
| **完整 Logo**(立方体 + 节点) | `logo.svg` | 营销页、PPT 大尺寸展示 |
| **方形 Icon**(无外延节点) | `icon.svg` | App Icon、favicon、dock、菜单 |
| **Logo PNG**(多尺寸) | `logo-{16,32,128,256,512,1024}.png` | 替代 SVG 的场景 |
| **Icon PNG**(多尺寸) | `icon-{16,32,128,256,512,1024}.png` | 替代 SVG 的场景 |
| **OG Image**(1280×640) | `og-image.png` | 社交分享卡片 |
| **品牌色板** | `colors.md` | UI 设计 |
| **字体规范** | `typography.md` | 文档 / UI |

---

## 何时用哪个 / When to Use

### Logo vs Icon

- **Logo**(立方体 + 节点):只在营销材料、PPT、招聘广告中使用。**最小 64×64 px**。
- **Icon**(仅立方体):用作 App / favicon / dock / 菜单 / 浏览器标签。**最小 16×16 px**。

### 在不同场景

| 场景 | 资产 | 颜色 | 尺寸 |
| --- | --- | --- | --- |
| 文档站 hero | Logo | 灰阶 | ≥ 200 px |
| GitHub README | Icon | 灰阶 | 80-120 px |
| App 启动画面 | Icon | 灰阶 | 全屏 |
| favicon | Icon | 灰阶 | 16/32 px |
| 招聘 PDF | Logo + 文字 | 灰阶 | 顶部 |
| B 站视频封面 | Logo + 文字 | 灰阶 | 1280×720 |
| LinkedIn 头像 | Icon | 灰阶 | 400×400 |

---

## 留白 / Clear Space

Logo / Icon 周围必须留出**至少 Logo 高度 1× 的空白**:

```
┌─────────────────────────┐
│                         │
│    ┌──────────────┐     │
│    │              │     │ ← 至少 1× 高度空白
│    │     LOGO     │     │
│    │              │     │
│    └──────────────┘     │
│                         │
└─────────────────────────┘
```

不要在 Logo 周围放其他元素。

---

## 最小尺寸 / Minimum Size

| 资产 | Web 最小 | 印刷最小 |
| --- | --- | --- |
| Logo(立方体 + 节点) | 64 × 64 px | 16 mm |
| Icon(仅立方体) | 16 × 16 px | 4 mm |
| Logo + 文字组合 | 128 × 32 px | 32 mm |

低于最小尺寸 Logo 会糊。

---

## 颜色使用 / Color Usage

### ✅ 允许

- 灰阶 Logo 在浅色背景(白 / `#FAFAFA`)
- 灰阶 Logo 在深色背景(`#0A0A0A` / `#171717`)
- Logo 与品牌色文字组合(参见 `colors.md`)

### ❌ 禁止

- Logo 在彩色背景上(白 / 黑 / 灰才合规)
- Logo 用作背景填充
- Logo 旋转 / 翻转
- Logo 加阴影 / 渐变 / 描边

---

## 错误使用 / Don't

### ❌ 不要修改颜色

```
✅ Logo 在灰阶           ❌ Logo 在彩色
┌──────────┐              ┌──────────┐
│  ▓▓▓▓▓▓  │              │ ███▓▓███ │
│  ▓▓▓▓▓▓  │              │ ▓▓▓██▓▓▓ │ ← 禁止上色
│  ▓▓▓▓▓▓  │              │ ███▓▓███ │
└──────────┘              └──────────┘
```

### ❌ 不要变形

- 拉伸 / 压缩比例
- 倾斜 / 旋转
- 透视变形

### ❌ 不要添加元素

- 阴影
- 描边
- 高光
- 其他装饰

### ❌ 不要混用其他 Logo

- 不要与第三方 Logo 并列(看起来像合作)
- 不要嵌入到其他 Logo 中

### ❌ 不要改造

- 不要把立方体改成球体 / 圆锥
- 不要添加文字到 Logo 内
- 不要去掉 Logo 中的神经节点

---

## 文字配 Logo / Logo + Wordmark

如果需要 "Logo + 文字" 组合:

```
┌────────────────────────────┐
│                            │
│  [ICON]  FnixAgent          │
│          Local-First AI    │
│                            │
└────────────────────────────┘
```

- Logo 与文字间距 = Logo 高度的 0.5×
- 文字用 `Inter`,字重 600 (Semibold)
- 文字颜色 = Logo 的最深色 `#0A0A0A`

---

## 在第三方平台 / Third-Party Platforms

### GitHub

- repo 头像:Icon,512×512 px
- README 顶部:Icon + 文字(80-120 px)
- Social preview:og-image.png

### 社交媒体

- LinkedIn / X 头像:Icon,400×400 px
- B 站 / YouTube 封面:Logo + 文字,1280×720 px
- 小红书封面:Logo + 文字,3:4 (900×1200) 或 1:1 (1080×1080)

### 文档站(MkDocs / VitePress)

- favicon:Icon,16/32 px
- 顶部导航 Logo:Icon,32 px
- 首页 Hero:Logo,≥ 200 px

---

## 在第三方物料上的使用

### 名片

- 正面:Logo + 个人姓名 + 职位
- 背面:个人联系方式 + GitHub 链接
- Logo 居中或左上角

### T 恤 / 周边

- 胸前:Logo,≥ 80 mm
- 背面:Logo + URL,**禁止**印其他第三方 Logo

### 演示文稿

- 标题页:Logo 居中 + 演讲标题
- 章节页:小 Logo(32 px) 角落 + 章节标题
- 结尾页:大 Logo + 联系方式 + GitHub

---

## 商标声明 / Trademark Notice

所有使用 FnixAgent Logo / 名称的物料**必须**包含:

```
© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.
```

或在显著位置声明"基于 FnixAgent 开源浏览"(详见 [LICENSE](../../LICENSE) 与 [TRADEMARKS.md](../../TRADEMARKS.md))。

---

## 联系 / Contact

如有 Logo 使用疑问:`liuyifeidashuaibi@gmail.com`

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.