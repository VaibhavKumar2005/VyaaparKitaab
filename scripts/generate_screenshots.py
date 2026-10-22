import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
OUT_DIR = ROOT / "report_screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FIREFOX_BIN = "/usr/lib/firefox/firefox"


def take_browser_screenshot(url: str, out_path: Path, width: int = 1440, height: int = 1280) -> None:
    ff_home = Path("/tmp/vk_ff_home")
    if ff_home.exists():
        shutil.rmtree(ff_home, ignore_errors=True)
    ff_home.mkdir(parents=True, exist_ok=True)

    ff_env = os.environ.copy()
    ff_env["HOME"] = str(ff_home)
    ff_env["MOZ_HEADLESS"] = "1"

    print(f"Capturing {url} -> {out_path.name} ...")
    cmd = [
        FIREFOX_BIN,
        "--headless",
        "--no-remote",
        f"--window-size={width},{height}",
        f"--screenshot={out_path}",
        url,
    ]

    subprocess.run(cmd, env=ff_env, check=True, timeout=60)
    shutil.rmtree(ff_home, ignore_errors=True)


def generate_swagger_screenshot(out_path: Path) -> None:
    from app.main import app

    spec = app.openapi()
    paths = spec.get("paths", {})

    # Group operations by tag
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for path, methods in paths.items():
        for method, meta in methods.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            tags = meta.get("tags") or ["default"]
            tag = tags[0]
            summary = meta.get("summary") or meta.get("operationId") or ""
            groups.setdefault(tag, []).append((method.upper(), path, summary))

    method_colors = {
        "GET": ("#61affe", "rgba(97,175,254,0.1)"),
        "POST": ("#49cc90", "rgba(73,204,144,0.1)"),
        "PATCH": ("#50e3c2", "rgba(80,227,194,0.1)"),
        "DELETE": ("#f93e3e", "rgba(249,62,62,0.1)"),
    }

    sections_html = []
    for tag, ops in groups.items():
        rows = []
        for method, path, summary in ops:
            badge_bg, row_bg = method_colors.get(method, ("#61affe", "#f8fafc"))
            rows.append(
                f"""
                <div class="opblock" style="border-color:{badge_bg};background:{row_bg};">
                  <span class="opblock-method" style="background:{badge_bg};">{method}</span>
                  <span class="opblock-path">{path}</span>
                  <span class="opblock-summary">{summary}</span>
                </div>
                """
            )
        sections_html.append(
            f"""
            <div class="tag-section">
              <div class="tag-header">
                <span class="tag-title">{tag}</span>
                <span class="tag-sub">VyaparKitaab REST API Controller</span>
              </div>
              {''.join(rows)}
            </div>
            """
        )

    html_file = OUT_DIR / "_swagger_ui.html"
    html_file.write_text(
        f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {{
    margin: 0;
    background: #fafafa;
    color: #3b4151;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }}
  .topbar {{
    background: #1b1b1b;
    padding: 12px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    color: #fff;
  }}
  .topbar-brand {{
    font-weight: 700;
    font-size: 18px;
    color: #89bf04;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .url-bar {{
    background: #fff;
    color: #3b4151;
    padding: 5px 14px;
    border-radius: 4px;
    font-size: 13px;
    font-family: monospace;
    width: 360px;
    border: 2px solid #89bf04;
  }}
  .container {{
    max-width: 1280px;
    margin: 0 auto;
    padding: 24px 32px;
  }}
  .info-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(59,65,81,.2);
    padding-bottom: 16px;
    margin-bottom: 20px;
  }}
  .title {{
    font-size: 32px;
    font-weight: 700;
    color: #3b4151;
    margin: 0;
  }}
  .badge {{
    background: #7d8492;
    color: #fff;
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 12px;
    margin-left: 8px;
    vertical-align: middle;
  }}
  . badge-oas {{
    background: #89bf04;
    color: #fff;
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 12px;
    margin-left: 6px;
    vertical-align: middle;
  }}
  .auth-btn {{
    border: 2px solid #49cc90;
    color: #49cc90;
    background: transparent;
    padding: 6px 18px;
    font-weight: 700;
    border-radius: 4px;
    font-size: 13px;
  }}
  .tag-section {{
    margin-bottom: 18px;
  }}
  .tag-header {{
    display: flex;
    align-items: baseline;
    gap: 12px;
    border-bottom: 1px solid rgba(59,65,81,.2);
    padding: 6px 4px;
    margin-bottom: 8px;
  }}
  .tag-title {{
    font-size: 20px;
    font-weight: 700;
    color: #3b4151;
  }}
  .tag-sub {{
    font-size: 13px;
    color: #6b7280;
  }}
  .opblock {{
    display: flex;
    align-items: center;
    gap: 14px;
    border: 1px solid;
    border-radius: 4px;
    padding: 6px 10px;
    margin-bottom: 6px;
  }}
  .opblock-method {{
    color: #fff;
    font-weight: 700;
    font-size: 12px;
    min-width: 68px;
    text-align: center;
    padding: 5px 0;
    border-radius: 3px;
  }}
  .opblock-path {{
    font-family: 'DejaVu Sans Mono', monospace;
    font-weight: 600;
    font-size: 14px;
    color: #3b4151;
  }}
  .opblock-summary {{
    font-size: 13px;
    color: #4b5563;
  }}
</style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-brand">Swagger UI — FastAPI OpenAPI 3.1</div>
    <div class="url-bar">http://localhost:8000/openapi.json</div>
  </div>
  <div class="container">
    <div class="info-header">
      <div>
        <h1 class="title">
          {spec.get("info", {}).get("title", "VyaparKitaab API")}
          <span class="badge">{spec.get("info", {}).get("version", "0.1.0")}</span>
          <span class="badge-oas">OAS 3.1</span>
        </h1>
        <div style="font-size:12px;color:#4990e2;margin-top:4px;font-family:monospace;">/openapi.json</div>
      </div>
      <button class="auth-btn">Authorize (JWT Bearer)</button>
    </div>
    {''.join(sections_html)}
  </div>
</body>
</html>""",
        encoding="utf-8",
    )
    take_browser_screenshot(f"file://{html_file}", out_path, width=1440, height=1320)
    html_file.unlink(missing_ok=True)


if __name__ == "__main__":
    generate_swagger_screenshot(OUT_DIR / "Figure_4_8_Swagger_API_Docs.png")
