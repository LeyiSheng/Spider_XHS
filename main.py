import json
import os
import time
from loguru import logger
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import init
from xhs_utils.data_util import handle_note_info, handle_comment_info, download_note, save_to_xlsx


class Data_Spider():
    def __init__(self):
        self.xhs_apis = XHS_Apis()

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

    def spider_some_note(self, notes: list, cookies_str: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
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
        want_comments = (save_choice == 'all') or ('comments' in save_choice) or (save_choice == 'excel')
        for note_url in notes:
            success, msg, note_info = self.spider_note(note_url, cookies_str, proxies)
            if note_info is not None and success:
                note_list.append(note_info)
                comments = []
                if want_comments:
                    ok, cmsg, comments = self.spider_note_comments(note_url, cookies_str, proxies)
                    if ok and comments:
                        all_comments.extend(comments)
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
            save_to_xlsx(all_comments, cmt_path, type='comment')
        # 额外输出：将笔记与评论合为一个 JSON 文件（包含视频长度字段）
        try:
            if len(merged_items) > 0:
                merged_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}_merged.json')) if (save_choice == 'all' or save_choice == 'excel') and excel_name else os.path.abspath(os.path.join(base_path['excel'], 'merged.json'))
                with open(merged_path, 'w', encoding='utf-8') as f:
                    json.dump(merged_items, f, ensure_ascii=False, indent=2)
                logger.info(f'合并JSON已保存至 {merged_path}')
        except Exception as e:
            logger.warning(f'保存合并JSON失败: {e}')

    def spider_note_comments(self, note_url: str, cookies_str: str, proxies=None):
        """
        爬取一个笔记的全部评论（含一级与二级）并结构化返回
        :param note_url: 笔记链接（携带 xsec_token/xsec_source）
        :param cookies_str: Cookies
        :return: (success, msg, comments_list)
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
            return True, 'success', flat
        except Exception as e:
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
            self.spider_some_note(note_list, cookies_str, base_path, save_choice, excel_name, proxies)
        except Exception as e:
            success = False
            msg = e
        logger.info(f'搜索关键词 {query} 笔记: {success}, msg: {msg}')
        return note_list, success, msg

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
        r'https://www.xiaohongshu.com/explore/69007525000000000401553d?xsec_token=ABTk2gyVOWolL8_2zzH_2_7N5yiDBEKb5pn41EYDfhK9Y=&xsec_source=pc_feed',
    ]
    data_spider.spider_some_note(notes, cookies_str, base_path, 'all', 'test')

    # 2 爬取用户的所有笔记信息 用户链接 如下所示 注意此url会过期！
    #user_url = 'https://www.xiaohongshu.com/user/profile/64f37b4a0000000004025d45?xsec_token=ABljtPmm-R8O36m_8QZSrR0ridjylPwLq9ZZoqPawdv7o%3D&xsec_source=pc_search'
    
    #data_spider.spider_user_all_note(user_url, cookies_str, base_path, 'all')

    # 3 搜索指定关键词的笔记
    query = "糖"
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
