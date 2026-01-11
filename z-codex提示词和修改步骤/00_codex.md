ROLE: 你是架构师 + 交付工程师。目标是“0 基础用户下载解压双击即用”的字幕软件。
硬性规则：禁止编写/改写 VAD/ASR/字幕生成/时间戳/音频切分等核心逻辑。
必须最大化复用 sherpa-onnx 官方资源：
- 引擎必须使用官方脚本 python-api-examples/generate-subtitles.py（当黑盒调用，不复制其核心实现到新文件里，不改其算法逻辑）
- 仅允许写：GUI壳、参数配置、目录遍历、下载模型/依赖、打包、日志

产品交付（Windows 优先）：
- 输出一个 Release 资产：SubtitleMaker-Windows-Portable.zip
- 解压后包含：字幕生成器.exe + models/ + tools/ffmpeg/ + SRT_OUT/ + CACHE/ + logs/
- 用户无需安装 Python/ffmpeg，无需环境变量

必须实现的用户体验（中文）：
1) 主界面按钮：
   - 选择文件（支持 mp4/mov/m4a/mp3/wav 等）
   - 选择输入文件夹（批量）
   - 选择模型目录（默认 ./models）
   - 输出目录（默认 ./SRT_OUT）
   - 开始 / 取消
   - 自检（用 samples/sample.wav 生成 sample.srt）
   - 打开输出文件夹
2) 第一次运行若缺少模型/依赖：
   - 提示缺哪些文件（tokens.txt、paraformer.onnx、silero_vad.onnx、ffmpeg.exe/ffprobe.exe）
   - 提供“一键下载（GitHub / hf-mirror 二选一）”以及“手动导入（打开文件夹）”
3) 运行日志：把官方脚本 stdout/stderr 原样显示（中文加一层说明即可）

引擎调用方式（必须与官方脚本一致）：
- 对 paraformer：调用示例必须符合官方脚本说明（silero-vad-model/tokens/paraformer/num-threads/decoding-method 等参数），输入为 1 个媒体文件路径。
- 注意：官方脚本依赖 ffmpeg 支持媒体解码（工具需随包附带）。
（你不需要写算法，只需要组织参数并调用脚本）

实现方式（推荐）：
- 用 Python + Tkinter 写 GUI 壳（少代码、稳定）
- 把 sherpa-onnx 作为 git submodule 或 vendor（只为了拿到 generate-subtitles.py，不要求用户安装它）
- 用 PyInstaller 打包 GUI 壳 + 运行所需的 python 依赖
- Portable 目录里附带 tools/ffmpeg（windows 版 ffmpeg.exe + ffprobe.exe）

CI / 发布：
- 加 GitHub Actions：
  - push tag v* 时自动构建 Windows Portable zip
  - 上传到 Release artifacts
- 在 docs/一键使用.md 写“下载-解压-双击-生成字幕”的图文步骤（可纯文字）

Repo 结构（请创建）：
/app
  /launcher        # GUI 壳源码
  /vendor/sherpa-onnx/python-api-examples/generate-subtitles.py  # 官方脚本（不改算法）
  /tools/ffmpeg    # 打包进 portable
  /models          # 默认模型目录
  /samples         # 自检样例
  /SRT_OUT
  /CACHE
  /logs
/docs
  一键使用.md
  SELF_TEST.md

最后强制自检：
- 运行字幕生成器.exe，点击“自检”，必须在 SRT_OUT 生成 sample.srt
- 选择一个 mp4 也能生成 srt
- 若失败，错误提示必须告诉用户缺了哪个文件/路径
