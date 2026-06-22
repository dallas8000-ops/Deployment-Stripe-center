"""Run platform CLI deploy commands in the project directory."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .platform import platform_deploy_command


def push_to_platform(project_root: Path, platform: str) -> dict:
    if platform == "unknown":
        return {
            "success": False,
            "platform": platform,
            "message": "Unknown platform — run scan or add vercel.json / railway.toml",
        }

    cmd = platform_deploy_command(platform)
    if platform == "railway" and not shutil.which("railway"):
        return {
            "success": False,
            "platform": platform,
            "message": (
                "Railway CLI not installed — push from GitHub instead: connect the SilverFox repo "
                "in Railway dashboard, or run: npm i -g @railway/cli"
            ),
        }
    try:
        subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        return {"success": True, "platform": platform, "message": f"Deployed via: {cmd}"}
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "")[:500]
        stderr_suffix = f"\n{stderr}" if stderr else ""
        return {
            "success": False,
            "platform": platform,
            "message": f"{exc}{stderr_suffix}",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "platform": platform, "message": "Deploy command timed out (10m)"}
    except OSError as exc:
        return {"success": False, "platform": platform, "message": str(exc)}
