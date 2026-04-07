#!/usr/bin/env python3
"""Unit tests for skills/x-news-tts/scripts/tts.py."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "skills/x-news-tts/scripts"))


class MockArgs:
    """Lightweight mock for tts args namespace."""


class TestResolveText(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        )
        self.temp_file.write("file content here")
        self.temp_file.close()
        self.temp_path = self.temp_file.name

    def tearDown(self):
        os.unlink(self.temp_path)

    def test_from_text_arg(self):
        from tts import resolve_text

        args = MockArgs()
        args.text = "inline text"
        args.input = None
        self.assertEqual(resolve_text(args), "inline text")

    def test_from_file(self):
        from tts import resolve_text

        args = MockArgs()
        args.text = None
        args.input = self.temp_path
        self.assertEqual(resolve_text(args), "file content here")

    def test_missing_file_exits(self):
        from tts import resolve_text

        args = MockArgs()
        args.text = None
        args.input = "/nonexistent/path/file.txt"
        with self.assertRaises(SystemExit):
            resolve_text(args)


class TestResolveOutput(unittest.TestCase):
    def test_explicit_output(self):
        from tts import resolve_output

        args = MockArgs()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "audio.mp3")
            args.output = output_path
            args.input = None
            self.assertEqual(resolve_output(args), output_path)

    def test_derived_from_input(self):
        from tts import resolve_output

        args = MockArgs()
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "script.txt")
            Path(input_path).touch()
            args.output = None
            args.input = input_path
            self.assertEqual(resolve_output(args), os.path.join(tmpdir, "script.mp3"))

    def test_no_input_no_output_exits(self):
        from tts import resolve_output

        args = MockArgs()
        args.output = None
        args.input = None
        with self.assertRaises(SystemExit):
            resolve_output(args)


if __name__ == "__main__":
    unittest.main()
