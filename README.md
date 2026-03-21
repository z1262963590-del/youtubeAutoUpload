# youtubeAutoUpload

这个仓库现在包含两套“固定时间自动上传视频”的脚本：
- `uploader.py`：自动上传到 **YouTube**；
- `x_uploader.py`：自动上传到 **X**。

两者都支持：
- 你自己指定视频源文件夹；
- 你自己配置每天的多个固定执行时间；
- 每次到点后随机挑选一个“尚未上传过”的视频进行发布；
- 用状态文件记录已处理文件，避免重复上传。

---

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

---

## 2. YouTube 自动上传

### 2.1 准备 Google API 凭证

1. 打开 Google Cloud Console 创建项目并启用 **YouTube Data API v3**。
2. 创建 OAuth 客户端（Desktop App）。
3. 下载凭证文件并重命名为 `client_secret.json`，放在项目根目录。

首次运行会拉起浏览器授权，生成 `token.json`。

### 2.2 配置 YouTube 上传任务

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
- `default_title_prefix`: 视频标题前缀。
- `default_description`: 默认描述。

### 2.3 运行 YouTube 上传脚本

```bash
python uploader.py
```

脚本会常驻运行并在设定时间点触发上传。

---

## 3. X 自动上传

### 3.1 准备 X API 凭证

你需要在 X Developer Portal 创建应用，并拿到以下 4 个用户级别凭证：
- API Key
- API Key Secret
- Access Token
- Access Token Secret

脚本会使用：
- `upload.twitter.com/1.1/media/upload.json` 完成视频分片上传；
- `api.twitter.com/2/tweets` 创建带视频的帖子。

### 3.2 配置 X 上传任务

复制模板：

```bash
cp x_config.example.json x_config.json
```

然后编辑 `x_config.json`：

- `video_directory`: 你想自动上传到 X 的视频源目录。
- `schedule_times`: 你自己设置的固定时间点，例如 `"10:00"`、`"18:00"`。
- `timezone`: 你的时区。
- `state_file`: X 上传记录文件。
- `x_api_key` / `x_api_secret`: X 应用凭证。
- `x_access_token` / `x_access_token_secret`: 用户授权凭证。
- `post_text_template`: 发帖文案模板，支持：
  - `{filename}`：完整文件名；
  - `{stem}`：不带扩展名的文件名；
  - `{timestamp}`：当前时间戳。
- `media_category`: 默认 `tweet_video`。
- `upload_chunk_size`: 分片上传大小，默认 4MB。

### 3.3 运行 X 上传脚本

```bash
python x_uploader.py
```

脚本会常驻运行，并在你配置的固定时间自动上传一个未发布过的视频到 X。

---

## 4. 注意事项

- 默认支持扩展名：`.mp4 .mov .mkv .avi .webm`。
- 每次只上传一个随机视频。
- 上传成功后会把文件名写入对应的状态文件：
  - YouTube 默认是 `upload_state.json`；
  - X 默认是 `x_upload_state.json`。
- 如果所有视频都上传过了，会在日志中提示没有可上传视频。
- X 的视频时长、体积、编码格式与接口权限限制可能因账号等级/API 计划而不同；如果上传失败，请优先检查开发者权限与视频规格是否符合当前 X API 要求。
