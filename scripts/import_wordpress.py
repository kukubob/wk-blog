"""Import only publicly published posts and their referenced resources. No credentials.

Run before changing DNS. Re-runs reuse the checked media manifest.
"""
from __future__ import annotations
import concurrent.futures as cf
import hashlib
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, quote

import requests
import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://wk.yr.al'
HOSTS = {'wk.yr.al', 'wkbhjlq.tw', 'www.wkbhjlq.tw', 'jsdelivr.wkbhjlq.tw', 'air.wkbhjlq.tw'}
REMOVED_PATHS = {'/giffgaff/', '/express/'}
MEDIA_EXT = {'.pdf','.jpg','.jpeg','.png','.gif','.webp','.svg','.ico','.zip','.doc','.docx','.xls','.xlsx','.mp4','.mp3'}

def api_all(endpoint):
    items = []
    for page in range(1, 100):
        r = requests.get(f'{SOURCE}/wp-json/wp/v2/{endpoint}', params={'per_page':100,'page':page}, timeout=45)
        r.raise_for_status()
        items.extend(r.json())
        if page >= int(r.headers.get('X-WP-TotalPages', 1)):
            assert len(items) == int(r.headers['X-WP-Total']), (endpoint, len(items))
            return items
    raise RuntimeError('Pagination did not finish')

def canonical(url):
    url = html.unescape(url.strip())
    p = urlsplit(urljoin(SOURCE, url))
    if p.hostname in HOSTS:
        return SOURCE + quote(unquote(p.path), safe='/')
    return p._replace(scheme='https', fragment='').geturl()

def local_path(url):
    p = urlsplit(url)
    path = unquote(p.path)
    if p.hostname in HOSTS and path.startswith('/wp-content/uploads/'):
        if '..' in Path(path).parts: raise ValueError(path)
        return path
    suffix = Path(path).suffix.lower()
    if suffix not in MEDIA_EXT: suffix = '.img'
    return '/media/' + hashlib.sha256(url.encode()).hexdigest()[:24] + suffix

def clean_body(body, post_id=None):
    # User explicitly removed donations, including the introductory QR-code block.
    soup = BeautifulSoup(body, 'html.parser')
    if post_id == 2248:
        start=next((p for p in soup.find_all('p') if p.get_text(strip=True).startswith('首先這是一個電子錢包')),None)
        if start is None: raise ValueError('Ozan donation boundary changed; review before importing')
        while start.previous_sibling is not None: start.previous_sibling.extract()
    for node in soup.select('script, style, noscript, form, iframe, input, button'):
        node.decompose()
    for node in soup.find_all('img'):
        src = node.get('data-src') or node.get('data-original') or node.get('src')
        node.attrs = {'src': canonical(src), 'alt': node.get('alt','')} if src else {}
    for node in soup.find_all('a', href=True):
        p = urlsplit(urljoin(SOURCE, node['href']))
        if p.hostname == 'buy.stripe.com' or (p.hostname in HOSTS and p.path.rstrip('/')+'/' in REMOVED_PATHS):
            node.decompose()
    for node in list(soup.find_all('p')):
        text=node.get_text('',strip=True)
        if re.search(r'^(最後|如果你喜歡|如果各位|博客的發展|文章的最後|各位老闆|別問我為啥|好了這篇文章就到這裡).*(捐款|捐獻|捐贈|捐個款)',text) or re.search(r'^你是不是以為我要走了.*要飯|^即可給我賞口飯',text):
            node.decompose()
    return soup

def download(item):
    url, record = item
    target = ROOT / 'assets' / record['path'].lstrip('/')
    if target.exists() and record.get('sha256') == hashlib.sha256(target.read_bytes()).hexdigest():
        return url, record
    candidates = [url]
    original = re.sub(r'-\d+x\d+(?=\.[a-zA-Z]{2,5}(?:$|\?))', '', url)
    if original != url: candidates.append(original)
    error = ''
    for candidate in candidates:
        for attempt in range(2):
            try:
                r = requests.get(candidate, timeout=(10,40), headers={'User-Agent':'WK-Archive-Migration/1.0'}, allow_redirects=True)
                r.raise_for_status()
                mime = r.headers.get('Content-Type','').split(';')[0]
                if not r.content or mime in {'text/html', 'application/json'} or r.content.lstrip().lower().startswith((b'<!doctype html', b'<html')):
                    raise ValueError('Expected resource, received empty/HTML/JSON')
                if '/wp-content/uploads/' in record['path'] and Path(record['path']).suffix.lower() not in MEDIA_EXT:
                    raise ValueError('Unsupported attachment type')
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(target.suffix+'.part')
                tmp.write_bytes(r.content)
                tmp.replace(target)
                record.update(status='ok', bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest(), content_type=mime, fetched_url=r.url)
                record.pop('error',None)
                return url, record
            except Exception as e:
                error = str(e)
                if attempt == 0: time.sleep(.4)
    record.update(status='failed', error=error)
    return url, record

def main():
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    seed = ROOT/'content/source-posts.json'
    posts = json.loads(seed.read_text()) if seed.exists() else api_all('posts')
    cats = {x['id']: x for x in api_all('categories')}
    tags = {x['id']: html.unescape(x['name']) for x in api_all('tags')}
    authors = {x['id']: html.unescape(x['name']) for x in api_all('users')}
    (cache/'posts.json').write_text(json.dumps(posts, ensure_ascii=False))
    manifest_file = ROOT/'media-manifest.json'
    old = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
    wanted = {}
    prepared = []
    for post in posts:
        soup = clean_body(post['content']['rendered'],post['id'])
        for node in soup.find_all(['img','a']):
            attr = 'src' if node.name == 'img' else 'href'
            raw = node.get(attr)
            if not raw: continue
            url = canonical(raw)
            p = urlsplit(url)
            if node.name == 'img' or (p.hostname in HOSTS and '/wp-content/uploads/' in p.path):
                wanted[url] = old.get(url, {'path':local_path(url)})
                node[attr] = wanted[url]['path']
        prepared.append((post,soup))
    print(f'Published posts: {len(posts)}; referenced resources: {len(wanted)}', flush=True)
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        for i,(url,record) in enumerate(pool.map(download, wanted.items()),1):
            wanted[url] = record
            if i % 50 == 0:
                manifest_file.write_text(json.dumps(wanted,ensure_ascii=False,indent=2))
                print(f'Resources {i}/{len(wanted)}; failures so far {sum(x.get("status")=="failed" for x in wanted.values())}',flush=True)
    manifest_file.write_text(json.dumps(wanted,ensure_ascii=False,indent=2))
    (ROOT/'media-status.json').write_text(json.dumps([{k:v for k,v in entry.items() if k in {'path','status','bytes','sha256','content_type'}} for entry in wanted.values()],ensure_ascii=False,indent=2))
    # Remove obsolete downloaded assets from this new project after explicit content removal.
    retained = {str((ROOT/'assets'/v['path'].lstrip('/')).resolve()) for v in wanted.values()}
    for folder in [ROOT/'assets/wp-content/uploads', ROOT/'assets/media']:
        if folder.exists():
            for file in folder.rglob('*'):
                if file.is_file() and str(file.resolve()) not in retained: file.unlink()
    posts_dir = ROOT/'content/posts'
    posts_dir.mkdir(exist_ok=True)
    for post,soup in prepared:
        path = unquote(urlsplit(post['link']).path)
        meta = {'id':post['id'], 'title':html.unescape(post['title']['rendered']), 'date':post['date'][:10],
                'modified':post['modified'][:10], 'path':path, 'slug':unquote(post['slug']),
                'author':authors.get(post['author'],'奶酪'),
                'categories':[{'name':html.unescape(cats[c]['name']), 'slug':cats[c]['slug']} for c in post['categories']],
                'tags':[tags[t] for t in post['tags'] if t in tags], 'original_url':post['link']}
        body = markdownify(str(soup), heading_style='ATX', strip=['div','span','kbd','mark'])
        body = re.sub(r'\n{3,}','\n\n',body).strip()
        (posts_dir/f'{post["id"]}.md').write_text('---\n'+yaml.safe_dump(meta,allow_unicode=True,sort_keys=False)+'---\n\n'+body+'\n')
    result = {'posts':len(posts),'resources':len(wanted),'ok':sum(x.get('status')=='ok' for x in wanted.values()),
              'failed':[{'host':urlsplit(k).hostname,'path':v['path'],'status':v['status']} for k,v in wanted.items() if v.get('status')!='ok'],
              'bytes':sum(x.get('bytes',0) for x in wanted.values())}
    (ROOT/'migration-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='failed'},ensure_ascii=False),flush=True)
    print(f'Failed resources: {len(result["failed"])}',flush=True)

if __name__ == '__main__': main()
