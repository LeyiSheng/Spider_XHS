import json
import os
import random
from collections import deque, defaultdict

import time
from loguru import logger
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import init
from xhs_utils.data_util import handle_note_info, handle_comment_info, download_note, save_to_xlsx


class Data_Spider():
    def __init__(self):
        self.xhs_apis = XHS_Apis()
        self._limiter = AdaptiveLimiter()
        # Track comment crawl failures to optionally halt the run
        self.comment_fail_total = 0
        self.comment_fail_stop = 10

    def spider_note(self, note_url: str, cookies_str: str, proxies=None):
        """
        爬取一个笔记的信息
        :param note_url:
        :param cookies_str:
        :return:
        """
        note_info = None
        try:
            success, msg, note_info = self.xhs_apis.get_note_info(note_url, cookies_str, proxies)
            if success:
                note_info = note_info['data']['items'][0]
                note_info['url'] = note_url
                note_info = handle_note_info(note_info)
            else:
                raise Exception('接口返回为空或无items，可能缺少/失效xsec_token')
        except Exception as e:
            success = False
            msg = e
        logger.info(f'爬取笔记信息 {note_url}: {success}, msg: {msg}')
        return success, msg, note_info

    def spider_some_note(
        self,
        notes: list,
        cookies_str: str,
        base_path: dict,
        save_choice: str,
        excel_name: str = '',
        proxies=None,
        fetch_comments: bool = True
    ):
        """
        爬取一些笔记的信息
        :param notes:
        :param cookies_str:
        :param base_path:
        :return:
        """
        if (save_choice == 'all' or save_choice == 'excel') and excel_name == '':
            raise ValueError('excel_name 不能为空')
        note_list = []
        all_comments = []
        merged_items = []  # 用于最终合并为一个JSON：每条笔记 + 其评论
        comment_failures = 0
        # 仅当 fetch_comments=True 且保存选项需要评论时才爬取评论
        want_comments = fetch_comments and ((save_choice == 'all') or ('comments' in save_choice) or (save_choice == 'excel'))

        def _is_rate_limited(err_msg):
            s = str(err_msg)
            # 尽量识别出各种“访问过于频繁 / 限制访问”类型的提示
            keywords = [
                '频次', '频繁', '访问过于频繁', '请求过于频繁',
                'rate limit', 'Too Many', '429',
                '风险控制', '访问受限', 'forbidden', 'Forbidden'
            ]
            return any(k in s for k in keywords)

        # Phase 1: 详情队列
        for note_url in notes:
            success, msg, note_info = self.spider_note(note_url, cookies_str, proxies)
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
                    comment_failures += 1
                    self.comment_fail_total += 1
                    if self.comment_fail_total > self.comment_fail_stop:
                        raise RuntimeError(f'评论抓取失败次数超过 {self.comment_fail_stop} 次，已停止。')
                # 如果需要下载媒体，优先下载并在此过程中写入视频统计信息
                save_dir = None
                if (save_choice == 'all') or ('media' in save_choice):
                    save_dir = download_note(item, base_path['media'], save_choice)
                # 写入爬取时间
                try:
                    item['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                except Exception:
                    item['crawl_time'] = None
                # 组装合并结构（每条笔记 + 评论），此时 item 可能已含视频统计
                merged = dict(item)
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
                # 如需下载媒体，先下载并在此过程中写入视频统计信息
                save_dir = None
                if (save_choice == 'all') or ('media' in save_choice):
                    save_dir = download_note(note_info, base_path['media'], save_choice)
                try:
                    note_info['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                except Exception:
                    note_info['crawl_time'] = None
                merged = dict(note_info)
                merged['comments'] = []
                merged_items.append(merged)
                if save_dir:
                    try:
                        with open(os.path.join(save_dir, 'info.json'), 'w', encoding='utf-8') as f:
                            json.dump(merged, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        logger.warning(f'写入合并JSON失败: {e}')
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
        return merged_path, comment_failures

    def spider_note_comments(self, note_url: str, cookies_str: str, proxies=None):
        """
        爬取一个笔记的全部评论（含一级与二级）并结构化返回
        """
        try:
            # 单条笔记评论抓取上限，可通过环境变量调节，避免单条笔记评论过多把账号打“红线”
            limit_env = os.environ.get('XHS_COMMENT_LIMIT_PER_NOTE') or os.environ.get('XHS_COMMENT_LIMIT')
            try:
                limit_total = int(limit_env) if limit_env else 200
            except Exception:
                limit_total = 200
            success, msg, out_comments = self.xhs_apis.get_note_all_comment(
                note_url,
                cookies_str,
                proxies,
                limit_total=limit_total
            )
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
        :param user_url:
        :param cookies_str:
        :param base_path:
        :return:
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

    def spider_some_search_note(self, query: str, require_num: int, cookies_str: str, base_path: dict, save_choice: str, sort_type_choice=0, note_type=0, note_time=0, note_range=0, pos_distance=0, geo: dict = None,  excel_name: str = '', proxies=None):
        """
            指定数量搜索笔记，设置排序方式和笔记类型和笔记数量
            :param query 搜索的关键词
            :param require_num 搜索的数量
            :param cookies_str 你的cookies
            :param base_path 保存路径
            :param sort_type_choice 排序方式 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
            :param note_type 笔记类型 0 不限, 1 视频笔记, 2 普通笔记
            :param note_time 笔记时间 0 不限, 1 一天内, 2 一周内天, 3 半年内
            :param note_range 笔记范围 0 不限, 1 已看过, 2 未看过, 3 已关注
            :param pos_distance 位置距离 0 不限, 1 同城, 2 附近 指定这个必须要指定 geo
            返回搜索的结果
        """
        note_list = []
        merged_path = None
        comment_failures = 0
        try:
            success, msg, notes = self.xhs_apis.search_some_note(query, require_num, cookies_str, sort_type_choice, note_type, note_time, note_range, pos_distance, geo, proxies)
            if success:
                notes = list(filter(lambda x: x['model_type'] == "note", notes))
                logger.info(f'搜索关键词 {query} 笔记数量: {len(notes)}')
                for note in notes:
                    note_url = f"https://www.xiaohongshu.com/explore/{note['id']}?xsec_token={note['xsec_token']}"
                    note_list.append(note_url)
            if save_choice == 'all' or save_choice == 'excel':
                excel_name = query
            merged_path, comment_failures = self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies)
        except RuntimeError:
            # 让上层感知到评论失败次数过多的终止信号
            raise
        except Exception as e:
            success = False
            msg = e
        logger.info(f'搜索关键词 {query} 笔记: {success}, msg: {msg}')
        return note_list, success, msg, merged_path, comment_failures

    def fill_comments_for_merged_json(self, merged_json_path: str, cookies_str: str, proxies=None):
        """
        读取上次生成的合并JSON（仅含笔记或无评论），为每条笔记补齐评论，并尽量补齐视频时长，
        然后写回同一文件。返回（success, msg, count），其中 count 为补齐评论的笔记数量。
        """
        try:
            if not merged_json_path or (not os.path.exists(merged_json_path)):
                return False, f'文件不存在: {merged_json_path}', 0
            with open(merged_json_path, 'r', encoding='utf-8') as f:
                items = json.load(f)
            if not isinstance(items, list):
                return False, 'JSON结构异常，期望为列表', 0
            updated_comments = 0
            total_comments = 0
            updated_duration = 0
            for it in items:
                note_url = it.get('note_url') or it.get('url')
                if not note_url:
                    continue
                # 1) 先尝试补齐视频时长（仅针对视频笔记且当前为 None 或非法值）
                try:
                    note_type = it.get('note_type')
                    cur_dur = it.get('video_duration')
                    need_duration = (
                        note_type == '视频'
                        and (cur_dur is None or isinstance(cur_dur, str) or (isinstance(cur_dur, (int, float)) and cur_dur <= 0))
                    )
                except Exception:
                    need_duration = False
                if need_duration:
                    try:
                        self._limiter.pre_sleep('detail')
                        ok_d, msg_d, note_info = self.spider_note(note_url, cookies_str, proxies)
                        self._limiter.post_record('detail', ok_d, (not ok_d and ('429' in str(msg_d) or '频次' in str(msg_d))))
                        if ok_d and note_info:
                            vd = note_info.get('video_duration')
                            if isinstance(vd, (int, float)) and vd > 0:
                                it['video_duration'] = vd
                                updated_duration += 1
                        else:
                            logger.warning(f'补齐视频时长失败: {note_url}，原因: {msg_d}')
                    except Exception as e2:
                        logger.warning(f'补齐视频时长异常: {note_url}, {e2}')
                # 2) 补齐评论：若已有评论且非空，可跳过；只在为空或不存在时补齐
                comments_exist = it.get('comments')
                if comments_exist:
                    continue
                self._limiter.pre_sleep('comment')
                ok, msg, comments = self.spider_note_comments(note_url, cookies_str, proxies)
                self._limiter.post_record('comment', ok, (not ok and ('429' in str(msg) or '频次' in str(msg))))
                if ok:
                    it['comments'] = comments
                    updated_comments += 1
                    total_comments += len(comments or [])
                else:
                    logger.warning(f'补齐评论失败: {note_url}，原因: {msg}')
            with open(merged_json_path, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            msg = f'已更新 {updated_comments} 条笔记的评论，累计 {total_comments} 条评论'
            if updated_duration:
                msg += f'；补齐视频时长 {updated_duration} 条'
            return True, msg, updated_comments
        except Exception as e:
            logger.warning(f'填充评论/视频时长至合并JSON失败: {e}')
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
        # 评论接口更敏感，基础等待时间稍长一些
        base = (0.8, 1.8) if kind == 'detail' else (1.6, 3.2)
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
        r'https://www.xiaohongshu.com/explore/690f1db300000000070179fd?xsec_token=AB051BgS9kf17q9XewaTRcCGVcq2aYRQzYLULoNxlZ93I=&xsec_source=pc_feed',
    ]
    path, _ = data_spider.spider_some_note(notes, cookies_str, base_path, 'all', 'test')
    print(f'爬取完成，数据保存至: {path}')

    # fillcomments 测试：先生成一个不包含评论的合并JSON，再调用填充方法补齐评论
    # 将此开关设为 True 以运行测试
    enable_fillcomments_test = False
    if enable_fillcomments_test:
        try:
            # 使用相同的 notes，生成不带评论的合并 JSON（comments 将为空数组）
            test_excel_name = 'filltest'
            empty_comments_path, _ = data_spider.spider_some_note(
                notes,
                cookies_str,
                base_path,
                save_choice='excel',
                excel_name=test_excel_name,
                proxies=None,
                fetch_comments=False
            )
            print(f'已生成空评论合并JSON: {empty_comments_path}')
            if empty_comments_path and os.path.exists(empty_comments_path):
                ok, msg, updated = data_spider.fill_comments_for_merged_json(empty_comments_path, cookies_str)
                print(f'fillcomments 结果: success={ok}, updated={updated}, msg={msg}')
            else:
                print('未找到用于测试的合并JSON文件，跳过 fillcomments 测试。')
        except Exception as e:
            print(f'fillcomments 测试失败: {e}')
    # 2 爬取用户的所有笔记信息 用户链接 如下所示 注意此url会过期！
    #user_url = 'https://www.xiaohongshu.com/user/profile/64c3f392000000002b009e45?xsec_token=AB-GhAToFu07JwNk_AMICHnp7bSTjVz2beVIDBwSyPwvM=&xsec_source=pc_feed'
   # data_spider.spider_user_all_note(user_url, cookies_str, base_path, 'all')

    # 3 搜索指定关键词的笔记
    query = "榴莲"
    query_num = 10
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
