import argparse
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


@dataclass(frozen=True)
class VideoClip:
    path: Path
    duration_seconds: float


class VideoConcatTool:
    """从指定目录随机挑选多个视频，拼接出时长刚好大于目标秒数的视频。"""

    def __init__(
        self,
        source_dir: Path,
        output_dir: Path,
        target_seconds: float = 60.0,
        supported_extensions: Optional[Iterable[str]] = None,
    ) -> None:
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.target_seconds = target_seconds
        self.supported_extensions = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in (supported_extensions or SUPPORTED_EXTENSIONS)
        }

    def ensure_ffmpeg_tools(self) -> None:
        missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
        if missing_tools:
            raise EnvironmentError(
                "缺少视频处理依赖工具: "
                f"{', '.join(missing_tools)}。请先安装 FFmpeg 并确保 ffmpeg / ffprobe 可执行。"
            )

    def list_videos(self) -> List[Path]:
        if not self.source_dir.exists():
            raise FileNotFoundError(f"源视频目录不存在: {self.source_dir}")

        videos = [
            path
            for path in sorted(self.source_dir.iterdir())
            if path.is_file() and path.suffix.lower() in self.supported_extensions
        ]
        if not videos:
            raise FileNotFoundError(f"源视频目录下没有可用视频: {self.source_dir}")
        return videos

    def get_duration_seconds(self, video_path: Path) -> float:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    def load_video_clips(self) -> List[VideoClip]:
        return [VideoClip(path=path, duration_seconds=self.get_duration_seconds(path)) for path in self.list_videos()]

    def select_videos(self, clips: Sequence[VideoClip], seed: Optional[int] = None) -> List[VideoClip]:
        if not clips:
            raise ValueError("没有可选视频。")

        shuffled_clips = list(clips)
        rng = random.Random(seed)
        rng.shuffle(shuffled_clips)

        total_duration = 0.0
        selected: List[VideoClip] = []
        for clip in shuffled_clips:
            selected.append(clip)
            total_duration += clip.duration_seconds
            if total_duration > self.target_seconds:
                return selected

        raise ValueError(
            f"目录内全部视频总时长只有 {total_duration:.2f} 秒，仍然无法超过 {self.target_seconds:.2f} 秒。"
        )

    def normalize_video(self, input_path: Path, output_path: Path) -> None:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(output_path),
        ]
        subprocess.run(command, check=True)

    def concat_normalized_videos(self, normalized_paths: Sequence[Path], output_path: Path) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as concat_file:
            for video_path in normalized_paths:
                escaped_path = video_path.as_posix().replace("'", r"'\''")
                concat_file.write(f"file '{escaped_path}'\n")
            concat_list_path = Path(concat_file.name)

        try:
            command = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(output_path),
            ]
            subprocess.run(command, check=True)
        finally:
            concat_list_path.unlink(missing_ok=True)

    def build_output_path(self, output_name: Optional[str] = None) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if output_name:
            filename = output_name if output_name.endswith(".mp4") else f"{output_name}.mp4"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"combined_{timestamp}.mp4"
        return self.output_dir / filename

    def create_video(self, output_name: Optional[str] = None, seed: Optional[int] = None) -> Path:
        self.ensure_ffmpeg_tools()
        clips = self.load_video_clips()
        selected_clips = self.select_videos(clips, seed=seed)
        output_path = self.build_output_path(output_name)

        with tempfile.TemporaryDirectory(prefix="video_concat_") as temp_dir:
            temp_dir_path = Path(temp_dir)
            normalized_paths: List[Path] = []
            for index, clip in enumerate(selected_clips, start=1):
                normalized_path = temp_dir_path / f"segment_{index:03d}.mp4"
                self.normalize_video(clip.path, normalized_path)
                normalized_paths.append(normalized_path)

            self.concat_normalized_videos(normalized_paths, output_path)

        total_duration = sum(clip.duration_seconds for clip in selected_clips)
        selected_names = ", ".join(clip.path.name for clip in selected_clips)
        print(
            f"已拼接完成: {output_path}\n"
            f"选中视频: {selected_names}\n"
            f"原始总时长: {total_duration:.2f} 秒（目标: > {self.target_seconds:.2f} 秒）"
        )
        return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="随机选取多个视频并拼接成刚好超过 1 分钟的视频")
    parser.add_argument("--source-dir", required=True, help="源视频目录")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--target-seconds", type=float, default=60.0, help="目标总时长，默认 60 秒")
    parser.add_argument("--output-name", default=None, help="输出文件名，可不带 .mp4")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，便于复现选择结果")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    tool = VideoConcatTool(
        source_dir=Path(args.source_dir),
        output_dir=Path(args.output_dir),
        target_seconds=args.target_seconds,
    )
    tool.create_video(output_name=args.output_name, seed=args.seed)


if __name__ == "__main__":
    main()
