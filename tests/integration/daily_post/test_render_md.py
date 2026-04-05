import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "x-news-to-daily-post" / "scripts" / "render_md.py"
FIXTURE = ROOT / "tests" / "fixtures" / "post" / "valid_post.json"


def test_render_md_matches_expected_structure(tmp_path: Path) -> None:
    output_path = tmp_path / "post.md"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(FIXTURE), "--output", str(output_path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    rendered = output_path.read_text(encoding="utf-8")
    assert rendered.startswith("---\n")
    assert '# AI 资讯日报 2024-01-15' in rendered
    assert "\n## 模型发布\n" in rendered
    assert (
        "### [OpenAI 发布 GPT-5](https://x.com/ai_news/status/1234567890) `#1`"
        in rendered
    )
    assert "OpenAI 发布 GPT-5，突破性推理能力" in rendered
    assert "相关链接：\n- 官方博客：https://openai.com/blog/gpt-5" in rendered
    assert "[官方博客](https://openai.com/blog/gpt-5)" not in rendered
