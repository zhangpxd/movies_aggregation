"""多站点爬虫并行 - qianhuizhengxin + zawxw"""
import json, re, os, time, requests
from datetime import datetime

H={'User-Agent':'Mozilla/5.0','Accept':'text/html','Accept-Language':'zh-CN','Connection':'close'}

SITES={
    'qhzx': {
        'base': 'http://qianhuizhengxin.com',
        'url_pattern': '/voddetail/{id}.html',
        'cats': [
            ('/page/dianying.html','movie','电影'),
            ('/page/dianshiju.html','tv','电视剧'),
            ('/page/zongyi.html','variety','综艺'),
            ('/page/dongman.html','anime','动漫'),
        ],
    },
    'zawxw': {
        'base': 'https://m.zawxw.com',
        'url_pattern': '/vod/{id}.html',
        'cats': [
            ('/jvd/dianying.html','movie','电影'),
            ('/jvd/dianshij.html','tv','电视剧'),
            ('/jvd/zongyi.html','variety','综艺'),
            ('/jvd/dongm.html','anime','动漫'),
            ('/jvd/jilup.html','variety','记录'),
        ],
    },
}

for name,cfg in SITES.items():
    B=cfg['base']; all_vids=[]
    sess=requests.Session()
    try: sess.get(B+'/',headers=H,timeout=15)
    except: pass
    
    for cat_url,cat_id,subcat in cfg['cats']:
        vids=[]
        for p in range(1,31):  # 30页上限
            url=B+cat_url if p==1 else f'{B}{cat_url}?page={p}'
            try:
                r=sess.get(url,headers=H,timeout=12)
                if r.status_code!=200: break
            except: break
            
            # 提取: href="voddetail/ID.html" title="TITLE" data-original="POSTER"
            page_vids=[]
            for m in re.finditer(
                r'href="(/[\w/]+/(\d+)\.html)"[^>]+title="([^"]+)".*?'
                r'data-original="([^"]+\.(?:jpg|png|jpeg))"',
                r.text, re.DOTALL):
                page_vids.append({'id':int(m.group(2)),'title':m.group(3),'poster':m.group(4),
                    'url':B if m.group(1).startswith('http') else B+m.group(1),
                    'category':cat_id,'subcat':subcat,'source':name,
                    'streamUrl':'','status':''})
            
            if not page_vids: break
            exist=set(x['id'] for x in vids)
            for v in page_vids:
                if v['id'] not in exist:
                    vids.append(v); exist.add(v['id'])
            time.sleep(0.3)
        
        if vids:
            total_pages_used=p-1
            print(f'  {subcat}: {len(vids)}条 / {total_pages_used}页')
            all_vids.extend(vids)
    
    os.makedirs('data',exist_ok=True)
    output={'source':name,'updated_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total':len(all_vids),'videos':all_vids}
    fname=f'data/{name}.json'
    with open(fname,'w',encoding='utf-8') as f:
        json.dump(output,f,ensure_ascii=False,indent=2)
    print(f'  {name} 完成: {len(all_vids)}条 -> {fname}')
