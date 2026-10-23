"""Extra tests: paraphrase scorer, theme serialisation, live loop (no audio, no Qt, no GUI)."""
import json
import os
import queue
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402

from revelatetw.approval import ApprovalQueue  # noqa: E402
from revelatetw.detection import VerseDetector  # noqa: E402
from revelatetw.live import SOURCE_MIC, SOURCE_TEXT, LiveTranscriptionLoop  # noqa: E402
from revelatetw.paraphrase import TokenSimilarityMatcher, stem  # noqa: E402
from revelatetw.pipeline import DetectionPipeline  # noqa: E402
from revelatetw.store import VerseStore  # noqa: E402
from revelatetw.theme import Background, Theme, ready_made_themes  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample_kjv.json")


class ParaphraseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = VerseStore.from_json(SAMPLE)

    def test_stemmer_kjv_forms(self):
        self.assertEqual(stem("suffereth"), "suffer")
        self.assertEqual(stem("shepherd"), "shepherd")

    def test_fuzzy_mishearing_still_matches(self):
        m = TokenSimilarityMatcher(self.store)
        top = m.match("the lord is my shepard")[0]
        self.assertEqual((top[2], top[3]), (23, 1))

    def test_threshold_is_tunable(self):
        strict = VerseDetector(self.store, paraphrase_threshold=99)
        loose = VerseDetector(self.store, paraphrase_threshold=10)
        text = "the lord is my shepherd and I shall not want"
        self.assertLessEqual(len(strict.detect(text)), len(loose.detect(text)))

    def test_no_false_positive_on_plain_talk(self):
        det = VerseDetector(self.store)
        self.assertEqual(det.detect("please pass the microphone and check the projector cable"), [])

    def test_offline_default_needs_no_model(self):
        det = VerseDetector(self.store, prefer_embeddings=False)
        self.assertEqual(det.paraphrase.backend, "token")


class ThemeTests(unittest.TestCase):
    def test_round_trip_all_ready_made(self):
        for t in ready_made_themes():
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, "t.json")
                t.save(p)
                back = Theme.load(p)
                self.assertEqual(back, t, t.name)
                self.assertEqual(back.problems(), [], t.name)

    def test_six_ready_made_themes(self):
        self.assertEqual(len(ready_made_themes()), 6)

    def test_unknown_keys_are_ignored(self):
        data = Theme().to_dict()
        data["future_field"] = 1
        data["background"]["future_bg"] = "x"
        t = Theme.from_dict(data)
        self.assertEqual(t.name, Theme().name)

    def test_invalid_theme_rejected_on_save(self):
        t = Theme(transition="spin", background=Background("solid", ["blue"]))
        self.assertTrue(t.problems())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                t.save(os.path.join(d, "bad.json"))
            self.assertFalse(os.path.exists(os.path.join(d, "bad.json")))

    def test_invalid_file_rejected_on_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"frame": "chevrons"}, f)
            with self.assertRaises(ValueError):
                Theme.load(p)

    def test_hex_colours_accept_alpha(self):
        from revelatetw.theme import is_hex_color
        self.assertTrue(is_hex_color("#00000000"))
        self.assertFalse(is_hex_color("#GGGGGG"))


class _FakeCapture:
    def __init__(self, chunks):
        self.chunks = queue.Queue()
        for c in chunks:
            self.chunks.put(c)
        self.meter = {"peak_db": -3.0, "rms_db": -20.0}

    def stop(self):
        pass


class _FakeTranscriber:
    def __init__(self):
        self.calls = 0

    def transcribe(self, audio):
        self.calls += 1
        return "the lord is my shepherd"


class _BrokenTranscriber:
    def transcribe(self, audio):
        raise RuntimeError("model missing")


class LiveLoopTests(unittest.TestCase):
    def _loop(self, transcriber):
        store = VerseStore.from_json(SAMPLE)
        q = ApprovalQueue()
        pipe = DetectionPipeline(VerseDetector(store), q)
        return LiveTranscriptionLoop(pipe, transcriber, window_s=1.0, overlap_s=0.0), q

    def test_text_feed_detects_and_queues_without_projecting(self):
        loop, q = self._loop(_FakeTranscriber())
        self.assertEqual(loop.source, SOURCE_TEXT)
        added = loop.feed_text("the lord is my shepherd")
        self.assertTrue(added)
        self.assertIsNone(q.live)                 # detection queues only

    def test_audio_chunks_reach_transcriber_and_pipeline(self):
        loop, q = self._loop(_FakeTranscriber())
        rate = 16000
        chunks = [np.zeros(rate, dtype=np.float32)] * 2     # two seconds of audio = two windows
        loop.capture = _FakeCapture(chunks)
        loop.source = SOURCE_MIC
        loop._stop = threading.Event()
        threading.Timer(1.5, loop._stop.set).start()         # worker exits once the feed is drained
        loop._run()
        self.assertGreaterEqual(loop.transcriber.calls, 1)
        self.assertEqual(loop.last_text, "the lord is my shepherd")
        self.assertTrue(q.pending())
        self.assertIsNone(q.live)

    def test_transcriber_error_does_not_kill_loop(self):
        loop, q = self._loop(_BrokenTranscriber())
        statuses = []
        loop.on_status = statuses.append
        loop.capture = _FakeCapture([np.zeros(16000, dtype=np.float32)] * 2)
        loop._stop = threading.Event()
        threading.Timer(1.5, loop._stop.set).start()
        loop._run()
        self.assertTrue(any("transcriber error" in s for s in statuses))
        self.assertEqual(q.pending(), [])

    def test_meter_idle_without_capture(self):
        loop, _ = self._loop(_FakeTranscriber())
        self.assertEqual(loop.meter()["peak_db"], -120.0)


if __name__ == "__main__":
    unittest.main()
