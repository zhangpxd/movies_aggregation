"""jieshui8 流地址抓取 - 从 vodplay 页提取 m3u8"""
import json, re, time, requests
from concurrent.futures import ThreadPoolExecutor

H = {'User-Agent':'Mozilla/5.0','Accept':'text/html','Accept-Language':'zh-CN','Accept-Encoding':'gzip, deflate','Referer':'https://m.jieshui8.com/'}

def extract(vid):
    try:
        r = requests.get(f'https://m.jieshui8.com/vodplay/{vid}-1-1.html', headers=H, timeout=10)
        m = re.search(r'var player_\w+\s*=\s*\{[^}]*"url":"([^"]+\.m3u8[^"]*)"', r.text)
        if m:
            src = m.group(1).replace('\\/', '/')
            if not src.startswith('http'): src = 'https://' + src.lstrip('/')
            return src
    except: pass
    return None

print('='*55)
print('  jieshui8 流地址抓取 (10线程/300进度)')
print('='*55)

with open('data/jieshui8.json','r',encoding='utf-8') as f: data=json.load(f)
videos = data['videos']
total = len(videos)
tasks=[(v['id'],i) for i,v in enumerate(videos) if not v.get('streamUrl')]
need = len(tasks)
print(f'  总量:{total} 需抓取:{need}')

BATCH=300; done=0; start_t=time.time()
for i in range(0,need,BATCH):
    batch=tasks[i:i+BATCH]
    with ThreadPoolExecutor(15) as ex:
        def p(item):
            vid,idx=item; s=extract(vid)
            if s: videos[idx]['streamUrl']=s
        list(ex.map(p,batch))
    done+=len(batch)
    elapsed=time.time()-start_t
    rate=done/elapsed if elapsed>0 else 0
    eta=(need-done)/rate if rate>0 else 0
    print(f'  [{done}/{need}] {done*100//need}% | {rate:.0f}条/s | 剩余{eta:.0f}s')
    if (i//BATCH)%10==0:
        data['updated_at']=time.strftime('%Y-%m-%d %H:%M:%S')
        with open('data/jieshui8.json','w',encoding='utf-8') as fp: json.dump(data,fp,ensure_ascii=False)

data['updated_at']=time.strftime('%Y-%m-%d %H:%M:%S')
with open('data/jieshui8.json','w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
n=sum(1 for v in videos if v.get('streamUrl'))
print(f'\n  完成！流地址:{n}/{total}')
