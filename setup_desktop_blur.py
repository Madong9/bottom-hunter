"""Install the matching GNOME compositor blur provider for Bottom Hunter.

The installer downloads only from extensions.gnome.org, validates the UUID and
GNOME Shell compatibility in metadata.json, and never requests screen-capture
permission.  It is intentionally separate from normal application startup.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urljoin

EXTENSION_UUID = "blur-my-shell@aunetx"
EXTENSION_INFO_URL = "https://extensions.gnome.org/extension-info/?pk=3193&shell_version={major}"
EXTENSIONS_ORIGIN = "https://extensions.gnome.org"


def command_output(*command: str) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT, timeout=15).strip()


def gnome_shell_major() -> str:
    output = command_output("gnome-shell", "--version")
    match = re.search(r"(\d+)(?:\.\d+)*", output)
    if match is None:
        raise RuntimeError(f"无法识别 GNOME Shell 版本：{output}")
    return match.group(1)


def extension_metadata(path: Path) -> dict[str, object] | None:
    metadata_path = path / "metadata.json"
    if not metadata_path.is_file():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def metadata_supports(metadata: dict[str, object] | None, major: str) -> bool:
    if metadata is None or metadata.get("uuid") != EXTENSION_UUID:
        return False
    versions = metadata.get("shell-version", [])
    return isinstance(versions, list) and major in {str(value).split(".", 1)[0] for value in versions}


def download_extension(major: str, destination: Path) -> dict[str, object]:
    request = urllib.request.Request(
        EXTENSION_INFO_URL.format(major=major),
        headers={"User-Agent": "Bottom-Hunter-Desktop-Blur-Setup/1"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS origin
        info = json.load(response)
    relative_url = info.get("download_url")
    if info.get("uuid") != EXTENSION_UUID or not isinstance(relative_url, str):
        raise RuntimeError("官方扩展站未返回兼容的 Blur My Shell 版本。")
    download_url = urljoin(EXTENSIONS_ORIGIN, relative_url)
    request = urllib.request.Request(
        download_url,
        headers={"User-Agent": "Bottom-Hunter-Desktop-Blur-Setup/1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS origin
        destination.write_bytes(response.read())
    return info


def validate_archive(archive: Path, major: str) -> None:
    try:
        with zipfile.ZipFile(archive) as package:
            metadata = json.loads(package.read("metadata.json").decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise RuntimeError("下载的 GNOME 扩展包无效。") from exc
    if not metadata_supports(metadata, major):
        raise RuntimeError(f"扩展包不支持 GNOME Shell {major}，已拒绝安装。")


def configure_extension(extension_dir: Path) -> None:
    schema_dir = extension_dir / "schemas"
    if not schema_dir.is_dir():
        raise RuntimeError("扩展缺少 GSettings schema，无法安全配置。")
    schema = "org.gnome.shell.extensions.blur-my-shell.applications"
    values = {
        "blur": "true",
        "customize": "true",
        "sigma": "52",
        "brightness": "0.96",
        # Preserve fully opaque text/icons. QML controls material alpha itself.
        "opacity": "255",
        "enable-all": "false",
    }
    for key, value in values.items():
        subprocess.run(
            ["gsettings", "--schemadir", str(schema_dir), "set", schema, key, value],
            check=True,
            timeout=15,
        )


def queue_extension_enable() -> None:
    """Persist enablement for the next Shell reload without losing user entries."""
    raw = command_output("gsettings", "get", "org.gnome.shell", "enabled-extensions")
    if raw.startswith("@as "):
        raw = raw[4:]
    try:
        current = ast.literal_eval(raw)
    except (SyntaxError, ValueError) as exc:
        raise RuntimeError("无法解析 GNOME 已启用扩展列表，未更改设置。") from exc
    if not isinstance(current, list) or not all(isinstance(item, str) for item in current):
        raise RuntimeError("GNOME 已启用扩展列表格式异常，未更改设置。")
    if EXTENSION_UUID not in current:
        current.append(EXTENSION_UUID)
        subprocess.run(
            ["gsettings", "set", "org.gnome.shell", "enabled-extensions", repr(current)],
            check=True,
            timeout=15,
        )


def main() -> int:
    if shutil.which("gnome-shell") is None or shutil.which("gnome-extensions") is None:
        raise RuntimeError("未找到 GNOME Shell 扩展管理工具。")
    major = gnome_shell_major()
    extension_dir = Path.home() / ".local/share/gnome-shell/extensions" / EXTENSION_UUID
    metadata = extension_metadata(extension_dir)

    if metadata_supports(metadata, major):
        print(f"复用已安装的 Blur My Shell v{metadata.get('version', '?')}。")
    else:
        with tempfile.TemporaryDirectory(prefix="bottom-hunter-blur-") as temporary:
            archive = Path(temporary) / f"{EXTENSION_UUID}.shell-extension.zip"
            info = download_extension(major, archive)
            validate_archive(archive, major)
            subprocess.run(
                ["gnome-extensions", "install", "--force", str(archive)],
                check=True,
                timeout=30,
            )
            print(f"已安装官方 Blur My Shell v{info.get('version', '?')}。")

    configure_extension(extension_dir)
    queue_extension_enable()
    enable = subprocess.run(
        ["gnome-extensions", "enable", EXTENSION_UUID],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if enable.returncode == 0:
        print("扩展已启用。重新启动 Bottom Hunter 即可看到实时桌面模糊。")
    else:
        print("扩展已安装、配置并加入启用列表，但 GNOME Shell 尚未重载。")
        print("X11 会话请按 Alt+F2，输入 r 并回车；无需再运行本脚本。")
        if enable.stderr.strip():
            print(f"详情：{enable.stderr.strip()}")
    print("安全设置：只接受 Bottom Hunter 窗口主动请求，不截屏，不保存桌面像素。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
