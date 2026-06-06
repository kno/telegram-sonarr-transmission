from types import SimpleNamespace

from app.media import extract_media_info, get_media


def _message(**overrides):
    base = {
        "document": None,
        "video": None,
        "audio": None,
        "photo": None,
        "sticker": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _media(file_name="file.mkv", file_size=1234, mime_type="video/x-matroska"):
    return SimpleNamespace(file_name=file_name, file_size=file_size, mime_type=mime_type)


def test_get_media_prefers_document_then_video_audio_photo():
    document = _media("doc.mkv")
    video = _media("video.mp4")
    audio = _media("track.mp3")
    photo = _media(None, 2048, "image/jpeg")

    assert get_media(_message(document=document, video=video)) is document
    assert get_media(_message(video=video, audio=audio)) is video
    assert get_media(_message(audio=audio, photo=photo)) is audio
    assert get_media(_message(photo=photo)) is photo


def test_extract_media_info_supports_audio_and_photo():
    audio_info = extract_media_info(_message(audio=_media("song.flac", 4096, "audio/flac")))
    photo_info = extract_media_info(_message(photo=_media(None, 2048, "image/jpeg")))

    assert audio_info == {"filename": "song.flac", "size": 4096, "mime_type": "audio/flac"}
    assert photo_info == {"filename": None, "size": 2048, "mime_type": "image/jpeg"}


def test_extract_media_info_excludes_text_and_stickers():
    text_message = _message()
    sticker_message = _message(sticker=_media("sticker.webp", 100, "image/webp"))

    assert extract_media_info(text_message) is None
    assert extract_media_info(sticker_message) is None
