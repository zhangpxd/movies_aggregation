"""
m.jieshui8.com (片多多) 爬虫 - Apple CMS
流地址需JS动态加载，暂用iframe降级
"""
import json, re, os, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

H = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'text/html',
    'Accept-Language': 'zh-CN',
    'Accept-Encoding': 'gzip, deflate',
    'Referer': 'https://m.jieshui8.com/',
}
B = 'https://m.jieshui8.com'
sess = requests.Session()

SUBS = [
    # 电影
    (6,  'movie', '动作'),
    (7,  'movie', '喜剧'),
    (8,  'movie', '爱情'),
    (9,  'movie', '科幻'),
    (10, 'movie', '恐怖'),
    (11, 'movie', '剧情'),
    # 电视剧
    (13, 'tv', '国产剧'),
    (14, 'tv', '香港剧'),
    (15, 'tv', '台湾剧'),
    (16, 'tv', '日本剧'),
    (20, 'tv', '泰国剧'),
    (21, 'tv', '韩国剧'),
]

def parse_page(html):
    # 标题: <p class="video-name"><a class="text-overflow" href="/voddetail/{id}.html" title="title">title</a></p>
    titles = {}
    for m in re.finditer(
        r'<p class="video-name"><a[^>]*?href="/voddetail/(\d+)\.html"[^>]*title="([^"]+)"[^>]*>',
        html
    ):
        titles[int(m.group(1))] = m.group(2).strip()

    # 海报: <a class="video-img lazyload" href="/voddetail/{id}.html" data-original="{poster}">
    vids = []
    for m in re.finditer(
        r'<a class="video-img lazyload" href="/voddetail/(\d+)\.html"[^>]*?data-original="([^"]+)"',
        html
    ):
        vid = int(m.group(1))
        poster = m.group(2)
        title = titles.get(vid, '')
        if title and len(title) > 1:
            vids.append({
                'id': vid,
                'title': title,
                'url': B + '/voddetail/' + m.group(1) + '.html',
                'poster': poster,
            })
    return vids

def scrape_sub(slug, cat_id, subcat, max_pages=50):
    url1 = f'{B}/vodtype/{slug}.html'
    r = sess.get(url1, headers=H, timeout=20)
    r.encoding = 'utf-8'
    if r.status_code != 200:
        print(f'    ❌ 无法访问')
        return []

    # 总页数 - jieshui8 移动端模板
    pages = re.findall(rf'/vodtype/{slug}-(\d+)\.html', r.text)
    tp = max(int(p) for p in pages) if pages else 1
    MAX_PAGES = min(tp, max_pages)

    vids = parse_page(r.text)

    if MAX_PAGES > 1:
        pages = list(range(2, MAX_PAGES + 1))
        BATCH = 3
        def fp(p):
            r2 = sess.get(f'{B}/vodtype/{slug}-{p}.html', headers=H, timeout=20)
            r2.encoding = 'utf-8'
            return parse_page(r2.text) if r2.status_code == 200 else []

        for i in range(0, len(pages), BATCH):
            batch = pages[i:i+BATCH]
            with ThreadPoolExecutor(3) as ex:
                fs = {ex.submit(fp, p): p for p in batch}
                for f in as_completed(fs):
                    vids.extend(f.result())
            time.sleep(0.15)

    seen = set()
    uni = []
    for v in vids:
        if v['id'] not in seen:
            seen.add(v['id'])
            v['category'] = cat_id
            v['subcat'] = subcat
            v['source'] = 'jieshui8'
            v['streamUrl'] = ''  # JS动态加载，暂无
            v['status'] = ''
            uni.append(v)

    print(f'    {subcat or cat_id}: {len(uni)}条 / {MAX_PAGES}页')
    return uni

print('=' * 55)
print('  m.jieshui8.com (片多多) 爬虫')
print('=' * 55)

all_vids = []
for slug, cat_id, subcat in SUBS:
    all_vids.extend(scrape_sub(slug, cat_id, subcat))

os.makedirs('data', exist_ok=True)
output = {
    'source': 'm.jieshui8.com',
    'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'total': len(all_vids),
    'videos': all_vids,
}
with open('data/jieshui8.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'\n{"="*55}')
print(f'  完成！总计: {len(all_vids)} 条')
for c in ['movie','tv']:
    n = sum(1 for v in all_vids if v['category'] == c)
    print(f'    {c}: {n} 条')
print(f'{"="*55}')
