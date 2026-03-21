import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from requests_oauthlib import OAuth1

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
POST_TWEET_URL = "https://api.twitter.com/2/tweets"
MEDIA_STATUS_CHECK_INTERVAL_SECONDS = 5
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024


class XUploadError(Exception):
    pass


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def load_config(config_path: Path) -> Dict:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing {config_path}. Copy x_config.example.json to x_config.json and edit it."
        )

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    required_keys = [
        "video_directory",
        "schedule_times",
        "timezone",
        "state_file",
        "x_api_key",
        "x_api_secret",
        "x_access_token",
        "x_access_token_secret",
    ]
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


def create_oauth1(config: Dict) -> OAuth1:
    return OAuth1(
        client_key=config["x_api_key"],
        client_secret=config["x_api_secret"],
        resource_owner_key=config["x_access_token"],
        resource_owner_secret=config["x_access_token_secret"],
    )


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


def build_post_text(video_path: Path, config: Dict) -> str:
    template = config.get("post_text_template", "{filename}")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = template.format(
        filename=video_path.name,
        stem=video_path.stem,
        timestamp=now_str,
    ).strip()

    if not text:
        raise ValueError("post_text_template generated an empty post text.")

    return text


def raise_for_x_error(response: requests.Response, context: str) -> None:
    if response.ok:
        return

    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    raise XUploadError(f"{context} failed with status {response.status_code}: {payload}")


def init_media_upload(auth: OAuth1, video_path: Path, media_category: str) -> str:
    response = requests.post(
        MEDIA_UPLOAD_URL,
        auth=auth,
        data={
            "command": "INIT",
            "media_type": "video/mp4",
            "total_bytes": video_path.stat().st_size,
            "media_category": media_category,
        },
        timeout=60,
    )
    raise_for_x_error(response, "INIT media upload")
    return response.json()["media_id_string"]


def append_media_chunks(auth: OAuth1, video_path: Path, media_id: str, chunk_size: int) -> None:
    with video_path.open("rb") as f:
        segment_index = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            response = requests.post(
                MEDIA_UPLOAD_URL,
                auth=auth,
                data={
                    "command": "APPEND",
                    "media_id": media_id,
                    "segment_index": segment_index,
                },
                files={"media": chunk},
                timeout=120,
            )
            raise_for_x_error(response, f"APPEND media upload segment {segment_index}")
            segment_index += 1


def finalize_media_upload(auth: OAuth1, media_id: str) -> Dict:
    response = requests.post(
        MEDIA_UPLOAD_URL,
        auth=auth,
        data={
            "command": "FINALIZE",
            "media_id": media_id,
        },
        timeout=60,
    )
    raise_for_x_error(response, "FINALIZE media upload")
    return response.json()


def wait_for_media_processing(auth: OAuth1, media_id: str, processing_info: Optional[Dict]) -> None:
    info = processing_info
    while info:
        state = info.get("state")
        if state == "succeeded":
            return
        if state == "failed":
            error = info.get("error", {})
            raise XUploadError(f"Media processing failed: {error}")

        wait_seconds = int(info.get("check_after_secs", MEDIA_STATUS_CHECK_INTERVAL_SECONDS))
        logging.info("Media still processing, checking again in %s seconds", wait_seconds)
        time.sleep(wait_seconds)

        response = requests.get(
            MEDIA_UPLOAD_URL,
            auth=auth,
            params={
                "command": "STATUS",
                "media_id": media_id,
            },
            timeout=60,
        )
        raise_for_x_error(response, "STATUS media upload")
        payload = response.json()
        info = payload.get("processing_info")


def upload_media(auth: OAuth1, video_path: Path, config: Dict) -> str:
    media_category = config.get("media_category", "tweet_video")
    chunk_size = int(config.get("upload_chunk_size", DEFAULT_CHUNK_SIZE))

    media_id = init_media_upload(auth, video_path, media_category)
    append_media_chunks(auth, video_path, media_id, chunk_size)
    finalize_payload = finalize_media_upload(auth, media_id)
    wait_for_media_processing(auth, media_id, finalize_payload.get("processing_info"))
    return media_id


def create_tweet(auth: OAuth1, text: str, media_id: str) -> str:
    response = requests.post(
        POST_TWEET_URL,
        auth=auth,
        json={
            "text": text,
            "media": {"media_ids": [media_id]},
        },
        timeout=60,
    )
    raise_for_x_error(response, "Create tweet")
    return response.json()["data"]["id"]


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
        auth = create_oauth1(config)
        media_id = upload_media(auth, video_to_upload, config)
        tweet_text = build_post_text(video_to_upload, config)
        tweet_id = create_tweet(auth, tweet_text, media_id)
    except Exception as e:
        logging.error("Upload to X failed: %s", e)
        return

    uploaded_files.append(video_to_upload.name)
    state["uploaded_files"] = uploaded_files
    save_state(state_file, state)

    logging.info("Upload to X succeeded. Tweet ID: %s", tweet_id)


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
        scheduler.add_job(
            run_upload_job,
            trigger=trigger,
            args=[config],
            id=f"x-upload-{hour}-{minute}",
        )
        logging.info("Added schedule: %s", schedule_time)

    return scheduler


def main() -> None:
    setup_logging()
    config = load_config(Path("x_config.json"))

    scheduler = schedule_jobs(config)
    logging.info("X scheduler started. Waiting for configured upload times...")
    scheduler.start()


if __name__ == "__main__":
    main()
