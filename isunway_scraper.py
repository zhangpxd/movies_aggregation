"""isunway.com (51电影网) 爬虫"""
import json, re, os, time, requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

H={'User-Agent':'Mozilla/5.0','Accept':'text/html','Accept-Language':'zh-CN',
   'Connection':'close'}
B='https://isunway.com'

CATS=[
    ('/t/dianying.html','movie','电影'),
    ('/t/dianshiju.html','tv','电视剧'),
    ('/t/zongyi.html','variety','综艺'),
    ('/t/dongman.html','anime','动漫'),
    ('/t/duanju.html','short','短剧'),
]

sess=requests.Session()
sess.get(B+'/',headers=H,timeout=15)

all_vids=[]
for cat_url,cat_id,subcat in CATS:
    vids=[]
    for p in range(1,21):
        url=B+cat_url if p==1 else f'{B}{cat_url}?page={p}'
        try:
            r=sess.get(url,headers=H,timeout=15)
            if r.status_code!=200: break
        except: break
        
        # 解析: <li><a href="/v/ID.html" title="TITLE"><img data-original="POSTER">
        page_vids=[]
        for m in re.finditer(r'href="(/v/(\d+)\.html)"[^>]+title="([^"]+)".*?data-original="([^"]+\.(?:jpg|png|jpeg))"',r.text,re.DOTALL):
            page_vids.append({'id':int(m.group(2)),'title':m.group(3),'poster':m.group(4),
                'url':B+m.group(1),'category':cat_id,'subcat':subcat,
                'source':'isunway','streamUrl':'','status':''})
        
        if not page_vids: break
        # 去重
        for v in page_vids:
            if v['id'] not in {x['id'] for x in vids}:
                vids.append(v)
        time.sleep(0.3)
    
    print(f'  {subcat}: {len(vids)}条 / {p-1}页')
    all_vids.extend(vids)

os.makedirs('data',exist_ok=True)
output={'source':'isunway.com','updated_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total':len(all_vids),'videos':all_vids}
with open('data/isunway.json','w',encoding='utf-8') as f:
    json.dump(output,f,ensure_ascii=False,indent=2)

print(f'\nisunway 完成: {len(all_vids)}条')
for c in ['movie','tv','variety','anime','short']:
    n=sum(1 for v in all_vids if v['category']==c)
    if n: print(f'  {c}: {n}')
