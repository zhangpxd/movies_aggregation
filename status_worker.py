"""全源status+stream补充 - 并行版，一个源一个文件"""
import json, re, time, requests, sys
from concurrent.futures import ThreadPoolExecutor

SOURCE_NAME = sys.argv[1] if len(sys.argv) > 1 else 'mediavip'

CFG = {
    'mediavip': {
        'file': 'data/full_videos.json',
        'play_url': 'https://www.mediavip.cn/splay/{vid}-1-1/',
        'headers': {'UA':'Mozilla/5.0','Referer':'https://www.mediavip.cn/'},
        'extract_status': lambda t: (
            re.search(r'(?:更新|状态)[：:]\s*([^<>\n]{2,20})', t) or
            re.search(r'(?:全|共)\s*(\d+)\s*集', t) or
            re.search(r'(HD|TC|TS)', t)
        ),
        'extract_stream': lambda t: (m := re.search(r'videoSrc\s*=\s*"([^"]+)"', t)) and m.group(1).replace(r'\/', '/'),
        'threads': 15,
    },
    'xfej': {
        'file': 'data/xfej.json',
        'play_url': 'https://xfej.net/spd/{vid}.html',
        'headers': {'UA':'Mozilla/5.0','Referer':'https://xfej.net/'},
        'extract_status': lambda t: (
            re.search(r'更新[：:]\s*<span[^>]*>([^<]+)', t) or
            re.search(r'(?:全|共)\s*(\d+)\s*集', t) or
            re.search(r'<span class="pic-tag[^"]*"[^>]*>([^<]+)', t)
        ),
        'extract_stream': lambda t: (m := re.search(r'"url":"([^"]+?\.m3u8[^"]*?)"', t)) and m.group(1).replace(r'\/', '/'),
        'threads': 10,
    },
    'jieshui8': {
        'file': 'data/jieshui8.json',
        'play_url': 'https://m.jieshui8.com/vodplay/{vid}-1-1.html',
        'headers': {'UA':'Mozilla/5.0','Referer':'https://m.jieshui8.com/'},
        'extract_status': lambda t: (
            re.search(r'更新[至:]?\s*([^<>\"\'\n]{2,20})', t) or
            re.search(r'(?:全|共)\s*(\d+)\s*集', t) or
            re.search(r'第(\d+)集', t)
        ),
        'extract_stream': lambda t: (m := re.search(r'var player_\w+\s*=\s*\{[^}]*"url":"([^"]+\.m3u8[^"]*)"', t)) and m.group(1).replace(r'\/', '/'),
        'threads': 15,
    },
    '12ju': {
        'file': 'data/12ju.json',
        'play_url': 'https://v.12ju.com/tv/{vid}.html',
        'headers': {'UA':'Mozilla/5.0','Sec-Ch-Ua':'"Chromium";v="130"','Sec-Fetch-Dest':'document'},
        'extract_status': lambda t: (
            re.search(r'更新[：:]\s*([^<>\n]{2,20})', t) or
            re.search(r'(?:全|共)\s*(\d+)\s*集', t)
        ),
        'extract_stream': lambda t: None,
        'threads': 5,
    },
}

cfg = CFG[SOURCE_NAME]
filepath = cfg['file']
with open(filepath, 'r', encoding='utf-8') as f: data = json.load(f)
videos = data['videos']

tasks = []
for i, v in enumerate(videos):
    if v.get('category','movie') != 'movie':
        need_status = not v.get('status')
        need_stream = not v.get('streamUrl')
        if need_status or need_stream:
            tasks.append((v['id'], i, need_status, need_stream))

need = len(tasks)
total = len(videos)
print(f'{SOURCE_NAME}: non-movie={total - sum(1 for v in videos if v["category"]=="movie")} tasks={need}')

sess = requests.Session()
start_t = time.time()
BATCH = 100
done = 0

for bi in range(0, need, BATCH):
    batch = tasks[bi:bi+BATCH]
    with ThreadPoolExecutor(cfg['threads']) as ex:
        def process(item):
            vid, idx, need_s, need_str = item
            try:
                url = cfg['play_url'].format(vid=vid)
                r = sess.get(url, headers={'User-Agent':cfg['headers']['UA'], 
                    'Referer':cfg['headers'].get('Referer',''),
                    'Accept':'text/html','Accept-Language':'zh-CN',
                    'Sec-Ch-Ua':cfg['headers'].get('Sec-Ch-Ua',''),
                    'Sec-Fetch-Dest':cfg['headers'].get('Sec-Fetch-Dest','')},
                    timeout=15)
                if r.status_code == 200:
                    t = r.text
                    if need_s:
                        st = cfg['extract_status'](t)
                        if st:
                            val = st.group(1).strip() if st.groups() else st.group(0).strip()
                            if val: videos[idx]['status'] = val
                    if need_str:
                        s = cfg['extract_stream'](t)
                        if s:
                            if not s.startswith('http'): s = 'https://' + s.lstrip('/')
                            videos[idx]['streamUrl'] = s
            except: pass
        list(ex.map(process, batch))
    done += len(batch)
    e = time.time() - start_t
    rate = done / e if e > 0 else 0
    eta = (need - done) / rate if rate > 0 else 0
    print(f'  [{done}/{need}] {rate:.0f}条/s | 剩余{eta:.0f}s')
    if (bi // BATCH) % 10 == 0:
        data['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(filepath, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)

with open(filepath, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
hs = sum(1 for v in videos if v.get('status'))
ss = sum(1 for v in videos if v.get('streamUrl'))
print(f'  {SOURCE_NAME} 完成！status:{hs}/{total} stream:{ss}/{total}')
