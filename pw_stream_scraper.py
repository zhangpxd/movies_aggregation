"""isunway+zawxw 流地址 - Playwright无头浏览器"""
import json, re, time
from playwright.sync_api import sync_playwright

SOURCES = [
    {'file':'data/isunway.json','play_url':'https://isunway.com/index.php?m=vod-play-id-{vid}-src-1-num-1'},
    {'file':'data/zawxw.json','play_url':'https://m.zawxw.com/vodplay/{vid}-1-1.html'},
]

for cfg in SOURCES:
    with open(cfg['file'],'r',encoding='utf-8') as f: data=json.load(f)
    videos=data['videos']
    tasks=[(i,v) for i,v in enumerate(videos) if not v.get('streamUrl')]
    need=len(tasks)
    if not need:
        fname = cfg['file']
        print(f'{fname}: 全部有流, 跳过')
        continue
    
    fname = cfg['file']
    print(f'{fname}: {need}/{len(videos)} 需补')
    start=time.time()
    done=0
    
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for idx,v in tasks:
            try:
                page=browser.new_page()
                url=cfg['play_url'].format(vid=v['id'])
                page.goto(url,timeout=15000,wait_until='domcontentloaded')
                page.wait_for_timeout(2000)  # 等JS加载
                html=page.content()
                m=re.search(r'https?://[^\s"<>]+\.m3u8[^\s"<>]*',html)
                if not m:
                    m=re.search(r'"url":"([^"]+\.m3u8[^"]*)"',html)
                if m:
                    videos[idx]['streamUrl']=m.group(0) if m.lastindex is None else m.group(1)
                page.close()
            except:
                try: page.close()
                except: pass
            
            done+=1
            if done%50==0:
                n=sum(1 for x in videos if x.get('streamUrl'))
                e=time.time()-start; rate=done/e if e>0 else 0
                eta=(need-done)/rate if rate>0 else 0
                print(f'  [{done}/{need}] {rate:.1f}条/s 剩余{eta/60:.0f}分 stream={n}')
                data['updated_at']=time.strftime('%Y-%m-%d %H:%M:%S')
                with open(cfg['file'],'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False)
        
        browser.close()
    
    with open(cfg['file'],'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False)
    n=sum(1 for x in videos if x.get('streamUrl'))
    print(f'  {fname} 完成！stream={n}/{len(videos)}')
