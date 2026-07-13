OfficeAgent Desktop buildResources — 打包资源目录
================================================

此目录存放 electron-builder 打包所需的资源文件。

必需图标文件(根据目标平台提供):
  icon.ico      Windows 图标(多尺寸,推荐 256x256 + 128 + 64 + 48 + 32 + 16)
  icon.icns     macOS 图标(多尺寸 icns 格式)
  icon.png      Linux 图标(512x512 PNG,用于 AppImage/deb/rpm)
  icon-512.png  Linux 高分辨率图标(可选,部分桌面环境需要)

图标缺失时 electron-builder 会使用默认 Electron 图标并打印警告。
设计交付图标后,放置到此目录即可,无需修改 electron-builder.yml。

可选文件:
  entitlements.mac.plist   macOS Hardened Runtime 权限清单(已提供)
  notarize.js              macOS Notarization afterSign 钩子(已提供,默认不启用)

图标生成(从 1024x1024 PNG 源文件):
  # 安装 electron-icon-builder:
  npm install -g electron-icon-builder
  # 从 icon.png 生成所有平台图标:
  electron-icon-builder --input=icon.png --output=buildResources
