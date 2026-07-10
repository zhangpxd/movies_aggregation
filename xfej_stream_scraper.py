"""xfej.net 全量流地址抓取 - 10线程/300条进度"""
import json, re, time, requests
from concurrent.futures import ThreadPoolExecutor

H = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'text/html',
    'Accept-Language': 'zh-CN',
    'Accept-Encoding': 'gzip, deflate',
    'Referer': 'https://xfej.net/',
}

def extract(vid):
    try:
        r = requests.get(f'https://xfej.net/spplay/{vid}-1-1.html', headers=H, timeout=10)
        m = re.search(r'"url":"([^"]+?\.m3u8[^"]*?)"', r.text)
        if m:
            src = m.group(1).replace(r'\/', '/')
            if not src.startswith('http'):
                src = 'https://' + src.lstrip('/')
            return src
    except:
        pass
    return None

print('=' * 55)
print('  xfej.net 全量流地址 (10线程/300进度)')
print('=' * 55)

with open('data/xfej.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

videos = data['videos']
total = len(videos)
# 找出需要抓取的
tasks = [(v['id'], i) for i, v in enumerate(videos) if not v.get('streamUrl')]
need = len(tasks)
print(f'  总量: {total}, 需抓取: {need}')

BATCH = 300
done = 0
start_t = time.time()

for i in range(0, need, BATCH):
    batch = tasks[i:i+BATCH]
    with ThreadPoolExecutor(10) as ex:
        def process(item):
            vid, idx = item
            s = extract(vid)
            if s: videos[idx]['streamUrl'] = s
        list(ex.map(process, batch))

    done += len(batch)
    elapsed = time.time() - start_t
    rate = done / elapsed if elapsed > 0 else 0
    eta = (need - done) / rate if rate > 0 else 0
    pct = done * 100 // need
    print(f'  [{done}/{need}] {pct}% | {rate:.0f}条/s | 剩余{eta:.0f}s')

data['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
with open('data/xfej.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

n = sum(1 for v in videos if v.get('streamUrl'))
print(f'\n  完成！流地址: {n}/{total}')
