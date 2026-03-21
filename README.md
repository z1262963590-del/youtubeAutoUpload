# youtubeAutoUpload

一个可配置定时点的 YouTube 自动上传脚本：
- 你把本地视频放到指定目录；
- 在配置里自定义每天的多个时间点；
- 每到一个时间点，脚本会随机挑选一个“尚未上传过”的视频上传到 YouTube。

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 准备 Google API 凭证

1. 打开 Google Cloud Console 创建项目并启用 **YouTube Data API v3**。
2. 创建 OAuth 客户端（Desktop App）。
3. 下载凭证文件并重命名为 `client_secret.json`，放在项目根目录。

首次运行会拉起浏览器授权，生成 `token.json`。

## 3. 配置定时和目录

复制模板：

```bash
cp config.example.json config.json
```

然后编辑 `config.json`：

- `video_directory`: 你本地视频目录。
- `schedule_times`: 每天执行上传的时间点（24 小时制），例如 `"09:00"`、`"21:30"`。
- `timezone`: 时区，例如 `Asia/Shanghai`。
- `privacy_status`: `private` / `public` / `unlisted`。
- `state_file`: 已上传文件记录（用于避免重复上传）。

## 4. 运行

```bash
python uploader.py
```

脚本会常驻运行并在设定时间点触发上传。

## 注意事项

- 默认支持扩展名：`.mp4 .mov .mkv .avi .webm`。
- 每次只上传一个随机视频。
- 上传成功后会把文件名写入 `upload_state.json`（或你配置的 `state_file`）。
- 如果所有视频都上传过了，会在日志中提示没有可上传视频。


## 5. 拼接多个视频为刚好超过 1 分钟的新视频

如果你想先从某个目录里随机挑几个视频，拼接成一个**总时长刚刚大于 1 分钟**的新视频，可以使用新增工具：`video_concat_tool.py`。

### 依赖

这个工具依赖系统安装 `ffmpeg` 和 `ffprobe`。

### 命令行用法

```bash
python video_concat_tool.py \
  --source-dir ./videos \
  --output-dir ./combined_videos \
  --target-seconds 60 \
  --output-name combined_1min
```

说明：
- 工具会在 `source-dir` 下随机选择多个视频。
- 一旦总时长**超过** `target-seconds`（默认 60 秒）就停止继续选择。
- 拼接结果会输出到 `output-dir`。
- 输出文件默认是 `.mp4`。

### 代码里调用

```python
from pathlib import Path
from video_concat_tool import VideoConcatTool

tool = VideoConcatTool(
    source_dir=Path("./videos"),
    output_dir=Path("./combined_videos"),
    target_seconds=60,
)

tool.create_video(output_name="combined_1min")
```
