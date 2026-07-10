"""并行慢速增量流地址抓取 - 2线程×2源, 每秒~5请求"""
import json, re, time, requests, random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

def scrape_source(filepath, name, get_stream, need_refresh=False):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    videos = data['videos']
    
    tasks = [(i, v) for i, v in enumerate(videos) if not v.get('streamUrl')]
    need = len(tasks)
    t0 = time.time()
    sess = requests.Session()
    
    if need_refresh:
        sess.get('https://v.12ju.com/', headers={
            'User-Agent': 'Mozilla/5.0', 'Sec-Ch-Ua': '"Chromium";v="130"',
        }, timeout=15)
    else:
        sess.get(f'https://{name.lower()}./', headers={
            'User-Agent': 'Mozilla/5.0'
        }, timeout=15)
    
    done = 0; errors = 0; BATCH = 3  # 3条/批 ×2子线程 /1.2s ≈ 5条/s
    
    for bi in range(0, need, BATCH):
        batch = tasks[bi:bi+BATCH]
        with ThreadPoolExecutor(3) as ex:
            def process(item):
                idx, v = item
                try:
                    url, src = get_stream(sess, v['id'])
                    if src:
                        videos[idx]['streamUrl'] = src
                        return True
                except: pass
                return False
            list(ex.map(process, batch))
        
        done += len(batch)
        if done % 200 == 0 or done == need:
            n = sum(1 for x in videos if x.get('streamUrl'))
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (need - done) / rate if rate > 0 else 0
            print(f'  {name} [{done}/{need}] 流={n} {rate:.1f}条/s 剩余{eta/60:.0f}分 {datetime.now().strftime("%H:%M:%S")}')
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        
        time.sleep(1.2)  # 批次间隔
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    n = sum(1 for x in videos if x.get('streamUrl'))
    print(f'  {name} 完成！流={n}/{len(videos)}')

# mediavip: 从splay页提取stream
def mediavip_stream(sess, vid):
    url = f'https://www.mediavip.cn/splay/{vid}-1-1/'
    r = sess.get(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.mediavip.cn/', 'Accept': 'text/html',
    }, timeout=12)
    if 'Just a moment' in r.text:
        return url, None
    m = re.search(r'videoSrc\s*=\s*"([^"]+)"', r.text)
    return url, (m.group(1).replace(r'\/', '/') if m else None)

# 12ju: 从视频页提取stream
def j12ju_stream(sess, vid):
    for ep in [2, 1]:
        url = f'https://v.12ju.com/video/{vid}-{ep}-1.html'
        r = sess.get(url, headers={
            'User-Agent': 'Mozilla/5.0', 'Sec-Fetch-Dest': 'document',
            'Accept': 'text/html',
        }, timeout=12)
        if r.status_code == 404: continue
        if '502' in r.text[:100]: return url, None
        m = re.search(r'"url":"([^"]+\.m3u8[^"]*?)"', r.text)
        if m:
            return url, m.group(1).replace(r'\\/', '/')
    return url, None

print(f'并行流地址增量 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 50)

# 并行跑两个源
with ThreadPoolExecutor(2) as pool:
    futures = [
        pool.submit(scrape_source, 'data/full_videos.json', 'mediavip', mediavip_stream, False),
        pool.submit(scrape_source, 'data/12ju.json', '12ju', j12ju_stream, True),
    ]
    for f in futures:
        f.result()

print(f'\n全部完成！{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
