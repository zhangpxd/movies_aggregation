"""
xfej.net (葡萄影视) 爬虫
输出: data/xfej.json
用法: python xfej_scraper.py
"""
import json, re, os, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Referer': 'https://xfej.net/',
}
B = 'https://xfej.net'
sess = requests.Session()

# 子分类: slug → (主分类, 子分类名)
SUBS = [
    # 电影
    (6,  'movie', '动作'),
    (7,  'movie', '喜剧'),
    (8,  'movie', '爱情'),
    (9,  'movie', '科幻'),
    (10, 'movie', '恐怖'),
    (11, 'movie', '剧情'),
    (12, 'movie', '战争'),
    (20, 'movie', '论理'),
    (21, 'movie', '其他'),
    (25, 'movie', '动漫电影'),
    # 电视剧
    (13, 'tv', '国产剧'),
    (14, 'tv', '港台剧'),
    (15, 'tv', '日韩剧'),
    (16, 'tv', '欧美剧'),
]

def parse_page(html):
    """提取有海报的视频"""
    vids = []
    for m in re.finditer(
        r'<a\s[^>]*?href="/spd/(\d+)\.html"[^>]*?title="([^"]+)"[^>]*?>',
        html
    ):
        poster_m = re.search(r'data-original="([^"]+)"', m.group(0))
        if poster_m:
            vids.append({
                'id': int(m.group(1)),
                'title': m.group(2).strip(),
                'url': B + '/spd/' + m.group(1) + '.html',
                'poster': poster_m.group(1),
            })
    return vids

def scrape_sub(slug, cat_id, subcat, max_pages=50):
    """刮取单个子分类"""
    url1 = f'{B}/sptype/{slug}.html'
    r = sess.get(url1, headers=H, timeout=20)
    r.encoding = 'utf-8'
    if r.status_code != 200:
        print(f'    ❌ 无法访问')
        return []

    # 总页数
    last = re.search(rf'/sptype/{slug}-(\d+)\.html[^>]*>尾页', r.text)
    tp = int(last.group(1)) if last else 1
    MAX_PAGES = min(tp, max_pages)

    vids = parse_page(r.text)

    if MAX_PAGES > 1:
        pages = list(range(2, MAX_PAGES + 1))
        BATCH = 3
        def fp(p):
            r2 = sess.get(f'{B}/sptype/{slug}-{p}.html', headers=H, timeout=20)
            r2.encoding = 'utf-8'
            return parse_page(r2.text) if r2.status_code == 200 else []

        for i in range(0, len(pages), BATCH):
            batch = pages[i:i+BATCH]
            with ThreadPoolExecutor(3) as ex:
                fs = {ex.submit(fp, p): p for p in batch}
                for f in as_completed(fs):
                    vids.extend(f.result())
            time.sleep(0.15)

    # 去重并添加 meta
    seen = set()
    uni = []
    for v in vids:
        if v['id'] not in seen:
            seen.add(v['id'])
            v['category'] = cat_id
            v['subcat'] = subcat
            v['source'] = 'xfej'
            v['streamUrl'] = ''
            v['status'] = ''
            uni.append(v)

    print(f'    {subcat or cat_id}: {len(uni)}条 / {MAX_PAGES}页')
    return uni

print('=' * 55)
print('  xfej.net (葡萄影视) 爬虫')
print('=' * 55)

all_vids = []
for slug, cat_id, subcat in SUBS:
    label = subcat or {'movie':'电影','tv':'连续剧'}[cat_id]
    print(f'  [{cat_id}] {label} (type {slug})')
    all_vids.extend(scrape_sub(slug, cat_id, subcat))

# 保存
os.makedirs('data', exist_ok=True)
output = {
    'source': 'xfej.net',
    'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'total': len(all_vids),
    'videos': all_vids,
}
with open('data/xfej.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'\n{"="*55}')
print(f'  完成！总计: {len(all_vids)} 条')
for c in ['movie','tv']:
    n = sum(1 for v in all_vids if v['category'] == c)
    print(f'    {c}: {n} 条')
print(f'{"="*55}')
