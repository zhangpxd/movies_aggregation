"""通用 MacCMS 三源并行元数据抓取 — 多线程详情版"""
import json, re, time, sys, requests, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try: import urllib3; urllib3.disable_warnings()
except: pass
sys.stdout.reconfigure(line_buffering=True)

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
     'Accept': 'text/html', 'Accept-Language': 'zh-CN,zh;q=0.9'}

DELAY = 1.0
CATS = [(1, 'movie', '电影'), (2, 'tv', '电视剧')]
SKIP_TV = True  # 电影详情完成后不爬电视剧(用户要求先去抓流地址)
DETAIL_WORKERS_PER_SOURCE = 3  # 每源独立详情线程池(三源×3≈9并发,分属不同域名安全,互不饥饿)

# 全局限流冷却:一旦任一线程命中 444/429,所有线程一起暂停 PAUSE_SEC 秒
rl_lock = threading.Lock()
rate_limit_until = 0.0
PAUSE_SEC = 60  # 触发预警/444 后必须暂停的秒数


def fetch(url):
    global rate_limit_until
    for attempt in range(2):  # 冷却后最多重试一次
        # 全局冷却等待:若处于暂停期,所有线程一起等
        while True:
            now = time.time()
            with rl_lock:
                wait = rate_limit_until - now
            if wait <= 0:
                break
            time.sleep(min(wait, 5))
        time.sleep(DELAY)
        try:
            r = requests.get(url, headers=H, timeout=20, verify=False)
            if r.status_code == 200 and len(r.text) > 500:
                return r.text
            if r.status_code in (444, 429):
                print(f'  ⚠ {r.status_code} 限流预警, 全局暂停 {PAUSE_SEC} 秒...')
                with rl_lock:
                    rate_limit_until = max(rate_limit_until, time.time() + PAUSE_SEC)
                time.sleep(PAUSE_SEC)
                continue  # 冷却结束后重试一次
        except Exception:
            pass
        return None
    return None


def parse_list(html):
    results = []
    items = re.findall(r'<a[^>]*stui-vodlist__thumb[^>]*href="/voddetail/(\d+).html"[^>]*title="([^"]+)"', html)
    seen = set()
    for vid, title in items:
        if vid not in seen:
            seen.add(vid)
            results.append({'id': vid, 'title': title, 'url': '', 'poster': '', 'note': '', 'subcat': ''})
    return results


def parse_detail(html, info):
    info = dict(info)
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
    # 根因修复: 补全海报(poster)与子类(subcat)
    # 之前 parse_detail 只抓年份/地区/导演/简介, 漏抓这两个字段,
    # 导致 MacCMS 三源(555/龙腾/大象)在前端无海报、且按子类(动作/喜剧)筛选时匹配不到。
    m = re.search(r'data-original="([^"]+\.(?:jpg|jpeg|png|webp))"', html, re.I)
    if m:
        info['poster'] = m.group(1).strip()
    m = re.search(r'类型[：:]</span>\s*<a[^>]*>([^<]+)</a>', html)
    if m:
        info['subcat'] = m.group(1).strip()
    return info


def run_source(name, label, base_url, workers=DETAIL_WORKERS_PER_SOURCE):
    OUTPUT = f'data/{name}.json'
    print(f'[{label}] 启动 {datetime.now().strftime("%H:%M:%S")}')

    all_v = {}
    try:
        with open(OUTPUT, 'r', encoding='utf-8') as f:
            for v in json.load(f).get('videos', []):
                all_v[v['id']] = v
        print(f'[{label}] 已有 {len(all_v)} 条')
    except Exception:
        pass

    existing = set(all_v.keys())
    v_lock = threading.Lock()
    t0 = time.time()

    run_cats = [c for c in CATS if not (SKIP_TV and c[1] == 'tv')]
    for tid, cat_k, cat_n in run_cats:
        cp_file = f'data/{name}_{cat_k}_cp.json'
        list_items = []
        start_page = 1

        try:
            with open(cp_file, 'r', encoding='utf-8') as f:
                cp = json.load(f)
            list_items = cp.get('items', [])
            start_page = cp.get('next_page', 1)
            for it in list_items:
                existing.add(it['id'])
            print(f'[{label}] {cat_n}断点 {len(list_items)}ID,从页{start_page}')
        except Exception:
            pass

        # 探测总页数
        html = fetch(f'{base_url}/vodshow/{tid}-----------.html')
        max_page = 1
        if html:
            last_m = re.search(r'(\d+)---\.html\">尾页</a>', html)
            if last_m:
                max_page = int(last_m.group(1))
            else:
                pages = re.findall(rf'{tid}--------(\d+)---.html', html)
                max_page = max(int(p) for p in pages if p.isdigit()) if pages else 1
        print(f'[{label}] {cat_n} 总{max_page}页, 从{start_page}开始')

        for page in range(start_page, max_page + 1):
            html = fetch(f'{base_url}/vodshow/{tid}--------{page}---.html')
            if html:
                items = parse_list(html)
                new = [it for it in items if it['id'] not in existing]
                list_items.extend(new)
                for it in items:
                    existing.add(it['id'])
            if page % 100 == 0:
                print(f'[{label}] {cat_n} {page}/{max_page} {len(list_items)}ID')
                with open(cp_file, 'w', encoding='utf-8') as f:
                    json.dump({'next_page': page, 'items': list_items,
                               'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False)

        with open(cp_file, 'w', encoding='utf-8') as f:
            json.dump({'next_page': max_page, 'items': list_items,
                       'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False)

        print(f'[{label}] {cat_n}列表完: {len(list_items)}ID')
        if not list_items:
            continue

        need = len(list_items)
        done = 0
        done_lock = threading.Lock()

        def do_detail(it, nm=name, src=base_url, ck=cat_k):
            vid = it['id']
            with v_lock:
                if vid in all_v and all_v[vid].get('desc'):
                    return
            url = it['url'] or f'{src}/voddetail/{it["id"]}.html'
            html = fetch(url)
            if html:
                d = parse_detail(html, it)
                d['source'] = nm
                d['category'] = ck
                if 'url' not in d or not d['url']:
                    d['url'] = url
                with v_lock:
                    all_v[d['id']] = d

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(do_detail, it) for it in list_items]
            for fu in as_completed(futs):
                fu.result()
                with done_lock:
                    done += 1
                    if done % 100 == 0:
                        e = time.time() - t0
                        rate = done / e if e > 0 else 0
                        eta = (need - done) / rate if rate > 0 else 0
                        print(f'[{label}] 详情 {done}/{need} {rate:.1f}/s 剩{eta/60:.0f}分 {datetime.now().strftime("%H:%M:%S")}')
                        with v_lock, open(OUTPUT, 'w', encoding='utf-8') as f:
                            json.dump({'source': base_url, 'videos': list(all_v.values()),
                                       'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False)

        with v_lock, open(OUTPUT, 'w', encoding='utf-8') as f:
            json.dump({'source': base_url, 'videos': list(all_v.values()),
                       'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False)
        print(f'[{label}] {cat_n}详情完成 {len(all_v)}条')

    print(f'[{label}] ✅ {len(all_v)}条 耗时{int((time.time()-t0)/60)}分')


if __name__ == '__main__':
    # (name, label, base_url, 详情线程数) — 大象/555 服务端软限流,提线程数填空档;龙腾已快,保持3
    sources = [
        ('szbwzl', '大象', 'https://m.szbwzl.com', 6),
        ('pbmkjx', '555', 'https://pbmkjx.com', 6),
        ('whyungu', '龙腾', 'https://www.whyungu.com', 3),
    ]
    print(f'三源并行启动(每源详情线程={[s[3] for s in sources]}) {datetime.now().strftime("%H:%M:%S")}')
    with ThreadPoolExecutor(3) as ex:
        for n, l, b, w in sources:
            ex.submit(run_source, n, l, b, w)
    print(f'\n全部完成 {datetime.now().strftime("%H:%M:%S")}')
