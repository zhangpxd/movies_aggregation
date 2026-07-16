"""通用 MacCMS 元数据抓取(多源并行) — 多线程详情版"""
import json, os, re, time, sys, requests, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_common as cc
NEWEST_FIRST = True  # MacCMS 列表按更新时间倒序(新内容在顶部), 可安全"整页已知即停页"

try: import urllib3; urllib3.disable_warnings()
except: pass
sys.stdout.reconfigure(line_buffering=True)

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
     'Accept': 'text/html', 'Accept-Language': 'zh-CN,zh;q=0.9'}

DELAY = 1.0
CATS = [(1, 'movie', '电影'), (2, 'tv', '电视剧')]
SKIP_TV = True  # 电影详情完成后不爬电视剧(用户要求先去抓流地址)
DETAIL_WORKERS_PER_SOURCE = 3  # 每源独立详情线程池(分属不同域名安全,互不饥饿)

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
    # 导致 MacCMS 源(555/龙腾)在前端无海报、且按子类(动作/喜剧)筛选时匹配不到。
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
                if NEWEST_FIRST and not new:
                    print(f'[{label}] {cat_n} 第{page}页无新条目, 增量停页')
                    break
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


def _is_empty(val):
    """判断是否为"应保留原值"的空值。"""
    return val is None or val == '' or val == [] or val == {}

def merge_item(old, new):
    """增量 upsert 合并: new 的空值(None/''/[]/{})不会覆盖 old 的非空值,
    避免补全流地址/海报时把已有元数据(如 year)抹成空。"""
    for k, val in new.items():
        if _is_empty(val) and k in old and not _is_empty(old[k]):
            continue
        old[k] = val
    return old

def run_test(name, label, base_url, n=20, delay=5, output=None):
    """测试模式: 单线程逐条抓完整内容(列表+详情+流), 只抓前n条, 增量续抓。
    已知且流地址新鲜的条目跳过抓流, 只抓新/缺流/超期条目。
    """
    from fetch_streams import get_streams_for
    OUTPUT = output or f'data/{name}.json'
    print(f'>>> [{label}] TEST 单线程: 每条间隔约{delay}s, 抓前{n}条, 增量upsert进 {OUTPUT}')
    videos = []
    if os.path.exists(OUTPUT):
        try:
            videos = json.load(open(OUTPUT, encoding='utf-8')).get('videos', [])
            print(f'[{label}] 现有主文件 {len(videos)} 条')
        except Exception as e:
            print(f'[{label}] 读主文件失败: {e}, 从头开始')
            videos = []
    id2v = {v['id']: v for v in videos}
    state = cc.load_state(videos=videos)
    html = fetch(f'{base_url}/vodshow/1-----------.html')
    items = parse_list(html) if html else []
    sample = items[:n]
    print(f'[{label}] 列表解析 {len(items)} 条, 取前 {len(sample)} 条测试')
    done = 0
    for it in sample:
        vid = it['id']
        url = it.get('url') or f'{base_url}/voddetail/{vid}.html'
        existing = id2v.get(vid)
        if existing is not None:
            merge_item(existing, {'id': vid, 'title': it.get('title', ''), 'url': url,
                                  'poster': '', 'year': '', 'subcat': '', 'category': 'movie',
                                  'region': '', 'cast': '', 'desc': '', 'source': name,
                                  'streams': [], 'streamUrl': ''})
        else:
            videos.append({'id': vid, 'title': it.get('title', ''), 'url': url, 'poster': '',
                           'year': '', 'subcat': '', 'category': 'movie', 'region': '',
                           'cast': '', 'desc': '', 'source': name, 'streams': [], 'streamUrl': ''})
            id2v[vid] = videos[-1]
            existing = id2v[vid]
        if cc.need_detail(vid, existing, state):
            dh = fetch(url)
            info = parse_detail(dh, it) if dh else {}
            streams = get_streams_for(url) if dh else []
            first = (streams[0]['url'] if streams and isinstance(streams[0], dict) else '') or ''
            v = {
                'id': vid,
                'title': info.get('title', it.get('title', '')),
                'url': url,
                'poster': info.get('poster', ''),
                'year': info.get('year', ''),
                'subcat': info.get('subcat', ''),
                'category': 'movie',
                'region': info.get('region', ''),
                'cast': info.get('cast', ''),
                'desc': info.get('desc', ''),
                'source': name,
                'streams': streams,
                'streamUrl': first,
            }
            merge_item(existing, v)
            cc.mark_verified(state, vid)
            tag = '抓流'
        else:
            tag = '跳过(已知+流新鲜)'
        done += 1
        print(f'    [{label}] {done}/{n} #{vid} {existing.get("title","")[:20]!r} 流={"有" if existing.get("streamUrl") else "无"} [{tag}] 主文件={len(videos)}条')
        if done % 10 == 0:
            _write_main(OUTPUT, name, base_url, videos)
            cc.save_state(state)
            print(f'    [{label}] 💾 存盘 {done} 条 (主文件 {len(videos)} 条)')
        time.sleep(delay)
    _write_main(OUTPUT, name, base_url, videos)
    cc.save_state(state)
    print(f'>>> [{label}] TEST 完成: 抓取{done}条, 主文件现有 {len(videos)} 条')


def _write_main(OUTPUT, name, base_url, videos):
    """原子写主文件: 先写 .tmp 再 os.replace, 避免写到一半崩溃损坏。
    注意: 不在此更新 versions.json(多源并发写同文件有覆盖风险), 由各源 test 跑完后统一刷新。"""
    tmp = OUTPUT + '.tmp'
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump({'source': base_url, 'videos': videos, 'updated_at': now},
              open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(tmp, OUTPUT)


if __name__ == '__main__':
    # (name, label, base_url, 详情线程数) — 555 服务端软限流,提线程数填空档;龙腾已快,保持3
    # 注意: 大象(szbwzl)/草民(sychuojia) 已下架, 不再抓取; 正确入口请用 crawl_pbmkjx.py / crawl_whyungu.py
    sources = [
        ('pbmkjx', '555', 'https://pbmkjx.com', 6),
        ('whyungu', '龙腾', 'https://www.whyungu.com', 3),
    ]
    print(f'两源并行启动(每源详情线程={[s[3] for s in sources]}) {datetime.now().strftime("%H:%M:%S")}')
    with ThreadPoolExecutor(3) as ex:
        for n, l, b, w in sources:
            ex.submit(run_source, n, l, b, w)
    print(f'\n全部完成 {datetime.now().strftime("%H:%M:%S")}')
