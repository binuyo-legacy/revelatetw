# RevelateTW MVP Product Specification

Live verse detection for church production on Windows.

Version 1.0 (draft for review). October 2026.

## 1. Brand

**Product name:** RevelateTW. "Rhema" is the spoken word of God as it is heard and applied in the moment. "Flow" describes the continuous live listening the product performs. The founder reports that the name was checked online and is not claimed. A formal trademark search is still required before public launch.

**Tagline (recommended):** AI that hears the word.
**Alternate tagline:** The word, as it is spoken.

**Brand colors (dark UI first):**

| Role | Name | Hex | Use |
|---|---|---|---|
| Primary surface | Royal Indigo | #1E1B4B | Panels, sidebars, cards |
| Brand accent | Royal Purple | #4C1D95 | Primary buttons, active states, selection |
| Highlight | Sanctuary Gold | #D4A017 | Approve action, live indicator, key metrics |
| App background | Midnight | #0F0B2E | Main window background |
| Primary text | Parchment | #F5F3FF | Body text and verse text on dark surfaces |
| Alert | Ember Red | #DC2626 | Reject, blank output, error states |

Gold on indigo and midnight gives strong contrast for approval controls. Purple and gold read as premium next to the blue used by EasyWorship and differ from the output projected in the sanctuary, which keeps the operator interface visually separate from the screen the congregation sees.

## 2. Problem

A church that projects Scripture during a sermon depends on a volunteer operator who finds each verse by hand. The operator is often a few verses behind, misreads references, or misses a paraphrase entirely. A preacher who says "the Lord is my shepherd" is not giving a reference, so a text-search tool cannot help. Current production software has no listening capability.

Professional tools are expensive for many churches. Verified list prices include ProPresenter at $29 per month, EasyWorship at $17.50 to $27.50 per month, Proclaim at $270 to $1,000 per year, and MediaShout at $599 one-time. In Nigeria, resellers sell pirated EasyWorship licenses for roughly N4,000 to N6,000 one-time, which is the real local price anchor. African-language Scripture (Yoruba, Hausa, Igbo, Swahili) is poorly served by existing tools.

## 3. Product Overview

RevelateTW is a Windows desktop application that listens to a live audio feed, transcribes speech locally, detects Bible references (exact citations and paraphrases), queues candidates for human approval, and renders approved verses through a configurable theme to one or more outputs.

**Processing pipeline:**

Audio input, then speech-to-text (faster-whisper, local), then verse detection (exact regex plus fuzzy and semantic matching), then the approval queue, then the theme renderer, then outputs (projector window, NDI, virtual camera, normal window for OBS capture).

**Product principles:**

1. Local first. Transcription and detection run on the church computer. No audio leaves the building.
2. Human approval always. Nothing is projected without an operator action. Auto-approve is not part of v1.
3. Offline capable. Only license checks and pack downloads require internet access.
4. Built for the sanctuary. Operator controls work at a glance and by keyboard during a live service.

**Users:**

- Operator: a volunteer or technical staff member running the service.
- Speaker or pastor: benefits indirectly through accurate, timely verses.
- Church administrator: sets the brand look, manages team accounts and licenses.
- Streaming or media team: consumes NDI, virtual camera, and window outputs.

## 4. Feature Specifications

### F1. Live Verse Detection

**User story:** As an operator, when the preacher quotes or paraphrases a verse, I want to see a candidate verse with its reference and text within seconds, so that I can approve it for the screen.

**Requirements:**

- Speech-to-text uses faster-whisper running locally. The model size is selectable: a small model by default for CPU-only machines, a medium or large model where a capable GPU is present.
- Audio is segmented with voice activity detection and processed in a rolling window with overlap, so that references spoken across segment boundaries are still found.
- Exact citation detection uses a regular expression engine over canonical book names, common abbreviations, numerals, and spoken forms ("John chapter three verse sixteen", "Jn 3 16", "First Corinthians 13 verse 4"). Book aliases in Yoruba, Hausa, Igbo, and Swahili come from the translation pack metadata.
- Paraphrase detection embeds the verse corpus with a small multilingual sentence embedding model shipped with the app or downloaded once. The transcript window is compared by cosine similarity. A lexical BM25 index over the same text serves as a fallback and as a tie-breaker.
- Each candidate carries a confidence score from 0 to 100, the match type (exact or paraphrase), and the transcript snippet that triggered it.
- Verse text is read from the SQLite store of the active translation pack.
- A verse already queued is not queued again within a configurable window (default 5 minutes) unless the operator requests it.

**Proposed targets (to be validated in the prototype phase on a labeled corpus of recorded sermons):**

- Latency from end of utterance to queue entry: under 3 seconds on the recommended hardware.
- Precision on exact citations: at least 90 percent at the default threshold.
- Precision on paraphrase matches: at least 75 percent at the default threshold.
- False candidates per hour of speech without scripture: reported per session and kept low enough that the queue is not noisy.

**Acceptance criteria:**

1. Saying "John 3:16" clearly produces a candidate for John 3:16 with the active translation's text inside the latency target.
2. Saying "the Lord is my shepherd" produces Psalm 23:1 as the top candidate with a confidence score shown.
3. A sermon section with no scripture produces no candidates above the default threshold.
4. Detection works with the network disabled.
5. Every candidate and its triggering snippet is written to the session log.

### F2. Operator Approval Queue

**User story:** As an operator, I want to approve, reject, or edit each candidate in one action, so that I control exactly what appears on screen and can work fast during service.

**Requirements:**

- The queue panel shows reference, translation (or translations), verse text preview, confidence, the triggering transcript snippet, and the time detected.
- Actions per candidate: Approve (projects immediately), Approve and Edit (opens the text for correction before projection), Reject, and Hold (keeps the candidate without projecting).
- Keyboard shortcuts (all remappable): Enter approves the selected candidate, Escape rejects it, E edits, arrow keys move through the queue, number keys choose a translation, and B blanks the output immediately.
- A clear live indicator shows whether the output is live, blank, or idle.
- Each approval, rejection, and edit is logged with a timestamp.
- The queue never changes the output without an operator action.

**Acceptance criteria:**

1. No candidate reaches the output without an Approve action.
2. The time from keypress to the updated output frame is under 200 milliseconds on the recommended hardware.
3. An operator can run an entire service using the keyboard alone.
4. Blank output takes effect in one keystroke.
5. Edits to a verse persist for the session and appear in the log.

### F3. Theme Editor

**User story:** As a church administrator, I want to design the screen look once and reuse it for every service, so that the congregation sees a consistent, professional brand.

**Requirements:**

- Frames: selectable border styles and insets for the verse block.
- Backgrounds: solid color, linear and radial gradients (two or three stops), image backgrounds (JPG, PNG), and video backgrounds (MP4, H.264).
- Typography: font family, size, weight, line height, shadow, and outline. Text fits its frame automatically and never overflows.
- Per-translation accent colors, so that a translation is visually identifiable when several are shown.
- Layouts: full-screen verse and lower-third.
- Transition presets: fade, slide, and kinetic type (word-by-word reveal).
- Ready-made themes: at least six at launch.
- Saved church brand looks: a named theme saved to the church profile.
- Import and export of themes as a single portable file (JSON manifest with bundled assets).
- Live preview of the actual output as the theme is edited.

**Acceptance criteria:**

1. A theme change appears in the live preview within 1 second.
2. Transitions run at 30 frames per second or better on the recommended hardware.
3. A theme exported on one machine imports identically on another.
4. Long verses shrink or wrap inside the frame without clipping.

### F4. Audio Source Configuration

**User story:** As an operator, I want to choose my sound desk output or USB interface as the input and tune it the way I would in OBS, so that the detection hears the preacher clearly in any room.

**Requirements:**

- The device picker lists every input: built-in microphone, USB audio interfaces and soundcards, and WASAPI loopback of output devices (so the mixing desk's main output can be captured directly).
- Per-device gain, adjustable from minus 60 dB to plus 20 dB.
- Noise gate with threshold, attack, and release controls.
- Sample rate selection, with capture at the device's native rate and resampling to the rate the speech model requires.
- Multichannel interfaces: the operator chooses the channel to use.
- A level meter showing peak and RMS levels.
- Hot-plug detection: a device that is unplugged and replugged is recognized, with a prompt to reconnect.
- Switching input devices does not require a restart.

**Acceptance criteria:**

1. The device list matches the operating system's list, including loopback devices.
2. The level meter responds within 100 milliseconds.
3. The noise gate removes steady room hum below its threshold in a test recording.
4. After an unplug and replug, the app recovers the device without a restart.

### F5. Output Routing

**User story:** As an operator, I want the approved verses sent to the projector, to the streaming team as an NDI source, to a virtual camera for Zoom or OBS, or to a normal window that OBS can capture.

**Requirements:**

- Projector output: full-screen borderless output on a chosen display, with no operator interface visible on the projector.
- NDI output: sends the program output as an NDI source on the local network. This feature is gated by the NDI license review described in section 10. It does not ship until that review is complete.
- Virtual camera: exposes the program output as a camera device usable by OBS, Zoom, and other applications. DirectShow is supported for legacy applications, and Media Foundation virtual camera is used where Windows supports it.
- Window output: a normal resizable window that OBS can capture through Windows Graphics Capture.
- Several outputs can run at the same time, for example program output plus a confidence monitor for the speaker.
- Resolution options: 1920 by 1080 and 1280 by 720. A 60 frames per second option is available on capable hardware.

**Acceptance criteria:**

1. The projector output appears on the second monitor with no operator window visible.
2. The NDI source is visible in an NDI receiver on the local network (once NDI is licensed and enabled).
3. The virtual camera is selectable in OBS and Zoom.
4. OBS window capture shows the output correctly.
5. A 30-minute run completes without frame drops beyond an agreed threshold.

### F6. Translation Pack System

**User story:** As a church, I want to install the Bible translation my congregation reads, and to add premium translations later without updating the app, so that I can always use the Scripture my people use.

**Requirements:**

- Translations are distributed as signed pack files (SQLite) downloaded from the RevelateTW catalog and stored in the app data folder. The app does not bundle translation text except the starter translation.
- An in-app store lists available packs with license terms, language, and size.
- Each pack is checked on install against its entitlement: the license key is tied to the church's subscription.
- Launch free packs: KJV (bundled as the starter), WEB, and public-domain and open-license translations, including African-language Scripture (Yoruba, Hausa, Igbo, Swahili) from ebible.org. Each pack's license is verified individually before inclusion, because licenses differ across translations on that site.
- Premium translations (NKJV, NIV, ESV) are added through publisher agreements and distributed as paid packs. Adding a pack requires no app update.
- The catalog carries a compatibility version, so an older app can ignore packs it cannot read rather than failing.

**Acceptance criteria:**

1. A pack with a modified byte fails verification and is refused.
2. An entitlement for one pack does not unlock another.
3. Installing a new catalog pack appears in the store without an app update.
4. The attribution and license text for each installed pack appears in the About screen.
5. A church that goes offline keeps access to installed packs within the grace period (section 8).

### F7. Roadmap Add-ons (Post-v1)

These features are specified for planning. They are not part of the v1 release.

**F7a. Multi-translation side-by-side display.** As an operator, I want two translations shown together so the congregation can follow the reading in their own language. Acceptance: two or more installed translations render in one layout, with each translation's accent color, and the operator can switch the pair from the queue.

**F7b. Lyrics and hymn library.** As a worship leader, I want to search and project lyrics alongside verses. Acceptance: lyrics import from common text formats, appear in the same queue, and use the same themes. Licensing for copyrighted songs is a separate business matter and is not part of the software.

**F7c. Auto sermon outline.** As a pastor, I want an outline of the sermon with the verses in the order they were spoken, so that I can share notes after service. The transcript is stored with timestamps for each detected and approved verse. Acceptance: export to PDF, DOCX, and Markdown; each entry shows the time, reference, and the sentence in which it was spoken.

**F7d. WhatsApp integration.** As a church communications lead, I want to send the week's verses to members. Acceptance: members opt in explicitly; messages are sent through an approved WhatsApp Business channel and follow that platform's policies. Consent records are kept.

## 5. Competitive Analysis

| Product | Price | Live verse detection | NDI | Themes | Audio device routing | Notes |
|---|---|---|---|---|---|---|
| ProPresenter | $29 per month | No | Not verified | Not verified | Not verified | Mature production suite |
| EasyWorship | $17.50 to $27.50 per month | No | Not verified | Not verified | Not verified | Common in Nigerian churches; pirated copies sold locally for N4,000 to N6,000 one-time |
| Proclaim | $270 to $1,000 per year | No | Not verified | Not verified | Not verified | Church-focused suite |
| MediaShout | $599 one-time | No | Not verified | Not verified | Not verified | One-time license model |
| TajiCast | Free | Yes (offline) | Yes | No | No | No themes or audio routing |
| Loghema | N9,999 to N37,000 per month | Yes | Yes | Yes | No | Lagos-based; cloud transcription; no audio routing |
| Pewbeam | $14 to $30 per month | Yes | Not verified | Not verified | Not verified | Verse detection rival |
| RhemaCast | $12 to $25 per month | Yes | Not verified | Not verified | Not verified | Verse detection rival |

"Not verified" means the feature was not confirmed in the research brief and must be checked before launch marketing relies on it. The gap RevelateTW targets is the combination of verse detection, audio device routing, NDI, and themes at a low price. No product in the research set combined all four.

## 6. Pricing

| Tier | Price (USD) | Price (NGN, indicative) | Includes |
|---|---|---|---|
| Free | $0 | N0 | Verse agent, single display, KJV and WEB, approval queue |
| Pro | About $4 per month | About N3,000 per month | All free translations, theme editor, sermon notes (see open decision) |
| Church | About $10 per month | Price to be set | Multi-screen output, team accounts, OBS control, premium translations available as add-ons |

Pricing rationale:

- Local price anchor: pirated EasyWorship at N4,000 to N6,000 one-time. A Pro subscription at about N3,000 per month costs more over a year than a one-time pirated copy, so the value case must rest on live verse detection, updates, and legitimate licensing. The Free tier is the primary tool for lowering the barrier.
- Competitor anchors: Loghema at N9,999 to N37,000 per month sets the upper end for a comparable feature set.
- Naira prices should be reviewed regularly because exchange rates move.
- Operating costs are low because detection runs locally. Recurring costs are the licensing server, pack hosting and bandwidth, code signing certificates, support, and publisher royalties for premium translations.

## 7. Technical Architecture

**Stack:**

- Language and UI: Python 3.11 or later with PyQt6.
- Speech-to-text: faster-whisper (CTranslate2 backend), with model sizes selectable by hardware.
- Semantic matching: small multilingual sentence embedding model, run locally.
- Lexical matching: BM25 index over verse text, plus SQLite FTS5.
- Storage: SQLite for verse packs, session logs, and settings, stored under the user's application data folder.
- Audio: PortAudio-based capture with WASAPI, including loopback devices.
- Outputs: a borderless full-screen window for projection; an NDI sender built on the NDI SDK (license gated); a virtual camera component for DirectShow and Media Foundation; Windows Graphics Capture compatible window output.
- Packaging: PyInstaller or Nuitka for the Windows build, with an installer and Authenticode code signing.
- Licensing service: a small HTTPS API that ties keys to subscriptions, issues signed entitlement tokens, and publishes the pack catalog.

**Module breakdown:**

1. Audio capture module (devices, gain, gate, metering).
2. Transcription module (VAD, faster-whisper, rolling window).
3. Detection module (exact parser, semantic matcher, lexical fallback, deduplication).
4. Verse store module (pack loader, verification, queries).
5. Queue module (candidates, approvals, keyboard map, logging).
6. Theme and render module (layouts, backgrounds, transitions, preview).
7. Output module (projector, NDI, virtual camera, window).
8. Licensing and store module (entitlements, downloads, verification).

**Threading model:**

- Audio capture runs on its own thread, feeding a fixed-size ring buffer.
- The transcription worker consumes buffered audio, so that inference never blocks capture.
- The detection worker consumes transcript segments.
- The UI thread owns the queue and preview. The render thread owns output frames.

**Offline behavior:** Capture, transcription, detection, rendering, and output all function without internet access. Internet is used only for license validation, pack downloads, and update checks.

## 8. Translation Pack and Licensing System

**Pack format:** A pack is a SQLite file containing:

- meta table: pack identifier, name, language, version, license identifier, attribution text, publisher, and checksum.
- books table: canonical book identifiers with names and aliases in each supported language.
- verses table: book, chapter, verse, and text.
- FTS5 index over verse text.

**Signing:** Each pack's manifest is signed with an Ed25519 key held by RevelateTW. The application holds only the public key. The signature and checksum are verified on install and on each load.

**Install flow:**

1. The user selects a pack in the store.
2. The app requests an entitlement from the licensing service with the license key and pack identifier.
3. The service checks the subscription and returns a signed entitlement token for that pack.
4. The app downloads the pack, verifies signature and checksum, and installs it to the packs folder.
5. The app records the installation and the entitlement expiry.

**Offline grace period:** Entitlement tokens remain valid offline for a grace period (proposed: 30 days). The app revalidates when it next connects.

**Premium pack protection:** A publisher agreement may require encryption at rest. Packs for premium translations can be encrypted with a key derived from the entitlement. Software running offline on a church machine cannot be fully protected from copying, so the protection goal is deterrence and contract compliance, not absolute security. Terms are to be agreed with each publisher.

**Adding a pack later:** A new pack is published to the catalog. The catalog is JSON with a compatibility version field. The app reads it and shows the pack in the store. No app update is required.

**Free pack licensing:** Each free translation is checked against its own license before inclusion. Attribution text is stored in the pack metadata and shown in the About screen.

## 9. MVP Scope

| Area | v1 (ships) | Roadmap (post-v1) |
|---|---|---|
| Verse detection | Exact citations and paraphrase matching, English plus pack aliases | Tuning from operator corrections |
| Translations | KJV (bundled), WEB, free packs including licensed African-language packs | Premium packs (NKJV, NIV, ESV) after publisher deals |
| Approval queue | Full queue, keyboard map, logging | Auto-approve as an explicit opt-in |
| Themes | Editor, six or more ready-made themes, saved brand looks, image and gradient backgrounds | Richer motion templates |
| Video backgrounds | Included if stable in beta; otherwise first post-v1 release | n/a |
| Audio | Device picker, gain, gate, metering, WASAPI loopback | Multi-source mixing |
| Outputs | Projector, window, virtual camera | NDI (enabled only after license review) |
| Multi-translation display | Not in v1 | F7a |
| Lyrics and hymns | Not in v1 | F7b |
| Sermon outline | Session transcript log only | F7c export |
| WhatsApp | Not in v1 | F7d |
| Platforms | Windows 10 and 11 | macOS or Linux (not planned) |
| Licensing | Free, Pro, and Church entitlements; pack store | Team administration portal |

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| NDI licensing terms block commercial shipping | Medium | High | Review NDI SDK terms before any NDI build ships; keep NDI behind a feature flag; ship v1 without NDI if needed |
| Publisher deals delayed or costly | High | Medium | Launch with free translations; architecture supports adding packs with no app update; negotiate usage terms early |
| Transcription accuracy in sanctuary acoustics (echo, weak PA, accents, mixed English and local languages) | High | High | Prototype on recorded sermons from partner churches; device guidance; gain and gate controls; model size choice |
| Paraphrase false positives queue a wrong verse | Medium | High | Confidence threshold; mandatory human approval; clear match-type labels |
| Hardware too weak for the speech model | Medium | Medium | Small model default; benchmark on minimum spec; GPU acceleration where present |
| Pirated copies undercut paid tiers | High | Medium | Strong free tier; value through detection and updates; local pricing |
| Virtual camera driver issues on some Windows machines | Medium | Medium | Support both DirectShow and Media Foundation paths; test on a matrix of Windows builds |
| Licenses of individual free translations | Low to medium | Medium | Verify each pack's license before inclusion; publish attribution |
| Trademark conflict for the name | Low | High | Run a formal trademark search before public launch |
| Currency movement affects naira pricing | High | Medium | Review naira prices on a fixed schedule |
| Support burden for non-technical churches | Medium | Medium | Installer with guided setup; documentation; video guides; partner church champions |

## 11. Phased Roadmap

**Phase 0. Prototype (proposed duration: about 6 weeks).**
Goal: prove detection accuracy and latency.
Deliverables: faster-whisper transcription on the reference machine; exact citation parser on KJV; paraphrase matcher with embeddings; benchmark set of recorded sermons with labeled references.
Gate: exact-citation precision and paraphrase precision meet the proposed targets on the benchmark set.

**Phase 1. Internal alpha (proposed duration: about 6 weeks).**
Goal: a working operator application.
Deliverables: audio device picker and metering; approval queue with keyboard map; projector and window output; KJV and WEB packs with signed-pack verification.
Gate: a full dry-run service completed by a test operator without mouse use.

**Phase 2. Beta with partner churches (proposed: 5 to 10 churches over about 8 weeks).**
Goal: validate in real sanctuaries.
Deliverables: theme editor and brand looks; virtual camera; African-language packs where licensed; licensing service and entitlements; feedback and metrics collection.
Gate: beta churches run at least four consecutive services without a critical failure, and operators rate the queue as usable in their own words.

**Phase 3. Public launch.**
Goal: sell the product.
Deliverables: signed Windows installer; pack store live; Free, Pro, and Church tiers; NDI enabled after license clearance; first premium publisher deal integrated as a paid pack; support documentation.
Gate: trademark clearance, NDI clearance, and payment and licensing flows tested end to end.

## 12. Success Metrics

- Exact-citation precision and paraphrase precision on the benchmark set.
- Median time from utterance to queue entry.
- Share of candidates approved by operators (a signal of relevance).
- Crashes or critical failures per service.
- Free-to-paid conversion, and churn after the first three months.

## 13. Open Decisions

1. Whether sermon notes belong in Pro at launch or wait for F7c.
2. Whether premium translations are included in the Church tier or sold as add-ons.
3. The NDI licensing path and whether NDI is required for launch.
4. Final naira price points for Pro and Church.
5. Whether a free trial of Pro is offered.
6. Whether auto-approve is offered at all, and under what explicit opt-in.
