import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def load_config(config_path: Path) -> Dict:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing {config_path}. Copy config.example.json to config.json and edit it."
        )

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    required_keys = ["video_directory", "schedule_times", "timezone", "state_file"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing config key: {key}")

    if not isinstance(config["schedule_times"], list) or not config["schedule_times"]:
        raise ValueError("schedule_times must be a non-empty list like ['09:00', '18:30']")

    return config


def load_state(state_file: Path) -> Dict:
    if not state_file.exists():
        return {"uploaded_files": []}

    with state_file.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state_file: Path, state: Dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with state_file.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_authenticated_service() -> object:
    creds = None
    token_path = Path("token.json")
    client_secret_path = Path("client_secret.json")

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secret_path.exists():
                raise FileNotFoundError(
                    "client_secret.json not found. Create OAuth client in Google Cloud first."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def list_candidate_videos(video_directory: Path, uploaded_files: List[str]) -> List[Path]:
    if not video_directory.exists():
        logging.warning("Video directory does not exist: %s", video_directory)
        return []

    uploaded_set = set(uploaded_files)
    candidates = [
        p
        for p in video_directory.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and p.name not in uploaded_set
    ]
    return candidates


def upload_video(youtube, video_path: Path, config: Dict) -> str:
    title_prefix = config.get("default_title_prefix", "Auto Upload")
    description = config.get("default_description", "Uploaded by youtubeAutoUpload")
    privacy_status = config.get("privacy_status", "private")
    category_id = config.get("category_id", "22")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"{title_prefix} - {video_path.stem} ({now_str})"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    return response["id"]


def run_upload_job(config: Dict) -> None:
    video_directory = Path(config["video_directory"])
    state_file = Path(config["state_file"])

    state = load_state(state_file)
    uploaded_files = state.get("uploaded_files", [])

    candidates = list_candidate_videos(video_directory, uploaded_files)
    if not candidates:
        logging.info("No new videos available for upload.")
        return

    video_to_upload = random.choice(candidates)
    logging.info("Selected video: %s", video_to_upload.name)

    try:
        youtube = get_authenticated_service()
        video_id = upload_video(youtube, video_to_upload, config)
    except HttpError as e:
        logging.error("YouTube API error: %s", e)
        return
    except Exception as e:
        logging.error("Upload failed: %s", e)
        return

    uploaded_files.append(video_to_upload.name)
    state["uploaded_files"] = uploaded_files
    save_state(state_file, state)

    logging.info("Upload succeeded. Video ID: %s", video_id)


def schedule_jobs(config: Dict) -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=config["timezone"])

    for schedule_time in config["schedule_times"]:
        try:
            hour_str, minute_str = schedule_time.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
        except ValueError as e:
            raise ValueError(f"Invalid schedule time '{schedule_time}', use HH:MM") from e

        trigger = CronTrigger(hour=hour, minute=minute, timezone=config["timezone"])
        scheduler.add_job(run_upload_job, trigger=trigger, args=[config], id=f"upload-{hour}-{minute}")
        logging.info("Added schedule: %s", schedule_time)

    return scheduler


def main() -> None:
    setup_logging()
    config = load_config(Path("config.json"))

    scheduler = schedule_jobs(config)
    logging.info("Scheduler started. Waiting for configured upload times...")
    scheduler.start()


if __name__ == "__main__":
    main()
