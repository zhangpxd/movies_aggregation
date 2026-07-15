"""crawl_12ju.py —— VIP影院(v.12ju.com) 整合抓取脚本(单文件产出)。

把原来分散的 12ju_scraper.py(列表) + 12ju_stream_scraper.py(抓流) 整合为一个入口,
最终只保留一份可用主文件 data/12ju.json(含列表/海报/分类/流地址等)。

用法:
  python crawl_12ju.py all       # 列表 -> 抓流 -> 写单文件 data/12ju.json
  python crawl_12ju.py list      # 仅列表
  python crawl_12ju.py stream    # 仅补抓缺失流地址
  python crawl_12ju.py smoke:10  # 冒烟: 前 10 条验证连通+字段, 写 data/12ju_smoke.json(不改生产)
"""
import os, sys, json, re, time, requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

NAME = '12ju'
LABEL = 'VIP影院'
BASE = 'https://v.12ju.com'
OUT = 'data/12ju.json'
SMOKE = 'data/12ju_smoke.json'

H_TPL = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Sec-Ch-Ua': '";Not A(Brand";v="99";, "Google Chrome";v="130"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '";Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Upgrade-Insecure-Requests': '1',
}

# (slug, 主分类, 子分类名) —— 取自原 12ju_scraper.py 的 SUBS
SUBS = [
    ('dongzuopian', 'movie', '动作'), ('xijupian', 'movie', '喜剧'),
    ('aiqingpian', 'movie', '爱情'), ('kehuanpian', 'movie', '科幻'),
    ('guochanju', 'tv', '国产剧'), ('xianggangju', 'tv', '港台剧'),
    ('oumeiju', 'tv', '欧美剧'), ('ribenju', 'tv', '日本剧'),
]


def new_session():
    for attempt in range(3):
        try:
            s = requests.Session()
            s.get(BASE + '/', headers=H_TPL, timeout=30)
            return s
        except Exception:
            time.sleep(2)
    raise RuntimeError(f'{BASE} unreachable')


sess = new_session()
last_refresh = time.time()


def parse_list(html):
    vids = []
    for m in re.finditer(
        r'<img[^>]+(?:src|data-original)="([^"]+)"[^>]*>.*?<a[^>]+href="/tv/(\d+)\.html"[^>]*>([^<]+)',
        html, re.DOTALL):
        poster = m.group(1)
        if 'pic.png' not in poster:
            vids.append({'id': int(m.group(2)), 'title': m.group(3).strip(),
                         'url': BASE + '/tv/' + m.group(2) + '.html', 'poster': poster})
    return vids


def scrape_sub(slug, cat_id, subcat, max_pages=500):
    vids = []
    p = 1
    while p <= max_pages:
        url = BASE + '/' + slug + '/' if p == 1 else BASE + '/' + slug + '/index-' + str(p) + '.html'
        ref = BASE + '/'
        if p > 1:
            ref = BASE + '/' + slug + ('/' if p == 2 else '/index-' + str(p - 1) + '.html')
        h = dict(H_TPL); h['Referer'] = ref; h['Sec-Fetch-Site'] = 'same-origin'
        try:
            r = sess.get(url, headers=h, timeout=20)
            if r.status_code != 200:
                break
            pv = parse_list(r.text)
            if not pv:
                break
            vids.extend(pv)
        except Exception:
            break
        p += 1
        time.sleep(0.3)
    seen = set(); uni = []
    for v in vids:
        if v['id'] not in seen:
            seen.add(v['id'])
            v['category'] = cat_id
            v['subcat'] = subcat
            v['source'] = NAME
            v['streamUrl'] = ''
            v['status'] = ''
            v['year'] = ''
            v['desc'] = ''
            v['cast'] = ''
            uni.append(v)
    return uni


def extract_stream(vid):
    global sess, last_refresh
    if time.time() - last_refresh > 120:
        sess = new_session()
        last_refresh = time.time()
    try:
        r = sess.get(f'{BASE}/video/{vid}-2-1.html', headers=H_TPL, timeout=10)
        if r.status_code == 404:
            r = sess.get(f'{BASE}/video/{vid}-1-1.html', headers=H_TPL, timeout=10)
        if r.status_code != 200:
            return None
        m = re.search(r'"url":"([^"]+\.m3u8[^"]*?)"', r.text)
        if m:
            src = m.group(1).replace('\\/', '/')
            if not src.startswith('http'):
                src = 'https://' + src.lstrip('/')
            return src
    except Exception:
        return None
    return None


def load_existing():
    try:
        return {v['id']: v for v in json.load(open(OUT, encoding='utf-8')).get('videos', [])}
    except Exception:
        return {}


def save(all_v):
    out = {'source': BASE, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
           'videos': list(all_v.values())}
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    return len(out['videos'])


def run_list():
    all_v = load_existing()
    for slug, cat_id, subcat in SUBS:
        uni = scrape_sub(slug, cat_id, subcat)
        added = 0
        for v in uni:
            if v['id'] not in all_v:
                all_v[v['id']] = v
                added += 1
        print(f'  [{cat_id}] {subcat}: +{added} 条')
    total = save(all_v)
    print(f'[{LABEL}] 列表完成, 总计 {total} 条 -> {OUT}')


def run_stream():
    try:
        data = json.load(open(OUT, encoding='utf-8'))
    except Exception as e:
        print(f'[{LABEL}] 读取 {OUT} 失败: {e}'); return
    videos = data['videos']
    tasks = [(v['id'], i) for i, v in enumerate(videos) if not v.get('streamUrl')]
    need = len(tasks)
    print(f'[{LABEL}] 抓流: 总量 {len(videos)} 需抓 {need}')
    done = 0
    for i in range(0, need, 300):
        batch = tasks[i:i + 300]
        with ThreadPoolExecutor(15) as ex:
            def p(item):
                vid, idx = item
                s = extract_stream(vid)
                if s:
                    videos[idx]['streamUrl'] = s
            list(ex.map(p, batch))
        done += len(batch)
        if (i // 300) % 5 == 0:
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    n = sum(1 for v in videos if v.get('streamUrl'))
    print(f'[{LABEL}] 抓流完成: 有流 {n}/{len(videos)}')


def smoke(n=10):
    print(f'>>> [{LABEL}] 冒烟测试 前 {n} 条 {datetime.now():%H:%M:%S}')
    slug, cat_id, subcat = SUBS[0]
    uni = scrape_sub(slug, cat_id, subcat)
    print(f'    列表连通: {len(uni)>0} | 首类解析 {len(uni)} 条')
    sample = uni[:n]
    rows = []
    for v in sample:
        s = extract_stream(v['id'])
        rows.append({'id': v['id'], 'title': v['title'], 'poster': bool(v['poster']),
                     'stream': (s or '')[:80]})
        print(f'    {v["id"]} {v["title"][:20]!r} 海报={bool(v["poster"])} 流={"有" if s else "无"}')
    report = {'source': BASE, 'mode': 'smoke', 'n': n,
              'connectivity': len(uni) > 0, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
              'sample': rows}
    json.dump(report, open(SMOKE, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'>>> [{LABEL}] 冒烟报告 -> {SMOKE}')


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else 'all').lower()
    if mode == 'list':
        run_list()
    elif mode == 'stream':
        run_stream()
    elif mode.startswith('smoke'):
        n = 10
        if ':' in mode:
            try:
                n = int(mode.split(':', 1)[1])
            except Exception:
                pass
        smoke(n)
    elif mode == 'all':
        print(f'>>> [{LABEL}] 完整管线启动 {datetime.now():%H:%M:%S}')
        run_list()
        run_stream()
        print(f'>>> [{LABEL}] 完整管线结束 {datetime.now():%H:%M:%S}')
    else:
        print('用法: python crawl_12ju.py [all|list|stream|smoke:N]')
        sys.exit(1)


if __name__ == '__main__':
    main()
