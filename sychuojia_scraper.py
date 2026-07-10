"""草民影院元数据 - 慢速安全版 (3线程, ~2条/s)"""
import json, re, time, requests, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

try: import urllib3; urllib3.disable_warnings()
except: pass

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
     'Accept': 'text/html', 'Accept-Language': 'zh-CN,zh;q=0.9'}

BASE = 'https://m.sychuojia.com'
OUTPUT = 'data/sychuojia.json'
THREADS = 3
DELAY = 1.0  # 请求间隔

def fetch(url, timeout=20):
    time.sleep(DELAY)
    try:
        r = requests.get(url, headers=H, timeout=timeout, verify=False)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
        if r.status_code == 444:
            print(f'  ⚠ 限流! 等待30秒...')
            time.sleep(30)
    except: pass
    return None

def parse_list(html):
    results = []
    items = re.findall(r'<li[^>]*class=\"[^\"]*p1[^\"]*\">.*?</li>', html, re.DOTALL)
    for item in items:
        link = re.search(r'href=\"([^\"]*vdd[^\"]*)\"', item)
        title = re.search(r'title=\"([^\"]+)\"', item)
        img = re.search(r'(?:data-original|src)=\"([^\"]+\.(?:jpg|png|webp))\"', item, re.I)
        note = re.search(r'<i[^>]*>([^<]+)</i>', item)
        cat_info = re.findall(r'<p[^>]*class=\"[^\"]*actor[^\"]*\">([^<]+)', item)
        
        if link and title:
            vid = re.search(r'/vdd/(\d+)', link.group(1))
            rec = {
                'id': vid.group(1) if vid else link.group(1),
                'title': title.group(1),
                'poster': img.group(1) if img else '',
                'source': 'sychuojia',
                'url': BASE + link.group(1),
                'note': note.group(1) if note else '',
                'subcat': cat_info[0] if len(cat_info) > 0 else '',
                'region': cat_info[1] if len(cat_info) > 1 else '',
            }
            results.append(rec)
    return results

def parse_detail(html, base_info):
    info = dict(base_info)
    m = re.search(r'年份[：:</span>]*\s*<\/?[^>]*>\s*(\d{4})', html)
    if m: info['year'] = int(m.group(1))
    m = re.search(r'地区[：:</span>]*\s*<\/?[^>]*>\s*([^<]+)', html)
    if m: info['region'] = m.group(1).strip()
    m = re.search(r'导演[：:</span>]*\s*<\/?[^>]*>\s*([^<]{1,200})', html)
    if m: info['cast'] = m.group(1).strip()
    m = re.search(r'(?:剧情|简介|介绍)[：:</span>]*\s*([^<]{20,500})', html)
    if m: info['desc'] = m.group(1).strip()
    if not info.get('cast'):
        m = re.search(r'主演[：:</span>]*\s*<\/?[^>]*>\s*([^<]{1,300})', html)
        if m: info['cast'] = m.group(1).strip()
    return info

# 加载已有数据
all_videos = {}
existing_ids = set()
try:
    with open(OUTPUT, 'r', encoding='utf-8') as f:
        old = json.load(f)
    for v in old.get('videos', []):
        all_videos[v['id']] = v
        existing_ids.add(v['id'])
    print(f'已加载 {len(all_videos)} 条已有数据')
except: pass

def process_cat(slug, cat_key):
    global all_videos, existing_ids
    cat_name = '电影' if slug == 'dy' else '电视剧'
    print(f'\\n=== {cat_name} ({slug}) ===')
    
    # 探测总页数
    html = fetch(f'{BASE}/vd/{slug}-1.html')
    if not html: return
    pages = re.findall(f'{slug}-(\\d+)\\.html', html)
    max_page = max(int(p) for p in pages if p.isdigit()) if pages else 1
    print(f'总页数: {max_page}')
    
    # 批量收列表
    list_items = []
    for page in range(1, max_page + 1):
        html = fetch(f'{BASE}/vd/{slug}-{page}.html')
        if html:
            items = parse_list(html)
            new = [it for it in items if it['id'] not in existing_ids]
            list_items.extend(new)
            for it in items:
                existing_ids.add(it['id'])
        if page % 200 == 0 or page == max_page:
            print(f'  列表 {page}/{max_page} 新增{len(list_items)}  {datetime.now().strftime("%H:%M:%S")}')
    
    print(f'列表完成! 新增 {len(list_items)}')
    if not list_items: return
    
    # 详情页
    need = len(list_items)
    done = 0
    t0 = time.time()
    BATCH = 100
    
    for bi in range(0, need, BATCH):
        batch = list_items[bi:bi + BATCH]
        for it in batch:
            html = fetch(it['url'])
            if html:
                detail = parse_detail(html, it)
                all_videos[detail['id']] = detail
        
        done += len(batch)
        e = time.time() - t0
        rate = done / e if e > 0 else 0
        eta = (need - done) / rate if rate > 0 else 0
        print(f'  详情 {done}/{need} {rate:.1f}条/s 剩{eta/60:.0f}分 总{len(all_videos)} {datetime.now().strftime("%H:%M:%S")}')
        
        output = {
            'source': 'm.sychuojia.com',
            'videos': list(all_videos.values()),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        with open(OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False)

# 顺序执行
process_cat('dy', 'movie')
process_cat('dianshiju', 'tv')

print(f'\\n✅ 完成! 总计: {len(all_videos)} 耗时: {int(time.time()-time.time()):.0f}秒?')
