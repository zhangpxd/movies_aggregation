"""crawl_xfej.py —— 葡萄影视(xfej.net) 整合抓取脚本(单文件产出)。

把原来分散的 xfej_scraper.py(列表) + xfej_stream_scraper.py(抓流) 整合为一个入口,
最终只保留一份可用主文件 data/xfej.json(含列表/海报/分类/流地址等)。

用法:
  python crawl_xfej.py all       # 列表 -> 抓流 -> 写单文件 data/xfej.json
  python crawl_xfej.py list      # 仅列表
  python crawl_xfej.py stream    # 仅补抓缺失流地址
  python crawl_xfej.py smoke:10  # 冒烟: 前 10 条验证连通+字段, 写 data/xfej_smoke.json(不改生产)
"""
import os, sys, json, re, time, requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

NAME = 'xfej'
LABEL = '葡萄影视'
BASE = 'https://xfej.net'
OUT = 'data/xfej.json'
SMOKE = 'data/xfej_smoke.json'

H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Referer': BASE + '/',
}
DELAY = 0.2
sess = requests.Session()

# (type_id, 主分类, 子分类名) —— 取自原 xfej_scraper.py 的 SUBS
SUBS = [
    (6, 'movie', '动作'), (7, 'movie', '喜剧'), (8, 'movie', '爱情'),
    (9, 'movie', '科幻'), (10, 'movie', '恐怖'), (11, 'movie', '剧情'),
    (12, 'movie', '战争'), (20, 'movie', '论理'), (21, 'movie', '其他'),
    (25, 'movie', '动漫电影'),
    (13, 'tv', '国产剧'), (14, 'tv', '港台剧'), (15, 'tv', '日韩剧'), (16, 'tv', '欧美剧'),
]


def parse_list(html):
    vids = []
    for m in re.finditer(r'<a\s[^>]*?href="/spd/(\d+)\.html"[^>]*?title="([^"]+)"[^>]*?>', html):
        pm = re.search(r'data-original="([^"]+)"', m.group(0))
        if pm:
            vids.append({
                'id': int(m.group(1)),
                'title': m.group(2).strip(),
                'url': BASE + '/spd/' + m.group(1) + '.html',
                'poster': pm.group(1),
            })
    return vids


def scrape_sub(slug, cat_id, subcat, max_pages=50):
    vids = []
    try:
        r = sess.get(f'{BASE}/sptype/{slug}.html', headers=H, timeout=20)
        r.encoding = 'utf-8'
    except Exception:
        return vids
    if r.status_code != 200:
        return vids
    last = re.search(rf'/sptype/{slug}-(\d+)\.html[^>]*>尾页', r.text)
    tp = int(last.group(1)) if last else 1
    MAX_PAGES = min(tp, max_pages)
    vids = parse_list(r.text)
    if MAX_PAGES > 1:
        pages = list(range(2, MAX_PAGES + 1))
        for i in range(0, len(pages), 3):
            batch = pages[i:i + 3]
            with ThreadPoolExecutor(3) as ex:
                def fp(p):
                    try:
                        r2 = sess.get(f'{BASE}/sptype/{slug}-{p}.html', headers=H, timeout=20)
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
        r = requests.get(f'{BASE}/spplay/{vid}-1-1.html', headers=H, timeout=10)
        m = re.search(r'"url":"([^"]+?\.m3u8[^"]*?)"', r.text)
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
    done = 0; t0 = time.time()
    for i in range(0, need, 300):
        batch = tasks[i:i + 300]
        with ThreadPoolExecutor(10) as ex:
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
        print('用法: python crawl_xfej.py [all|list|stream|smoke:N]')
        sys.exit(1)


if __name__ == '__main__':
    main()
