"""Video processing; no account credentials or paid API required."""
import json
import math
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import numpy as np

MAX_BYTES = 200 * 1024 * 1024
MAX_SECONDS = 20 * 60
YOUTUBE_FORMAT = 'bv*[height<=720]+ba/b[height<=720]'


def run(args, cwd=None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=900, cwd=cwd)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-1200:])
    return result.stdout


def probe(path):
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))
    length = float(data['format']['duration'])
    if not math.isfinite(length) or length <= 0 or length > MAX_SECONDS:
        raise ValueError('Use a video between 1 second and 20 minutes long.')
    if not any(s['codec_type'] == 'video' for s in data['streams']):
        raise ValueError('This file has no video track.')
    return length, any(s['codec_type'] == 'audio' for s in data['streams'])


def youtube_url(value):
    try:
        u = urlparse(value.strip())
        if u.scheme != 'https' or u.username or u.password or u.port:
            return None
        host = (u.hostname or '').lower()
        if host == 'youtu.be':
            ident = u.path.strip('/')
        elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if u.path == '/watch':
                ident = parse_qs(u.query).get('v', [''])[0]
            elif u.path.startswith(('/shorts/', '/live/')):
                ident = u.path.split('/')[2]
            else:
                return None
        else:
            return None
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', ident):
            return 'https://www.youtube.com/watch?v=' + ident
    except (ValueError, IndexError):
        pass
    return None


def validate_youtube_input(info, *, incomplete=False):
    if info.get('is_live'):
        raise ValueError('Live streams are not supported. Use a finished video.')
    duration = info.get('duration')
    if duration is not None and duration > MAX_SECONDS:
        raise ValueError(f'This video is {duration / 60:.1f} minutes long. The app limit is 20 minutes; use a shorter video or trimmed upload.')
    streams = info.get('requested_formats') or [info]
    size = sum(s.get('filesize') or s.get('filesize_approx') or 0 for s in streams)
    if size > MAX_BYTES:
        raise ValueError('The selected video and audio exceed 200 MB. Upload a smaller copy.')
    return None


def download(url, folder):
    import yt_dlp
    canonical = youtube_url(url)
    if not canonical:
        raise ValueError('Enter a valid HTTPS YouTube video link.')
    downloaded = {}
    def limit(progress):
        downloaded[progress.get('filename', 'source')] = progress.get('downloaded_bytes', 0)
        if sum(downloaded.values()) > MAX_BYTES:
            raise ValueError('Video exceeds the 200 MB limit. Upload a shorter copy.')
    options = {
        'format': YOUTUBE_FORMAT,
        'merge_output_format': 'mkv',
        'outtmpl': str(folder / 'source.%(ext)s'), 'noplaylist': True,
        'quiet': True, 'max_filesize': MAX_BYTES, 'socket_timeout': 30,
        'retries': 2, 'progress_hooks': [limit],
        'match_filter': validate_youtube_input,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([canonical])
    files = [p for p in folder.glob('source.*') if p.stem == 'source' and p.suffix in ('.mp4', '.mkv', '.webm', '.mov')]
    if not files:
        raise RuntimeError('YouTube could not provide this video. Upload your video file instead.')
    if files[0].stat().st_size > MAX_BYTES:
        raise ValueError('Video exceeds 200 MB.')
    probe(files[0])
    return files[0]


def select_windows(candidates, count, seconds, duration):
    length = min(seconds, duration)
    picks = []
    for score, proposed in sorted(candidates, reverse=True):
        start = max(0., min(float(proposed), duration - length))
        if all(start + length <= old or old + length <= start for old, _ in picks):
            picks.append((start, length))
        if len(picks) >= count:
            break
    return sorted(picks)


def energy_highlights(path, count, seconds, duration, has_audio):
    if not has_audio:
        return select_windows([(0, n) for n in range(0, math.ceil(duration), seconds)], count, seconds, duration)
    raw = path.parent / 'audio.raw'
    run(['ffmpeg', '-y', '-i', str(path), '-vn', '-ac', '1', '-ar', '2000', '-f', 'f32le', str(raw)])
    samples = np.fromfile(raw, dtype=np.float32)
    levels = np.array([np.sqrt(np.mean(samples[i:i+2000] ** 2)) for i in range(0, len(samples), 2000)])
    candidates = []
    for start in range(0, max(1, math.ceil(duration - seconds) + 1), max(1, seconds // 4)):
        chunk = levels[start:start+seconds]
        score = float(chunk.mean() + .4 * chunk.max()) if len(chunk) else 0
        candidates.append((score, start))
    return select_windows(candidates, count, seconds, duration)


def speech_highlights(segments, count, seconds, duration):
    # Explainable transcript ranking, not a claim about virality or an LLM judgment.
    hooks = {'why', 'how', 'never', 'secret', 'best', 'worst', 'wait', 'what', 'crazy', 'wow', 'porque', 'cómo', 'mira'}
    candidates = []
    for segment in segments:
        start = max(0, segment['start'] - .2)
        text = ' '.join(s['text'] for s in segments if start <= s['start'] < start + seconds)
        words = re.findall(r'\w+', text.lower())
        score = len(set(words) & hooks) * 3 + text.count('?') + min(len(words) / max(seconds, 1), 4)
        candidates.append((score, start))
    return select_windows(candidates, count, seconds, duration)


def timestamp(seconds):
    milliseconds = round(max(0, seconds) * 1000)
    secs, ms = divmod(milliseconds, 1000)
    mins, sec = divmod(secs, 60)
    hours, minute = divmod(mins, 60)
    return f'{hours:02}:{minute:02}:{sec:02},{ms:03}'


def srt_for(segments, start, length):
    blocks = []
    for segment in segments:
        a, b = max(start, segment['start']), min(start + length, segment['end'])
        if b > a:
            blocks.append(f"{len(blocks)+1}\n{timestamp(a-start)} --> {timestamp(b-start)}\n{segment['text'].strip()}\n")
    return '\n'.join(blocks)


def render(path, out, start, length, layout='Fit full video', captions=False):
    if layout == 'Center crop':
        vf = 'scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1'
    else:
        vf = 'scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1'
    # Subtitle filename is generated internally; source filenames never enter filter syntax.
    if captions:
        vf += ",subtitles=captions.srt:force_style='FontSize=20,Outline=2,MarginV=70'"
    run(['ffmpeg', '-y', '-ss', str(start), '-i', str(path.resolve()), '-t', str(length),
         '-vf', vf, '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast', '-crf', '25',
         '-c:a', 'aac', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out.resolve())], cwd=str(out.parent))
