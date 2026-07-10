"""
影视数据源爬虫 - mediavip.cn
生成结构化 JSON 供前端 index.html 使用
用法: python scraper.py
输出: data/mediavip.json
"""

import requests
import json
import re
import os
import time
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.google.com/',
}

BASE_URL = 'https://www.mediavip.cn'

# 分类映射：h3 标题 -> 我们的分类 ID
CATEGORY_MAP = {
    '最新电影': 'movie',
    '最新电视剧': 'tv',
    '最新综艺': 'variety',
    '最新动漫': 'anime',
    '最新动画片': 'anime',
    '最新体育赛事': 'sports',
    '最新电影解说': 'movie',
    '最新演唱会': 'music',
    '最新资讯预告': 'news',
}

# 周榜单标题
RANK_TITLES = ['电影周榜单', '电视剧周榜单', '综艺周榜单', '动漫周榜单',
               '动画片周榜单', '体育赛事周榜单', '电影解说周榜单',
               '演唱会周榜单', '资讯预告周榜单']


def fetch_page(url, timeout=20):
    """抓取页面"""
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.encoding = 'utf-8'
    if r.status_code != 200:
        raise Exception(f'HTTP {r.status_code}')
    return BeautifulSoup(r.text, 'html.parser')


def extract_id_from_url(url):
    """从 /mvip/123456/ 提取 123456"""
    m = re.search(r'/mvip/(\d+)/?', url)
    return int(m.group(1)) if m else None


def clean_title(title):
    """清理标题，去掉 [电影解说] 等后缀"""
    return title.strip()


def parse_video_box(box):
    """解析单个视频盒子"""
    thumb = box.find('a', class_='stui-vodlist__thumb1')
    if not thumb:
        return None

    href = thumb.get('href', '')
    vid = extract_id_from_url(href)
    if not vid:
        return None

    title = thumb.get('title', '').strip()
    poster = thumb.get('data-original', '')
    if poster and not poster.startswith('http'):
        poster = ''

    # 状态标签
    status_tag = box.find('span', class_='pic-text')
    status = status_tag.get_text(strip=True) if status_tag else ''

    # 演员
    actor_tag = box.find('p', class_='text-muted')
    actors = actor_tag.get_text(strip=True) if actor_tag else ''
    if actors == '暂无演员信息':
        actors = ''

    return {
        'id': vid,
        'title': title,
        'url': BASE_URL + href,
        'poster': poster,
        'status': status,
        'actors': actors,
    }


def parse_detail_page(vid, timeout=20):
    """抓取详情页获取更多信息（简介、年份、地区等）"""
    url = f'{BASE_URL}/mvip/{vid}/'
    try:
        time.sleep(0.3)  # 礼貌延迟
        soup = fetch_page(url, timeout)

        # 简介
        desc_tag = soup.find('span', class_='detail-content') or \
                   soup.find('div', class_='detail-content') or \
                   soup.find('div', class_='stui-content__detail')
        desc = desc_tag.get_text(strip=True)[:500] if desc_tag else ''

        # 年份/地区/类型等标签
        tags = {}
        for span in soup.find_all('span', class_='split-line'):
            pass

        # 查找 detail info 区域
        detail_div = soup.find('div', class_='stui-content__detail')
        if detail_div:
            # 查找包含 年份/地区 等的 p 标签
            for p in detail_div.find_all('p'):
                text = p.get_text()
                if '年份' in text:
                    tags['year'] = re.search(r'年份[：:]\s*(\d{4})', text)
                    if tags['year']:
                        tags['year'] = tags['year'].group(1)
                if '地区' in text:
                    tags['region'] = re.search(r'地区[：:]\s*(.+?)(?:\s|$)', text)
                    if tags['region']:
                        tags['region'] = tags['region'].group(1).strip()
                if '类型' in text:
                    tags['genre'] = re.search(r'类型[：:]\s*(.+?)(?:\s|$)', text)
                    if tags['genre']:
                        tags['genre'] = tags['genre'].group(1).strip()

        return {
            'desc': desc,
            'year': tags.get('year', ''),
            'region': tags.get('region', ''),
            'genre': tags.get('genre', ''),
        }
    except Exception as e:
        print(f'  ⚠ 详情页抓取失败 vid={vid}: {e}')
        return {}


def scrape_homepage():
    """抓取首页所有视频数据"""
    print('🚀 开始抓取 mediavip.cn 首页...')
    soup = fetch_page(BASE_URL)

    # 找到所有 section(panel)
    panels = soup.find_all('div', class_='stui-pannel')
    print(f'  找到 {len(panels)} 个内容面板')

    all_videos = {}
    current_category = None

    for panel in panels:
        # 找 h3 标题
        h3 = panel.find('h3', class_='title')
        if not h3:
            continue

        section_title = h3.get_text(strip=True)

        # 跳过周榜单section
        if section_title in RANK_TITLES:
            continue

        # 确定分类
        if section_title in CATEGORY_MAP:
            current_category = CATEGORY_MAP[section_title]
            if section_title == '最新电影解说':
                current_category = 'movie'  # 电影解说归入电影
            elif section_title == '最新演唱会':
                current_category = 'variety'  # 演唱会归入综艺
            elif section_title == '最新体育赛事':
                current_category = 'variety'  # 体育归入综艺
            elif section_title == '最新资讯预告':
                current_category = 'movie'  # 资讯预告归入电影
            elif section_title == '最新动画片':
                current_category = 'anime'

        # 找到该面板内的所有视频盒子
        boxes = panel.find_all('div', class_='stui-vodlist__box')
        count = 0
        for box in boxes:
            video = parse_video_box(box)
            if video and video['id']:
                video['source'] = 'mediavip'
                video['category'] = current_category or 'movie'
                video['streamUrl'] = ''  # 流地址需单独抓取详情页获取

                # 合并或新增（按id去重）
                if video['id'] not in all_videos:
                    all_videos[video['id']] = video
                    count += 1

        emoji = '🎬' if current_category == 'movie' else '📺' if current_category == 'tv' else '🎤' if current_category == 'variety' else '🦸' if current_category == 'anime' else '🎵'
        print(f'  {emoji} {section_title}: {count} 条')

    print(f'\n✅ 首页共提取 {len(all_videos)} 条不重复视频')
    return list(all_videos.values())


def scrape_detail_pages(videos, limit=30):
    """抓取部分影片的详情页"""
    print(f'\n📄 开始抓取详情页（前 {limit} 条）...')
    count = 0
    for v in videos[:limit]:
        count += 1
        detail = parse_detail_page(v['id'])
        if detail:
            v.update(detail)
        if count % 5 == 0:
            print(f'  进度: {count}/{min(limit, len(videos))}')
    print(f'✅ 详情页抓取完成')


def map_subcategory(video):
    """根据标题/类型推测子分类"""
    title = video.get('title', '')
    genre = video.get('genre', '')
    cat = video.get('category', 'movie')

    # 电影子分类关键词（对齐源站 http://www.mediavip.cn/hgft/dianying/）
    movie_keywords = {
        '动作': ['动作', '杀手', '格斗', '速度', '战', '复仇'],
        '爱情': ['爱情', '恋爱', '浪漫'],
        '喜剧': ['喜剧', '搞笑', '幽默'],
        '恐怖': ['恐怖', '鬼', '咒', '怨', '凶', '丧尸', '怪谈'],
        '惊悚': ['惊悚', '悬疑', '推理', '侦探'],
        '科幻': ['科幻', '星际', '宇宙', '太空', '外星', '未来', '机器人', 'AI'],
        '奇幻': ['奇幻', '魔法', '传说', '神话', '魔幻'],
        '战争': ['战争', '战役', '军队', '抗日'],
        '灾难': ['灾难', '末日', '地震', '海啸'],
        '剧情': ['剧情', '人生', '家庭', '时代'],
        '犯罪': ['犯罪', '黑帮', '毒枭', '警察'],
        '冒险': ['冒险', '探险', '探索'],
        '纪录': ['纪录', '脉动', 'BBC'],
    }

    # 连续剧子分类关键词（对齐源站 http://www.mediavip.cn/hgft/dianshiju/）
    tv_keywords = {
        '国产剧': ['国产', '大陆', '中国'],
        '港台剧': ['港台', '香港', '台湾', 'TVB'],
        '韩国剧': ['韩国', '韩剧'],
        '日本剧': ['日本', '日剧'],
        '欧美剧': ['欧美', '美国', '英国', '美剧', '英剧'],
        '泰国剧': ['泰国', '泰剧'],
        '短剧': ['短剧'],
    }

    keywords_map = movie_keywords if cat == 'movie' else tv_keywords
    if cat == 'anime':
        keywords_map = {
            '国产动漫': ['国产', '国漫'],
            '日韩动漫': ['日本', '日漫', '韩漫'],
            '欧美动漫': ['欧美', '美漫'],
        }
    if cat == 'variety':
        keywords_map = {
            '大陆综艺': ['大陆', '国产', '中国'],
            '港台综艺': ['港台', '香港', '台湾'],
            '日韩综艺': ['日本', '韩国', '日韩'],
            '欧美综艺': ['欧美', '美国'],
        }

    combined = title + ' ' + genre
    for subcat, keywords in keywords_map.items():
        for kw in keywords:
            if kw in combined:
                return subcat
    return ''


def build_json(videos, fetch_detail=False):
    """构建最终 JSON 数据结构"""
    result = {
        'source': 'mediavip.cn',
        'source_url': BASE_URL,
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(videos),
        'categories': {},
        'videos': [],
    }

    for v in videos:
        # 映射子分类
        subcat = v.get('subcat', '')
        if not subcat:
            v['subcat'] = map_subcategory(v)
        if not v.get('subcat'):
            v['subcat'] = v.get('genre', '')

        # 组织分类结构
        cat = v['category']
        if cat not in result['categories']:
            result['categories'][cat] = {
                'id': cat,
                'name': {
                    'movie': '电影', 'tv': '电视剧',
                    'variety': '综艺', 'anime': '动漫',
                    'sports': '体育', 'music': '音乐', 'news': '资讯'
                }.get(cat, cat),
                'count': 0,
            }
        result['categories'][cat]['count'] += 1

        # 构建视频条目
        entry = {
            'id': v['id'],
            'title': v['title'],
            'url': v['url'],
            'poster': v.get('poster', ''),
            'posterColor': '',  # 前端用渐变占位
            'status': v.get('status', ''),
            'actors': v.get('actors', ''),
            'year': v.get('year', ''),
            'duration': '',  # 由 status 推导
            'rating': 0,  # 无评分数据
            'tags': [],  # 无标签数据
            'desc': v.get('desc', ''),
            'cast': v.get('actors', ''),
            'source': v['source'],
            'streamUrl': v.get('streamUrl', ''),
            'category': v['category'],
            'subcat': v.get('subcat', ''),
        }

        # 从 status 推导 duration
        status = v.get('status', '')
        if '集' in status or '完结' in status:
            entry['duration'] = status
        elif '分钟' in status:
            entry['duration'] = status
        else:
            entry['duration'] = status if status else '未知'

        result['videos'].append(entry)

    return result


def main():
    print('=' * 60)
    print('  影视数据源爬虫 - mediavip.cn')
    print('=' * 60)

    # 1. 抓取首页
    videos = scrape_homepage()

    # 2. 可选：抓取详情页
    # scrape_detail_pages(videos, limit=20)

    # 3. 构建 JSON
    result = build_json(videos)

    # 4. 保存
    os.makedirs('data', exist_ok=True)
    output_path = 'data/mediavip.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'\n💾 已保存到 {output_path}')
    print(f'   总视频: {result["total"]} 条')
    for cat_id, cat_info in result['categories'].items():
        print(f'   {cat_info["name"]}: {cat_info["count"]} 条')


if __name__ == '__main__':
    main()
