# Tauri 图标生成器 / Icon Generator

> 从单一 SVG 源生成 Tauri 2 / iOS / Android / Windows 全部图标。

---

## 为什么需要这个?

Tauri 2 打包需要:

- Windows:`icon.ico` (含 16/24/32/48/64/128/256 多种尺寸)
- macOS:`icon.icns` (含 10+ 种尺寸)
- Linux:`PNG` 多尺寸
- Android:`mipmap-*/ic_launcher.png` 5 套
- iOS:`AppIcon-*.png` 15+ 种

手工准备 = 几十张图。**容易漏、容易不一致**。

这个生成器:

1. 设计师只需画一张矢量 SVG (`assets/brand/icon.svg`)
2. 跑 `pnpm generate` 一键生成所有平台图标
3. 自动保证视觉一致

---

## 用法

```bash
# 装依赖
cd apps/desktop-tauri/src-tauri/icons/generator
pip install pillow cairosvg

# 全部生成
pnpm generate

# 单平台
pnpm generate:tauri
pnpm generate:android
pnpm generate:ios
```

### 自定义源

```bash
python3 generate.py \
  --source=assets/brand/icon.svg \
  --output=apps/desktop-tauri/src-tauri/icons
```

---

## 设计规范

SVG 必须遵循:

| 属性 | 规范 |
| --- | --- |
| viewBox | `0 0 512 512`(必须是正方形) |
| 背景 | 透明 (用于蒙版) |
| 最小可视区域 | `512x512` 内 `64x64 ~ 448x448`(避免边缘裁切) |
| 颜色 | 单一品牌色 `#FF6B35` 或 `#FF5A1F` |
| 字号 | 矢量,不内嵌位图 |
| 字体 | 系统字体(避免外嵌字体文件) |

### 最小 SVG 模板

```xml
<svg viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <!-- 背景 -->
  <rect width="512" height="512" rx="96" fill="#FF6B35"/>
  <!-- Logo F -->
  <path d="M180 130 H320 V180 H230 V230 H310 V280 H230 V380 H180 Z"
        fill="white"/>
</svg>
```

### 替换当前占位图

1. 用 Figma / Sketch / Inkscape 画 `assets/brand/icon.svg`
2. 跑 `pnpm generate`
3. 检查 `apps/desktop-tauri/src-tauri/icons/icon.png`(1024x1024)
4. 跑 `pnpm dev` 看效果

---

## 输出列表

### Tauri 2 (15 个文件)

```
apps/desktop-tauri/src-tauri/icons/
├── 32x32.png
├── 128x128.png
├── 128x128@2x.png
├── icon.png                  (1024×1024)
├── icon.icns                 (macOS)
├── icon.ico                  (Windows)
├── Square{30,44,71,89,107,142,150,284,310}xLogo.png
└── StoreLogo.png
```

### Android (5 个尺寸)

```
android/
├── mipmap-mdpi/ic_launcher.png      (48)
├── mipmap-hdpi/ic_launcher.png      (72)
├── mipmap-xhdpi/ic_launcher.png     (96)
├── mipmap-xxhdpi/ic_launcher.png    (144)
└── mipmap-xxxhdpi/ic_launcher.png   (192)
```

### iOS (15 个尺寸)

```
ios/
└── AppIcon/
    ├── AppIcon-20.png
    ├── AppIcon-20@2x.png
    ├── AppIcon-20@3x.png
    ├── ...
    └── AppIcon-1024.png
```

---

## 平台特殊说明

### macOS `.icns`

`.icns` 是 Apple 的图标容器格式,需要 macOS 上的 `iconutil`:

```bash
# 在 macOS 上
cd apps/desktop-tauri/src-tauri/icons
iconutil -c icns icon.iconset
```

生成器会先把 PNG 放到 `icon.iconset/`,然后调用 `iconutil`。
**非 macOS 平台只生成 PNG,不生成 .icns**。

### Windows `.ico`

`.ico` 用 PIL 直接生成(支持透明度),无需额外工具。

### Android Adaptive Icon

Android 8+ 推荐使用 Adaptive Icon(`<adaptive-icon>`):

```
res/
├── mipmap-anydpi-v26/
│   ├── ic_launcher.xml       ← 引用 fg + bg
│   ├── ic_launcher_round.xml
│   └── drawable/
│       ├── ic_launcher_background.xml
│       └── ic_launcher_foreground.xml
```

需要设计师额外提供**前景层**和**背景层**两个 SVG。

---

## 集成到 CI

`.github/workflows/icons.yml`:

```yaml
name: Generate Icons
on:
  workflow_dispatch:
    inputs:
      source_svg:
        description: 'SVG source file'
        required: true

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pillow cairosvg
      - run: |
          python3 apps/desktop-tauri/src-tauri/icons/generator/generate.py \
            --source=${{ inputs.source_svg }} \
            --output=apps/desktop-tauri/src-tauri/icons
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore(icons): regenerate from ${{ inputs.source_svg }}"
```

---

## 参考 / References

- [Tauri Icons Guide](https://tauri.app/v2/guides/features/icons)
- [Apple Icon Guidelines](https://developer.apple.com/design/human-interface-guidelines/app-icons)
- [Android Adaptive Icons](https://developer.android.com/develop/ui/views/launch/icon_design_adaptive)
- [cairosvg 文档](https://cairosvg.org/)

---

© 2024-2026 FnixAgent. All Rights Reserved.