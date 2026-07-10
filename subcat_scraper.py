"""
子分类批量爬虫 v2 - 多线程并发版
每个子分类500条，并发爬取
用法: python subcat_scraper.py
"""

import json
import re
import time
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Referer': 'https://www.mediavip.cn/',
}
BASE = 'https://www.mediavip.cn'
MAX_WORKERS = 4  # 并发线程数（不要太高否则被限流）
PRINT_LOCK = Lock()
SESSION = None  # 复用连接

SUBCATS = {
    'movie': ('电影', {
        'shaoshi':'邵氏电影','lilun':'理论电影','dongzuo':'动作',
        'aiqing':'爱情','xiju':'喜剧','kongbu':'恐怖','jings':'惊悚',
        'xuanyi':'悬疑','fanzui':'犯罪','juqing':'剧情','zhanzheng':'战争',
        'zainan':'灾难','kehuan':'科幻','qihuan':'奇幻','maoxian':'冒险',
        'jilu':'纪录','qita':'其他',
    }),
    'tv': ('连续剧', {
        'guochanju':'国产剧','gangtaiju':'港台剧','hanguoju':'韩国剧',
        'ribenju':'日本剧','oumeiju':'欧美剧','taiguoju':'泰国剧',
        'duanju':'短剧','qitaju':'其他剧',
    }),
}


def fetch_page(url, referer):
    """抓取单页（带重试）"""
    global SESSION
    if SESSION is None:
        SESSION = requests.Session()
    hdrs = dict(HEADERS)
    hdrs['Referer'] = referer
    for attempt in range(3):
        try:
            r = SESSION.get(url, headers=hdrs, timeout=20)
            r.encoding = 'utf-8'
            if r.status_code == 200 and '/mvip/' in r.text:
                return r
            if r.status_code == 403:
                time.sleep(1.5)
                continue
        except:
            time.sleep(1)
    return None


def parse_page(html):
    """解析页面中的视频"""
    videos = []
    for m in re.finditer(
        r'<a\s[^>]*?href="(/mvip/(\d+)/)"[^>]*?title="([^"]+)"[^>]*?>',
        html
    ):
        poster_m = re.search(r'data-original="([^"]+)"', m.group(0))
        if not poster_m:
            continue
        title = m.group(3).strip()
        if 1 < len(title) < 100:
            videos.append({
                'id': int(m.group(2)),
                'title': title,
                'url': BASE + m.group(1),
                'poster': poster_m.group(1),
            })
    return videos


def get_total_pages(html, slug):
    """获取总页数"""
    last = re.search(rf'/{slug}-(\d+)/[^>]*>尾页', html)
    total = re.search(r'共\s*(\d+)\s*页', html)
    if last:
        return int(last.group(1))
    if total:
        return int(total.group(1))
    return 1


def scrape_subcategory(cat_id, slug, name, max_items=500):
    """刮取单个子分类（并发抓页）"""
    # 先抓第一页获取总页数
    url1 = f'{BASE}/hgft/{slug}/'
    r = fetch_page(url1, BASE)
    if not r:
        with PRINT_LOCK:
            print(f'    {name}: ❌ 无法访问')
        return []

    total_pages = get_total_pages(r.text, slug)
    videos = parse_page(r.text)
    per_page = max(len(videos), 1)

    # 计算需要多少页才能达到 max_items
    pages_needed = min(total_pages, max(2, (max_items + per_page - 1) // per_page))

    # 并发抓取剩余页面
    urls = []
    for p in range(2, pages_needed + 1):
        urls.append((
            f'{BASE}/hgft/{slug}-{p}/',
            f'{BASE}/hgft/{slug}/'
        ))

    if urls:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(fetch_page, u, ref): (u, p) for p, (u, ref) in enumerate(urls, 2)}
            for f in as_completed(futures):
                try:
                    resp = f.result()
                    if resp:
                        videos.extend(parse_page(resp.text))
                except:
                    pass

    # 截断到 max_items
    videos = videos[:max_items]

    # 去重
    seen = set()
    unique = []
    for v in videos:
        if v['id'] not in seen:
            seen.add(v['id'])
            unique.append(v)

    with PRINT_LOCK:
        print(f'    {name}({slug}): {len(unique)} 条 ({pages_needed} 页)')

    return unique


def scrape_category_parallel(cat_id, cat_name, subs):
    """并发抓取一个主分类下的所有子分类"""
    with PRINT_LOCK:
        print(f'\n📂 {cat_name} ({len(subs)} 个子分类)')

    all_videos = []
    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for slug, name in subs.items():
            tasks.append(ex.submit(scrape_subcategory, cat_id, slug, name, 500))

        for f in as_completed(tasks):
            try:
                all_videos.extend(f.result())
            except Exception as e:
                print(f'  ❌ Error: {e}')

    return all_videos


def main():
    print('=' * 60)
    print('  子分类批量爬虫 v2 - 多线程并发')
    print('=' * 60)

    all_videos = []

    for cat_id, (cat_name, subs) in SUBCATS.items():
        all_videos.extend(scrape_category_parallel(cat_id, cat_name, subs))

    # 全局去重
    seen = set()
    unique = []
    for v in all_videos:
        key = (v['category'], v['id'])
        if key not in seen:
            seen.add(key)
            v['category'] = v.get('category', 'movie')  # ensure set
            v['subcat'] = v.get('subcat', '')
            v['source'] = 'mediavip'
            v['streamUrl'] = ''
            v['status'] = ''
            unique.append(v)

    # 保存
    os.makedirs('data', exist_ok=True)
    output = {
        'source': 'mediavip.cn',
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(unique),
        'videos': unique,
    }
    with open('data/full_videos.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n{"="*60}')
    print(f'  完成！总计: {len(unique)} 条')
    for cat_id in ['movie','tv']:
        n = sum(1 for v in unique if v['category'] == cat_id)
        print(f'    {SUBCATS[cat_id][0]}: {n} 条')
    print(f'{"="*60}')


if __name__ == '__main__':
    main()
