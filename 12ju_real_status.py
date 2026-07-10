"""12ju 真实status提取 - cloudscraper绕过"""
import cloudscraper, json, re, time
from concurrent.futures import ThreadPoolExecutor

scraper = None

def get_scraper():
    global scraper
    if scraper is None:
        for _ in range(3):
            try:
                scraper = cloudscraper.create_scraper()
                scraper.get('https://v.12ju.com/', timeout=20)
                return scraper
            except: time.sleep(3)
    return scraper

scraper = get_scraper()

with open('data/12ju.json','r',encoding='utf-8') as f: data = json.load(f)
videos = data['videos']

tasks = []
for i,v in enumerate(videos):
    if v['category']!='movie' and v.get('status') in ('','连载中','更新中'):
        tasks.append((v['id'],i))

need = len(tasks); done = 0; t0 = time.time()
print(f'12ju real status: {need}/{len(videos)} 需提取')

BATCH = 50
for bi in range(0, need, BATCH):
    batch = tasks[bi:bi+BATCH]
    with ThreadPoolExecutor(3) as ex:
        def process(item):
            vid,idx = item
            for attempt in range(3):
                try:
                    s = get_scraper()
                    r = s.get(f'https://v.12ju.com/tv/{vid}.html', timeout=15)
                    t = r.text
                    st = re.search(r'class=\"title text-muted\"[^>]*>(全\d+集|更新[^<]+|连载[^<]+|完结[^<]+)</span>', t)
                    if not st:
                        st = re.search(r'(?:全(\d+)\s*集|共(\d+)\s*集|更新至?\s*第?(\d+)\s*集)', t[:5000])
                    if st:
                        val = st.group(1) if st.groups() else st.group(0)
                        if val and len(val.strip())>1 and val.strip()!='状态：':
                            videos[idx]['status'] = val.strip()
                    return
                except:
                    global scraper; scraper = None
                    time.sleep(2)
            print(f'    FAILED {vid}')
        list(ex.map(process, batch))
    done += len(batch)
    e = time.time()-t0; rate = done/e if e>0 else 0
    eta = (need-done)/rate if rate>0 else 0
    print(f'  [{done}/{need}] {rate:.0f}条/s | 剩余{eta:.0f}s')
    if (bi//BATCH)%20==0:
        data['updated_at']=time.strftime('%Y-%m-%d %H:%M:%S')
        with open('data/12ju.json','w') as f: json.dump(data,f,ensure_ascii=False)

with open('data/12ju.json','w') as f: json.dump(data,f,ensure_ascii=False)
real_st=sum(1 for v in videos if v.get('status') and v.get('status') not in ('连载中','更新中'))
print(f'12ju 完成！真实status: {real_st}/{len(videos)}')
