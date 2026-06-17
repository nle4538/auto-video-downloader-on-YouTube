import os
import yaml
from datetime import datetime, timedelta
from googleapiclient.http import MediaFileUpload
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import pytz
import time
import logging
import shutil

# —-------------------------------------------------------------—
# CONFIG
# —-------------------------------------------------------------—

CLIENT_SECRET_FILE = 'client_secrets.json'
CREDENTIALS_PICKLE = 'token.pickle'
VIDEO_DIR = 'videos/'
CONFIG_FILE = 'config.yaml'
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]    
LOG_FILE = "upload_log.txt"
UPLOADED_DIR = os.path.join(VIDEO_DIR, "uploaded")

# Часовой пояс
tz = pytz.timezone('Asia/Yekaterinburg')  # Можно изменить на свой

# Логирование
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    encoding='utf-8'
)

# —-------------------------------------------------------------—
# AUTH & UTILS
# —-------------------------------------------------------------—

def get_authenticated_service():
    credentials = None
    if os.path.exists(CREDENTIALS_PICKLE):
        with open(CREDENTIALS_PICKLE, 'rb') as f:
            credentials = pickle.load(f)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open(CREDENTIALS_PICKLE, 'wb') as f:
            pickle.dump(credentials, f)
    return build("youtube", "v3", credentials=credentials)

def schedule_time(date_str, time_str):
    dt_str = f"{date_str} {time_str}"
    dt = tz.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
    return dt.isoformat()

# —-------------------------------------------------------------—
# UPLOAD LOGIC
# —-------------------------------------------------------------—

def upload_video(youtube, full_path, title, description, tags, scheduled_at, made_for_kids, category_id):
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": scheduled_at,
            "selfDeclaredMadeForKids": made_for_kids
        }
    }

    try:
        media = MediaFileUpload(full_path)
        response = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        ).execute()

        msg = f"✅ Видео '{title}' загружено: {response['id']}"
        print(msg)
        logging.info(msg)
        return True
    except Exception as e:
        msg = f"❌ Ошибка при загрузке: {str(e)}"
        print(msg)
        logging.error(msg)
        return False

# —-------------------------------------------------------------—
# MAIN FUNCTION
# —-------------------------------------------------------------—

def main():
    youtube = get_authenticated_service()

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    use_defaults = config.get("use_default_params", False)
    default_params = config.get("default_params", {})
    schedule_blocks = config.get("schedule", [])
    videos_config = config.get("videos", [])

    uploaded_count = 0

    # Получаем список всех .mp4 файлов в папке videos/
    
    video_files = sorted([f for f in os.listdir(VIDEO_DIR) if f.endswith(".mp4")])
    total_videos = len(video_files)

    print(f"Найдено видео в папке: {total_videos}")
    print(f"Блоки расписания: {len(schedule_blocks)}")
    print(f"Использовать общие параметры: {'Да' if use_defaults else 'Нет'}")

    if len(videos_config) < total_videos and not use_defaults:
        print("⚠️ Недостаточно данных в конфиге для всех видео")
        print(f"ℹ️  Будут загружены первые {len(videos_config)} видео")
        total_videos = len(videos_config)

    for idx_block, conf in enumerate(schedule_blocks):
        base_date = conf["date"]
        base_time = conf["time"]

        scheduled_at = schedule_time(base_date, base_time)
        print(f"\n🚀 Загрузка блока #{idx_block + 1} ({scheduled_at})")
        logging.info(f"--- Блок #{idx_block + 1}: {scheduled_at} ---")

        start_index = idx_block * 3
        end_index = min(start_index + 3, total_videos)

        block_videos = videos_config[start_index:end_index]

        if not block_videos:
            print("❌ Нет данных для этого блока")
            continue

        for i, video_data in enumerate(block_videos):
            filename_idx = start_index + i
            if filename_idx >= total_videos:
                print("❌ Нет файла для загрузки")
                break

            filename = video_files[filename_idx]
            full_path = os.path.join(VIDEO_DIR, filename)

            if not os.path.isfile(full_path):
                print(f"❌ Файл {filename} не найден!")
                logging.warning(f"❌ Файл {filename} не найден")
                continue

            title = video_data.get("title", filename.replace('.mp4', ''))
            description = video_data.get("description", "")
            tags = video_data.get("tags", [])
            category_id = str(video_data.get("category_id", "22"))
            made_for_kids = video_data.get("made_for_kids", False)

            print(f"🎥 Загружается: {filename}")

            success = upload_video(
                youtube=youtube,
                full_path=full_path,
                title=title,
                description=description,
                tags=tags,
                scheduled_at=scheduled_at,
                made_for_kids=made_for_kids,
                category_id=category_id
            )

            if success:
                shutil.move(full_path, os.path.join(UPLOADED_DIR, filename))
                print(f"✅ {filename} перемещено в 'uploaded'")
                logging.info(f"✅ {filename} перемещено в 'uploaded'")
                uploaded_count += 1

            time.sleep(5)

        print("\n⏳ Ждём 1 минуту перед следующим блоком...")
        time.sleep(60)

    print(f"\n🎉 Загружено видео: {uploaded_count}")

if __name__ == "__main__":
    if not os.path.exists(UPLOADED_DIR):
        os.makedirs(UPLOADED_DIR)

    main()