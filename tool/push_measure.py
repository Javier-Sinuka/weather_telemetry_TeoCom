#!/usr/bin/env python3
import argparse, base64, json, os, sys
from datetime import datetime, timezone
import requests


API = "https://api.github.com"


def get_file(owner, repo, path, token):
url = f"{API}/repos/{owner}/{repo}/contents/{path}"
r = requests.get(url, headers={"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"})
if r.status_code == 404:
return None
r.raise_for_status()
return r.json()




def put_file(owner, repo, path, token, content, sha=None, msg="update data.json"):
url = f"{API}/repos/{owner}/{repo}/contents/{path}"
data = {
"message": msg,
"content": base64.b64encode(content).decode("utf-8"),
"branch": "main"
}
if sha:
data["sha"] = sha
r = requests.put(url, headers={"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"}, json=data)
r.raise_for_status()
return r.json()




def main():
ap = argparse.ArgumentParser()
ap.add_argument('--owner', required=True)
ap.add_argument('--repo', required=True)
ap.add_argument('--path', default='data/data.json')
ap.add_argument('--temp', type=float, required=True)
ap.add_argument('--hum', type=float, required=True)
ap.add_argument('--pres', type=float, required=True)
ap.add_argument('--token', default=os.getenv('GITHUB_TOKEN'))
args = ap.parse_args()


if not args.token:
print("Falta GITHUB_TOKEN", file=sys.stderr)
sys.exit(1)


# 1) Leer archivo actual si existe
meta = get_file(args.owner, args.repo, args.path, args.token)
if meta is None:
data = {"measurements": []}
sha = None
else:
sha = meta.get('sha')
content_b64 = meta['content']
# a veces viene con newlines -> decodificar robusto
content = base64.b64decode(content_b64.encode('utf-8'))
data = json.loads(content)


# 2) Append nueva medición
now_iso = datetime.now(timezone.utc).isoformat()
data['measurements'].append({
'ts': now_iso,
'temperature': args.temp,
'humidity': args.hum,
'pressure': args.pres,
})


# (opcional) limitar a las últimas N mediciones
MAX_POINTS = 2000
if len(data['measurements']) > MAX_POINTS:
data['measurements'] = data['measurements'][-MAX_POINTS:]


# 3) Subir archivo
new_bytes = json.dumps(data, ensure_ascii=False, separators=(',',':')).encode('utf-8')
put_file(args.owner, args.repo, args.path, args.token, new_bytes, sha=sha, msg=f"telemetry: +1 ({now_iso})")
print("OK: medición publicada")


if __name__ == '__main__':
main()