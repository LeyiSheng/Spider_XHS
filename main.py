import json
import os
import time
import random
from collections import deque, defaultdict

# Adaptive limiter is defined before Data_Spider to avoid any nesting/indent confusion
    
from loguru import logger
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import init
from xhs_utils.data_util import handle_note_info, handle_comment_info, download_note, save_to_xlsx


class Data_Spider():
    def __init__(self):
        self.xhs_apis = XHS_Apis()
        self._limiter = AdaptiveLimiter()

    def spider_note(self, note_url: str, cookies_str: str, proxies=None):
        """
        爬取一个笔记的信息
        :param note_url:
        :param cookies_str:
        :return:
        """
        note_info = None
        try:
            success, msg, res_json = self.xhs_apis.get_note_info(note_url, cookies_str, proxies)
            if success and res_json and 'data' in res_json and res_json['data'].get('items'):
                note_info = res_json['data']['items'][0]
                note_info['url'] = note_url
                note_info = handle_note_info(note_info)
            else:
                raise Exception('接口返回为空或无items，可能缺少/失效xsec_token')
        except Exception as e:
            success = False
            msg = e
        logger.info(f'爬取笔记信息 {note_url}: {success}, msg: {msg}')
        return success, msg, note_info

    def spider_some_note(self, notes: list, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None, fetch_comments: bool = True):
        """
        爬取一些笔记的信息（详情队列 -> 评论队列，带自适应等待）
        """
        if (save_choice == 'all' or save_choice == 'excel') and excel_name == '':
            raise ValueError('excel_name 不能为空')
        # 去重同一批中的重复 URL（保持顺序）
        if notes:
            notes = list(dict.fromkeys(notes))
        note_list = []
        all_comments = []
        merged_items = []  # 用于最终合并为一个JSON：每条笔记 + 其评论
        # 仅当 fetch_comments=True 且保存选项需要评论时才爬取评论
        want_comments = fetch_comments and ((save_choice == 'all') or ('comments' in save_choice) or (save_choice == 'excel'))

        def _is_rate_limited(err_msg):
            s = str(err_msg)
            return any(k in s for k in ['频次', 'rate limit', 'Too Many', '429'])

        # Phase 1: 详情队列
        for note_url in notes:
            self._limiter.pre_sleep('detail')
            success, msg, note_info = self.spider_note(note_url, cookies_str, proxies)
            rate_limit_hit = _is_rate_limited(msg) if not success else False
            self._limiter.post_record('detail', success, rate_limit_hit)
            if note_info is not None and success:
                note_list.append(note_info)
        # Phase 2: 评论队列（与详情解耦，支持自适应等待）
        if want_comments and len(note_list) > 0:
            for item in note_list:
                note_url = item.get('note_url') or item.get('url')
                self._limiter.pre_sleep('comment')
                ok, cmsg, comments = self.spider_note_comments(note_url, cookies_str, proxies)
                rate_limit_hit = (not ok) and _is_rate_limited(cmsg)
                self._limiter.post_record('comment', ok, rate_limit_hit)
                if ok and comments:
                    all_comments.extend(comments)
                elif ok and not comments:
                    print(f"该笔记无可用评论或未返回评论: {note_url}")
                else:
                    print(f"评论获取失败: {note_url}，原因: {cmsg}")
                # 如果需要下载媒体，优先下载并在此过程中写入视频统计信息
                save_dir = None
                if (save_choice == 'all') or ('media' in save_choice):
                    save_dir = download_note(note_info, base_path['media'], 'media')
                # 写入爬取时间
                try:
                    note_info['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                except Exception:
                    note_info['crawl_time'] = None
                # 组装合并结构（每条笔记 + 评论），此时 note_info 可能已含视频统计
                merged = dict(note_info)
                merged['comments'] = comments
                merged_items.append(merged)
                # 每条笔记目录里也落地一个合并后的 JSON
                if save_dir:
                    try:
                        with open(os.path.join(save_dir, 'info.json'), 'w', encoding='utf-8') as f:
                            json.dump(merged, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        logger.warning(f'写入合并JSON失败: {e}')
        # 未抓取评论时，仍然生成合并条目（comments 为空列表），以便下次运行补齐
        if not want_comments and len(note_list) > 0:
            for note_info in note_list:
                try:
                    note_info['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                except Exception:
                    note_info['crawl_time'] = None
                merged = dict(note_info)
                merged['comments'] = []
                merged_items.append(merged)
        # download media for notes (if not already done above)
        for note_info in note_list:
            if save_choice == 'all' or 'media' in save_choice:
                download_note(note_info, base_path['media'], save_choice)
        # save note excel
        if save_choice == 'all' or save_choice == 'excel':
            file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))
            save_to_xlsx(note_list, file_path)
        # save comment excel when requested
        if want_comments and len(all_comments) > 0:
            cmt_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}_comments.xlsx'))
            # save_to_xlsx is a no-op to avoid generating xlsx files
            save_to_xlsx(all_comments, cmt_path, type='comment')
            print(f"共爬取评论 {len(all_comments)} 条（已跳过 xlsx 导出）")
        elif want_comments:
            print("未获取到任何评论或接口返回为空。")
        merged_path = None
        try:
            if len(merged_items) > 0:
                merged_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}_merged.json')) if (save_choice == 'all' or save_choice == 'excel') and excel_name else os.path.abspath(os.path.join(base_path['excel'], 'merged.json'))
                with open(merged_path, 'w', encoding='utf-8') as f:
                    json.dump(merged_items, f, ensure_ascii=False, indent=2)
                logger.info(f'合并JSON已保存至 {merged_path}')
        except Exception as e:
            logger.warning(f'保存合并JSON失败: {e}')
        return merged_path

    def spider_note_comments(self, note_url: str, cookies_str: str, proxies=None):
        """
        爬取一个笔记的全部评论（含一级与二级）并结构化返回
        """
        try:
            success, msg, out_comments = self.xhs_apis.get_note_all_comment(note_url, cookies_str, proxies)
            if not success:
                return success, msg, []
            # 扁平化：包含一级与其所有子评论
            flat = []
            for c in out_comments:
                # 规范化一级
                c['note_url'] = note_url
                flat.append(handle_comment_info(c))
                # 规范化所有子评论
                if 'sub_comments' in c and c['sub_comments']:
                    for sc in c['sub_comments']:
                        sc['note_url'] = note_url
                        flat.append(handle_comment_info(sc))
            print(f'共爬取评论 {len(flat)} 条')
            return True, 'success', flat
        except Exception as e:
            logger.warning(f'爬取笔记评论失败: {e}')
            return False, e, []

    def spider_user_all_note(self, user_url: str, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
        """
        爬取一个用户的所有笔记
        """
        note_list = []
        try:
            success, msg, all_note_info = self.xhs_apis.get_user_all_notes(user_url, cookies_str, proxies)
            if success:
                logger.info(f'用户 {user_url} 作品数量: {len(all_note_info)}')
                for simple_note_info in all_note_info:
                    note_url = f"https://www.xiaohongshu.com/explore/{simple_note_info['note_id']}?xsec_token={simple_note_info['xsec_token']}"
                    note_list.append(note_url)
            if save_choice == 'all' or save_choice == 'excel':
                excel_name = user_url.split('/')[-1].split('?')[0]
            self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies)
        except Exception as e:
            success = False
            msg = e
        logger.info(f'爬取用户所有视频 {user_url}: {success}, msg: {msg}')
        return note_list, success, msg

    def spider_some_search_note(self, query: str, require_num: int, cookies_str: str, base_path: dict, save_choice: str, sort_type_choice=0, note_type=0, note_time=0, note_range=0, pos_distance=0, geo: dict = None,  excel_name: str = '', proxies=None, seen_note_ids: set = None, fetch_comments: bool = True):
        """
        指定数量搜索笔记，设置排序方式和笔记类型和笔记数量
        """
        note_list = []
        try:
            success, msg, notes = self.xhs_apis.search_some_note(query, require_num, cookies_str, sort_type_choice, note_type, note_time, note_range, pos_distance, geo, proxies)
            if success:
                notes = list(filter(lambda x: x['model_type'] == "note", notes))
                logger.info(f'搜索关键词 {query} 笔记数量: {len(notes)}')
                # 去重：同一关键词返回中的重复ID
                seen_ids_local = set()
                filtered_urls = []
                for note in notes:
                    nid = note.get('id')
                    if not nid or nid in seen_ids_local:
                        continue
                    seen_ids_local.add(nid)
                    note_url = f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={note['xsec_token']}"
                    filtered_urls.append(note_url)
                # 如果传入了跨批次去重集合，则进一步过滤
                if seen_note_ids is not None:
                    def _nid_from_url(u: str):
                        try:
                            return u.split('/explore/')[1].split('?')[0]
                        except Exception:
                            return None
                    filtered_urls = [u for u in filtered_urls if (_nid_from_url(u) not in seen_note_ids)]
                note_list = filtered_urls
            if save_choice == 'all' or save_choice == 'excel':
                excel_name = query
            path = self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies, fetch_comments=fetch_comments)
            # 成功后将已处理的ID加入去重集合
            if path is not None and seen_note_ids is not None:
                for u in (note_list or []):
                    try:
                        nid = u.split('/explore/')[1].split('?')[0]
                        if nid:
                            seen_note_ids.add(nid)
                    except Exception:
                        pass
        except Exception as e:
            success = False
            msg = e
        logger.info(f'搜索关键词 {query} 笔记: {success}, msg: {msg}')
        return note_list, success, msg, path

    def fill_comments_for_merged_json(self, merged_json_path: str, cookies_str: str, proxies=None):
        """
        读取上次生成的合并JSON（仅含笔记或无评论），为每条笔记补齐评论并写回同一文件。
        返回（success, msg, count）
        """
        try:
            if not merged_json_path or (not os.path.exists(merged_json_path)):
                return False, f'文件不存在: {merged_json_path}', 0
            with open(merged_json_path, 'r', encoding='utf-8') as f:
                items = json.load(f)
            if not isinstance(items, list):
                return False, 'JSON结构异常，期望为列表', 0
            updated = 0
            total_comments = 0
            for it in items:
                note_url = it.get('note_url') or it.get('url')
                if not note_url:
                    continue
                # 若已有评论且非空，可跳过；也可强制刷新，此处选择只在为空或不存在时补齐
                comments_exist = it.get('comments')
                if comments_exist:
                    continue
                self._limiter.pre_sleep('comment')
                ok, msg, comments = self.spider_note_comments(note_url, cookies_str, proxies)
                self._limiter.post_record('comment', ok, (not ok and ('429' in str(msg) or '频次' in str(msg))))
                if ok:
                    it['comments'] = comments
                    updated += 1
                    total_comments += len(comments or [])
                else:
                    logger.warning(f'补齐评论失败: {note_url}，原因: {msg}')
            with open(merged_json_path, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            return True, f'已更新 {updated} 条笔记的评论，累计 {total_comments} 条评论', updated
        except Exception as e:
            logger.warning(f'填充评论至合并JSON失败: {e}')
            return False, e, 0

class AdaptiveLimiter:
    """Simple adaptive rate limiter based on recent failure rate.
    Maintains separate windows for 'detail' and 'comment'.
    """
    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self.recent = {
            'detail': deque(maxlen=window_size),
            'comment': deque(maxlen=window_size),
        }
        self.calls = defaultdict(int)
        self.consec_fail = defaultdict(int)

    def _failure_rate(self, kind: str) -> float:
        q = self.recent.get(kind)
        if not q or len(q) == 0:
            return 0.0
        fails = sum(1 for s in q if not s)
        return fails / float(len(q))

    def pre_sleep(self, kind: str):
        """Sleep a small jitter, scaled by recent failure rate."""
        self.calls[kind] += 1
        base = (0.8, 1.8) if kind == 'detail' else (1.0, 2.2)
        rate = self._failure_rate(kind)
        factor = 1.0
        if rate > 0.15:
            factor = 2.0
        if rate > 0.30:
            factor = 4.0
        wait = random.uniform(base[0] * factor, base[1] * factor)
        time.sleep(wait)
        # periodic cool-down when failure rate is high
        if rate > 0.30 and (self.calls[kind] % 5 == 0):
            cool = random.uniform(25, 55)
            logger.warning(f"[{kind}] 高失败率 {rate:.0%}，冷却 {int(cool)}s ...")
            time.sleep(cool)

    def post_record(self, kind: str, success: bool, rate_limited: bool):
        self.recent[kind].append(bool(success))
        self.consec_fail[kind] = 0 if success else (self.consec_fail[kind] + 1)
        # Backoff for rate limit events
        if rate_limited:
            cool = random.uniform(45, 90)
            logger.warning(f"[{kind}] 命中频次限制，冷却 {int(cool)}s ...")
            time.sleep(cool)
        # Escalating backoff for consecutive failures (non-429)
        elif not success and self.consec_fail[kind] >= 3:
            cool = min(120, 15 * self.consec_fail[kind])
            logger.warning(f"[{kind}] 连续失败 {self.consec_fail[kind]} 次，冷却 {int(cool)}s ...")
            time.sleep(cool)


if __name__ == '__main__':
    """
        此文件为爬虫的入口文件，可以直接运行
        apis/xhs_pc_apis.py 为爬虫的api文件，包含小红书的全部数据接口，可以继续封装
        apis/xhs_creator_apis.py 为小红书创作者中心的api文件
        感谢star和follow
    """

    cookies_str, base_path = init()
    data_spider = Data_Spider()
    """
        save_choice: all: 保存所有的信息, media: 保存视频和图片（media-video只下载视频, media-image只下载图片，media都下载）, excel: 保存到excel
        save_choice 为 excel 或者 all 时，excel_name 不能为空
    """


    # 1 爬取列表的所有笔记信息 笔记链接 如下所示 注意此url会过期！
    notes = [
        r'https://www.xiaohongshu.com/explore/690565df0000000003018c13?xsec_token=ABl7kbd59yUDXICiT6bhGWO2mGHVOV4KgXR7bkAgAmIPU=&xsec_source=pc_feed&source=404',
    ]
    path = data_spider.spider_some_note(notes, cookies_str, base_path, 'all', 'test')
    print(f'爬取完成，数据保存至: {path}')
    # 2 爬取用户的所有笔记信息 用户链接 如下所示 注意此url会过期！
    #user_url = 'https://www.xiaohongshu.com/user/profile/64f37b4a0000000004025d45?xsec_token=ABljtPmm-R8O36m_8QZSrR0ridjylPwLq9ZZoqPawdv7o%3D&xsec_source=pc_search'
    
    #data_spider.spider_user_all_note(user_url, cookies_str, base_path, 'all')

    # 3 搜索指定关键词的笔记
    query = "运动"
    query_num = 0
    sort_type_choice = 0  # 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
    note_type = 0 # 0 不限, 1 视频笔记, 2 普通笔记
    note_time = 0  # 0 不限, 1 一天内, 2 一周内天, 3 半年内
    note_range = 0  # 0 不限, 1 已看过, 2 未看过, 3 已关注
    pos_distance = 0  # 0 不限, 1 同城, 2 附近 指定这个1或2必须要指定 geo
    # geo = {
    #     # 经纬度
    #     "latitude": 39.9725,
    #     "longitude": 116.4207
    # }
    #data_spider.spider_some_search_note(query, query_num, cookies_str, base_path, 'all', sort_type_choice, note_type, note_time, note_range, pos_distance, geo=None)

    # 已去除 Selenium 采集功能；如需采集 URL，可手动提供 notes 列表或使用搜索/用户API。
