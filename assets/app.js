(() => {
  'use strict';
  const base = document.body.dataset.base || '';
  const params = new URLSearchParams(location.search);
  const norm = value => String(value).normalize('NFKC').toLocaleLowerCase();
  if (params.has('p') || params.has('page_id')) {
    fetch(base + '/post-map.json').then(r => { if (!r.ok) throw Error(r.status); return r.json(); }).then(map => {
      const path = map[params.get('p') || params.get('page_id')];
      if (path) location.replace(base + path + location.hash);
    }).catch(() => {});
  }
  const input = document.querySelector('#search');
  if (!input) return;
  const rows = [...document.querySelectorAll('.post-row')];
  const filters = [...document.querySelectorAll('.filter')];
  const status = document.querySelector('#search-status');
  let category = '', index = new Map(), ready = false;
  function update() {
    const terms = norm(input.value.trim()).split(/\s+/).filter(Boolean);
    let count = 0;
    for (const row of rows) {
      const haystack = index.get(row.dataset.id) || norm(row.textContent);
      const visible = (!category || row.dataset.categories.split(' ').includes(category)) && terms.every(t => haystack.includes(t));
      row.hidden = !visible;
      count += Number(visible);
    }
    document.querySelector('#result-count').textContent = `${count} 篇`;
    document.querySelector('#no-results').hidden = count !== 0;
    status.textContent = terms.length && !ready ? '正在載入全文索引，目前先搜尋標題與摘要。' : '';
  }
  fetch(base + '/search.json').then(r => { if (!r.ok) throw Error(r.status); return r.json(); }).then(posts => {
    index = new Map(posts.map(p => [String(p.id), norm([p.title, p.text, ...p.tags].join(' '))]));
    ready = true; update();
  }).catch(() => { ready = true; update(); status.textContent = '全文索引暫時無法載入，仍可搜尋標題與摘要。'; });
  input.value = params.get('q') || '';
  input.addEventListener('input', () => { update(); const u = new URL(location); input.value ? u.searchParams.set('q', input.value) : u.searchParams.delete('q'); history.replaceState(null, '', u); });
  filters.forEach(button => button.addEventListener('click', () => { category = button.dataset.category; filters.forEach(b => b.classList.toggle('active', b === button)); update(); }));
  document.addEventListener('keydown', e => { if (e.key === '/' && !['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) { e.preventDefault(); input.focus(); } });
  if (params.has('search')) input.focus();
  update();
})();
