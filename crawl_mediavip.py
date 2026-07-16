"""crawl_mediavip.py —— 免VIP电影网(mediavip.cn) 整合抓取脚本(单文件产出)。

把原来分散的 full_scraper.py(列表) + mediavip_stream_scraper.py(抓流) 整合为一个入口,
最终只保留一份可用主文件 data/full_videos.json(含列表/海报/分类/流地址等)。

注: 按用户要求"缺失字段暂不补", 本脚本做 列表+抓流 两级;
    year/desc/cast/status 字段保留在 schema 中(置空), 如需补全可后续接入 scraper.py 的详情逻辑。

用法:
  python crawl_mediavip.py all       # 列表 -> 抓流 -> 写单文件 data/full_videos.json
  python crawl_mediavip.py list      # 仅列表
  python crawl_mediavip.py stream    # 仅补抓缺失流地址
  python crawl_mediavip.py smoke:10  # 冒烟: 前 10 条验证连通+字段, 写 data/full_videos_smoke.json(不改生产)
"""
import os, sys, json, re, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl_common as cc
NEWEST_FIRST = True  # MacCMS 列表按更新时间倒序(新内容在顶部), 可安全"整页已知即停页"

NAME = 'mediavip'
LABEL = '免VIP电影网'
BASE = 'https://www.mediavip.cn'
OUT = 'data/full_videos.json'
SMOKE = 'data/full_videos_smoke.json'

H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Referer': BASE + '/',
}
DELAY = 0.3
sess = requests.Session()

# (slug, 主分类, 子分类名) —— 取自原 full_scraper.py 的 CATS 映射
SUBS = [
    ('shaoshi', 'movie', '邵氏电影'), ('lilun', 'movie', '理论电影'),
    ('dongzuo', 'movie', '动作'), ('aiqing', 'movie', '爱情'),
    ('xiju', 'movie', '喜剧'), ('kongbu', 'movie', '恐怖'),
    ('jings', 'movie', '惊悚'), ('xuanyi', 'movie', '悬疑'),
    ('fanzui', 'movie', '犯罪'), ('juqing', 'movie', '剧情'),
    ('zhanzheng', 'movie', '战争'), ('zainan', 'movie', '灾难'),
    ('kehuan', 'movie', '科幻'), ('qihuan', 'movie', '奇幻'),
    ('maoxian', 'movie', '冒险'), ('jilu', 'movie', '纪录'),
    ('qita', 'movie', '其他'),
    ('guochanju', 'tv', '国产剧'), ('gangtaiju', 'tv', '港台剧'),
    ('hanguoju', 'tv', '韩国剧'), ('ribenju', 'tv', '日本剧'),
    ('oumeiju', 'tv', '欧美剧'), ('taiguoju', 'tv', '泰国剧'),
    ('duanju', 'tv', '短剧'), ('qitaju', 'tv', '其他剧'),
]


def parse_list(html):
    vids = []
    for m in re.finditer(r'<a\s[^>]*?href="(/mvip/(\d+)/)"[^>]*?title="([^"]+)"[^>]*?>', html):
        pm = re.search(r'data-original="([^"]+)"', m.group(0))
        if pm:
            vids.append({
                'id': int(m.group(2)),
                'title': m.group(3).strip(),
                'url': BASE + m.group(1),
                'poster': pm.group(1),
            })
    return vids


def scrape_sub(slug, cat_id, subcat, max_pages=50, known_ids=None, stop_if_known=False):
    vids = []
    try:
        r = sess.get(f'{BASE}/hgft/{slug}/', headers=H, timeout=20)
        r.encoding = 'utf-8'
    except Exception:
        return vids
    if r.status_code != 200 or '/mvip/' not in r.text:
        return vids
    last = re.search(rf'/{slug}-(\d+)/[^>]*>尾页', r.text)
    tp = int(last.group(1)) if last else 1
    MAX_PAGES = min(tp, max_pages)
    vids = parse_list(r.text)
    if stop_if_known and known_ids is not None and vids and all(v['id'] in known_ids for v in vids):
        print(f'    [{cat_id}] 首页全部已知, 增量停页')
        MAX_PAGES = 1
    if MAX_PAGES > 1:
        pages = list(range(2, MAX_PAGES + 1))
        for i in range(0, len(pages), 3):
            batch = pages[i:i + 3]
            with ThreadPoolExecutor(3) as ex:
                def fp(p):
                    try:
                        r2 = sess.get(f'{BASE}/hgft/{slug}-{p}/', headers=H, timeout=20)
                        r2.encoding = 'utf-8'
                        return parse_list(r2.text) if r2.status_code == 200 else []
                    except Exception:
                        return []
                for res in ex.map(fp, batch):
                    vids.extend(res)
            time.sleep(0.2)
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
        r = requests.get(f'{BASE}/splay/{vid}-1-1/', headers=H, timeout=10)
        m = re.search(r'videoSrc\s*=\s*"([^"]+)"', r.text)
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
    out = {
        'source': BASE,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'videos': list(all_v.values()),
    }
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    return len(out['videos'])


def run_list():
    all_v = load_existing()
    known = set(all_v.keys())
    for slug, cat_id, subcat in SUBS:
        uni = scrape_sub(slug, cat_id, subcat, known_ids=known, stop_if_known=NEWEST_FIRST)
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
    state = cc.load_state(videos=videos)
    tasks = [(v['id'], i) for i, v in enumerate(videos) if cc.need_detail(v['id'], v, state)]
    need = len(tasks)
    print(f'[{LABEL}] 抓流: 总量 {len(videos)} 需抓(新/缺流/超期){need}')
    done = 0; t0 = time.time()
    for i in range(0, need, 300):
        batch = tasks[i:i + 300]
        with ThreadPoolExecutor(15) as ex:
            def p(item):
                vid, idx = item
                s = extract_stream(vid)
                if s:
                    videos[idx]['streamUrl'] = s
                    cc.mark_verified(state, vid)
            list(ex.map(p, batch))
        done += len(batch)
        if (i // 300) % 10 == 0:
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
            cc.save_state(state)
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    cc.save_state(state)
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


def _is_empty(val):
    return val is None or val == '' or val == [] or val == {}

def merge_item(old, new):
    """增量 upsert 合并: new 的空值不覆盖 old 的非空值, 避免补全时抹掉已有元数据(year等)。"""
    for k, val in new.items():
        if _is_empty(val) and k in old and not _is_empty(old[k]):
            continue
        old[k] = val
    return old

def run_test(n=20, delay=5):
    """测试模式: 单线程, 只抓首类前n条; 增量续抓——已知且流地址新鲜的条目跳过抓流, 只抓新/缺流/超期条目。"""
    import os
    print(f'>>> [{LABEL}] TEST 单线程: 每条约{delay}s, 抓前{n}条, 增量upsert进 {OUT}')
    videos = []
    if os.path.exists(OUT):
        try:
            videos = json.load(open(OUT, encoding='utf-8')).get('videos', [])
        except Exception:
            videos = []
    id2v = {v['id']: v for v in videos}
    state = cc.load_state(videos=videos)
    slug, cat_id, subcat = SUBS[0]
    uni = scrape_sub(slug, cat_id, subcat, max_pages=1)
    sample = uni[:n]
    print(f'[{LABEL}] 首类解析 {len(uni)} 条, 取前 {len(sample)} 条')
    done = 0
    for v in sample:
        vid = v['id']
        existing = id2v.get(vid)
        if existing is not None:
            merge_item(existing, v)          # 合并列表元数据(空值不覆盖非空)
        else:
            videos.append(v)
            id2v[vid] = v
            existing = v
        if cc.need_detail(vid, existing, state):
            s = extract_stream(vid)
            if s:
                existing['streamUrl'] = s
            cc.mark_verified(state, vid)
            tag = '抓流'
        else:
            tag = '跳过(已知+流新鲜)'
        done += 1
        print(f'    [{LABEL}] {done}/{n} #{vid} {existing.get("title","")[:20]!r} 流={"有" if existing.get("streamUrl") else "无"} [{tag}] 主文件={len(videos)}条')
        if done % 10 == 0:
            _save_test(videos)
            cc.save_state(state)
            print(f'    [{LABEL}] 💾 存盘 {done} 条')
        time.sleep(delay)
    _save_test(videos)
    cc.save_state(state)
    print(f'>>> [{LABEL}] TEST 完成: 抓取{done}条, 主文件现有 {len(videos)}条')


def _save_test(videos):
    import os
    out = {'source': BASE, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'videos': videos}
    tmp = OUT + '.tmp'
    json.dump(out, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(tmp, OUT)


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
    elif mode.startswith('test'):
        n = 20
        if ':' in mode:
            try:
                n = int(mode.split(':', 1)[1])
            except Exception:
                pass
        run_test(n=n, delay=5)
    elif mode == 'all':
        print(f'>>> [{LABEL}] 完整管线启动 {datetime.now():%H:%M:%S}')
        run_list()
        run_stream()
        print(f'>>> [{LABEL}] 完整管线结束 {datetime.now():%H:%M:%S}')
    else:
        print('用法: python crawl_mediavip.py [all|list|stream|smoke:N]')
        sys.exit(1)


if __name__ == '__main__':
    main()
