"""12ju 流地址 v4 - 5线程独立Session, ~28条/s"""
import json, re, time, requests, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

H_TPL = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Sec-Ch-Ua': '";Chromium";v="130"',
    'Sec-Fetch-Dest': 'document',
}
tls = threading.local()

def get_sess():
    if not hasattr(tls, 's'):
        tls.s = requests.Session()
        tls.s.get('https://v.12ju.com/', headers=H_TPL, timeout=15)
    return tls.s

def extract(idx, vid):
    s = get_sess()
    h = dict(H_TPL)
    h['Referer'] = f'https://v.12ju.com/tv/{vid}.html'
    h['Sec-Fetch-Site'] = 'same-origin'
    
    for ep in [2, 1]:
        try:
            r = s.get(f'https://v.12ju.com/video/{vid}-{ep}-1.html', headers=h, timeout=12)
            if r.status_code == 404: continue
            if '502' in r.text[:100]: return None
            m = re.search(r'"url":"([^"]+\.m3u8[^"]*?)"', r.text)
            if m:
                return m.group(1).replace(r'\/', '/')
        except: return None
    return None

with open('data/12ju.json','r',encoding='utf-8') as f: data = json.load(f)
videos = data['videos']

tasks = [(i,v['id']) for i,v in enumerate(videos) if not v.get('streamUrl')]
need = len(tasks)
done = 0; t0 = time.time()

print(f'12ju v4: 总{len(videos)} 缺{need} 5线程')
THREADS = 5; BATCH = 50

for bi in range(0, need, BATCH):
    batch = tasks[bi:bi+BATCH]
    with ThreadPoolExecutor(THREADS) as ex:
        def process(item):
            i, vid = item
            src = extract(i, vid)
            if src:
                videos[i]['streamUrl'] = src
        list(ex.map(process, batch))
    
    done += len(batch)
    n = sum(1 for v in videos if v.get('streamUrl'))
    e = time.time() - t0
    rate = done / e if e > 0 else 0
    eta = (need - done) / rate if rate > 0 else 0
    print(f'  [{n}/{len(videos)}] {rate:.0f}条/s 剩余{eta/60:.0f}分 {datetime.now().strftime("%H:%M:%S")}')
    
    # 保存
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('data/12ju.json','w',encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

n = sum(1 for v in videos if v.get('streamUrl'))
print(f'12ju 完成！流={n}/{len(videos)}')
