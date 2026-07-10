"""年份抓取 - 三源并行，全速跑"""
import json, re, time, sys, requests, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
     'Accept': 'text/html', 'Accept-Language': 'zh-CN,zh;q=0.9'}
tls = threading.local()
SAVE_LOCK = threading.Lock()

def extract_year(html):
    m = re.search(r'(?:年份|年代|上映)[：:]\s*(?:</?(?:span|a|p|div)[^>]*>)*\s*(\d{4})', html)
    return int(m.group(1)) if m else None

def get_12ju_sess():
    if not hasattr(tls, 's_12ju'):
        tls.s_12ju = requests.Session()
        tls.s_12ju.headers.update({'Sec-Ch-Ua': '";Chromium";v="130"', 'Sec-Fetch-Dest': 'document'})
        tls.s_12ju.get('https://v.12ju.com/', timeout=15)
    return tls.s_12ju

def fetch_year(v, fname):
    url = v.get('url')
    if not url: return None
    try:
        if '12ju' in fname:
            sess = get_12ju_sess()
            resp = sess.get(url, headers=H, timeout=15)
        else:
            resp = requests.get(url, headers=H, timeout=15)
        if resp.status_code == 200:
            return extract_year(resp.text)
    except:
        pass
    return None

def run_source(fname, threads):
    import os
    labels = {'xfej.json': 'xfej', 'jieshui8.json': 'jieshui8', '12ju.json': '12ju'}
    label = labels.get(fname, fname)

    with open(f'data/{fname}', 'r', encoding='utf-8') as f:
        data = json.load(f)
    videos = data['videos']

    tasks = [(i, v) for i, v in enumerate(videos)
             if v.get('streamUrl') and not (v.get('year') and str(v['year']).isdigit())]

    total = len(videos)
    need = len(tasks)
    print(f'[{label}] 需补 {need}/{total}', flush=True)
    if need == 0: return

    done = 0; t0 = time.time(); BATCH = 500

    def process(item):
        i, v = item
        return i, fetch_year(v, fname)

    for bi in range(0, need, BATCH):
        batch = tasks[bi:bi+BATCH]
        with ThreadPoolExecutor(threads) as ex:
            results = list(ex.map(process, batch))

        for i, year in results:
            if year:
                videos[i]['year'] = year

        done += len(batch)
        n = sum(1 for v in videos if v.get('year') and str(v['year']).isdigit())
        e = time.time() - t0
        rate = done / e if e > 0 else 0
        eta = (need - done) / rate if rate > 0 else 0
        print(f'[{label}] {n}/{total} {rate:.0f}条/s 剩余{eta/60:.0f}分', flush=True)

        with SAVE_LOCK:
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(f'data/{fname}', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)

    n = sum(1 for v in videos if v.get('year') and str(v['year']).isdigit())
    print(f'[{label}] ✅ 完成！{n}/{total}', flush=True)

if __name__ == '__main__':
    print(f'三源并行年份抓取 {datetime.now().strftime("%H:%M:%S")}', flush=True)
    sources = [
        ('xfej.json', 15),
        ('jieshui8.json', 15),
        ('12ju.json', 8),
    ]
    with ThreadPoolExecutor(len(sources)) as ex:
        futs = {ex.submit(run_source, f, t): f for f, t in sources}
        for fut in as_completed(futs):
            fname = futs[fut]
            try:
                fut.result()
            except Exception as e:
                print(f'[{fname}] ❌ {e}', flush=True)
    print(f'\n全部完成 {datetime.now().strftime("%H:%M:%S")}', flush=True)
