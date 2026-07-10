"""xiaoccom.com 爬虫 - 小草影院"""
import requests, re, time, json, os
from datetime import datetime

H={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
   'Accept':'text/html,application/xhtml+xml,*/*;q=0.8',
   'Accept-Language':'zh-CN,zh;q=0.9','Accept-Encoding':'gzip, deflate'}
B='https://www.xiaoccom.com'

def fetch(url, timeout=30):
    for _ in range(3):
        try:
            r=requests.get(url,headers=H,timeout=timeout)
            if r.status_code==200: return r
            time.sleep(2)
        except: time.sleep(3)
    return None

# 检查首页
r0=fetch(B+'/')
if not r0:
    print('站点无法访问')
    exit()
print(f'Title: {re.search(r"<title>([^<]+)",r0.text).group(1)[:60]}')

# 找分类
cats=[]
for m in re.finditer(r'<a[^>]+href="(/vtype/\d+\.html)"[^>]*>([^<]+)</a>', r0.text):
    cats.append((m.group(1), m.group(2)))
if not cats:
    cats=[(f'/vtype/{i}.html', f'type{i}') for i in range(1,10)]

print(f'Categories: {len(cats)}')
CAT_MAP={
    '1':'movie','5':'tv','4':'variety','3':'anime',
}
SEO_MAP={
    '电影':'movie','电视剧':'tv','综艺':'variety','动漫':'anime',
    '记录':'variety','纪录':'variety','短剧':'short',
}

all_vids=[]
for cat_url,cat_name in cats:
    # 判断主分类
    cat_id=dict(CAT_MAP)
    cid=re.search(r'/vtype/(\d+)',cat_url)
    cid=cid.group(1) if cid else ''
    main_cat=CAT_MAP.get(cid,'')
    if not main_cat:
        for k,v in SEO_MAP.items():
            if k in cat_name: main_cat=v; break
    if not main_cat: main_cat='movie'
    
    max_pages=5
    for p in range(1,max_pages+1):
        url=B+cat_url if p==1 else f'{B}{cat_url}?page={p}'
        r=fetch(url)
        if not r: break
        
        # 解析视频卡片
        page_vids=[]
        for m in re.finditer(
            r'<a[^>]+href="(/v/(\d+)\.html)"[^>]*>.*?'
            r'<img[^>]+(?:data-original|data-src|src)="([^"]+\.(?:jpg|png|webp))"',
            r.text, re.DOTALL):
            pass
        # 尝试另一种卡片格式
        for m in re.finditer(
            r'href="(/v/(\d+)\.html)"[^>]*class="[^"]*cover[^"]*"[^>]*>.*?'
            r'data-original="([^"]+)"',
            r.text, re.DOTALL):
            vid=m.group(2); poster=m.group(3)
            # 在同一块中找标题
            block_start=m.start()
            block=r.text[block_start:block_start+500]
            title_m=re.search(r'title="([^"]+)"',block)
            title=title_m.group(1) if title_m else f'video_{vid}'
            page_vids.append({'id':vid,'title':title,'poster':poster})
        
        if not page_vids:
            # 实在不行，单独找
            vids=set(re.findall(r'/v/(\d+)\.html',r.text))
            titles=dict(re.findall(r'href="/v/(\d+)\.html"[^>]+title="([^"]+)"',r.text))
            imgs=dict(re.findall(r'/v/(\d+)\.html.*?data-original="([^"]+)"',r.text,re.DOTALL))
            for vid in vids:
                if vid not in {x['id'] for x in page_vids}:
                    page_vids.append({
                        'id':vid,
                        'title':titles.get(vid,f'video_{vid}'),
                        'poster':imgs.get(vid,''),
                    })
        
        if not page_vids: break
        for v in page_vids:
            v['url']=B+f'/v/{v["id"]}.html'
            v['category']=main_cat
            v['subcat']=cat_name
            v['source']='xiaoccom'
            v['streamUrl']=''
            v['status']=''
        all_vids.extend(page_vids)
        time.sleep(1)
    
    print(f'  {cat_name}: {len(page_vids)}条 (p1-{p})')

# 去重
seen=set()
uni=[]
for v in all_vids:
    if v['id'] not in seen:
        seen.add(v['id'])
        uni.append(v)

os.makedirs('data',exist_ok=True)
output={'source':'xiaoccom.com','updated_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total':len(uni),'videos':uni}
with open('data/xiaoccom.json','w',encoding='utf-8') as f:
    json.dump(output,f,ensure_ascii=False,indent=2)

print(f'\nDone: {len(uni)} videos')
for c in ['movie','tv','variety','anime','short']:
    n=sum(1 for v in uni if v['category']==c)
    if n: print(f'  {c}: {n}')
