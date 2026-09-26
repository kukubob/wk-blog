(() => {
 'use strict';
 const base=document.body.dataset.base||'';
 const q=new URLSearchParams(location.search);
 if(q.has('p')||q.has('page_id'))fetch(base+'/post-map.json').then(r=>r.json()).then(m=>{const p=m[q.get('p')||q.get('page_id')];if(p)location.replace(base+p+location.hash);});
 const modal=document.querySelector('.search-form--modal');
 document.querySelector('.js-toggle-search')?.addEventListener('click',()=>{modal.classList.add('is-visible');modal.querySelector('input').focus();});
 document.querySelector('.search_close')?.addEventListener('click',()=>modal.classList.remove('is-visible'));
 document.addEventListener('keydown',e=>{if(e.key==='Escape')modal?.classList.remove('is-visible');});
 document.querySelectorAll('.search-form--modal input,.m-search input').forEach(i=>i.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();location.href=base+'/search/?s='+encodeURIComponent(i.value);}}));
 document.querySelector('#show-nav')?.addEventListener('click',()=>document.querySelector('.lower nav').classList.toggle('show'));
 document.querySelector('.openNav .iconflat')?.addEventListener('click',()=>document.body.classList.toggle('static-nav-open'));
 document.querySelectorAll('.cd-top,#moblieGoTop').forEach(n=>n.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'})));
 document.querySelector('#moblieDarkLight')?.addEventListener('click',()=>document.body.classList.toggle('dark'));
 window.addEventListener('scroll',()=>document.querySelector('.site-header')?.classList.toggle('yya',window.scrollY>0),{passive:true});
 const input=document.querySelector('#archive-search');if(!input)return;
 const rows=[...document.querySelectorAll('.post-list-thumb')],norm=s=>s.normalize('NFKC').toLowerCase();let index=new Map();
 input.value=q.get('s')||q.get('q')||'';
 function update(){const terms=norm(input.value).trim().split(/\s+/).filter(Boolean);let count=0;for(const row of rows){const text=index.get(row.dataset.id)||norm(row.textContent);row.hidden=!terms.every(t=>text.includes(t));if(!row.hidden)count++;}document.querySelector('#search-status').textContent=count+' 篇';}
 fetch(base+'/search.json').then(r=>r.json()).then(posts=>{index=new Map(posts.map(p=>[String(p.id),norm(p.title+' '+p.text)]));update();});input.addEventListener('input',update);update();
})();
