"""Build a portable static archive, retaining original WordPress article paths."""
from __future__ import annotations
import argparse
import collections
import html
import json
import math
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit, quote

import bleach
import markdown
import yaml
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
HOSTS = {'wk.yr.al','wkbhjlq.tw','www.wkbhjlq.tw','jsdelivr.wkbhjlq.tw','air.wkbhjlq.tw'}
TAGS = {'p','a','img','h1','h2','h3','h4','h5','h6','strong','em','b','i','ul','ol','li','blockquote','pre','code','br','hr','table','thead','tbody','tr','td','th','del','s','sup','sub','figure','figcaption','details','summary','div','span'}

def main():
    args = argparse.ArgumentParser()
    args.add_argument('--base-path',default='')
    args.add_argument('--site-url',default='https://wk.yr.al')
    opts = args.parse_args()
    base = opts.base_path.rstrip('/')
    site = opts.site_url.rstrip('/')
    out = ROOT/'dist'
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(ROOT/'assets',out)
    (out/'.nojekyll').touch()
    url = lambda path: base + quote(path, safe='/#?=&%')
    posts = []
    for path in (ROOT/'content/posts').glob('*.md'):
        _,front,body = path.read_text().split('---',2)
        data = yaml.safe_load(front)
        data.update(markdown=body, category_slugs=[c['slug'] for c in data['categories']])
        # These exported section headings were bold paragraphs in WordPress.
        body = re.sub(r'^\*\*([^*\n]{2,45})\*\*\s*$', r'## \1', body, flags=re.M)
        body = re.sub(r'~~([^\n]+?)~~', r'<del>\1</del>', body)
        md = markdown.Markdown(extensions=['tables','fenced_code','toc','sane_lists'],extension_configs={'toc':{'permalink':False}})
        rendered = md.convert(body)
        clean = bleach.clean(rendered, tags=TAGS, attributes={'a':['href','title'],'img':['src','alt','title'],'*':['id'],'td':['colspan','rowspan'],'th':['colspan','rowspan']}, protocols=['http','https','mailto'],strip=True)
        data.update(html=clean,toc=md.toc)
        soup = BeautifulSoup(clean,'html.parser')
        text = soup.get_text(' ',strip=True)
        data.update(text=text,excerpt=text[:115] + ('…' if len(text)>115 else ''),minutes=max(1,math.ceil(len(text)/450)))
        posts.append(data)
    posts.sort(key=lambda p:(p['date'],p['id']),reverse=True)
    by_id = {str(p['id']):p['path'] for p in posts}
    by_slug = {p['slug']:p['path'] for p in posts}
    by_id.update({'3402':'/giffgaff/','1614':'/express/','140':'/about/','2040':'/links/'})
    manifest = json.loads((ROOT/'media-status.json').read_text())
    failed = {v['path'] for v in manifest if v.get('status')!='ok'}
    aliases = {}
    legacy_slugs = {'n26':'n26-bank', 'ultra-mobile-paygo（3-月）':'ultra'}
    def rewrite(body):
        soup = BeautifulSoup(body,'html.parser')
        for node in soup.find_all(['a','img']):
            attr = 'src' if node.name=='img' else 'href'
            raw = node.get(attr,'')
            if not raw: continue
            parsed = urlsplit(raw)
            path = unquote(parsed.path)
            if node.name=='a' and parsed.netloc in HOSTS and path.startswith('/wp-admin/'):
                node.unwrap()
                continue
            if node.name=='img' and path in failed:
                placeholder = soup.new_tag('span',attrs={'class':'missing-media'})
                placeholder.string = '原圖暫缺' + (' · '+node.get('alt','') if node.get('alt') else '')
                node.replace_with(placeholder)
                continue
            if node.name=='img': node['loading']='lazy'; node['decoding']='async'
            if parsed.netloc in HOSTS or (not parsed.netloc and path.startswith('/')):
                if parsed.query:
                    from urllib.parse import parse_qs
                    q=parse_qs(parsed.query)
                    if 'p' in q or 'page_id' in q:
                        path=by_id.get((q.get('p') or q.get('page_id'))[0],path)
                if path not in {p['path'] for p in posts} and path.endswith('.html'):
                    slug=Path(path).stem
                    slug=re.sub(r'(?:申請|開通|開戶)?教程$|介紹$', '', slug)
                    slug=legacy_slugs.get(slug,slug)
                    if slug in by_slug:
                        aliases[path]=by_slug[slug]
                        path=by_slug[slug]
                node[attr]=url(path or '/') + ('#'+parsed.fragment if parsed.fragment else '')
            if node.name=='a' and parsed.scheme in {'http','https'} and parsed.netloc not in HOSTS:
                node['rel']='noopener noreferrer'
        return str(soup)
    env=Environment(loader=FileSystemLoader(ROOT/'templates'),autoescape=select_autoescape(['html']))
    def emit(path,template,**context):
        target=out/path.lstrip('/')
        if not target.suffix: target=target/'index.html'
        target.parent.mkdir(parents=True,exist_ok=True)
        common=dict(url=url,base=base,title='無卡不歡',description='銀行帳戶、電話卡與海外生活的親歷記錄。無卡不歡博客文章典藏。',canonical=site+quote(path,safe='/'),page_type='page')
        common.update(context)
        target.write_text(env.get_template(template).render(**common))
    cats={}
    for p in posts:
        for c in p['categories']:
            cats.setdefault(c['slug'],{**c,'count':0})['count']+=1
    categories=sorted(cats.values(),key=lambda x:-x['count'])
    emit('/','home.html',posts=posts,categories=categories,category=None,page_type='home')
    for c in categories:
        selected=[p for p in posts if c['slug'] in p['category_slugs']]
        emit('/category/'+c['slug']+'/','home.html',title=c['name'],posts=selected,categories=[c],category=c,page_type='home')
    for i,p in enumerate(posts):
        emit(p['path'],'article.html',title=p['title'],description=p['excerpt'],post=p,body=rewrite(p['html']),toc=p['toc'],previous=posts[i-1] if i else None,next=posts[i+1] if i+1<len(posts) else None,page_type='article')
    for old,new in aliases.items():
        target=out/old.lstrip('/')
        target.parent.mkdir(parents=True,exist_ok=True)
        destination=html.escape(url(new),quote=True)
        target.write_text('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>文章已移至新網址 · 無卡不歡</title><link rel="canonical" href="'+html.escape(site+quote(new,safe='/'),quote=True)+'"><meta http-equiv="refresh" content="0;url='+destination+'"></head><body><h1>文章已移至新網址</h1><a href="'+destination+'">繼續閱讀</a></body></html>')
    (out/'legacy-aliases.json').write_text(json.dumps(aliases,ensure_ascii=False,indent=2))
    about='<p>這裡保存了「無卡不歡博客」的 108 篇文章，內容涵蓋銀行帳戶、信用卡、電話卡、轉運與海外生活。</p><p>文章保留原始內容、作者標示與發布日期，方便查閱和回顧。網站已轉為靜態閱讀版，提供分類瀏覽與全文搜尋。</p><p>SIM 卡銷售、快遞代發、捐款與其他交易入口已移除，本站不再提供這些服務。</p>'
    emit('/about/','page.html',title='關於這份文章典藏',body=about)
    for path in ['/giffgaff/','/express/']:
        emit(path,'page.html',title='此服務頁已移除',body='<p>本站已轉為文章典藏，不再提供 SIM 卡銷售、快遞代發或捐款入口。</p>')
    emit('/links/','page.html',title='友情連結',body='<p>原頁面未提供可遷移的連結內容，歡迎從文章目錄繼續閱讀。</p>')
    emit('/404.html','page.html',title='沒有找到這個頁面',body='<p>連結可能已變更。請返回文章目錄，用標題或關鍵字查找。</p>',canonical=None)
    (out/'search.json').write_text(json.dumps([{'id':p['id'],'title':p['title'],'path':p['path'],'text':p['text'],'tags':p['tags']} for p in posts],ensure_ascii=False))
    (out/'post-map.json').write_text(json.dumps(by_id,ensure_ascii=False))
    paths=['/','/about/']+[p['path'] for p in posts]+['/category/'+c['slug']+'/' for c in categories]
    (out/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+html.escape(site+quote(p,safe='/'))+'</loc></url>' for p in paths)+'</urlset>')
    (out/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+site+'/sitemap.xml\n')
    total=sum(f.stat().st_size for f in out.rglob('*') if f.is_file())
    assert total < 1_000_000_000, f'Site exceeds conservative 1 GB limit: {total}'
    print(json.dumps({'posts':len(posts),'categories':len(categories),'html_pages':len(list(out.rglob('*.html'))),'site_bytes':total,'missing_media':len(failed),'base_path':base}))

if __name__=='__main__': main()
