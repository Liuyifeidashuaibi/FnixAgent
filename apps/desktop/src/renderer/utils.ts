/**
 * 桌面端通用工具函数
 */

/**
 * 触发浏览器下载文本文件
 */
export function downloadTextFile(
  text: string,
  filename: string,
  mimeType = 'text/plain',
): void {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
