"""流地址(m3u8/mp4)抓取脚本 — 预创建版
读取已爬详情的 JSON(pbmkjx/whyungu), 为【电影】条目抓取播放流地址。

设计要点:
- 复用详情页 + 播放页解析, 支持 MacCMS 两种 player 配置:
  * encrypt=0 -> url 为明文 m3u8(仅把 '\\/' 还原为 '/')
  * encrypt=2 -> url 为 base64(百分号编码后的 m3u8), 解密: unquote(b64decode(url))
- 断点续跑: {name}_streams_cp.json 记录已抓取 id -> [streams], 重跑跳过已完成。
- 限流: MacCMS 源用线程池(默认6) + 全局444冷却。
- 只处理 category=='movie'(跳过电视剧, 符合"先不跑电视剧")。
- 输出: 检查点 {name}_streams_cp.json + 结束后写 {name}_streams.json(合并完整数据, 供查看/后续并入主JSON)。
  * 不改动正在被详情爬虫写入的 {name}.json, 避免并发写冲突。

用法(各源可分离启动, 互不阻塞):
  D:/Python313/python.exe fetch_streams.py            # 全部4源(默认, 串行)
  D:/Python313/python.exe fetch_streams.py mac        # 仅 MacCMS 源(pbmkjx/whyungu)
  D:/Python313/python.exe fetch_streams.py pbmkjx whyungu   # 显式指定若干源
(电影详情跑完后运行; 可反复运行, 自动续跑。)
"""
import json, re, time, sys, os, random, requests, threading, base64, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass
sys.stdout.reconfigure(line_buffering=True)

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
     'Accept': 'text/html', 'Accept-Language': 'zh-CN,zh;q=0.9'}
UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

DELAY = 1.0
JITTER = 1.0  # 用户选择C: 随机抖动上限(秒), 打乱请求节奏分散限流识别
PAUSE_SEC = 60
rl_lock = threading.Lock()
rate_limit_until = 0.0  # 模块级, 每个源启动时重置, 互不干扰


def fetch(url):
    global rate_limit_until
    for attempt in range(2):
        while True:
            now = time.time()
            with rl_lock:
                wait = rate_limit_until - now
            if wait <= 0:
                break
            time.sleep(min(wait, 5))
        time.sleep(DELAY + random.uniform(0, JITTER))
        try:
            h = dict(H)
            h['User-Agent'] = random.choice(UA_POOL)
            r = requests.get(url, headers=h, timeout=20, verify=False)
            if r.status_code == 200 and len(r.text) > 200:
                return r.text
            if r.status_code in (444, 429):
                print(f'  ⚠ {r.status_code} 限流, 全局暂停 {PAUSE_SEC}s')
                with rl_lock:
                    rate_limit_until = max(rate_limit_until, time.time() + PAUSE_SEC)
                time.sleep(PAUSE_SEC)
                continue
        except Exception:
            pass
        return None
    return None


def decode_url(val, encrypt):
    if encrypt == 0:
        return val.replace('\\/', '/')
    if encrypt == 2:
        try:
            return urllib.parse.unquote(base64.b64decode(val).decode('utf-8', 'ignore')).replace('\\/', '/')
        except Exception:
            return ''
    return val


def extract_player(html):
    m = re.search(r'var\s+(player_[A-Za-z0-9_]+|player_data|mac_player)\s*=\s*(\{.*?\})', html, re.DOTALL)
    if not m:
        return None
    cfg = m.group(2)
    um = re.search(r'"url"\s*:\s*"([^"]*)"', cfg)
    em = re.search(r'"encrypt"\s*:\s*(\d+)', cfg)
    fm = re.search(r'"from"\s*:\s*"([^"]*)"', cfg)
    return (um.group(1) if um else '', int(em.group(1)) if em else 0, fm.group(1) if fm else '')


def get_streams_for(detail_url):
    h = fetch(detail_url)
    if not h:
        return []
    links = re.findall(r'href="([^"]*(?:vodplay|vddp|vod/play)[^"]*)"', h)
    streams = []
    seen = set()
    for ln in links:
        if ln.startswith('/'):
            u = urllib.parse.urlparse(detail_url)
            ln = f'{u.scheme}://{u.netloc}{ln}'
        if ln in seen:
            continue
        seen.add(ln)
        ph = fetch(ln)
        if not ph:
            continue
        p = extract_player(ph)
        if p and p[0]:
            url = decode_url(p[0], p[1])
            if url and url not in [s['url'] for s in streams]:
                streams.append({'url': url, 'from': p[2], 'encrypt': p[1]})
    return streams


def run_source(name, label, workers):
    global rate_limit_until
    rate_limit_until = 0.0  # 每个源独立冷却
    SRC = f'data/{name}.json'
    CP = f'data/{name}_streams_cp.json'
    OUT = f'data/{name}_streams.json'
    print(f'[{label}] 启动流地址抓取 {datetime.now():%H:%M:%S}')
    try:
        data = json.load(open(SRC, encoding='utf-8'))
    except Exception as e:
        print(f'[{label}] 读取 {SRC} 失败: {e}'); return
    videos = data.get('videos', [])
    movies = [v for v in videos if v.get('category') == 'movie']
    print(f'[{label}] 电影 {len(movies)} 条')

    done = {}
    try:
        done = json.load(open(CP, encoding='utf-8'))
        print(f'[{label}] 续跑已有 {len(done)} 条流地址')
    except Exception:
        pass

    need = [v for v in movies if v['id'] not in done]
    print(f'[{label}] 待抓 {len(need)} 条')
    if not need:
        print(f'[{label}] 无需抓取'); return

    t0 = time.time()
    nd = 0
    lock = threading.Lock()

    def work(v):
        return v['id'], get_streams_for(v['url'])

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, v) for v in need]
        for fu in as_completed(futs):
            vid, st = fu.result()
            with lock:
                done[vid] = st
                nd += 1
                if nd % 10 == 0:  # 用户要求: 每10条落盘(原200), 降低444暂停期间崩溃的丢数据风险
                    json.dump(done, open(CP, 'w', encoding='utf-8'), ensure_ascii=False)
                    e = time.time() - t0
                    rate = nd / e if e > 0 else 0
                    eta = (len(need) - nd) / rate if rate > 0 else 0
                    print(f'[{label}] 流 {nd}/{len(need)} {rate:.2f}/s 剩{eta/60:.0f}分 {datetime.now():%H:%M:%S}')

    json.dump(done, open(CP, 'w', encoding='utf-8'), ensure_ascii=False)

    # 合并输出(独立文件, 不碰主JSON)
    id2v = {v['id']: v for v in videos}
    for vid, st in done.items():
        if vid in id2v:
            id2v[vid]['streams'] = st
            # 对齐前端: 取首个有效流地址作为 streamUrl 直连(HLS)
            if st:
                first = st[0]['url'] if isinstance(st[0], dict) else st[0]
                id2v[vid]['streamUrl'] = first or ''
    json.dump({'source': data.get('source'), 'videos': videos,
               'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'[{label}] ✅ 流地址完成 {len(done)} 条 -> {OUT}')


# 源定义(模块级, 供独立脚本 import): name -> (label, workers)
# 注意: 大象(szbwzl)/草民(sychuojia) 已下架, 不再抓取; 正确入口请用 crawl_pbmkjx.py / crawl_whyungu.py
SOURCES = {
    'pbmkjx': ('555', 6),
    'whyungu': ('龙腾', 5),
}
MAC_SOURCES = ['pbmkjx', 'whyungu']


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or args[0] in ('all', '--all'):
        sel = list(SOURCES.keys())          # 全部已启用源(默认)
    elif args[0] == 'mac':
        sel = MAC_SOURCES                    # 仅 MacCMS 源
    else:
        sel = [a for a in args if a in SOURCES]  # 显式指定源名
    if not sel:
        sel = list(SOURCES.keys())

    print(f'本次抓取源: {sel}  {datetime.now():%H:%M:%S}')
    for n in sel:
        l, w = SOURCES[n]
        run_source(n, l, w)
    print(f'\n流地址抓取结束 {datetime.now():%H:%M:%S}')
