"""
v.12ju.com 全量爬虫 v3 - Chrome指纹 + 延迟防检测
"""
import json, re, os, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Sec-Ch-Ua': '";Not A(Brand";v="99";, "Google Chrome";v="130"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '";Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Upgrade-Insecure-Requests': '1',
}
B = 'https://v.12ju.com'
sess = requests.Session()

SUBS = [
    # 电影子分类
    ('dongzuopian','movie','动作'),('xijupian','movie','喜剧'),
    ('aiqingpian','movie','爱情'),('kehuanpian','movie','科幻'),
    # ('dianying','movie','其他'),  # 页面结构不同，跳过
    # 电视剧
    ('guochanju','tv','国产剧'),('xianggangju','tv','港台剧'),
    ('oumeiju','tv','欧美剧'),('ribenju','tv','日本剧'),
    # 微电影 (已移除)
]

def parse_page(html):
    vids = []
    for m in re.finditer(
        r'<img[^>]+(?:src|data-original)="([^"]+)"[^>]*>.*?'
        r'<a[^>]+href="/tv/(\d+)\.html"[^>]*>([^<]+)',
        html, re.DOTALL
    ):
        poster = m.group(1)
        if 'pic.png' not in poster:
            vids.append({
                'id': int(m.group(2)),
                'title': m.group(3).strip(),
                'url': B + '/tv/' + m.group(2) + '.html',
                'poster': poster,
            })
    return vids

def scrape_sub(slug, cat_id, subcat, max_pages=500):
    vids = []
    p = 1
    while p <= max_pages:
        url = B + '/' + slug + '/' if p == 1 else B + '/' + slug + '/index-' + str(p) + '.html'
        ref = B + '/'
        if p > 1: ref = B + '/' + slug + ('/' if p == 2 else '/index-' + str(p-1) + '.html')
        h = dict(H); h['Referer'] = ref; h['Sec-Fetch-Site'] = 'same-origin'

        try:
            r = sess.get(url, headers=h, timeout=20)
            if r.status_code != 200: break
            pv = parse_page(r.text)
            if not pv: break
            vids.extend(pv)
        except: break
        p += 1
        time.sleep(0.3)

    seen = set(); uni = []
    for v in vids:
        if v['id'] not in seen:
            seen.add(v['id'])
            v['category'] = cat_id; v['subcat'] = subcat
            v['source'] = '12ju'; v['streamUrl'] = ''; v['status'] = ''
            uni.append(v)

    label = subcat or slug
    print(f'    {label}: {len(uni)}条 / {p-1}页')
    return uni

print('='*55)
print('  v.12ju.com (VIP影院) 全量 v4 (增量)')
print('='*55)

sess.get(B+'/', headers=H, timeout=15)
time.sleep(0.5)

# 加载已有数据
os.makedirs('data',exist_ok=True)
existing={}
if os.path.exists('data/12ju.json'):
    with open('data/12ju.json','r',encoding='utf-8') as f:
        old=json.load(f)
        for v in old['videos']:
            existing[v['id']]=v
        print(f'  已有: {len(existing)} 条\n')

for slug, cat_id, subcat in SUBS:
    # 检查该子分类已有多少
    label=subcat or slug
    have=sum(1 for v in existing.values() if v['category']==cat_id and v['subcat']==subcat)
    # 检查总数
    try:
        r=sess.get(B+'/'+slug+'/',headers=H,timeout=20)
        total_m=re.search(r'共有[^0-9]*(\d+)',r.text)
        total=int(total_m.group(1)) if total_m else 0
    except: total=0
    if total==0: total=99999
    if total>0 and have>=total*0.95:
        print(f'    {label}: 已满 {have}/{total} 跳过')
        continue
    print(f'    {label}: 已有{have} 总量{total} 继续抓...')

    new_vids=scrape_sub(slug,cat_id,subcat)
    added=0
    for v in new_vids:
        if v['id'] not in existing:
            existing[v['id']]=v
            added+=1
        else:
            # 已有，但可能缺 streamUrl
            old_v=existing[v['id']]
            if not old_v.get('streamUrl') and v.get('streamUrl'):
                old_v['streamUrl']=v['streamUrl']

    # 中间保存
    output={'source':'v.12ju.com','updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),
            'total':len(existing),'videos':list(existing.values())}
    with open('data/12ju.json','w',encoding='utf-8') as f:
        json.dump(output,f,ensure_ascii=False)

sep='='*55
print(f'\n{sep}')
print(f'  完成！总计: {len(existing)} 条')
for c in ['movie','tv']:
    n=sum(1 for v in existing.values() if v['category']==c)
    print(f'    {c}: {n} 条')
print(sep)
