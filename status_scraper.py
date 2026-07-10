"""各源状态补充脚本 - 从播放页获取集数状态"""
import json, re, time, requests
from concurrent.futures import ThreadPoolExecutor

SOURCES = {
    'mediavip': {
        'file': 'data/full_videos.json',
        'play_url': 'https://www.mediavip.cn/splay/{vid}-1-1/',
        'headers': {'User-Agent':'Mozilla/5.0','Referer':'https://www.mediavip.cn/'},
        'extract': lambda t: (re.search(r'更新[：:]?\s*([^<>\"\'\n]{2,20})', t) or re.search(r'class=\"(?:tag|status)[^\"]*\"[^>]*>([^<]+)', t)),
        'extract_stream': lambda t: (m:=re.search(r'videoSrc\s*=\s*\"([^\"]+)\"', t)) and m.group(1).replace('\\/','/'),
    },
    'xfej': {
        'file': 'data/xfej.json',
        'play_url': 'https://xfej.net/spd/{vid}.html',  # 用详情页
        'headers': {'User-Agent':'Mozilla/5.0','Referer':'https://xfej.net/'},
        'extract': lambda t: (re.search(r'更新[：:]\s*<span[^>]*>([^<]+)', t) or re.search(r'<span class=\"(?:pic-tag|tag)[^\"]*\"[^>]*>([^<]+)', t)),
        'extract_stream': lambda t: (m:=re.search(r'\"url\":\"([^\"]+?\.m3u8[^\"]*?)\"', t)) and 'skip',  # 已有skip
    },
    'jieshui8': {
        'file': 'data/jieshui8.json',
        'play_url': 'https://m.jieshui8.com/vodplay/{vid}-1-1.html',
        'headers': {'User-Agent':'Mozilla/5.0','Referer':'https://m.jieshui8.com/'},
        'extract': lambda t: (re.search(r'更新[至:]?\s*([^<>\"\'\n]{2,20})', t) or re.search(r'(?:全|共)\s*(\d+)\s*集', t)),
        'extract_stream': lambda t: (m:=re.search(r'var player_\w+\s*=\s*\{[^}]*\"url\":\"([^\"]+\.m3u8[^\"]*)\"', t)) and m.group(1),
    },
    '12ju': {
        'file': 'data/12ju.json',
        'play_url': 'https://v.12ju.com/tv/{vid}.html',  # 用详情页
        'headers': {'User-Agent':'Mozilla/5.0','Sec-Ch-Ua':'\";Chromium\";v=\"130\"','Sec-Fetch-Dest':'document'},
        'extract': lambda t: (re.search(r'更新[：:]\s*([^<>\"\'\n]{2,20})', t) or re.search(r'全(\d+)集', t) or re.search(r'第(\d+)集', t)),
        'extract_stream': lambda t: None,  # 这个是详情页不取流
    },
}

for name, cfg in SOURCES.items():
    filepath = 'E:/new_video/' + cfg['file']
    with open(filepath, 'r', encoding='utf-8') as f: data = json.load(f)
    videos = data['videos']
    
    # 只需要没有status的电视剧/综艺/动漫/短剧
    tasks = []
    for i, v in enumerate(videos):
        cat = v.get('category', '')
        if cat != 'movie' and not v.get('status'):
            tasks.append((v['id'], i))
    
    if not tasks:
        print(f'{name}: 全部有status，跳过')
        continue
    
    need = len(tasks)
    total = len(videos)
    print(f'\n=== {name}: {need}/{total} 需补status ===')
    
    sess = requests.Session()
    start_t = time.time()
    BATCH = 100
    done = 0
    
    for bi in range(0, need, BATCH):
        batch = tasks[bi:bi+BATCH]
        with ThreadPoolExecutor(10) as ex:
            def process(item):
                vid, idx = item
                try:
                    url = cfg['play_url'].format(vid=vid)
                    r = sess.get(url, headers=cfg['headers'], timeout=15)
                    if r.status_code == 200:
                        t = r.text
                        # 提取状态
                        st = cfg['extract'](t)
                        if st:
                            val = st.group(1).strip() if st.groups() else st.group(0).strip()
                            if val and len(val) > 0:
                                videos[idx]['status'] = val
                        # 如果没stream且需要提取
                        if not videos[idx].get('streamUrl'):
                            s = cfg['extract_stream'](t)
                            if s and s != 'skip':
                                if not s.startswith('http'): s = 'https://' + s.lstrip('/')
                                videos[idx]['streamUrl'] = s
                except: pass
            list(ex.map(process, batch))
        done += len(batch)
        e = time.time() - start_t
        rate = done / e if e > 0 else 0
        eta = (need - done) / rate if rate > 0 else 0
        print(f'  [{done}/{need}] {rate:.0f}条/s | 剩余{eta:.0f}s')
        # 定期保存
        if (bi // BATCH) % 10 == 0:
            data['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            with open(filepath, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
    
    with open(filepath, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
    have_status = sum(1 for v in videos if v.get('status'))
    print(f'  {name} 完成！status: {have_status}/{total}')
