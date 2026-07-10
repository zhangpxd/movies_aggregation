import requests, re
H={'User-Agent':'Mozilla/5.0','Accept':'text/html','Accept-Language':'zh-CN'}
s=requests.Session()
s.get('https://v.12ju.com/', headers=H, timeout=15)

for slug,label in [('guochanju','国产剧'),('dongzuopian','动作'),('dianying','电影')]:
    r=s.get(f'https://v.12ju.com/{slug}/', headers=H, timeout=15)
    if r.status_code==200:
        m=re.search(r'type_parms\s*=\s*(\{[^}]+\})', r.text)
        ajax=re.search(r'type_ajax_url\s*="([^"]+)"', r.text)
        id_m=re.search(r'"id":"(\d+)"', m.group(1)) if m else None
        print(f'{label}: id={id_m.group(1) if id_m else "?"} ajax_url={ajax.group(1) if ajax else "?"}')
    else:
        print(f'{label}: {r.status_code}')
