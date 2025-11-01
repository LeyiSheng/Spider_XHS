import json

import execjs

try:
    js = execjs.compile(open(r'../static/xhs_creator_xs.js', 'r', encoding='utf-8').read())
except:
    js = execjs.compile(open(r'static/xhs_creator_xs.js', 'r', encoding='utf-8').read())


def generate_xs(a1, api, data=''):
    method = 'GET' if (not data and ('?' in api)) else 'POST'
    try:
        ret = js.call('get_request_headers_params_with_method', method, api, data, a1)
    except Exception:
        ret = js.call('get_request_headers_params', api, data, a1)
    xs, xt = ret['xs'], ret['xt']
    if data:
        data = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    return xs, xt, data


def get_common_headers():
    return {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
        "accept": "application/json, text/plain, */*",
        "Host": "edith.xiaohongshu.com",
        "pragma": "no-cache",
        "cache-control": "no-cache",
        "sec-ch-ua-platform": "\"Windows\"",
        "authorization": "",
        "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Microsoft Edge\";v=\"138\"",
        "sec-ch-ua-mobile": "?0",
        "x-t": "",
        "x-s": "",
        "origin": "https://creator.xiaohongshu.com",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": "https://creator.xiaohongshu.com/",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "priority": "u=1, i"
    }


def splice_str(api, params):
    from urllib.parse import urlencode
    safe_params = {}
    for k, v in (params or {}).items():
        if v is None:
            v = ''
        safe_params[k] = v
    qs = urlencode(safe_params, doseq=True)
    if not qs:
        return api
    joiner = '&' if ('?' in api) else '?'
    return api + joiner + qs
