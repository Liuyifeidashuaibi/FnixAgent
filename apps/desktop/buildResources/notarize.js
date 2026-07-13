/**
 * macOS Notarization afterSign 钩子 — Phase 2.6
 *
 * 此文件为 electron-builder 的 afterSign 钩子,用于在代码签名后对产物
 * 做 Notarization(公证)。electron-builder 24.x 已内置 notarize 支持
 * (通过 electron-builder.yml 的 mac.notarize.teamId 配置),大多数情况
 * 下无需此脚本。仅在以下场景启用:
 *   - 需要对 .zip 包也做公证(默认只公证 .dmg)
 *   - 需要自定义公证逻辑(如 stapler 合并)
 *
 * 启用方法:
 *   在 package.json 中添加:
 *   "build": {
 *     "afterSign": "buildResources/notarize.js"
 *   }
 *
 * 必需环境变量(已在 release.yml 中配置):
 *   APPLE_ID                    Apple ID 邮箱
 *   APPLE_APP_SPECIFIC_PASSWORD Apple 应用专用密码
 *   APPLE_TEAM_ID               Apple Team ID
 */
const { notarize } = require('@electron/notarize');

module.exports = async function notarizeAfterSign(context) {
  const { electronPlatformName, appOutDir } = context;
  // 仅 macOS 需要 Notarization
  if (electronPlatformName !== 'darwin') return;

  // 未配置 Apple 凭据时跳过(开发环境)
  const appleId = process.env.APPLE_ID;
  const appleIdPassword = process.env.APPLE_APP_SPECIFIC_PASSWORD;
  const teamId = process.env.APPLE_TEAM_ID;
  if (!appleId || !appleIdPassword || !teamId) {
    console.log('[notarize] 跳过:未配置 APPLE_ID / APPLE_APP_SPECIFIC_PASSWORD / APPLE_TEAM_ID');
    return;
  }

  const appName = context.packager.appInfo.productFilename;
  const appPath = `${appOutDir}/${appName}.app`;

  console.log(`[notarize] 提交公证: ${appPath}`);
  await notarize({
    appBundleId: context.packager.appInfo.id,
    appPath,
    appleId,
    appleIdPassword,
    teamId,
    tool: 'notarytool',  // 使用 Apple notarytool(推荐,比 altool 快)
  });
  console.log('[notarize] 公证完成');
};
