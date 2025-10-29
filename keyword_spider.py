import os
from typing import List, Tuple

from loguru import logger

from xhs_utils.common_util import init
from xhs_utils.keywords_util import (
    load_keywords_library,
    save_keywords_library,
    filter_tags_for_keyword,
    merge_sub_tags,
)
from apis.xhs_pc_apis import XHS_Apis
from main import Data_Spider


def build_note_urls_from_search(res_items: List[dict]) -> List[str]:
    urls = []
    for item in res_items or []:
        try:
            if item.get('model_type') != 'note':
                continue
            note_id = item['id']
            token = item['xsec_token']
            urls.append(f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}")
        except Exception:
            continue
    return urls


def collect_tags_for_keyword(ds: Data_Spider, cookies: str, keyword: str, require_num: int = 50,
                             sort_type_choice: int = 0, note_type: int = 0, note_time: int = 0,
                             note_range: int = 0, pos_distance: int = 0, geo=None,
                             proxies=None) -> Tuple[bool, List[str]]:
    """
    搜索指定关键词，抓取若干笔记，汇总其 tags。
    返回 (success, tags)
    """
    try:
        # 直接使用底层API，避免触发保存逻辑
        api = ds.xhs_apis if hasattr(ds, 'xhs_apis') else XHS_Apis()
        success, msg, res_items = api.search_some_note(keyword, require_num, cookies,
                                                       sort_type_choice, note_type, note_time,
                                                       note_range, pos_distance, geo, proxies)
        if not success:
            logger.warning(f"搜索失败: {keyword}, msg: {msg}")
            return False, []
        note_urls = build_note_urls_from_search(res_items)
        all_tags: List[str] = []
        for url in note_urls:
            ok, m, note_info = ds.spider_note(url, cookies, proxies)
            if ok and note_info and isinstance(note_info.get('tags'), list):
                all_tags.extend([t for t in note_info['tags'] if t])
        return True, all_tags
    except Exception as e:
        logger.exception(e)
        return False, []


def main():
    cookies_str, base_path = init()
    if not cookies_str:
        logger.error('未加载到 COOKIES，请先在 .env 中配置 COOKIES=...')
        return

    ds = Data_Spider()

    keywords_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'datas', 'keywords.json'))
    lib = load_keywords_library(keywords_path)
    keywords = list(lib.get('keywords', {}).keys())
    if not keywords:
        logger.warning(f'关键词库为空，可在 {keywords_path} 中添加 keywords。')
        return

    # 默认爬取参数，可根据需要调整
    require_num = 50
    sort_type_choice = 0  # 0 综合, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
    note_type = 0         # 0 不限, 1 视频, 2 普通
    note_time = 0         # 0 不限
    note_range = 0        # 0 不限
    pos_distance = 0      # 0 不限
    geo = None

    updated = False
    for kw in keywords:
        logger.info(f'开始处理关键词: {kw}')
        ok, tags = collect_tags_for_keyword(ds, cookies_str, kw, require_num,
                                            sort_type_choice, note_type, note_time,
                                            note_range, pos_distance, geo)
        if not ok:
            continue
        kw_obj = lib['keywords'].get(kw, {})
        include_patterns = kw_obj.get('include_patterns', [])
        exclude_patterns = kw_obj.get('exclude_patterns', [])
        filtered = filter_tags_for_keyword(tags, kw, include_patterns, exclude_patterns)
        if filtered:
            merge_sub_tags(kw_obj, filtered)
            lib['keywords'][kw] = kw_obj
            updated = True
            logger.info(f'关键词 [{kw}] 新增子库标签: {len(filtered)}')

    if updated:
        save_keywords_library(keywords_path, lib)
        logger.info(f'关键词库已更新: {keywords_path}')
    else:
        logger.info('未发现可更新的子库标签。')


if __name__ == '__main__':
    main()

