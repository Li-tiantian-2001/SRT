自检说明

自检按钮会使用 `samples/sample.wav` 生成 `SRT_OUT/sample.srt`。

准备工作
~~- 确保模型文件存在：tokens.txt、paraformer.onnx、silero_vad.onnx~~
-确保模型文件存在：tokens.txt、model.onnx、silero_vad.onnx
- 确保 ffmpeg 已随包提供：tools/ffmpeg/ffmpeg.exe 与 ffprobe.exe
- 确保 samples/sample.wav 存在

执行步骤
1. 打开程序，点击 “自检”
~~2. 在 `SRT_OUT` 中检查是否生成 `sample.srt`~~
2. 在 `输入文件的文件夹` 中检查是否生成 `sample.srt`
3. 如失败，请查看 `logs/run.log`，确认缺失文件或路径
