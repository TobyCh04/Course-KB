"""Focused, offline regression tests for Cornell KB media optimizations."""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

import diagrams  # noqa: E402
import transcribe  # noqa: E402


# A valid transparent 1x1 PNG; tests never need Pillow, GPU models, or Ollama.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
    "d8Z3qQAAAABJRU5ErkJggg=="
)


class DiagramVisionOptimizationTests(unittest.TestCase):
    def test_analyze_diagram_uses_one_injected_vision_call_for_type_and_description(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "diagram.png"
            image_path.write_bytes(PNG_BYTES)
            calls = []

            def transport(payload, url, timeout):
                calls.append((payload, url, timeout))
                return {
                    "response": json.dumps(
                        {
                            "diagram_type": "block_diagram",
                            "description": "A controller feeds a plant through a feedback loop.",
                        }
                    )
                }

            description, diagram_type = diagrams.analyze_diagram(
                str(image_path), transport=transport, ollama_url="http://offline"
            )

        self.assertEqual("block_diagram", diagram_type)
        self.assertEqual("A controller feeds a plant through a feedback loop.", description)
        self.assertEqual(1, len(calls))
        self.assertIn("diagram_type", calls[0][0]["prompt"])
        self.assertEqual("http://offline", calls[0][1])

    def test_deduplicate_extracted_images_keeps_the_first_content_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            first = temp_path / "first.png"
            duplicate = temp_path / "duplicate.png"
            unique = temp_path / "unique.png"
            first.write_bytes(PNG_BYTES)
            duplicate.write_bytes(PNG_BYTES)
            unique.write_bytes(PNG_BYTES + b"different")

            result = diagrams.deduplicate_extracted_images(
                [(1, 1, str(first)), (2, 1, str(duplicate)), (3, 1, str(unique))]
            )

        self.assertEqual([(1, 1, str(first)), (3, 1, str(unique))], result)

    def test_process_pdf_diagrams_cleans_its_unique_temporary_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)

            def extractor(_pdf_path, output_dir):
                image_path = Path(output_dir) / "page1.png"
                image_path.write_bytes(PNG_BYTES)
                return [(1, 0, str(image_path))]

            def transport(_payload, _url, _timeout):
                return {"response": '{"diagram_type": "general", "description": "slide"}'}

            facts = diagrams.process_pdf_diagrams(
                "slides.pdf",
                "TEST",
                1,
                extractor=extractor,
                transport=transport,
                temp_root=str(temp_root),
            )

            self.assertEqual("slide", facts[0]["content"])
            self.assertEqual([], list(temp_root.iterdir()))


class TranscriptionOptimizationTests(unittest.TestCase):
    def test_whisper_reuses_cached_model_with_an_injected_loader(self):
        class Segment:
            start, end, text = 0.0, 1.0, " hello"

        class Info:
            language, language_probability, duration = "en", 1.0, 1.0

        class Model:
            def transcribe(self, *_args, **_kwargs):
                return iter([Segment()]), Info()

        loads = []

        def loader(model_size, device, compute_type):
            loads.append((model_size, device, compute_type))
            return Model()

        with tempfile.TemporaryDirectory() as temp_dir:
            transcribe.clear_model_cache()
            transcribe.transcribe_whisper(
                "first.mp3", str(Path(temp_dir) / "first.txt"),
                model_loader=loader, device="cpu", compute_type="int8",
            )
            transcribe.transcribe_whisper(
                "second.mp3", str(Path(temp_dir) / "second.txt"),
                model_loader=loader, device="cpu", compute_type="int8",
            )

        self.assertEqual([("large-v3-turbo", "cpu", "int8")], loads)

    def test_ocr_pdf_uses_150_dpi_and_cleans_a_run_specific_temp_directory(self):
        rendered_dpis = []

        class Pixmap:
            def save(self, path):
                Path(path).write_bytes(PNG_BYTES)

        class Page:
            def get_text(self, mode=None):
                if mode == "dict":
                    return {"blocks": []}
                return ""

            def get_images(self, full=True):
                return [(1,)]

            def get_pixmap(self, dpi):
                rendered_dpis.append(dpi)
                return Pixmap()

        class Document:
            def __len__(self):
                return 1

            def __getitem__(self, _index):
                return Page()

            def close(self):
                pass

        ocr_calls = []

        def ocr_func(image_path, engine, **_kwargs):
            self.assertTrue(Path(image_path).exists())
            ocr_calls.append(engine)
            return "recognized"

        fake_pymupdf = SimpleNamespace(open=lambda _path: Document())
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(sys.modules, {"pymupdf": fake_pymupdf}):
            output_path = Path(temp_dir) / "ocr.txt"
            text = transcribe.ocr_pdf(
                "scanned.pdf", str(output_path), ocr_func=ocr_func, temp_root=temp_dir
            )
            self.assertEqual([], [p for p in Path(temp_dir).iterdir() if p.is_dir()])

        self.assertEqual([150], rendered_dpis)
        self.assertEqual(["glm-ocr"], ocr_calls)
        self.assertIn("recognized", text)

    def test_cli_exposes_model_reuse_and_ocr_rendering_configuration(self):
        parser = transcribe.build_parser()
        transcription = parser.parse_args(
            ["transcribe", "lecture.mp3", "--device", "cpu", "--compute-type", "int8", "--no-model-cache"]
        )
        ocr = parser.parse_args(
            ["ocr", "scan.pdf", "--dpi", "150", "--fallback-engine", "qwen3-vl:8b", "--ollama-url", "http://offline"]
        )
        moss = parser.parse_args(["transcribe", "group.wav", "--engine", "moss", "--moss-device", "cpu"])

        self.assertEqual(("cpu", "int8", False), (transcription.device, transcription.compute_type, transcription.reuse_model))
        self.assertEqual((150, "qwen3-vl:8b", "http://offline"), (ocr.dpi, ocr.fallback_engine, ocr.ollama_url))
        self.assertEqual("cpu", moss.moss_device)

    def test_moss_reuses_an_injected_runtime_bundle(self):
        class Segment:
            start, end, speaker, text = 0.0, 1.0, "SPEAKER_00", "hello"

        loads = []

        def loader(model_id, device_preference):
            loads.append((model_id, device_preference))
            return (
                object(), object(), "cpu", "float32",
                lambda _text: [Segment()], lambda _audio: ["message"],
                lambda *_args, **_kwargs: {"text": "raw"},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            transcribe.clear_model_cache()
            transcribe.transcribe_moss("first.wav", str(Path(temp_dir) / "one.txt"), model_loader=loader, device_preference="cpu")
            transcribe.transcribe_moss("second.wav", str(Path(temp_dir) / "two.txt"), model_loader=loader, device_preference="cpu")

        self.assertEqual([("OpenMOSS-Team/MOSS-Transcribe-Diarize", "cpu")], loads)


if __name__ == "__main__":
    unittest.main()
