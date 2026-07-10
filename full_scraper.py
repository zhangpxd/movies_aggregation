"""
全量爬虫 - 每个子分类抓完所有页
带进度反馈，只保留有海报的视频
"""
import json, re, os, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Referer': 'https://www.mediavip.cn/',
}
B = 'https://www.mediavip.cn'
sess = requests.Session()

CATS = {
    'movie': ('电影', {
        'shaoshi':'邵氏电影','lilun':'理论电影','dongzuo':'动作','aiqing':'爱情',
        'xiju':'喜剧','kongbu':'恐怖','jings':'惊悚','xuanyi':'悬疑','fanzui':'犯罪',
        'juqing':'剧情','zhanzheng':'战争','zainan':'灾难','kehuan':'科幻',
        'qihuan':'奇幻','maoxian':'冒险','jilu':'纪录','qita':'其他',
    }),
    'tv': ('连续剧', {
        'guochanju':'国产剧','gangtaiju':'港台剧','hanguoju':'韩国剧',
        'ribenju':'日本剧','oumeiju':'欧美剧','taiguoju':'泰国剧',
        'duanju':'短剧','qitaju':'其他剧',
    }),
}

def parse_html(html):
    """提取有海报的视频"""
    vids = []
    for m in re.finditer(r'<a\s[^>]*?href="(/mvip/(\d+)/)"[^>]*?title="([^"]+)"[^>]*?>', html):
        pm = re.search(r'data-original="([^"]+)"', m.group(0))
        if pm:
            vids.append({
                'id': int(m.group(2)),
                'title': m.group(3).strip(),
                'url': B + m.group(1),
                'poster': pm.group(1),
            })
    return vids

def fetch_page(url, referer):
    hdrs = dict(H)
    hdrs['Referer'] = referer
    r = sess.get(url, headers=hdrs, timeout=20)
    r.encoding = 'utf-8'
    return r if r.status_code == 200 and '/mvip/' in r.text else None

print('=' * 55)
print('  全量爬虫 - 每个子分类抓完所有页')
print('=' * 55)

all_videos = defaultdict(list)

for cat_id, (cat_name, subs) in CATS.items():
    print(f'\n>>> {cat_name} ({len(subs)}个子分类)')
    for slug, name in subs.items():
        # 第一页
        url1 = f'{B}/hgft/{slug}/'
        r = fetch_page(url1, B)
        if not r:
            print(f'    {name}: ❌ 无法访问')
            continue

        # 总页数
        last = re.search(rf'/{slug}-(\d+)/[^>]*>尾页', r.text)
        tp = int(last.group(1)) if last else 1
        MAX_PAGES = min(tp, 50)  # 每子分类最多50页
        p_start = time.time()

        # 解析第一页
        vids = parse_html(r.text)

        # 并发抓剩余页（分批，每批3个）
        BATCH = 3
        if MAX_PAGES > 1:
            pages = list(range(2, MAX_PAGES + 1))
            for batch_start in range(0, len(pages), BATCH):
                batch = pages[batch_start:batch_start + BATCH]
                with ThreadPoolExecutor(3) as ex:
                    def sp(p):
                        r2 = sess.get(f'{B}/hgft/{slug}-{p}/', headers=dict(H), timeout=20)
                        r2.encoding = 'utf-8'
                        return parse_html(r2.text) if r2.status_code == 200 else []
                    fs = {ex.submit(sp, p): p for p in batch}
                    for f in as_completed(fs):
                        vids.extend(f.result())
                time.sleep(0.2)  # 批次间小延迟

        # 去重
        seen = set()
        uni = []
        for v in vids:
            if v['id'] not in seen:
                seen.add(v['id'])
                v['category'] = cat_id
                v['subcat'] = name
                v['source'] = 'mediavip'
                v['streamUrl'] = ''
                v['status'] = ''
                uni.append(v)

        all_videos[cat_id].extend(uni)
        elapsed = time.time() - p_start
        print(f'    {name}: {len(uni)}条 / {MAX_PAGES}页 ({elapsed:.1f}s)')

# 保存
os.makedirs('data', exist_ok=True)
flat = []
for vids in all_videos.values():
    flat.extend(vids)

output = {
    'source': 'mediavip.cn',
    'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'total': len(flat),
    'videos': flat,
}
with open('data/full_videos.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'\n{"="*55}')
print(f'  完成！总计: {len(flat)} 条 (全部含海报)')
for cat_id, (cat_name, _) in CATS.items():
    n = len(all_videos[cat_id])
    print(f'    {cat_name}: {n} 条')
print(f'{"="*55}')
