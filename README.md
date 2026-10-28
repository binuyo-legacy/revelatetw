# RevelateTW

Church presentation software that listens to live preaching and auto-queues Bible verses for operator approval.

RevelateTW is a Windows presentation app for churches. While the preacher speaks, it listens through a microphone or audio feed, recognises Bible references and paraphrased verses, and places them in a queue. Nothing reaches the projector until a human operator approves it. The operator stays in control of every slide, and the app does the searching.

## Who it is for

RevelateTW is built for churches in Africa and other regions where a full presentation suite is expensive and where the church computer is often a modest machine running two or three other programs at the same time. The app is designed to stay light: the operator window updates once per second only while it is visible, and the projection window animates only during a slide change.

## Features

Bible
- Four translations: King James Version (KJV), American Standard Version (ASV), World English Bible (WEB), and Yoruba Contemporary.
- Translation dropdown on the Verses tab. The choice is remembered in settings.
- Add your own licensed translation from a JSON file (Settings > Bible > Add translation).
- Manual verse search by book, chapter and verse.

Live detection
- Listens to a microphone, mixing desk, external soundcard or WASAPI loopback and transcribes speech with faster-whisper.
- Detects citations spoken as digits or words (for example "John chapter three verse sixteen") and paraphrased verses.
- Every detection goes to the approval queue. Only the operator's approve action changes the projected output.
- A LIVE toggle controls whether detection is running.
- A "Getting ready" checklist on the Verses tab shows, before the sermon starts, whether the microphone is listening and hearing sound, which screen is the projector, and whether the output is on. Each problem has a button that opens the right setting.
- Input gain (Audio & display) changes the microphone level while it is running and is remembered between sessions.
- Ctrl+1 to Ctrl+4 switch between the Verses, Songs & sermon, Media and Settings tabs.

Songs and sermon
- Songs tab with create, read, update and delete for songs and their sections.
- Song slides show centred lyrics, section labels, a title and artist footer, and a section counter such as "Chorus, 2/8".
- Sermon slides for the church name, sermon title, speaker and scripture reference.

Media
- Media tab for images and video, with thumbnails and transitions between slides.

Themes
- Theme editor for frames, backgrounds, colours, fonts and transitions.
- Export and import themes as .json files so churches can share designs. Imported files are validated before they are accepted.

Projection and output
- Standalone projection window for a second screen.
- Output preview that can feed OBS through a virtual camera (optional pyvirtualcam package).
- NDI output is present in the code but disabled until its licence review is complete.

Service history
- Every projection (verse, song, sermon, media) is logged with its time to a daily file in data/history/.
- Help > Service history shows today's log or any past day, can copy it, and can export it to a text file. Logs stay on the computer.

Updates
- About > Check for updates compares the running version with the latest GitHub release. The check is off at startup unless you turn it on, and it sends nothing otherwise.

## Quick start

RevelateTW requires Python 3.11 or newer and runs on Windows (Windows 10 or 11, 64-bit, because PyQt6 requires it).

1. Clone the repository:

   git clone https://github.com/binuyo-legacy/revelatetw.git
   cd revelatetw

2. Install the dependencies:

   py -3.11 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt

3. Start the operator window:

   python -m revelatetw --gui

Optional packages (virtual camera output and embedding-based paraphrase matching) are listed in requirements-optional.txt. The app runs without them.

A packaged Windows release (exe) will be published on the GitHub Releases page once it has passed testing. No release has been published yet, so use the steps above for now.

For full setup, including the first Whisper model download, audio device selection, bundling ffmpeg for video, and build notes, read SETUP.md.

## Documentation

- SETUP.md: detailed setup, audio routing, Bible translations, ffmpeg bundling, large Whisper models and troubleshooting.
- revelatetw-mvp-spec.md (also in pdfs/revelatetw-mvp-spec.pdf): the product specification.

## Licences

RevelateTW is commercial software owned by its author. The source code in this repository is the property of its author. All rights reserved unless a separate licence is granted in writing.

The bundled Bible texts carry their own licences:

- King James Version (KJV), American Standard Version 1901 (ASV) and World English Bible (WEB): public domain. WEB has been dedicated to the public domain by its editors.
- Yoruba Contemporary Bible: Copyright © Biblica, Inc. Licensed under Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0), https://creativecommons.org/licenses/by-sa/4.0/. The credit "Yoruba Contemporary © Biblica, CC BY-SA 4.0" is shown on the About screen. Any modified or redistributed copy must stay under CC BY-SA 4.0 with the changes stated, and the Biblica trademark rules apply to derivatives. Full notes are in data/bible/LICENSES.md.

Nothing copyrighted is bundled beyond the Yoruba Contemporary text above. Churches that hold a licence for another translation can import it themselves.

ffmpeg, when bundled through scripts/fetch_ffmpeg.py, is distributed under its own licence (LGPL or GPL depending on the build). Ship the ffmpeg licence notice with any installer.

## Status

RevelateTW is pre-release.

- The automated test suite (over 200 tests) runs headless with QT_QPA_PLATFORM=offscreen and does not need audio hardware. The suite is run with python -m unittest discover -s tests -v.
- The Windows executable has not yet been tested on real church hardware. Testing on a Windows 11 PC is in progress.
- Live playback with real microphones and mixing desks has not been measured on a church PC yet.
- Live detection works best in English. Yoruba live detection is experimental and is most reliable with the large-v3 Whisper model. The app shows an advisory when Yoruba and live detection are both on.

## Roadmap

- Improved Yoruba live detection, including better recognition of spoken Yoruba book names and numbers.
- Packaged Windows installer with ffmpeg included, so end users need no internet connection or extra installs.
- Measured performance figures from church PCs.
