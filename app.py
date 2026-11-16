import io
import tempfile
import zipfile
from pathlib import Path

import streamlit as st
from clipper import (MAX_BYTES, download, probe, energy_highlights, speech_highlights,
                     render, srt_for, youtube_url)

st.set_page_config(page_title='AutoClip Studio', page_icon='🎬', layout='wide')
st.markdown('''<style>.stApp {background: #0b1020;} h1 {letter-spacing:-1.5px;}
div.stButton > button[kind="primary"] {border-radius:12px;}
.block-container {max-width:1100px;}</style>''', unsafe_allow_html=True)
st.caption('AUTOCLIP STUDIO  /  YOUR VIDEO → YOUR NEXT SHORT')
st.title('Long videos. Short highlights.')
st.write('Turn your footage into vertical clips for TikTok, Reels and YouTube Shorts.')

@st.cache_resource
def speech_model():
    from faster_whisper import WhisperModel
    return WhisperModel('tiny', device='cpu', compute_type='int8', cpu_threads=2, num_workers=1)

with st.sidebar:
    st.header('Clip settings')
    count = st.slider('Number of clips', 1, 5, 3)
    seconds = st.select_slider('Clip length (seconds)', [15, 20, 30, 45, 60], value=30)
    layout = st.selectbox('Vertical framing', ['Fit full video', 'Center crop'])
    use_ai = st.toggle('AI speech transcription & captions', value=False)
    st.caption('AI mode downloads a speech model on first use and can take several minutes. Supports English, Spanish and more.')
    st.caption('Highlights use audio energy, or simple transcript ranking in AI mode. No face tracking or guaranteed viral picks.')
    st.caption('Maximum: 200 MB and 20 minutes. Start with a short video on free hosting.')

source = st.radio('Video source', ['Upload video', 'YouTube link'], horizontal=True)
video = None
url = ''
if source == 'Upload video':
    video = st.file_uploader('Drop your video here', type=['mp4', 'mov', 'webm', 'mkv'])
else:
    url = st.text_input('YouTube video link', placeholder='https://www.youtube.com/watch?v=...')
    st.caption('YouTube can block downloads on cloud hosts. If that happens, upload your authorized copy.')
allowed = st.checkbox('I own this video or have permission to download and edit it.')

if st.button('✦ Generate my clips', type='primary', use_container_width=True):
    if not allowed:
        st.error('Confirm permission to use the video first.')
    elif (source == 'Upload video' and video is None) or (source == 'YouTube link' and not youtube_url(url)):
        st.error('Upload a video or enter a valid YouTube video link.')
    elif video is not None and video.size > MAX_BYTES:
        st.error('Choose a video smaller than 200 MB.')
    else:
        st.session_state.pop('results', None)
        try:
            with st.status('Preparing your video…', expanded=True) as status:
                with tempfile.TemporaryDirectory() as tmp:
                    folder = Path(tmp)
                    if source == 'Upload video':
                        path = folder / ('source' + Path(video.name).suffix.lower())
                        path.write_bytes(video.getbuffer())
                    else:
                        path = download(url, folder)
                    duration, has_audio = probe(path)
                    segments = []
                    if use_ai:
                        if not has_audio:
                            raise ValueError('AI speech mode needs an audio track. Switch it off for a silent video.')
                        st.write('Transcribing speech with Whisper…')
                        transcribed, _ = speech_model().transcribe(str(path), beam_size=1, vad_filter=True)
                        segments = [{'start': s.start, 'end': s.end, 'text': s.text} for s in transcribed]
                        if not segments:
                            raise ValueError('No speech was detected. Switch AI mode off to use audio highlights.')
                        picks = speech_highlights(segments, count, seconds, duration)
                    else:
                        st.write('Finding audio highlights…')
                        picks = energy_highlights(path, count, seconds, duration, has_audio)
                    clips = []
                    for index, (start, length) in enumerate(picks, 1):
                        st.write(f'Rendering clip {index} of {len(picks)}…')
                        srt = srt_for(segments, start, length)
                        (folder / 'captions.srt').write_text(srt, encoding='utf-8')
                        out = folder / f'clip_{index:02}.mp4'
                        render(path, out, start, length, layout, captions=bool(srt))
                        clips.append({'name': out.name, 'data': out.read_bytes(), 'start': start, 'srt': srt})
                    archive = io.BytesIO()
                    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as bundle:
                        for clip in clips:
                            bundle.writestr(clip['name'], clip['data'])
                            if clip['srt']:
                                bundle.writestr(clip['name'].replace('.mp4', '.srt'), clip['srt'])
                    st.session_state.results = {'clips': clips, 'zip': archive.getvalue()}
                status.update(label=f'Your {len(clips)} clips are ready', state='complete', expanded=False)
        except Exception as exc:
            st.error(f'Could not finish: {exc}')
            st.info('For YouTube errors, try uploading the file. For AI model or memory errors, turn AI mode off or use a shorter video.')

results = st.session_state.get('results')
if results:
    st.subheader('Your clips')
    st.caption('Downloads stay available during this session. Download before closing the page. Fewer clips may fit a short video.')
    st.download_button('Download all clips (ZIP)', results['zip'], 'autoclips.zip', 'application/zip')
    cols = st.columns(2)
    for index, clip in enumerate(results['clips']):
        with cols[index % 2]:
            st.write(f"**Clip {index+1}** · starts at {int(clip['start'])//60:02}:{int(clip['start'])%60:02}")
            st.video(clip['data'])
            st.download_button('Download MP4', clip['data'], clip['name'], 'video/mp4', key=f'mp4_{index}')
            if clip['srt']:
                st.download_button('Download captions', clip['srt'], clip['name'].replace('.mp4', '.srt'), key=f'srt_{index}')
    if st.button('Clear results'):
        del st.session_state['results']
        st.rerun()
