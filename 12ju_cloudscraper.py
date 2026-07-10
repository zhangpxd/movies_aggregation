"""12ju cloudscraper慢速增量"""
import cloudscraper, json, re, time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

with open('data/12ju.json','r',encoding='utf-8') as f: data = json.load(f)
videos = data['videos']

tasks = [(i,v) for i,v in enumerate(videos) if not v.get('streamUrl')]
need = len(tasks)
t0 = time.time()
done = 0
errors = 0

def new_sc():
    for _ in range(3):
        try:
            s = cloudscraper.create_scraper()
            s.get('https://v.12ju.com/', timeout=15)
            return s
        except: time.sleep(3)

sess = new_sc()
print(f'12ju: 总{len(videos)} 缺{need} 补流地址')

BATCH = 4  # 4条/批, ~2条/s
for bi in range(0, need, BATCH):
    batch = tasks[bi:bi+BATCH]
    
    for idx, v in batch:
        for attempt in range(2):
            try:
                for ep in [2, 1]:
                    r = sess.get(f'https://v.12ju.com/video/{v["id"]}-{ep}-1.html',
                        headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'}, timeout=12)
                    if r.status_code == 404: continue
                    m = re.search(r'"url":"([^"]+\.m3u8[^"]*?)"', r.text)
                    if m:
                        videos[idx]['streamUrl'] = m.group(1).replace(r'\\/', '/')
                        errors = 0
                        break
                break
            except:
                sess = new_sc()
                errors += 1
                time.sleep(2)
        
        time.sleep(0.3)  # 每条间隔
    
    done += len(batch)
    if done % 100 == 0:
        n = sum(1 for x in videos if x.get('streamUrl'))
        e = time.time() - t0
        rate = done / e if e > 0 else 0
        eta = (need - done) / rate if rate > 0 else 0
        print(f'  [{done}/{need}] 流={n} {rate:.1f}条/s 剩余{eta/60:.0f}分 {datetime.now().strftime("%H:%M:%S")}')
        data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open('data/12ju.json','w',encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    
    time.sleep(1.5)  # 批次间隔
    # 每500条刷新cloudscraper
    if done % 500 == 0:
        sess = new_sc()

with open('data/12ju.json','w',encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)
n = sum(1 for x in videos if x.get('streamUrl'))
print(f'  12ju 完成！流={n}/{len(videos)}')
