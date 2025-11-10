#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone

import requests

API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "weather-telemetry-script",
    }


def get_file(owner: str, repo: str, path: str, token: str):
    """Obtiene metadata + contenido (base64) del archivo en el repo.
    Devuelve None si no existe.
    """
    url = f"{API}/repos/{owner}/{repo}/contents/{path}"
    r = requests.get(url, headers=_headers(token))
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def put_file(
    owner: str,
    repo: str,
    path: str,
    token: str,
    content: bytes,
    sha: str | None = None,
    msg: str = "update data.json",
    branch: str = "main",
):
    """Crea o actualiza un archivo en GitHub (Contents API)."""
    url = f"{API}/repos/{owner}/{repo}/contents/{path}"
    data = {
        "message": msg,
        "content": base64.b64encode(content).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        data["sha"] = sha

    r = requests.put(url, headers=_headers(token), json=data)
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(description="Push de medición al repo (GitHub Contents API).")
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--path", default="data/data.json")
    ap.add_argument("--temp", type=float, required=True)
    ap.add_argument("--hum", type=float, required=True)
    ap.add_argument("--pres", type=float, required=True)
    ap.add_argument("--token", default=os.getenv("GITHUB_TOKEN"))
    ap.add_argument("--branch", default="main")
    ap.add_argument("--max-points", type=int, default=2000)
    args = ap.parse_args()

    if not args.token:
        print("Falta GITHUB_TOKEN (pasalo con --token o export GITHUB_TOKEN=...)", file=sys.stderr)
        sys.exit(1)

    # 1) Leer archivo actual si existe
    try:
        meta = get_file(args.owner, args.repo, args.path, args.token)
    except requests.HTTPError as e:
        print(f"Error al leer archivo remoto: {e}", file=sys.stderr)
        sys.exit(2)

    if meta is None:
        data = {"measurements": []}
        sha = None
    else:
        sha = meta.get("sha")
        # 'content' viene base64 y puede traer newlines; mejor normalizar.
        content_b64 = meta.get("content", "").replace("\n", "")
        try:
            content = base64.b64decode(content_b64.encode("utf-8"), validate=False)
            if not content:
                data = {"measurements": []}
            else:
                data = json.loads(content)
        except Exception:
            # Si está corrupto o vacío, arrancamos limpio para no romper el flujo
            data = {"measurements": []}

    # 2) Append nueva medición
    now_iso = datetime.now(timezone.utc).isoformat()
    data.setdefault("measurements", []).append(
        {
            "ts": now_iso,
            "temperature": args.temp,
            "humidity": args.hum,
            "pressure": args.pres,
        }
    )

    # 3) (opcional) limitar a las últimas N mediciones
    if args.max_points and len(data["measurements"]) > args.max_points:
        data["measurements"] = data["measurements"][-args.max_points :]

    # 4) Subir archivo
    new_bytes = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    try:
        put_file(
            args.owner,
            args.repo,
            args.path,
            args.token,
            new_bytes,
            sha=sha,
            msg=f"telemetry: +1 ({now_iso})",
            branch=args.branch,
        )
    except requests.HTTPError as e:
        # Mensaje más útil ante conflictos de SHA/branch
        if e.response is not None and e.response.status_code == 409:
            print(
                "Conflicto (409): el archivo cambió en remoto. Bajá el último SHA y volvé a intentar.",
                file=sys.stderr,
            )
        else:
            print(f"Error al subir archivo: {e}", file=sys.stderr)
        sys.exit(3)

    print("OK: medición publicada")


if __name__ == "__main__":
    main()
