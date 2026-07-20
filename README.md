# 樱海壁纸收藏夹

面向 Windows 11 的 Wallpaper Engine 原画质快照、Workshop 图库与视频选帧助手。

当前发布基线：`V1`。推荐仓库英文名：`wallpaper-exporter`。

`past_files_can_remove` contains old requirement confirmations. Removing that folder does not affect the program.

## 主要功能

- 一键导出当前 `WallpaperEngineLockOverride.jpg`。
- 保留源文件真实格式、原始像素和原始字节，不放大、不二次压缩。
- 自动识别 2K、4K 及更高分辨率并在界面中如实显示。
- 扫描 Windows Themes 中现存的有效 JPG/PNG，包括无扩展名的 `TranscodedWallpaper`。
- 扫描本机 Workshop 431960 目录，按 Wallpaper Engine 原始标题显示项目与缩略图。
- 支持搜索、类型筛选、勾选、全选当前结果和 48 项一页的懒加载图库。
- 图库使用完整比例预览，不裁掉人物和画面边缘；默认约 6 列，窗口放大后自动增加列数。
- 提供“缩小/放大”缩略图按钮，可在紧凑 6 列与大图 3–4 列之间切换。
- 滚动进度达到约 70% 时提前静默加载后续项目，不需要点击“加载更多”。
- 视频显示来自原始 MP4 的 A=25%、B=50%、C=75% 三张真实候选帧。
- 视频播放器支持进度条、播放/暂停、左右键 1 帧、Shift+左右键 10 帧精调。
- 视频可保存为无损 PNG 或高质量 JPG；批量保存默认选择 B 中间帧。
- Scene/Web 可调用 Wallpaper Engine 独立窗口播放，也可逐项应用到桌面并验证锁屏快照更新后保存。
- 右上角提供“自动保存：开/关”；首次默认关闭，开启后每 5 秒检查新快照。
- “查看当前快照”和“播放当前动态壁纸”是两个独立功能。
- SHA-256 内容去重，同一保存目录不会重复产生相同图片。
- 导出文件优先使用 `project.json` 中的原始标题；同名冲突时追加 Workshop ID。
- “当前壁纸”保存也会反查当前 Workshop 项目并使用原始标题，不再只叫“当前壁纸_时间”。
- 所有保存成功、重复跳过和批量完成结果都只显示数秒提示，不弹出需要手动关闭的成功对话框。
- 去重同时检查历史记录和目标文件夹真实内容；即使历史被清空，也不会再次保存完全相同的文件。
- 动态预览命令异步启动，不阻塞主界面；窗口出现后会可靠置前，且预览期间可在外部窗口直接按 Esc 关闭。
- 当前页提供上一张、下一张和 Steam 项目管理入口；图库每张卡片也可打开对应 Steam 页面。
- 支持自定义桌面全局快捷键：保存当前最高画质、下一张、上一张，默认分别为 `Ctrl+Alt+S`、`Ctrl+Alt+Right`、`Ctrl+Alt+Left`。
- 支持更换默认保存位置，也支持按“本程序发现日期”筛选历史并另存到其他文件夹。
- “桌面全局快捷键”是独立页面，集中显示保存、上一张、下一张和 Steam 项目管理；设置与更新历史也从这里直接进入。
- 全程只读源文件：不移动、不删除、不修改 Wallpaper Engine 或 Windows Themes 内容。

动态预览点击后可能短暂加载或卡顿，这是当前已知限制；关闭动态预览按钮和 Esc 关闭逻辑保持可用。

## Steam 取消订阅边界

- 程序会按 Workshop ID 打开准确的 Steam 项目页，方便用户在已登录的 Steam 中点击取消订阅。
- Wallpaper Engine 没有公开的“取消订阅当前项目”命令；Steam 的真正取消订阅依赖用户登录会话和 Steamworks 上下文。
- 因此本程序不会伪装成已经一键取消订阅，也不会通过删除本地 Workshop 文件夹冒充取消订阅。
- “上一张”读取 Wallpaper Engine 的最近项目记录；若配置中没有可用历史，会如实提示无法返回。

## 直接使用 EXE

推荐下载 `dist\WallpaperExporter_V1.zip`，解压后双击：

`WallpaperExporter.exe`

V1 使用文件夹版运行库，避免单文件 EXE 每次启动时重复解压大型 Qt 组件。不要只移动 EXE；请保留解压后的 `_internal` 文件夹。

第一次运行时，默认保存位置为：

`%USERPROFILE%\Pictures\Wallpaper Engine 导出`

程序配置与历史记录位于：

`%LOCALAPPDATA%\WallpaperExporter`

## Wallpaper 库使用方法

1. 打开“Wallpaper 库”，等待扫描完成。
2. 使用项目原始名称、Workshop ID 或类型筛选项目。
3. 视频项目点击“三候选 / 精细选帧”：
   - A 为 25%，B 为 50%，C 为 75%。
   - 左右方向键前后移动 1 帧，`Shift + 左/右`移动 10 帧，空格播放或暂停。
   - 恒定帧率视频按帧率换算单帧时间；特殊可变帧率视频显示“最接近可解码帧”。
4. 勾选多个视频后，点击“视频按 B 中间帧批量保存”。
5. 勾选 Scene/Web 后，点击“保存勾选的直接 / Scene 类”。该操作会连续切换桌面，结束时尝试恢复原壁纸。
6. 图库使用低清项目预览图帮助识别，但不会把这些预览图当作最终壁纸保存。
7. 默认紧凑模式约为每排 6 张；点击“放大”可切换为更大的 4 张或 3 张完整预览。窗口缩放停止约 160ms 后才重排，避免连续重建导致黑块。

## 从源代码运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

## 运行测试

```powershell
python -m unittest discover -s tests -v
python -m compileall -q main.py wallpaper_exporter tests
```

## 构建 EXE

```powershell
.\build.ps1
```

## 画质说明

- JPG 保存为 JPG，PNG 保存为 PNG。
- 程序不会把 2K 图片软件放大为 4K，因为放大不会恢复原始细节。
- 当前快照的最高画质上限由 Wallpaper Engine 实际写入的 `WallpaperEngineLockOverride.jpg` 决定。
- 若 Windows Themes 中存在多张图片，批量页面按真实像素面积从高到低排列；完全相同的文件只表示一次。
- 选择 JPG 还是 PNG 不决定清晰度，实际像素尺寸和源图内容才决定可保留的细节。
- 从视频保存 PNG 可以避免再次有损压缩，但不会产生超出原视频分辨率的额外细节。
- 高质量 JPG 文件较小，但会进行一次新的有损编码。
- Scene/Web 没有现成最终图片；保存质量上限取决于 Wallpaper Engine 实际生成的桌面覆盖快照。
- 2K 快照放大到 4K只会增加像素数量，不会恢复不存在的细节，因此程序不提供虚假“4K 增强”。
- “检查原生 4K”只检查真实来源：当前项目若是原始 4K 视频，就从原视频保存 4K 帧；若来源仍是 2K/1080p 或 Scene 的 2K 快照，则明确提示无法获得原生 4K。

## Scene/Web 安全说明

- 执行批量 Scene/Web 保存前，程序会明确提示桌面将连续变化。
- 每个项目都必须同时满足“Wallpaper Engine 当前配置已切换到对应 Workshop ID”和“覆盖快照已更新”，否则记为失败，不会沿用上一张图。
- 任务完成或取消后，会读取 Wallpaper Engine 开始任务前的项目路径并尝试恢复。
- 自动化测试不会真实切换用户桌面；该部分必须由用户按验收清单执行真实测试。

## 素材说明

界面中的头像与横幅裁切自用户为本项目提供的参考图，仅随本地程序使用。程序同时包含一个由 Qt 绘制、无需外部生成服务的原创 Q 版“樱海小助手”。当前会话没有提供 `imagegen` 内置位图生成工具，因此没有切换到需要 API 密钥的 CLI 路径。
