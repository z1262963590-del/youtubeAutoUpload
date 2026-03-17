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
