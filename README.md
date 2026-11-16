# AutoClip Studio

Turn uploaded videos or authorized YouTube videos into vertical MP4 clips.

## Open it as a website

1. Go to https://share.streamlit.io/ and sign in with GitHub.
2. Create an app with repository `aezc2003-del/youtube-ai-clipper`, branch `main`, and main file path `app.py`.
3. Choose Python 3.11 in Advanced settings and click Deploy.

`main.py` also works if your deployment already uses that filename. These files must be at the repository root; the old ZIP alone cannot run as an app.

## Features

- Upload MP4, MOV, WEBM or MKV, or use an authorized YouTube link.
- Generate 1–5 clips of 15–60 seconds, exported at 720×1280.
- Fit the entire video with padding, or center crop.
- Optional multilingual AI speech transcription with the Whisper tiny model, burned-in subtitles and SRT downloads. No paid API key required.
- MP4 and ZIP downloads persist through button interactions during the current session.
- Without AI mode, highlights use audio energy; with AI mode, they use simple transcript density and hook-word scoring. Selection is heuristic, not an LLM quality assessment.

## Run locally

Install Python 3.11 and FFmpeg (including ffprobe), then:

```sh
pip install -r requirements.txt
streamlit run app.py
```

## Limits

Maximum 200 MB, 20 minutes per input. AI mode downloads a model on first use and needs model-host network access. Free cloud resources may struggle with longer videos or simultaneous users. Start with a short upload and AI mode off. YouTube downloads can be blocked on cloud hosts; upload a local copy if needed. Downloads are temporary and disappear when the session ends. No face tracking, automatic TikTok posting, streamer discovery or guaranteed viral moments.

Use footage you own or have permission to download and edit. This app does not require or store account passwords or API keys. Do not commit secrets to this public repository.

## Verify

```sh
pip install pytest
pytest -q
```

Tests cover URL validation, non-overlapping clip selection, subtitle timing, and actual FFmpeg exports with audio, captions, and both layouts. Transcription needs a model download and is not covered by the offline tests.
