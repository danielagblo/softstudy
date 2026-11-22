# StudySoft

Live study overlay for Zoom / Google Meet tutorials.

It listens to tutorial audio, detects questions, searches **your course materials**, and shows answers on an always-on-top overlay.

## What it does

1. Captures speaker audio (loopback) or microphone
2. Transcribes speech in near real time (Whisper)
3. Detects question-like phrases
4. Retrieves answers from PDFs / TXT / DOCX / MD in `materials/`
5. Shows the answer on a floating overlay

## Quick start (Windows)

```powershell
cd C:\Users\Dora\Desktop\STUDYSOFT
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

1. Put each course in its own folder under `materials/` (e.g. `materials/Biology/`, `materials/Math/`)
2. On the overlay or backend page, select the course for your current Zoom class
3. Join Zoom/Meet and click **Start Listening**
4. Saying the course name on the call can also auto-switch the active course

First Whisper run downloads the model (`base`). That can take a minute.

## Capturing Zoom / Meet audio

StudySoft prefers **speaker loopback** (what you hear).

If loopback is missing:

- Enable **Stereo Mix** in Windows Sound settings, or
- Install a virtual cable (e.g. VB-Audio Cable) and set Meet/Zoom output to it, or
- Use a second device / mic near the speakers (lower quality)

## Optional clearer answers

Copy `.env.example` → `.env` and set:

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Without a key, StudySoft still works: it shows the best matching passages from your materials.

## Supported materials

- `.pdf`
- `.txt` / `.md`
- `.docx`

## Tips

- Put notes, slides exports, past papers, and handouts in `materials/`
- Click **Rebuild Index** after adding files
- Drag the overlay anywhere; it stays on top
- Use a quieter room / headphones for cleaner transcripts

## Privacy

Audio is processed locally with Whisper by default. Course files stay on your PC. Only optional OpenAI mode sends the question + retrieved text snippets to the API.
