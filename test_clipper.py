import json
import subprocess
from pathlib import Path
from clipper import (youtube_url, select_windows, srt_for, probe, energy_highlights, render)


def test_urls():
    assert youtube_url('https://youtu.be/abcdefghijk?t=10') == 'https://www.youtube.com/watch?v=abcdefghijk'
    for bad in ['https://youtube.com.evil.test/watch?v=abcdefghijk', 'http://youtube.com/watch?v=abcdefghijk', 'https://youtube.com/playlist?list=x', 'https://user@youtube.com/watch?v=abcdefghijk', 'https://youtu.be/a']:
        assert youtube_url(bad) is None


def test_windows():
    picks = select_windows([(5, 90), (4, 0), (3, 20), (2, 40)], 5, 30, 100)
    assert picks
    assert all(0 <= a and a+b <= 100 for a,b in picks)
    assert all(a+b <= c for (a,b),(c,d) in zip(picks,picks[1:]))
    assert select_windows([(1,0)], 3, 30, 5) == [(0,5)]


def test_subtitle_clamping():
    text = srt_for([{'start': 8, 'end': 12, 'text': 'Hello'}, {'start': 14, 'end': 25, 'text': 'World'}], 10, 10)
    assert '00:00:00,000 --> 00:00:02,000' in text
    assert '00:00:04,000 --> 00:00:10,000' in text


def test_real_video_export(tmp_path):
    source = tmp_path / 'input.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=12:duration=3', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', '-c:v', 'libx264', '-threads', '2', '-c:a', 'aac', '-shortest', str(source)], check=True)
    length, audio = probe(source)
    picks = energy_highlights(source, 1, 2, length, audio)
    assert len(picks) == 1
    (tmp_path/'captions.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\nHello test\n')
    for layout in ['Fit full video', 'Center crop']:
        out = tmp_path / ('fit.mp4' if layout == 'Fit full video' else 'crop.mp4')
        render(source, out, 0, 2, layout, captions=True)
        result = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out)]))
        stream = next(s for s in result['streams'] if s['codec_type'] == 'video')
        assert (stream['width'], stream['height']) == (720, 1280)
        assert 1.8 < float(stream['duration']) < 2.2
        assert any(s['codec_type'] == 'audio' for s in result['streams'])


def test_youtube_separate_tracks():
    import yt_dlp
    from clipper import YOUTUBE_FORMAT
    # Modern YouTube can expose only separate video-only and audio-only tracks.
    info = {'id': 'synthetic', 'title': 'Test', 'extractor': 'test', 'webpage_url': 'https://example.com', 'formats': [
        {'format_id': 'v720', 'url': 'https://example.com/v.mp4', 'ext': 'mp4', 'height': 720, 'vcodec': 'h264', 'acodec': 'none'},
        {'format_id': 'v1080', 'url': 'https://example.com/v1080.mp4', 'ext': 'mp4', 'height': 1080, 'vcodec': 'h264', 'acodec': 'none'},
        {'format_id': 'audio', 'url': 'https://example.com/a.webm', 'ext': 'webm', 'vcodec': 'none', 'acodec': 'opus'},
    ]}
    with yt_dlp.YoutubeDL({'format': YOUTUBE_FORMAT, 'quiet': True, 'no_warnings': True}) as y:
        selected = y.process_ie_result(info, download=False)
    assert [f['format_id'] for f in selected['requested_formats']] == ['v720', 'audio']


def test_youtube_limits_are_explained():
    import pytest
    from clipper import validate_youtube_input, MAX_BYTES
    assert validate_youtube_input({'duration': 1080, 'is_live': False}) is None
    with pytest.raises(ValueError, match='51.5 minutes'):
        validate_youtube_input({'duration': 3092})
    with pytest.raises(ValueError, match='Live streams'):
        validate_youtube_input({'is_live': True})
    with pytest.raises(ValueError, match='200 MB'):
        validate_youtube_input({'requested_formats': [{'filesize': MAX_BYTES}, {'filesize': 1}]})
