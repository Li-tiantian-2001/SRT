构建与打包（开发者）

依赖
- 已拉取 sherpa-onnx 官方脚本：
  `app/vendor/sherpa-onnx/python-api-examples/generate-subtitles.py`
- `tools/ffmpeg/` 内含 `ffmpeg.exe` 与 `ffprobe.exe`

PyInstaller 示例
1. 在仓库根目录运行：
   `powershell -ExecutionPolicy Bypass -File scripts/build_portable.ps1`
2. 确保便携目录包含：
   - `models/`
   - `tools/ffmpeg/`
   - `SRT_OUT/`
   - `CACHE/`
   - `logs/`
3. 产物为 `SubtitleMaker-Windows-Portable.zip`

注意
- `config.json` 可调整模型路径与脚本参数
- `download_sources` 需要填写实际下载地址
