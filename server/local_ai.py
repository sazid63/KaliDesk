"""Local AI Model Manager.

Handles local GGUF model storage, scanning, validation, and llama.cpp integration.
Models are stored in user_data_dir() / "models".
"""
from __future__ import annotations

import hashlib
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import kws_paths

MODELS_DIR = kws_paths.user_data_dir() / "models"
GGUF_MAGIC = b"GGUF"


def _ensure_models_dir() -> Path:
    """Create models directory if it doesn't exist."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return MODELS_DIR


def scan_models() -> list[dict[str, Any]]:
    """Scan MODELS_DIR for GGUF files and return metadata."""
    _ensure_models_dir()
    models = []
    for path in MODELS_DIR.glob("*.gguf"):
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
            quantization = _detect_quantization(path.name)
            capabilities = _infer_capabilities(quantization)
            models.append({
                "name": path.name,
                "path": str(path),
                "size_mb": round(size_mb, 2),
                "quantization": quantization,
                "capabilities": capabilities,
            })
        except OSError:
            continue
    return models


def _detect_quantization(filename: str) -> str:
    """Detect quantization type from filename."""
    filename = filename.lower()
    quants = ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q4_0", "Q3_K_M", "Q2_K", "FP16", "FP32"]
    for q in quants:
        if q.lower() in filename:
            return q
    return "unknown"


def _infer_capabilities(quantization: str) -> list[str]:
    """Infer model capabilities from quantization."""
    caps = ["chat"]
    if quantization in ("Q8_0", "FP16", "FP32"):
        caps.extend(["code", "reasoning"])
    if "K" in quantization:
        caps.append("general")
    return caps


def validate_model(path: str | Path) -> bool:
    """Validate a GGUF file by checking magic bytes."""
    try:
        p = Path(path)
        if not p.exists():
            return False
        with open(p, "rb") as f:
            magic = f.read(4)
        return magic == GGUF_MAGIC
    except OSError:
        return False


def download_model(hf_repo: str, filename: str, quantization: str = "Q4_K_M") -> dict[str, Any]:
    """Download a model from Hugging Face.

    Args:
        hf_repo: Hugging Face repo (e.g., "TheBloke/Llama-2-7B-Chat-GGUF")
        filename: Model filename (e.g., "llama-2-7b-chat.Q4_K_M.gguf")
        quantization: Quantization type for metadata

    Returns:
        dict with name, path, size_mb, quantization, success, error
    """
    _ensure_models_dir()
    dest = MODELS_DIR / filename

    if dest.exists():
        return {
            "name": filename,
            "path": str(dest),
            "size_mb": round(dest.stat().st_size / (1024 * 1024), 2),
            "quantization": quantization,
            "success": True,
            "error": None,
            "cached": True,
        }

    # Try huggingface_hub if available
    try:
        from huggingface_hub import hf_hub_download
        downloaded = hf_hub_download(repo_id=hf_repo, filename=filename, local_dir=str(MODELS_DIR))
        path = Path(downloaded)
        return {
            "name": filename,
            "path": str(path),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            "quantization": quantization,
            "success": True,
            "error": None,
            "cached": False,
        }
    except ImportError:
        pass
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    # Fallback to manual download
    # Validate hf_repo and filename to prevent SSRF and path traversal
    import re
    # Hugging Face repo format: username/model-name or organization/model-name
    if not re.match(r"^[\w\-.]+/[\w\-.]+$", hf_repo):
        return {"success": False, "error": "Invalid repository format"}
    if not re.match(r"^[\w\-.]+\.gguf$", filename):
        return {"success": False, "error": "Invalid filename format"}
    url = f"https://huggingface.co/{hf_repo}/resolve/main/{filename}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KaliDesk/1.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with dest.open("wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
        return {
            "name": filename,
            "path": str(dest),
            "size_mb": round(dest.stat().st_size / (1024 * 1024), 2),
            "quantization": quantization,
            "success": True,
            "error": None,
            "cached": False,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_model_info(path: str | Path) -> dict[str, Any]:
    """Get detailed info about a model file."""
    p = Path(path)
    if not p.exists():
        return {"error": "File not found"}

    try:
        stat = p.stat()
        size_mb = stat.st_size / (1024 * 1024)
        quantization = _detect_quantization(p.name)
        capabilities = _infer_capabilities(quantization)

        # Calculate SHA256
        sha256 = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

        return {
            "name": p.name,
            "path": str(p),
            "size_mb": round(size_mb, 2),
            "size_bytes": stat.st_size,
            "quantization": quantization,
            "capabilities": capabilities,
            "sha256": sha256.hexdigest(),
            "valid_gguf": validate_model(p),
        }
    except OSError as exc:
        return {"error": str(exc)}