"""crawl_jieshui8.py —— 片多多(m.jieshui8.com) 整合抓取脚本(单文件产出)。

把原来分散的 jieshui8_scraper.py(列表) + jieshui8_stream_scraper.py(抓流) 整合为一个入口,
最终只保留一份可用主文件 data/jieshui8.json(含列表/海报/分类/流地址等)。

用法:
  python crawl_jieshui8.py all       # 列表 -> 抓流 -> 写单文件 data/jieshui8.json
  python crawl_jieshui8.py list      # 仅列表
  python crawl_jieshui8.py stream    # 仅补抓缺失流地址
  python crawl_jieshui8.py smoke:10  # 冒烟: 前 10 条验证连通+字段, 写 data/jieshui8_smoke.json(不改生产)
"""
import os, sys, json, re, time, requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

NAME = 'jieshui8'
LABEL = '片多多'
BASE = 'https://m.jieshui8.com'
OUT = 'data/jieshui8.json'
SMOKE = 'data/jieshui8_smoke.json'

H = {
    'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html',
    'Accept-Language': 'zh-CN', 'Accept-Encoding': 'gzip, deflate',
    'Referer': BASE + '/',
}
DELAY = 0.15
sess = requests.Session()

# (type_id, 主分类, 子分类名) —— 取自原 jieshui8_scraper.py 的 SUBS
SUBS = [
    (6, 'movie', '动作'), (7, 'movie', '喜剧'), (8, 'movie', '爱情'),
    (9, 'movie', '科幻'), (10, 'movie', '恐怖'), (11, 'movie', '剧情'),
    (13, 'tv', '国产剧'), (14, 'tv', '香港剧'), (15, 'tv', '台湾剧'),
    (16, 'tv', '日本剧'), (20, 'tv', '泰国剧'), (21, 'tv', '韩国剧'),
]


def parse_list(html):
    titles = {}
    for m in re.finditer(
        r'<p class="video-name"><a[^>]*?href="/voddetail/(\d+)\.html"[^>]*title="([^"]+)"[^>]*>', html):
        titles[int(m.group(1))] = m.group(2).strip()
    vids = []
    for m in re.finditer(
        r'<a class="video-img lazyload" href="/voddetail/(\d+)\.html"[^>]*?data-original="([^"]+)"', html):
        vid = int(m.group(1))
        title = titles.get(vid, '')
        if title and len(title) > 1:
            vids.append({'id': vid, 'title': title,
                         'url': BASE + '/voddetail/' + m.group(1) + '.html',
                         'poster': m.group(2)})
    return vids


def scrape_sub(slug, cat_id, subcat, max_pages=50):
    vids = []
    try:
        r = sess.get(f'{BASE}/vodtype/{slug}.html', headers=H, timeout=20)
        r.encoding = 'utf-8'
    except Exception:
        return vids
    if r.status_code != 200:
        return vids
    pages = re.findall(rf'/vodtype/{slug}-(\d+)\.html', r.text)
    tp = max(int(p) for p in pages) if pages else 1
    MAX_PAGES = min(tp, max_pages)
    vids = parse_list(r.text)
    if MAX_PAGES > 1:
        plist = list(range(2, MAX_PAGES + 1))
        for i in range(0, len(plist), 3):
            batch = plist[i:i + 3]
            with ThreadPoolExecutor(3) as ex:
                def fp(p):
                    try:
                        r2 = sess.get(f'{BASE}/vodtype/{slug}-{p}.html', headers=H, timeout=20)
                        r2.encoding = 'utf-8'
                        return parse_list(r2.text) if r2.status_code == 200 else []
                    except Exception:
                        return []
                for res in ex.map(fp, batch):
                    vids.extend(res)
            time.sleep(0.15)
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
    try:
        r = requests.get(f'{BASE}/vodplay/{vid}-1-1.html', headers=H, timeout=10)
        m = re.search(r'var player_\w+\s*=\s*\{[^}]*"url":"([^"]+\.m3u8[^"]*)"', r.text)
        if m:
            src = m.group(1).replace('\\/', '/')
            if not src.startswith('http'):
                src = 'https://' + src.lstrip('/')
            return src
    except Exception:
        pass
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
        time.sleep(DELAY)
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
        if (i // 300) % 10 == 0:
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
        print('用法: python crawl_jieshui8.py [all|list|stream|smoke:N]')
        sys.exit(1)


if __name__ == '__main__':
    main()
