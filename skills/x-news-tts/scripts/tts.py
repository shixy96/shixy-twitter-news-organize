#!/usr/bin/env python3
"""edge-tts wrapper: convert text to speech audio (MP3).

Usage:
    python3 tts.py --input script.txt --output audio.mp3
    python3 tts.py --text "你好世界" --output audio.mp3
    python3 tts.py --input script.txt  # outputs to same dir as input, .mp3 extension
"""

import argparse
import asyncio
import importlib
import os
import subprocess
import sys
import tempfile

DEFAULT_VOICE = "zh-CN-YunyangNeural"
DEFAULT_RATE = "+0%"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Text-to-speech via edge-tts")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", "-i", help="Path to text file to read")
    group.add_argument("--text", "-t", help="Text string to convert")
    parser.add_argument("--output", "-o", help="Output MP3 file path (default: derived from input)")
    parser.add_argument(
        "--voice", "-v", default=DEFAULT_VOICE, help=f"Voice name (default: {DEFAULT_VOICE})"
    )
    parser.add_argument(
        "--rate",
        "-r",
        default=DEFAULT_RATE,
        help=f"Speech rate (default: {DEFAULT_RATE.replace('%', '%%')})",
    )
    return parser.parse_args(argv)


def resolve_text(args):
    """Return the text to synthesize from either --input or --text."""
    if args.text is not None:
        return args.text
    if not os.path.isfile(args.input):
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    with open(args.input, "r", encoding="utf-8") as f:
        return f.read()


def resolve_output(args):
    """Return the output file path, creating parent dirs if needed."""
    if args.output:
        path = args.output
    elif args.input:
        base, _ = os.path.splitext(args.input)
        path = base + ".mp3"
    else:
        print("Error: --output is required when using --text", file=sys.stderr)
        sys.exit(1)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


async def synthesize_with_module(text, output, voice, rate):
    """Run synthesis via Python edge_tts module."""
    edge_tts = importlib.import_module("edge_tts")
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    await communicate.save(output)


def synthesize_with_cli(args, text, output):
    """Run synthesis via edge-tts CLI."""
    temp_path = None
    try:
        cmd = ["edge-tts", "--voice", args.voice, "--rate", args.rate, "--write-media", output]
        if args.input:
            cmd.extend(["--file", args.input])
        else:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".txt", delete=False
            ) as f:
                f.write(text)
                temp_path = f.name
            cmd.extend(["--file", temp_path])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (
                result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            )
            raise RuntimeError(detail)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def main(argv=None):
    args = parse_args(argv)
    text = resolve_text(args)
    if not text.strip():
        print("Error: text is empty", file=sys.stderr)
        sys.exit(1)
    output = resolve_output(args)
    try:
        asyncio.run(synthesize_with_module(text, output, args.voice, args.rate))
    except ModuleNotFoundError:
        print(
            "Warning: edge_tts module not available, falling back to edge-tts CLI",
            file=sys.stderr,
        )
        try:
            synthesize_with_cli(args, text, output)
        except FileNotFoundError:
            print("Error: edge-tts CLI not found", file=sys.stderr)
            sys.exit(1)
        except RuntimeError as exc:
            print(f"Error: edge-tts CLI failed: {exc}", file=sys.stderr)
            sys.exit(1)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
