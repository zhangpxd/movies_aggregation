"""12ju 流地址 v2 - 增量 + Session自动刷新"""
import json, re, time, requests
from concurrent.futures import ThreadPoolExecutor

H_TPL = {
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept':'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language':'zh-CN,zh;q=0.9',
    'Sec-Ch-Ua':'"Not A(Brand";v="99"',
    'Sec-Fetch-Dest':'document',
    'Sec-Fetch-Mode':'navigate',
    'Sec-Fetch-Site':'same-origin',
}

def new_session():
    for attempt in range(3):
        try:
            s=requests.Session()
            s.get('https://v.12ju.com/',headers=H_TPL,timeout=30)
            return s
        except:
            time.sleep(2)
    raise RuntimeError('v.12ju.com unreachable')

sess=new_session()
last_refresh=time.time()

def extract(vid):
    global sess,last_refresh
    # 每500条刷新Session
    if time.time()-last_refresh>120:
        sess=new_session()
        last_refresh=time.time()
    try:
        r=sess.get(f'https://v.12ju.com/video/{vid}-2-1.html',headers=H_TPL,timeout=10)
        if r.status_code==404:
            r=sess.get(f'https://v.12ju.com/video/{vid}-1-1.html',headers=H_TPL,timeout=10)
        if r.status_code!=200: return None
        m=re.search(r'"url":"([^"]+\.m3u8[^"]*?)"',r.text)
        if m:
            src=m.group(1).replace('\\/','/')
            if not src.startswith('http'): src='https://'+src.lstrip('/')
            return src
    except: return None
    return None

print('='*55)
print('  12ju 流地址 v2 (增量+Session刷新)')
print('='*55)

with open('data/12ju.json','r',encoding='utf-8') as f: data=json.load(f)
videos=data['videos'];total=len(videos)

tasks=[(v['id'],i) for i,v in enumerate(videos) if not v.get('streamUrl')]
need=len(tasks)
already=total-need
print(f'  总量:{total} 已有:{already} 需抓:{need}')

BATCH=300;done=0;t0=time.time()
for i in range(0,need,BATCH):
    batch=tasks[i:i+BATCH]
    with ThreadPoolExecutor(15) as ex:
        def p(item):
            vid,idx=item;s=extract(vid)
            if s: videos[idx]['streamUrl']=s
        list(ex.map(p,batch))
    done+=len(batch)
    e=time.time()-t0;rate=done/e if e>0 else 0;eta=(need-done)/rate if rate>0 else 0
    print(f'  [{done+already}/{total}] {done*100//need}% | {rate:.0f}条/s | 剩余{eta:.0f}s')
    if (i//BATCH)%5==0:
        data['updated_at']=time.strftime('%Y-%m-%d %H:%M:%S')
        with open('data/12ju.json','w',encoding='utf-8') as fp: json.dump(data,fp,ensure_ascii=False)

data['updated_at']=time.strftime('%Y-%m-%d %H:%M:%S')
with open('data/12ju.json','w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False)
n=sum(1 for v in videos if v.get('streamUrl'))
print(f'\n  完成！流地址:{n}/{total}')
