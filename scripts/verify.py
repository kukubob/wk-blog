"""Verify article completeness and every generated local link/image target."""
import argparse
import json
import hashlib
from pathlib import Path
from urllib.parse import urlsplit,unquote
from bs4 import BeautifulSoup
import yaml

ROOT=Path(__file__).resolve().parents[1]
args=argparse.ArgumentParser(); args.add_argument('--base-path',default=''); opts=args.parse_args()
base=opts.base_path.rstrip('/')
out=ROOT/'dist'
issues=[]
media=json.loads((ROOT/'media-status.json').read_text())
for entry in media:
    if entry['status']=='ok':
        asset=out/entry['path'].lstrip('/')
        assert hashlib.sha256(asset.read_bytes()).hexdigest()==entry['sha256'], f'Media differs: {asset}'
posts=list((ROOT/'content/posts').glob('*.md'))
assert len(posts)==108, f'Expected 108 posts; got {len(posts)}'
for md in posts:
    meta=yaml.safe_load(md.read_text().split('---',2)[1])
    target=out/meta['path'].lstrip('/')
    assert target.is_file(), str(target)
for file in out.rglob('*.html'):
    soup=BeautifulSoup(file.read_text(),'html.parser')
    assert soup.title and soup.find('h1'), str(file)
    for node in soup.find_all(['a','img','link','script']):
        attr='src' if node.name in ['img','script'] else 'href'
        value=node.get(attr,'')
        if not value or value.startswith('#'): continue
        u=urlsplit(value)
        if u.scheme or u.netloc: continue
        path=unquote(u.path)
        if base and path.startswith(base+'/'): path=path[len(base):]
        target=out/path.lstrip('/') if path.startswith('/') else file.parent/path
        if target.is_dir(): target=target/'index.html'
        if not target.is_file(): issues.append({'page':str(file.relative_to(out)),'url':value})
    for node in soup.find_all(True):
        assert not any(k.lower().startswith('on') for k in node.attrs), f'Inline event: {file}'
    assert not soup.select('form,iframe'), f'Dynamic form/embed: {file}'
    assert 'buy.stripe.com' not in str(soup), f'Legacy payment: {file}'
    assert '收款码' not in unquote(str(soup)), f'Legacy donation QR: {file}'
    assert not any(s in soup.get_text() for s in ['可否捐獻','可否捐贈','捐個款','賞口飯','捐款時刻']), f'Legacy donation appeal: {file}'
report={'posts':len(posts),'pages':len(list(out.rglob('*.html'))),'broken_local_links':issues}
(ROOT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(1 if issues else 0)
